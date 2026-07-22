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
            if self.config.get("detector.use_tiling", False):
                return self._detect_with_tiling(frame)
            else:
                if self._backend == "ncnn":
                    return self._detect_ncnn(frame)
                elif self._backend == "opencv":
                    return self._detect_opencv(frame)
                else:
                    return self._detect_stub(frame)

    def _detect_with_tiling(self, frame: np.ndarray) -> list[BoundingBox]:
        """Run SAHI (Slicing Aided Hyper Inference) via image tiling."""
        h, w = frame.shape[:2]
        overlap = self.config.get("detector.tiling_overlap", 0.2)
        
        all_detections = []
        
        # 1. Full frame inference
        if self._backend == "ncnn":
            all_detections.extend(self._detect_ncnn(frame))
        elif self._backend == "opencv":
            all_detections.extend(self._detect_opencv(frame))
        else:
            all_detections.extend(self._detect_stub(frame))
            
        # If stub, just return (tiling doesn't make sense for stub)
        if self._backend == "stub":
            return all_detections
            
        # 2. Tile inference (4 quadrants with overlap)
        # Calculate tile size
        tile_w = int(w / (2 - overlap))
        tile_h = int(h / (2 - overlap))
        
        # Define the 4 top-left corners of the tiles
        origins = [
            (0, 0),                                # Top-Left
            (w - tile_w, 0),                       # Top-Right
            (0, h - tile_h),                       # Bottom-Left
            (w - tile_w, h - tile_h),              # Bottom-Right
        ]
        
        for x_offset, y_offset in origins:
            tile = frame[y_offset:y_offset + tile_h, x_offset:x_offset + tile_w]
            
            # Run inference on tile
            if self._backend == "ncnn":
                tile_dets = self._detect_ncnn(tile)
            else:
                tile_dets = self._detect_opencv(tile)
                
            # Translate normalized tile coordinates to normalized full-frame coordinates
            for det in tile_dets:
                # Convert from tile normalized to tile absolute
                abs_cx = det.x_center * tile_w
                abs_cy = det.y_center * tile_h
                abs_width = det.width * tile_w
                abs_height = det.height * tile_h
                
                # Add offset
                global_cx = abs_cx + x_offset
                global_cy = abs_cy + y_offset
                
                # Convert to global normalized
                det.x_center = global_cx / w
                det.y_center = global_cy / h
                det.width = abs_width / w
                det.height = abs_height / h
                
                all_detections.append(det)
                
        # 3. Apply NMS to merge overlapping detections
        return self._nms(all_detections)

    def _nms(self, detections: list[BoundingBox]) -> list[BoundingBox]:
        """Apply Non-Maximum Suppression to remove duplicate bounding boxes."""
        if not detections:
            return []
            
        # Sort by confidence descending
        detections = sorted(detections, key=lambda x: x.confidence, reverse=True)
        keep = []
        
        for det in detections:
            is_duplicate = False
            for kept_det in keep:
                if det.class_id == kept_det.class_id:
                    iou = det.intersection_over_union(kept_det)
                    if iou > self._nms_threshold:
                        is_duplicate = True
                        break
            
            if not is_duplicate:
                keep.append(det)
                
        return keep

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


class AerialDetector:
    """
    Aerial small-object detector using a YOLO (v8/v11) ONNX model.

    Intended for VisDrone-style weights so the drone can spot people from
    altitude, where a generic COCO detector struggles with tiny targets.

    Interface-compatible with :class:`PicoDetector` on purpose: it exposes
    ``load_model()`` and ``detect(frame) -> list[BoundingBox]`` so it drops
    into ``main.py`` and the tracker with no other changes. When no ONNX
    model file is present it falls back to the same style of stub detector,
    so the whole system still boots (and tests run) on a machine with no
    model weights.

    YOLOv8/v11 ONNX output note:
      The model emits ``[1, 4 + num_classes, num_boxes]`` (e.g. VisDrone's
      10 classes -> ``[1, 14, 8400]``). There is NO separate objectness
      score; per-class confidence lives in channels ``4:``. Coordinates are
      ``(cx, cy, w, h)`` in *letterboxed input pixels* (not normalized), so
      we undo the letterbox padding/scale before normalizing.
    """

    def __init__(self, config: Config):
        self.config = config

        self._input_w = config.get("detector_aerial.input_width", 640)
        self._input_h = config.get("detector_aerial.input_height", 640)
        self._conf_threshold = config.get(
            "detector_aerial.confidence_threshold", 0.4
        )
        self._nms_threshold = config.get("detector_aerial.nms_threshold", 0.45)

        # VisDrone classes 0 (pedestrian) and 1 (people) are both "person".
        # Detections in this set are re-mapped to class_id 0 so the existing
        # SubjectTracker (which filters class_id == 0) locks onto them.
        self._person_class_ids = set(
            config.get("detector_aerial.person_class_ids", [0, 1])
        )
        self._persons_only = config.get("detector_aerial.persons_only", True)
        # Number of model output classes. Used to disambiguate the ONNX
        # output orientation robustly. 0 = unknown -> size heuristic.
        self._num_classes = int(config.get("detector_aerial.num_classes", 0))

        self._net = None
        self._loaded = False
        self._backend = "none"

        log.info(
            f"Aerial detector initialized — "
            f"input={self._input_w}x{self._input_h}, "
            f"conf={self._conf_threshold}, nms={self._nms_threshold}, "
            f"person_classes={sorted(self._person_class_ids)}"
        )

    def load_model(self) -> bool:
        """
        Load a YOLO ONNX model via OpenCV DNN. Falls back to a stub detector
        when the model file is missing (so dev/CI works without weights).

        Returns True once a backend (real or stub) is ready.
        """
        models_dir = self.config.models_dir

        try:
            import cv2

            onnx_path = models_dir / self.config.get(
                "detector_aerial.model_onnx", "yolov11n_visdrone.onnx"
            )
            if onnx_path.exists():
                self._net = cv2.dnn.readNetFromONNX(str(onnx_path))
                self._net.setPreferableBackend(cv2.dnn.DNN_BACKEND_OPENCV)
                self._net.setPreferableTarget(cv2.dnn.DNN_TARGET_CPU)

                self._loaded = True
                self._backend = "yolo-onnx"
                log.info(f"Aerial YOLO model loaded via OpenCV DNN ({onnx_path.name})")
                return True
            else:
                log.info(
                    f"Aerial ONNX model not found: {onnx_path.name} — "
                    "using STUB detector. Place VisDrone YOLO weights in "
                    "models/ (see: huggingface.co VisDrone YOLO zoo)."
                )
        except Exception as e:
            log.warning(f"Aerial YOLO load failed ({e}) — using STUB detector")

        self._loaded = True
        self._backend = "stub"
        return True

    def detect(self, frame: np.ndarray) -> list[BoundingBox]:
        """Run detection on a single BGR frame -> list[BoundingBox]."""
        if not self._loaded:
            return []

        with profiler.measure("detector"):
            if self._backend == "yolo-onnx":
                return self._detect_yolo(frame)
            return self._detect_stub(frame)

    def _detect_yolo(self, frame: np.ndarray) -> list[BoundingBox]:
        """Full YOLO ONNX inference path: letterbox -> forward -> decode."""
        import cv2

        orig_h, orig_w = frame.shape[:2]
        padded, gain, pad_w, pad_h = self._letterbox(
            frame, (self._input_w, self._input_h)
        )

        blob = cv2.dnn.blobFromImage(
            padded,
            scalefactor=1.0 / 255.0,
            size=(self._input_w, self._input_h),
            swapRB=True,   # BGR (OpenCV) -> RGB (YOLO training)
            crop=False,
        )
        self._net.setInput(blob)
        output = self._net.forward()

        return self._postprocess(output, gain, pad_w, pad_h, orig_w, orig_h)

    @staticmethod
    def _letterbox(frame: np.ndarray, new_shape: tuple[int, int]):
        """Resize preserving aspect ratio and pad to ``new_shape``.

        Returns ``(padded_image, gain, pad_w, pad_h)`` where ``gain`` is the
        resize scale and ``pad_w/pad_h`` are the single-side pixel paddings.
        """
        import cv2

        h, w = frame.shape[:2]
        new_w, new_h = new_shape
        gain = min(new_w / w, new_h / h)
        unpad_w, unpad_h = int(round(w * gain)), int(round(h * gain))

        resized = cv2.resize(
            frame, (unpad_w, unpad_h), interpolation=cv2.INTER_LINEAR
        )

        pad_w = (new_w - unpad_w) / 2.0
        pad_h = (new_h - unpad_h) / 2.0
        top, bottom = int(round(pad_h - 0.1)), int(round(pad_h + 0.1))
        left, right = int(round(pad_w - 0.1)), int(round(pad_w + 0.1))

        padded = cv2.copyMakeBorder(
            resized, top, bottom, left, right,
            cv2.BORDER_CONSTANT, value=(114, 114, 114),
        )
        return padded, gain, pad_w, pad_h

    def _postprocess(
        self,
        output: np.ndarray,
        gain: float,
        pad_w: float,
        pad_h: float,
        orig_w: int,
        orig_h: int,
    ) -> list[BoundingBox]:
        """Decode a YOLOv8/v11 ONNX tensor into normalized BoundingBoxes.

        Kept as a standalone method (no network calls) so it can be
        unit-tested with a synthetic output array.
        """
        import cv2

        arr = output
        if arr.ndim == 3:
            arr = arr[0]  # drop batch dim only (keep size-1 box/channel dims)
        if arr.ndim != 2:
            return []

        # Orient to (num_boxes, 4 + num_classes). YOLOv8/v11 typically export
        # as (channels, boxes); some exporters transpose to (boxes, channels).
        # Prefer the configured channel count to disambiguate (robust even for
        # tiny synthetic tensors); otherwise fall back to "channels is the
        # smaller axis" (true for real models with thousands of boxes).
        expected_ch = 4 + self._num_classes if self._num_classes > 0 else 0
        if expected_ch and arr.shape[0] == expected_ch and arr.shape[1] != expected_ch:
            arr = arr.transpose()
        elif expected_ch and arr.shape[1] == expected_ch:
            pass
        elif arr.shape[0] < arr.shape[1]:
            arr = arr.transpose()

        num_classes = arr.shape[1] - 4
        if num_classes <= 0:
            return []

        boxes: list[list[float]] = []
        confidences: list[float] = []
        class_ids: list[int] = []

        for row in arr:
            scores = row[4:4 + num_classes]
            class_id = int(np.argmax(scores))
            confidence = float(scores[class_id])

            if confidence < self._conf_threshold:
                continue
            if self._persons_only and class_id not in self._person_class_ids:
                continue

            cx, cy, bw, bh = (
                float(row[0]), float(row[1]), float(row[2]), float(row[3])
            )
            # Top-left corner in letterboxed-pixel space for NMS.
            boxes.append([cx - bw / 2.0, cy - bh / 2.0, bw, bh])
            confidences.append(confidence)
            class_ids.append(class_id)

        if not boxes:
            return []

        indices = cv2.dnn.NMSBoxes(
            boxes, confidences, self._conf_threshold, self._nms_threshold
        )
        if len(indices) == 0:
            return []

        detections: list[BoundingBox] = []
        for idx in np.array(indices).flatten():
            x, y, bw, bh = boxes[idx]

            # Undo the letterbox: remove padding, then rescale to original.
            x0 = (x - pad_w) / gain
            y0 = (y - pad_h) / gain
            w0 = bw / gain
            h0 = bh / gain

            x_center = (x0 + w0 / 2.0) / orig_w
            y_center = (y0 + h0 / 2.0) / orig_h
            norm_w = w0 / orig_w
            norm_h = h0 / orig_h

            # Clamp into [0, 1].
            x_center = min(max(x_center, 0.0), 1.0)
            y_center = min(max(y_center, 0.0), 1.0)
            norm_w = min(max(norm_w, 0.0), 1.0)
            norm_h = min(max(norm_h, 0.0), 1.0)

            raw_class = class_ids[idx]
            out_class = 0 if raw_class in self._person_class_ids else raw_class

            detections.append(
                BoundingBox(
                    x_center=x_center,
                    y_center=y_center,
                    width=norm_w,
                    height=norm_h,
                    confidence=confidences[idx],
                    class_id=out_class,
                )
            )

        return detections

    def _detect_stub(self, frame: np.ndarray) -> list[BoundingBox]:
        """Stub detector — fake center detection so the pipeline runs
        without model weights (mirrors PicoDetector's stub behavior)."""
        t = time.time()
        if int(t * 10) % 3 == 0:
            return []

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
