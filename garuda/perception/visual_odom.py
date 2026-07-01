"""
GarudaOne DroneOS — Visual Odometry (SVO2 Interface)
=====================================================
Provides drone pose estimation and sparse depth mapping using
SVO2 (Semi-direct Visual Odometry) from ETH Zurich.

SVO2 was chosen over ORB-SLAM3 because:
  - ~50% less CPU usage on ARM
  - Designed specifically for micro-aerial vehicles (MAVs)
  - Provides sparse depth map useful for obstacle awareness
  - ARM-VO variant uses NEON SIMD for hardware acceleration

This module wraps SVO2 (built from source as a C++ binary)
and provides Python-accessible pose and depth data.
"""

import time
from dataclasses import dataclass, field
from typing import Optional

import numpy as np

from garuda.utils.logger import get_logger
from garuda.utils.profiler import profiler
from garuda.utils.transforms import PositionNED, AttitudeEuler

log = get_logger("visual_odom")


@dataclass
class VOPose:
    """Visual odometry pose estimate."""
    position: PositionNED = field(default_factory=PositionNED)
    attitude: AttitudeEuler = field(default_factory=AttitudeEuler)
    confidence: float = 0.0  # 0 = lost, 1 = confident
    timestamp: float = 0.0


@dataclass
class DepthMap:
    """
    Sparse depth map from visual odometry.

    Not every pixel has a depth value — only pixels with tracked
    features. The costmap converts this into an obstacle grid.
    """
    depths: Optional[np.ndarray] = None  # (H, W) float32, 0 = no data
    valid_mask: Optional[np.ndarray] = None  # (H, W) bool
    min_depth_m: float = 0.5
    max_depth_m: float = 20.0

    @property
    def has_data(self) -> bool:
        return self.depths is not None and self.valid_mask is not None

    def get_obstacle_regions(self, threshold_m: float = 3.0) -> list[tuple[int, int]]:
        """
        Find image regions where obstacles are closer than threshold.
        Returns list of (row, col) pixel coordinates.
        """
        if not self.has_data:
            return []

        close_mask = (self.depths < threshold_m) & self.valid_mask
        return list(zip(*np.where(close_mask)))


class VisualOdometry:
    """
    SVO2 visual odometry wrapper.

    In the real system, SVO2 runs as a C++ process and we read
    its output via shared memory or a Unix socket. For development,
    this provides a stub that simulates slowly changing poses.
    """

    def __init__(self):
        self._current_pose = VOPose()
        self._current_depth = DepthMap()
        self._initialized = False
        self._backend = "stub"
        self._frame_count = 0

        log.info("Visual odometry module initialized")

    def initialize(self) -> bool:
        """
        Initialize SVO2.

        On RPi5: starts the SVO2 C++ process.
        On dev: uses stub data.
        """
        try:
            # TODO: Start SVO2 process and connect
            # For now, use stub
            self._initialized = True
            self._backend = "stub"
            log.info("Visual odometry initialized (stub mode)")
            return True
        except Exception as e:
            log.error(f"Failed to initialize VO: {e}")
            return False

    def process_frame(self, frame: np.ndarray) -> tuple[VOPose, DepthMap]:
        """
        Process a camera frame through visual odometry.

        Args:
            frame: BGR camera frame

        Returns:
            (pose, depth_map) — current drone pose and sparse depth
        """
        with profiler.measure("visual_odom"):
            if self._backend == "stub":
                return self._process_stub(frame)
            else:
                return self._process_svo2(frame)

    def _process_svo2(self, frame: np.ndarray) -> tuple[VOPose, DepthMap]:
        """Real SVO2 processing — read from the SVO2 process output."""
        # TODO: Read pose and depth from SVO2 shared memory
        raise NotImplementedError("SVO2 integration pending")

    def _process_stub(self, frame: np.ndarray) -> tuple[VOPose, DepthMap]:
        """
        Stub VO — simulates a slowly drifting pose and random depth.
        Good enough to test the downstream control pipeline.
        """
        self._frame_count += 1
        t = time.time()

        # Simulated pose with gentle drift
        pose = VOPose(
            position=PositionNED(
                north=np.sin(t * 0.1) * 2,
                east=np.cos(t * 0.1) * 2,
                down=-3.0,  # ~3m altitude
            ),
            attitude=AttitudeEuler(
                roll_deg=np.sin(t * 0.3) * 2,
                pitch_deg=np.cos(t * 0.2) * 2,
                yaw_deg=(t * 5) % 360,
            ),
            confidence=0.85,
            timestamp=t,
        )

        # Simulated sparse depth (mostly empty, some features)
        h, w = 240, 320  # Reduced resolution
        depths = np.zeros((h, w), dtype=np.float32)
        valid = np.zeros((h, w), dtype=bool)

        # Sprinkle some random depth features
        n_features = 50
        rows = np.random.randint(0, h, n_features)
        cols = np.random.randint(0, w, n_features)
        depths[rows, cols] = np.random.uniform(2.0, 15.0, n_features)
        valid[rows, cols] = True

        depth_map = DepthMap(depths=depths, valid_mask=valid)

        self._current_pose = pose
        self._current_depth = depth_map
        return pose, depth_map

    @property
    def current_pose(self) -> VOPose:
        return self._current_pose

    @property
    def current_depth(self) -> DepthMap:
        return self._current_depth

    @property
    def is_initialized(self) -> bool:
        return self._initialized
