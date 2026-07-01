"""
GarudaOne DroneOS — Object Detector (PicoDet-S via ncnn)
=========================================================
Runs PicoDet-S at 45-55 FPS on RPi5's ARM CPU to detect people
in the camera feed. This is what lets the drone "see" its subject.

PicoDet-S was chosen because:
  - 3-4x faster than YOLOv8n on ARM (45-55 FPS vs 10-15 FPS)
  - Only 4MB model size
  - Sufficient accuracy for single-subject bounding box tracking

The detector outputs bounding boxes — then the tracker (tracker.py)
associates them across frames to maintain a stable subject lock.
"""

import time
from typing import Optional

import numpy as np

from garuda.core.config import Config
from garuda.utils.logger import get_logger
from garuda.utils.profiler import profiler
from garuda.utils.transforms import BoundingBox

log = get_logger("detector")


class PicoDetector:
    """
    PicoDet-S object detector using ncnn inference engine.

    On RPi5 (ARM Cortex-A76): 45-55 FPS at 320x320, INT8 quantized.
    Falls back to OpenCV DNN if ncnn is not available.
    """

    def __init__(self, config: Config):
        self.config = config

        # Model settings from config
        self._input_w = config.get("detector.input_width", 320)
        self._input_h = config.get("detector.input_height", 320)
        self._conf_threshold = config.get("detector.confidence_threshold", 0.5)
        self._nms_threshold = config.get("detector.nms_threshold", 0.45)
        self._target_classes = config.get("detector.target_classes", [0])

        # Model state
        self._net = None
        self._loaded = False
        self._backend = "none"

        log.info(
            f"PicoDet-S detector initialized — "
            f"input={self._input_w}x{self._input_h}, "
            f"conf={self._conf_threshold}, classes={self._target_classes}"
        )

    def load_model(self) -> bool:
        """
        Load the PicoDet-S model. Tries ncnn first, then OpenCV DNN,
        then falls back to stub detector.

        Returns True if a backend loaded successfully.
        """
        models_dir = self.config.models_dir

        # Attempt 1: ncnn (preferred — fastest on ARM, also works on x86)
        try:
            import ncnn

            param_path = models_dir / self.config.get(
                "detector.model_param", "picodet_s_320_coco.param"
            )
            bin_path = models_dir / self.config.get(
                "detector.model_bin", "picodet_s_320_coco.bin"
            )

            if param_path.exists() and bin_path.exists():
                self._net = ncnn.Net()
                self._net.opt.use_vulkan_compute = False
                self._net.opt.num_threads = 4
                self._net.opt.lightmode = False
                self._net.load_param(str(param_path))
                self._net.load_model(str(bin_path))

                self._loaded = True
                self._backend = "ncnn"
                log.info(f"✓ PicoDet-S loaded via ncnn ({param_path.name})")
                return True
            else:
                log.info(
                    f"ncnn installed but model files not found: "
                    f"{param_path.name}, {bin_path.name}"
                )
        except ImportError:
            log.info("ncnn not installed (optional). Install: pip install ncnn")
        except Exception as e:
            log.warning(f"ncnn load failed ({e})")

        # Attempt 2: OpenCV DNN (works everywhere, including Windows)
        try:
            import cv2

            # PicoDet also has ONNX exports
            onnx_path = models_dir / self.config.get(
                "detector.model_onnx", "picodet_s_320_coco.onnx"
            )
            if onnx_path.exists():
                self._net = cv2.dnn.readNetFromONNX(str(onnx_path))
                self._net.setPreferableBackend(cv2.dnn.DNN_BACKEND_OPENCV)
                self._net.setPreferableTarget(cv2.dnn.DNN_TARGET_CPU)

                self._loaded = True
                self._backend = "opencv"
                log.info(f"✓ PicoDet-S loaded via OpenCV DNN ({onnx_path.name})")
                return True
            else:
                log.info(
                    f"OpenCV available but ONNX model not found: {onnx_path.name}"
                )
        except Exception as e:
            log.warning(f"OpenCV DNN load failed ({e})")

        # Attempt 3: Stub detector (for development without models)
        self._loaded = True
        self._backend = "stub"
        log.info(
            "Using STUB detector (no real inference). "
            "Download models: python scripts/download_models.py"
        )
        return True

    def detect(self, frame: np.ndarray) -> list[BoundingBox]:
        """
        Run object detection on a single frame.

        Args:
            frame: BGR image as numpy array (H, W, 3)

        Returns:
            List of BoundingBox detections (normalized coordinates)
        """
        if not self._loaded:
            return []

        with profiler.measure("detector"):
            if self._backend == "ncnn":
                return self._detect_ncnn(frame)
            elif self._backend == "opencv":
                return self._detect_opencv(frame)
            else:
                return self._detect_stub(frame)

    def _detect_ncnn(self, frame: np.ndarray) -> list[BoundingBox]:
        """Real ncnn inference path for PicoDet-S.

        PicoDet outputs multiple feature maps. This implementation handles
        both single-output (simplified) and multi-output (stock PicoDet)
        architectures by probing for the standard output names.
        """
        import ncnn

        h, w = frame.shape[:2]

        # Preprocess: resize + normalize
        mat_in = ncnn.Mat.from_pixels_resize(
            frame, ncnn.Mat.PixelType.PIXEL_BGR2,
            w, h, self._input_w, self._input_h
        )

        # PicoDet normalization: ImageNet mean/std
        mean_vals = [0.485 * 255, 0.456 * 255, 0.406 * 255]
        norm_vals = [1.0 / (0.229 * 255), 1.0 / (0.224 * 255), 1.0 / (0.225 * 255)]
        mat_in.substract_mean_normalize(mean_vals, norm_vals)

        # Run inference
        ex = self._net.create_extractor()
        ex.input("image", mat_in)

        # PicoDet may have multiple outputs (concatenated or per-scale).
        # Try the standard output name first, then fall back to numbered outputs.
        raw_detections = []
        output_names = ["output", "outputs"]

        # Try to extract from named outputs
        found_output = False
        for name in output_names:
            try:
                ret, mat_out = ex.extract(name)
                if ret == 0:
                    found_output = True
                    # Parse rows: [class_id, confidence, x1, y1, x2, y2] per row
                    for i in range(mat_out.h):
                        values = mat_out.row(i)
                        class_id = int(values[0])
                        confidence = float(values[1])
                        if confidence >= self._conf_threshold:
                            raw_detections.append((
                                class_id, confidence,
                                float(values[2]), float(values[3]),
                                float(values[4]), float(values[5]),
                            ))
            except Exception:
                continue

        # If named extraction failed, try numbered outputs (PicoDet: 0, 1, 2, 3)
        if not found_output:
            for idx in range(4):
                try:
                    ret, mat_out = ex.extract(idx)
                    if ret == 0 and mat_out.h > 0:
                        # Multi-output format varies; decode conservatively
                        for i in range(mat_out.h):
                            values = mat_out.row(i)
                            # Heuristic: if row width >= 6, treat as detection
                            if mat_out.w >= 6:
                                class_id = int(values[0])
                                confidence = float(values[1])
                                if confidence >= self._conf_threshold:
                                    raw_detections.append((
                                        class_id, confidence,
                                        float(values[2]), float(values[3]),
                                        float(values[4]), float(values[5]),
                                    ))
                except Exception:
                    continue

        # Convert to normalized BoundingBox, filter by class
        detections = []
        for class_id, confidence, x1, y1, x2, y2 in raw_detections:
            if class_id not in self._target_classes:
                continue

            # Clamp to image bounds and normalize
            x1 = max(0.0, min(1.0, x1 / w))
            y1 = max(0.0, min(1.0, y1 / h))
            x2 = max(0.0, min(1.0, x2 / w))
            y2 = max(0.0, min(1.0, y2 / h))

            bbox = BoundingBox(
                x_center=(x1 + x2) / 2,
                y_center=(y1 + y2) / 2,
                width=x2 - x1,
                height=y2 - y1,
                confidence=confidence,
                class_id=class_id,
            )
            detections.append(bbox)

        return detections

    def _detect_opencv(self, frame: np.ndarray) -> list[BoundingBox]:
        """OpenCV DNN inference path (fallback for Windows / non-ARM dev).

        Uses the ONNX export of PicoDet-S. Slower than ncnn but works
        everywhere without compilation.
        """
        import cv2

        h, w = frame.shape[:2]

        # Create input blob: resize to model input, normalize
        blob = cv2.dnn.blobFromImage(
            frame,
            scalefactor=1.0 / (0.229 * 255.0),  # Combined scale (std)
            size=(self._input_w, self._input_h),
            mean=(0.485 * 255, 0.456 * 255, 0.406 * 255),  # ImageNet mean
            swapRB=False,  # BGR input matches frame
            crop=False,
        )

        self._net.setInput(blob)
        output = self._net.forward()

        # PicoDet ONNX output shape: (1, N, 6) → [class, conf, x1, y1, x2, y2]
        detections = []
        if output.ndim == 3:
            output = output[0]  # Remove batch dim

        for det in output:
            class_id = int(det[0])
            confidence = float(det[1])
            if confidence < self._conf_threshold:
                continue
            if class_id not in self._target_classes:
                continue

            x1 = max(0.0, min(1.0, float(det[2]) / w))
            y1 = max(0.0, min(1.0, float(det[3]) / h))
            x2 = max(0.0, min(1.0, float(det[4]) / w))
            y2 = max(0.0, min(1.0, float(det[5]) / h))

            bbox = BoundingBox(
                x_center=(x1 + x2) / 2,
                y_center=(y1 + y2) / 2,
                width=x2 - x1,
                height=y2 - y1,
                confidence=confidence,
                class_id=class_id,
            )
            detections.append(bbox)

        return detections

    def _detect_stub(self, frame: np.ndarray) -> list[BoundingBox]:
        """
        Stub detector for development — returns a fake detection
        at the center of the frame. Useful for testing the tracking
        pipeline without real model weights.
        """
        # Simulate detection every other frame with slight jitter
        t = time.time()
        if int(t * 10) % 3 == 0:
            return []  # Simulate occasional missed detections

        # Simulated subject near center with slight movement
        jitter_x = np.sin(t * 0.5) * 0.05
        jitter_y = np.cos(t * 0.3) * 0.03

        return [
            BoundingBox(
                x_center=0.5 + jitter_x,
                y_center=0.5 + jitter_y,
                width=0.15,
                height=0.30,
                confidence=0.92,
                class_id=0,
            )
        ]

    @property
    def is_loaded(self) -> bool:
        return self._loaded

    @property
    def backend(self) -> str:
        return self._backend
