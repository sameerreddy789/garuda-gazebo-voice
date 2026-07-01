"""
Tests for perception pipeline — detection, tracking, and transforms.
"""

import pytest
import numpy as np

from garuda.core.config import Config
from garuda.core.events import EventBus
from garuda.perception.detector import PicoDetector
from garuda.perception.tracker import SubjectTracker
from garuda.utils.transforms import (
    BoundingBox, VelocityNED, PositionNED, PositionGPS,
    body_to_ned, gps_to_ned, bbox_to_gimbal_error, angle_wrap_180,
)


@pytest.fixture
def config():
    return Config()


@pytest.fixture
def event_bus():
    return EventBus()


class TestDetector:
    """Test PicoDet-S detector (stub mode)."""

    def test_load_model_stub(self, config):
        """Detector should load in stub mode without model files."""
        detector = PicoDetector(config)
        assert detector.load_model() is True
        assert detector.backend == "stub"

    def test_detect_returns_list(self, config):
        """Detect should return a list of BoundingBox objects."""
        detector = PicoDetector(config)
        detector.load_model()
        frame = np.zeros((480, 640, 3), dtype=np.uint8)
        result = detector.detect(frame)
        assert isinstance(result, list)

    def test_stub_bboxes_are_valid(self, config):
        """Stub detections should have valid coordinates."""
        detector = PicoDetector(config)
        detector.load_model()
        frame = np.zeros((480, 640, 3), dtype=np.uint8)

        # Run multiple frames to get a detection (stub skips some)
        import time
        for _ in range(30):
            result = detector.detect(frame)
            if result:
                bbox = result[0]
                assert 0 <= bbox.x_center <= 1
                assert 0 <= bbox.y_center <= 1
                assert bbox.width > 0
                assert bbox.height > 0
                assert 0 <= bbox.confidence <= 1
                return
            time.sleep(0.05)  # Spread across time buckets

        # At least some frames should have detections
        pytest.fail("No detections in 30 frames")


class TestTracker:
    """Test IoU-based subject tracker."""

    @pytest.mark.asyncio
    async def test_acquire_subject(self, config, event_bus):
        """Tracker should acquire a new subject from detections."""
        tracker = SubjectTracker(config, event_bus)

        detections = [
            BoundingBox(x_center=0.5, y_center=0.5, width=0.2,
                        height=0.4, confidence=0.9, class_id=0)
        ]

        result = await tracker.update(detections)
        assert result is not None
        assert tracker.is_tracking is True
        assert result.confidence == 0.9

    @pytest.mark.asyncio
    async def test_track_across_frames(self, config, event_bus):
        """Tracker should maintain tracking when IoU is high."""
        tracker = SubjectTracker(config, event_bus)

        # Frame 1: Acquire
        await tracker.update([
            BoundingBox(0.5, 0.5, 0.2, 0.4, 0.9, 0)
        ])

        # Frame 2: Slight movement (high IoU)
        result = await tracker.update([
            BoundingBox(0.52, 0.51, 0.2, 0.4, 0.88, 0)
        ])

        assert result is not None
        assert tracker.is_tracking is True
        assert abs(result.x_center - 0.52) < 0.01

    @pytest.mark.asyncio
    async def test_no_detection_uses_prediction(self, config, event_bus):
        """Tracker should predict position when detection is missing."""
        tracker = SubjectTracker(config, event_bus)

        # Acquire subject
        await tracker.update([
            BoundingBox(0.5, 0.5, 0.2, 0.4, 0.9, 0)
        ])

        # Missing detection — should return predicted position
        result = await tracker.update([])
        assert result is not None  # Should have a predicted bbox
        assert tracker.is_tracking is True  # Not lost yet

    def test_iou_computation(self, config, event_bus):
        """Verify IoU computation is correct."""
        box_a = BoundingBox(0.5, 0.5, 0.2, 0.2, 1.0, 0)
        box_b = BoundingBox(0.5, 0.5, 0.2, 0.2, 1.0, 0)
        iou = SubjectTracker._compute_iou(box_a, box_b)
        assert abs(iou - 1.0) < 0.001  # Identical boxes = IoU 1.0

    def test_iou_no_overlap(self, config, event_bus):
        """Non-overlapping boxes should have IoU = 0."""
        box_a = BoundingBox(0.1, 0.1, 0.1, 0.1, 1.0, 0)
        box_b = BoundingBox(0.9, 0.9, 0.1, 0.1, 1.0, 0)
        iou = SubjectTracker._compute_iou(box_a, box_b)
        assert iou == 0.0


class TestTransforms:
    """Test coordinate transformation math."""

    def test_body_to_ned_north(self):
        """Moving forward (body X) while heading North = positive North."""
        result = body_to_ned(1.0, 0.0, 0.0, yaw_rad=0.0)
        assert abs(result.north - 1.0) < 0.01
        assert abs(result.east) < 0.01

    def test_body_to_ned_east(self):
        """Moving forward while heading East = positive East."""
        import math
        result = body_to_ned(1.0, 0.0, 0.0, yaw_rad=math.pi / 2)
        assert abs(result.north) < 0.01
        assert abs(result.east - 1.0) < 0.01

    def test_velocity_clamp(self):
        """Velocity clamping should preserve direction."""
        vel = VelocityNED(north=10.0, east=0.0, down=0.0)
        clamped = vel.clamp(5.0)
        assert abs(clamped.magnitude() - 5.0) < 0.01
        assert clamped.east == 0.0

    def test_gps_to_ned_at_home(self):
        """GPS position at home should be NED (0, 0, 0)."""
        home = PositionGPS(28.6, 77.2, 100.0)
        result = gps_to_ned(home, home)
        assert abs(result.north) < 0.01
        assert abs(result.east) < 0.01
        assert abs(result.down) < 0.01

    def test_angle_wrap(self):
        """Angle wrapping to [-180, 180]."""
        assert angle_wrap_180(270) == -90
        assert angle_wrap_180(-270) == 90
        assert angle_wrap_180(180) == 180
        assert angle_wrap_180(0) == 0

    def test_bbox_gimbal_error_centered(self):
        """Centered subject should have near-zero gimbal error."""
        bbox = BoundingBox(0.5, 0.5, 0.2, 0.4, 0.9, 0)
        yaw_err, pitch_err = bbox_to_gimbal_error(bbox)
        assert abs(yaw_err) < 0.01
        assert abs(pitch_err) < 0.01

    def test_bbox_gimbal_error_right(self):
        """Subject on right side should need positive yaw correction."""
        bbox = BoundingBox(0.8, 0.5, 0.2, 0.4, 0.9, 0)
        yaw_err, pitch_err = bbox_to_gimbal_error(bbox)
        assert yaw_err > 0  # Positive = rotate right
