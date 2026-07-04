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
      - "gazebo": PX4 SITL Gazebo camera stream (sim-to-real testing)
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
            source: "skydroid", "gazebo", "usb", "file:/path/to/video.mp4",
                    "gazebo:5600" (UDP port for Gazebo stream),
                    "synthetic", or "auto" (tries usb → synthetic)

            Note: "auto" never tries "gazebo" because probing for a UDP
            stream blocks indefinitely when no stream exists. To use the
            Gazebo camera, pass source="gazebo" explicitly.

        Returns:
            True if camera started successfully
        """
        if source == "auto":
            # Try sources in order of preference.
            # NOTE: gazebo is intentionally excluded from auto-detection
            # because the GStreamer/UDP probe blocks when no stream exists.
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
            elif source.startswith("gazebo"):
                # Parse optional port: "gazebo" or "gazebo:5600"
                port = 5600  # Default Gazebo camera UDP port
                if ":" in source:
                    port = int(source.split(":")[1])
                return self._start_gazebo(port)
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

    def _start_gazebo(self, udp_port: int = 5600) -> bool:
        """
        Start PX4 SITL Gazebo camera stream.

        When running PX4 SITL with Gazebo, the drone's virtual camera
        can stream video over UDP using GStreamer. Configure the Gazebo
        model's camera plugin to output to udp://<host>:<port>.

        Common setup (in PX4 SITL):
          - typhoon_h480 model has a downward + forward camera
          - The video streams to UDP port 5600 by default
          - QGroundControl also receives this stream

        On the GarudaOne side, we receive the UDP stream as if it were
        an RTP video source. OpenCV can read this with GStreamer backend.

        Args:
            udp_port: UDP port receiving the Gazebo camera stream
        """
        import socket

        # First, do a non-blocking probe: bind a UDP socket to check if
        # anything is streaming to this port. We listen briefly for data.
        # This avoids the infinite block that cv2.VideoCapture would do
        # if no Gazebo instance is actually streaming.
        try:
            probe = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            probe.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            probe.bind(("0.0.0.0", udp_port))
            probe.settimeout(1.5)  # Wait up to 1.5s for a packet
            try:
                probe.recvfrom(1024)
            except socket.timeout:
                probe.close()
                log.info(
                    f"No Gazebo camera stream on UDP port {udp_port} "
                    f"(no data within 1.5s). Falling back."
                )
                return False
            probe.close()
        except OSError as e:
            log.info(
                f"Cannot probe UDP port {udp_port} ({e}). "
                f"Falling back."
            )
            return False

        # A stream is present — now open it via GStreamer
        url = f"udpsrc port={udp_port} ! application/x-rtp,payload=26 ! " \
              f"rtpjpegdepay ! jpegdec ! videoconvert ! appsink"

        try:
            # Try GStreamer backend (requires opencv with gstreamer support)
            self._capture = cv2.VideoCapture(
                url, cv2.CAP_GSTREAMER
            )
            if self._capture.isOpened():
                self._is_streaming = True
                self._source_type = "gazebo"
                log.info(
                    f"✓ Gazebo camera stream started "
                    f"(UDP port {udp_port})"
                )
                return True
            else:
                self._capture.release()
                self._capture = None
        except Exception:
            pass

        # Fallback: try plain UDP URL (some OpenCV builds support this)
        try:
            self._capture = cv2.VideoCapture(f"udp://@0.0.0.0:{udp_port}")
            if self._capture.isOpened():
                self._is_streaming = True
                self._source_type = "gazebo"
                log.info(
                    f"✓ Gazebo camera stream started (UDP fallback, "
                    f"port {udp_port})"
                )
                return True
            else:
                self._capture.release()
                self._capture = None
        except Exception:
            pass

        log.info(
            f"Gazebo camera stream not available on port {udp_port}. "
            f"Ensure PX4 SITL + Gazebo is running with a camera model. "
            f"Falling back to other sources."
        )
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
