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

from garuda.core.config import Config
from garuda.core.events import Event, EventBus, EventType
from garuda.utils.logger import get_logger
from garuda.utils.transforms import BoundingBox

log = get_logger("tracker")


class SubjectTracker:
    """
    Single-subject IoU tracker with re-acquisition.

    Workflow:
      1. Detector finds bounding boxes in each frame
      2. Tracker matches them to the currently tracked subject
      3. If no match found for N frames → subject lost event
      4. When subject reappears → re-acquisition event
    """

    def __init__(self, config: Config, event_bus: EventBus):
        self.config = config
        self.bus = event_bus

        # Tracking state
        self._current_bbox: Optional[BoundingBox] = None
        self._previous_bbox: Optional[BoundingBox] = None
        self._track_id = 0
        self._is_tracking = False
        self._frames_without_detection = 0

        # Config
        self._iou_threshold = 0.3
        self._lost_timeout_s = config.get("tracking.lost_subject_timeout_s", 3.0)
        self._reacquire_timeout_s = config.get("tracking.reacquire_timeout_s", 10.0)
        self._lost_timestamp: Optional[float] = None

        # Velocity estimation (for predicting subject movement)
        self._velocity_x = 0.0  # Normalized units per second
        self._velocity_y = 0.0
        self._last_update_time = time.time()

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

    async def update(self, detections: list[BoundingBox]) -> Optional[BoundingBox]:
        """
        Update the tracker with new detections from the detector.

        Args:
            detections: List of BoundingBox from PicoDet-S

        Returns:
            The tracked subject's bounding box, or None if lost
        """
        now = time.time()
        dt = now - self._last_update_time
        self._last_update_time = now

        if not detections:
            # No detections this frame
            return await self._handle_no_detection(now)

        if not self._is_tracking:
            # Not tracking anything — acquire the highest confidence detection
            return await self._acquire_subject(detections, now)

        # Currently tracking — find the best match
        best_match = self._find_best_match(detections)

        if best_match is not None:
            # Update tracking
            self._previous_bbox = self._current_bbox
            self._current_bbox = best_match
            self._frames_without_detection = 0
            self._lost_timestamp = None

            # Estimate velocity
            if self._previous_bbox:
                self._velocity_x = (
                    (best_match.x_center - self._previous_bbox.x_center) / dt
                    if dt > 0 else 0.0
                )
                self._velocity_y = (
                    (best_match.y_center - self._previous_bbox.y_center) / dt
                    if dt > 0 else 0.0
                )

            return self._current_bbox
        else:
            # No matching detection
            return await self._handle_no_detection(now)

    def _find_best_match(self, detections: list[BoundingBox]) -> Optional[BoundingBox]:
        """Find the detection that best matches our tracked subject."""
        if self._current_bbox is None:
            return None

        best_iou = 0.0
        best_det = None

        for det in detections:
            iou = self._compute_iou(self._current_bbox, det)
            if iou > best_iou and iou > self._iou_threshold:
                best_iou = iou
                best_det = det

        return best_det

    async def _acquire_subject(
        self, detections: list[BoundingBox], now: float
    ) -> Optional[BoundingBox]:
        """Acquire a new subject — pick the most confident person detection."""
        # Pick highest confidence detection
        person_dets = [d for d in detections if d.class_id == 0]
        if not person_dets:
            return None

        best = max(person_dets, key=lambda d: d.confidence)
        self._current_bbox = best
        self._previous_bbox = None
        self._is_tracking = True
        self._track_id += 1
        self._frames_without_detection = 0
        self._lost_timestamp = None

        log.info(
            f"Subject acquired (ID={self._track_id}): "
            f"conf={best.confidence:.2f}, pos=({best.x_center:.2f}, {best.y_center:.2f})"
        )

        await self.bus.publish(Event(
            type=EventType.SUBJECT_DETECTED,
            data={"bbox": best, "track_id": self._track_id},
            source="tracker",
        ))

        return self._current_bbox

    async def _handle_no_detection(self, now: float) -> Optional[BoundingBox]:
        """Handle frames where the subject is not detected."""
        self._frames_without_detection += 1

        if self._lost_timestamp is None:
            self._lost_timestamp = now

        lost_duration = now - self._lost_timestamp

        if lost_duration > self._lost_timeout_s and self._is_tracking:
            # Subject officially lost
            log.warning(
                f"Subject LOST (track_id={self._track_id}) — "
                f"not seen for {lost_duration:.1f}s"
            )
            self._is_tracking = False
            await self.bus.publish(Event(
                type=EventType.SUBJECT_LOST,
                data={"track_id": self._track_id, "duration_s": lost_duration},
                source="tracker",
            ))
            self._current_bbox = None
            return None

        # Subject temporarily missing — use predicted position
        if self._current_bbox and lost_duration < self._lost_timeout_s:
            # Predict where the subject should be based on velocity
            dt = 1.0 / 30.0  # Assume 30fps
            predicted = BoundingBox(
                x_center=self._current_bbox.x_center + self._velocity_x * dt,
                y_center=self._current_bbox.y_center + self._velocity_y * dt,
                width=self._current_bbox.width,
                height=self._current_bbox.height,
                confidence=max(0.0, self._current_bbox.confidence - 0.1),
                class_id=0,
            )
            self._current_bbox = predicted
            return predicted

        return self._current_bbox

    @staticmethod
    def _compute_iou(box_a: BoundingBox, box_b: BoundingBox) -> float:
        """
        Compute Intersection over Union between two bounding boxes.

        Think of IoU like measuring how much two rectangles overlap.
        IoU = 1.0 means they're identical. IoU = 0.0 means no overlap.
        We use IoU > 0.3 to decide "this is the same person."
        """
        # Convert center format to corner format
        a_x1 = box_a.x_center - box_a.width / 2
        a_y1 = box_a.y_center - box_a.height / 2
        a_x2 = box_a.x_center + box_a.width / 2
        a_y2 = box_a.y_center + box_a.height / 2

        b_x1 = box_b.x_center - box_b.width / 2
        b_y1 = box_b.y_center - box_b.height / 2
        b_x2 = box_b.x_center + box_b.width / 2
        b_y2 = box_b.y_center + box_b.height / 2

        # Intersection
        ix1 = max(a_x1, b_x1)
        iy1 = max(a_y1, b_y1)
        ix2 = min(a_x2, b_x2)
        iy2 = min(a_y2, b_y2)

        intersection = max(0, ix2 - ix1) * max(0, iy2 - iy1)

        # Union
        area_a = box_a.width * box_a.height
        area_b = box_b.width * box_b.height
        union = area_a + area_b - intersection

        return intersection / union if union > 0 else 0.0

    def reset(self) -> None:
        """Reset tracker state — lose current subject."""
        self._current_bbox = None
        self._previous_bbox = None
        self._is_tracking = False
        self._frames_without_detection = 0
        self._lost_timestamp = None
        log.info("Tracker reset")
