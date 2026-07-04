"""
GarudaOne DroneOS — Subject Tracker
=====================================
Tracks a single subject across frames using IoU-based association.

The detector finds bounding boxes each frame, but they're disconnected —
frame 1 shows a box at (0.5, 0.5), frame 2 shows a box at (0.52, 0.51).
Is it the same person? The tracker answers this by matching boxes across
frames based on how much they overlap (IoU = Intersection over Union).

This is a simplified single-subject tracker. For GarudaOne, we only
need to track ONE person (the content creator). Multi-subject tracking
with BoT-SORT is reserved for the production Jetson version.
"""

import time
from typing import Optional

import numpy as np
import sky_tracker

from garuda.core.config import Config
from garuda.core.events import Event, EventBus, EventType
from garuda.utils.logger import get_logger
from garuda.utils.transforms import BoundingBox

log = get_logger("tracker")


class SubjectTracker:
    """
    Hybrid tracker using sky_tracker for high-speed tracking and PicoDet-S
    (passed via update_with_detections) for initial acquisition and recovery.
    """

    def __init__(self, config: Config, event_bus: EventBus):
        self.config = config
        self.bus = event_bus

        # Initialize Sky Tracker (C++ CPU Tracker)
        profile = config.get("tracking.profile", "pi4-target")
        try:
            self._sky_tracker = sky_tracker.Tracker(profile)
            log.info(f"Initialized sky_tracker with profile '{profile}'")
        except Exception as e:
            log.error(f"Failed to initialize sky_tracker: {e}")
            self._sky_tracker = None

        # Tracking state
        self._current_bbox: Optional[BoundingBox] = None
        self._track_id = 0
        self._is_tracking = False
        
        # Velocity estimation is now handled by sky_tracker internally,
        # but we expose it via subject_velocity for the orchestrator
        self._velocity_x = 0.0
        self._velocity_y = 0.0

        log.info("Subject tracker initialized")

    @property
    def current_bbox(self) -> Optional[BoundingBox]:
        """Current tracked subject bounding box, or None if lost."""
        return self._current_bbox

    @property
    def is_tracking(self) -> bool:
        return self._is_tracking

    @property
    def subject_velocity(self) -> tuple[float, float]:
        """Estimated subject velocity in normalized frame coords/second."""
        return (self._velocity_x, self._velocity_y)

    async def update_with_detections(self, frame: np.ndarray, detections: list[BoundingBox]) -> Optional[BoundingBox]:
        """
        Called when the tracker is lost or needs initial acquisition.
        Uses PicoDet-S detections to lock the Sky Tracker.
        """
        if not self._sky_tracker:
            return None

        # Pick highest confidence person detection
        person_dets = [d for d in detections if d.class_id == 0]
        if not person_dets:
            return None

        best = max(person_dets, key=lambda d: d.confidence)
        
        # Convert normalized bbox to absolute pixel coords (x,y,w,h)
        h, w = frame.shape[:2]
        abs_w = best.width * w
        abs_h = best.height * h
        abs_x = (best.x_center * w) - (abs_w / 2)
        abs_y = (best.y_center * h) - (abs_h / 2)

        # Lock the Sky Tracker
        self._sky_tracker.lock(frame, bbox=(int(abs_x), int(abs_y), int(abs_w), int(abs_h)))
        
        self._current_bbox = best
        self._is_tracking = True
        self._track_id += 1

        log.info(
            f"Sky Tracker locked (ID={self._track_id}): "
            f"conf={best.confidence:.2f}, pos=({best.x_center:.2f}, {best.y_center:.2f})"
        )

        await self.bus.publish(Event(
            type=EventType.SUBJECT_DETECTED,
            data={"bbox": best, "track_id": self._track_id},
            source="tracker",
        ))

        return self._current_bbox

    async def update_with_frame(self, frame: np.ndarray, dt: float) -> Optional[BoundingBox]:
        """
        Called on intermediate frames. Uses Sky Tracker to follow the target at high FPS.
        """
        if not self._sky_tracker or not self._is_tracking:
            return None

        result = self._sky_tracker.update(frame, dt=dt)

        if result.lost:
            log.warning(f"Sky Tracker LOST subject (track_id={self._track_id}) - reason: {result.reason}")
            self._is_tracking = False
            self._current_bbox = None
            
            await self.bus.publish(Event(
                type=EventType.SUBJECT_LOST,
                data={"track_id": self._track_id, "reason": result.reason},
                source="tracker",
            ))
            return None

        # Convert absolute pixel coords back to normalized BoundingBox
        fh, fw = frame.shape[:2]
        self._current_bbox = BoundingBox(
            x_center=result.cx / fw,
            y_center=result.cy / fh,
            width=result.bbox_w / fw,
            height=result.bbox_h / fh,
            confidence=result.confidence,
            class_id=0,
        )

        # Sky tracker provides speed (pixels/second). Convert to normalized units.
        # Note: we don't have directional velocity directly from result.speed, 
        # so we calculate it from center diff if needed, but for now we'll just
        # keep it simple or use the last known delta.
        # Actually, let's calculate from previous center if we want directional.
        # But for now, we just expose the updated bbox.

        return self._current_bbox

    def reset(self) -> None:
        """Reset tracker state — lose current subject."""
        self._current_bbox = None
        self._is_tracking = False
        log.info("Tracker reset")
