"""
GarudaOne DroneOS — Camera Feed (Skydroid C10 Pro)
====================================================
Captures video frames from the Skydroid C10 Pro 3-axis gimbal camera.

The Skydroid C10 uses a PROPRIETARY protocol — it's NOT standard
UVC or HDMI. The hardware team has reverse-engineered the feed.

This module provides OpenCV-compatible frames (BGR numpy arrays)
at 30fps for the perception pipeline. It also handles recording
to disk for session replay and CfC training data collection.

Fallback sources:
  - USB webcam (for desktop development)
  - Video file (for offline testing)
  - Synthetic frames (for unit tests)
"""

import asyncio
import os
import time
from pathlib import Path
from typing import Optional

import cv2
import numpy as np

from garuda.core.config import Config
from garuda.utils.logger import get_logger
from garuda.utils.profiler import profiler

log = get_logger("camera")


class CameraFeed:
    """
    Camera frame provider — abstracts the video source.

    Supports multiple sources:
      - "skydroid": Reverse-engineered Skydroid C10 Pro feed
      - "usb": Standard USB webcam via OpenCV
      - "file": Pre-recorded video file
      - "synthetic": Generated test frames
    """

    def __init__(self, config: Config):
        self.config = config

        # Camera state
        self._capture: Optional[cv2.VideoCapture] = None
        self._is_streaming = False
        self._source_type = "synthetic"
        self._frame_count = 0
        self._fps = config.get("camera.fps", 30)

        # Recording state
        self._is_recording = False
        self._recorder: Optional[cv2.VideoWriter] = None
        self._recording_path: Optional[str] = None

        # Latest frame cache
        self._current_frame: Optional[np.ndarray] = None

        log.info("Camera feed initialized")

    @property
    def is_streaming(self) -> bool:
        return self._is_streaming

    @property
    def is_recording(self) -> bool:
        return self._is_recording

    @property
    def current_frame(self) -> Optional[np.ndarray]:
        return self._current_frame

    def start(self, source: str = "auto") -> bool:
        """
        Start the camera feed.

        Args:
            source: "skydroid", "usb", "file:/path/to/video.mp4",
                    "synthetic", or "auto" (try skydroid → usb → synthetic)

        Returns:
            True if camera started successfully
        """
        if source == "auto":
            # Try sources in order of preference
            for try_source in ["usb", "synthetic"]:
                if self._try_start(try_source):
                    return True
            return False
        else:
            return self._try_start(source)

    def _try_start(self, source: str) -> bool:
        """Attempt to start a specific camera source."""
        try:
            if source == "skydroid":
                return self._start_skydroid()
            elif source == "usb":
                return self._start_usb()
            elif source.startswith("file:"):
                return self._start_file(source[5:])
            elif source == "synthetic":
                return self._start_synthetic()
            else:
                log.error(f"Unknown camera source: {source}")
                return False
        except Exception as e:
            log.error(f"Failed to start {source} camera: {e}")
            return False

    def _start_skydroid(self) -> bool:
        """
        Start Skydroid C10 Pro reverse-engineered feed.
        The protocol details are handled by the hardware team's driver.
        """
        # TODO: Implement Skydroid proprietary protocol capture
        # The reverse-engineered driver provides frames via shared memory
        # or a custom socket interface
        log.warning("Skydroid driver not implemented — use USB or synthetic")
        return False

    def _start_usb(self) -> bool:
        """Start USB webcam via OpenCV."""
        self._capture = cv2.VideoCapture(0)
        if self._capture.isOpened():
            self._capture.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
            self._capture.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
            self._capture.set(cv2.CAP_PROP_FPS, self._fps)
            self._is_streaming = True
            self._source_type = "usb"
            log.info("✓ USB camera started (640x480)")
            return True
        else:
            self._capture.release()
            self._capture = None
            return False

    def _start_file(self, filepath: str) -> bool:
        """Start playback from a video file."""
        if not os.path.exists(filepath):
            log.error(f"Video file not found: {filepath}")
            return False

        self._capture = cv2.VideoCapture(filepath)
        if self._capture.isOpened():
            self._is_streaming = True
            self._source_type = "file"
            log.info(f"✓ Video file opened: {filepath}")
            return True
        return False

    def _start_synthetic(self) -> bool:
        """Start synthetic frame generation (for testing)."""
        self._is_streaming = True
        self._source_type = "synthetic"
        log.info("✓ Synthetic camera started (test frames)")
        return True

    def read_frame(self) -> Optional[np.ndarray]:
        """
        Read the next frame from the camera.

        Returns:
            BGR numpy array (H, W, 3), or None if no frame available
        """
        if not self._is_streaming:
            return None

        with profiler.measure("camera"):
            if self._source_type == "synthetic":
                frame = self._generate_synthetic_frame()
            elif self._capture is not None:
                ret, frame = self._capture.read()
                if not ret:
                    if self._source_type == "file":
                        # Loop video file
                        self._capture.set(cv2.CAP_PROP_POS_FRAMES, 0)
                        ret, frame = self._capture.read()
                    if not ret:
                        return None
            else:
                return None

        self._current_frame = frame
        self._frame_count += 1

        # Write to recording if active
        if self._is_recording and self._recorder is not None:
            self._recorder.write(frame)

        return frame

    def _generate_synthetic_frame(self) -> np.ndarray:
        """
        Generate a synthetic test frame with a moving target marker.
        Useful for testing the detection → tracking → control pipeline
        without any real camera.
        """
        h, w = 480, 640
        frame = np.zeros((h, w, 3), dtype=np.uint8)

        # Background gradient (sky-like)
        for y in range(h):
            blue = int(200 - (y / h) * 100)
            frame[y, :] = [blue, int(blue * 0.7), int(blue * 0.3)]

        # Moving "subject" rectangle
        t = time.time()
        cx = int(w / 2 + np.sin(t * 0.5) * w * 0.2)
        cy = int(h / 2 + np.cos(t * 0.3) * h * 0.1)
        size = 60

        cv2.rectangle(
            frame,
            (cx - size, cy - size * 2),
            (cx + size, cy + size * 2),
            (0, 255, 0),
            -1,
        )

        # Frame counter
        cv2.putText(
            frame,
            f"Frame {self._frame_count} [{self._source_type}]",
            (10, 30),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.7,
            (255, 255, 255),
            2,
        )

        return frame

    # ── Recording ─────────────────────────────────────────────────────────

    def start_recording(self, output_dir: str = "recordings") -> bool:
        """Start recording frames to a video file."""
        os.makedirs(output_dir, exist_ok=True)
        timestamp = time.strftime("%Y%m%d_%H%M%S")
        self._recording_path = os.path.join(output_dir, f"flight_{timestamp}.mp4")

        fourcc = cv2.VideoWriter_fourcc(*"mp4v")
        self._recorder = cv2.VideoWriter(
            self._recording_path, fourcc, self._fps, (640, 480)
        )

        if self._recorder.isOpened():
            self._is_recording = True
            log.info(f"Recording started: {self._recording_path}")
            return True
        return False

    def stop_recording(self) -> Optional[str]:
        """Stop recording and return the file path."""
        if self._recorder is not None:
            self._recorder.release()
            self._recorder = None
        self._is_recording = False
        path = self._recording_path
        self._recording_path = None
        log.info(f"Recording stopped: {path}")
        return path

    def stop(self) -> None:
        """Stop the camera feed and release resources."""
        if self._is_recording:
            self.stop_recording()
        if self._capture is not None:
            self._capture.release()
            self._capture = None
        self._is_streaming = False
        log.info("Camera feed stopped")
