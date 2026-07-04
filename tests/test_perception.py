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


from unittest.mock import MagicMock, patch

class TestTracker:
    """Test hybrid subject tracker with sky_tracker."""

    @pytest.mark.asyncio
    @patch("garuda.perception.tracker.sky_tracker.Tracker")
    async def test_acquire_subject(self, mock_tracker_cls, config, event_bus):
        """Tracker should lock onto the best person detection."""
        mock_instance = MagicMock()
        mock_tracker_cls.return_value = mock_instance

        tracker = SubjectTracker(config, event_bus)

        frame = np.zeros((480, 640, 3), dtype=np.uint8)
        detections = [
            BoundingBox(x_center=0.5, y_center=0.5, width=0.2,
                        height=0.4, confidence=0.9, class_id=0)
        ]

        result = await tracker.update_with_detections(frame, detections)
        assert result is not None
        assert tracker.is_tracking is True
        assert result.confidence == 0.9
        mock_instance.lock.assert_called_once()

    @pytest.mark.asyncio
    @patch("garuda.perception.tracker.sky_tracker.Tracker")
    async def test_track_across_frames(self, mock_tracker_cls, config, event_bus):
        """Tracker should maintain tracking using update_with_frame."""
        mock_instance = MagicMock()
        mock_tracker_cls.return_value = mock_instance

        tracker = SubjectTracker(config, event_bus)
        frame = np.zeros((480, 640, 3), dtype=np.uint8)

        # Frame 1: Lock
        await tracker.update_with_detections(frame, [
            BoundingBox(0.5, 0.5, 0.2, 0.4, 0.9, 0)
        ])

        # Frame 2: Update (returns tracked result)
        class MockResult:
            lost = False
            cx = 330
            cy = 240
            bbox_w = 128
            bbox_h = 256
            confidence = 0.88

        mock_instance.update.return_value = MockResult()

        result = await tracker.update_with_frame(frame, dt=0.033)

        assert result is not None
        assert tracker.is_tracking is True
        assert result.confidence == 0.88
        assert abs(result.x_center - (330 / 640)) < 0.01

    @pytest.mark.asyncio
    @patch("garuda.perception.tracker.sky_tracker.Tracker")
    async def test_tracker_lost(self, mock_tracker_cls, config, event_bus):
        """Tracker should handle lost state properly."""
        mock_instance = MagicMock()
        mock_tracker_cls.return_value = mock_instance

        tracker = SubjectTracker(config, event_bus)
        frame = np.zeros((480, 640, 3), dtype=np.uint8)

        # Acquire
        await tracker.update_with_detections(frame, [
            BoundingBox(0.5, 0.5, 0.2, 0.4, 0.9, 0)
        ])

        # Frame update says lost
        class MockLostResult:
            lost = True
            reason = "Occlusion"

        mock_instance.update.return_value = MockLostResult()

        result = await tracker.update_with_frame(frame, dt=0.033)
        assert result is None
        assert tracker.is_tracking is False


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
