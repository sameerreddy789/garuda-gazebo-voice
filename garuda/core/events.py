"""
GarudaOne DroneOS — Event Bus
==============================
Lightweight async pub/sub event system that decouples all modules.

Think of this like a drone-wide intercom. Any module can shout an event
("I detected a person!") and any other module listening for that event
type will hear it and react — without the two modules knowing about each other.

This is what allows the perception module to tell the flight module
"subject moved left" without importing each other directly.
"""

import asyncio
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum, auto
from typing import Any, Callable, Coroutine


# ── Event Types ───────────────────────────────────────────────────────────────

class EventType(Enum):
    """All event types in the DroneOS system."""

    # Core lifecycle
    SYSTEM_READY = auto()
    SYSTEM_SHUTDOWN = auto()

    # Flight state
    ARMED = auto()
    DISARMED = auto()
    TAKEOFF_COMPLETE = auto()
    LANDING_COMPLETE = auto()
    OFFBOARD_STARTED = auto()
    OFFBOARD_LOST = auto()

    # Perception
    SUBJECT_DETECTED = auto()
    SUBJECT_LOST = auto()
    SUBJECT_REACQUIRED = auto()
    OBSTACLE_DETECTED = auto()

    # Voice commands
    WAKE_WORD_DETECTED = auto()
    VOICE_COMMAND_RECEIVED = auto()
    VOICE_COMMAND_PARSED = auto()

    # Brain / Tool calls
    TOOL_CALL_REQUESTED = auto()
    TOOL_CALL_COMPLETED = auto()

    # Mission
    MODE_CHANGED = auto()
    MISSION_STARTED = auto()
    MISSION_COMPLETED = auto()

    # Safety
    BATTERY_WARNING = auto()
    BATTERY_CRITICAL = auto()
    GEOFENCE_BREACH = auto()
    HEARTBEAT_LOST = auto()
    EMERGENCY_STOP = auto()

    # Telemetry
    POSITION_UPDATE = auto()
    ATTITUDE_UPDATE = auto()
    BATTERY_UPDATE = auto()
    GPS_STATUS_UPDATE = auto()


# ── Event Data ────────────────────────────────────────────────────────────────

@dataclass
class Event:
    """
    A single event published on the event bus.

    Attributes:
        type: What happened (from EventType enum)
        data: Arbitrary payload (dict, dataclass, or None)
        source: Which module published this event
        timestamp: When it happened
    """
    type: EventType
    data: Any = None
    source: str = "unknown"
    timestamp: datetime = field(default_factory=datetime.now)


# ── Event Bus ─────────────────────────────────────────────────────────────────

# Type alias for event handler callbacks
EventHandler = Callable[[Event], Coroutine[Any, Any, None]]


class EventBus:
    """
    Async event bus for inter-module communication.

    Usage:
        bus = EventBus()

        # Subscribe to events
        async def on_subject_detected(event):
            bbox = event.data["bbox"]
            print(f"Subject at {bbox.x_center}, {bbox.y_center}")

        bus.subscribe(EventType.SUBJECT_DETECTED, on_subject_detected)

        # Publish events
        await bus.publish(Event(
            type=EventType.SUBJECT_DETECTED,
            data={"bbox": bbox, "confidence": 0.95},
            source="perception"
        ))
    """

    def __init__(self):
        self._subscribers: dict[EventType, list[EventHandler]] = {}
        self._event_queue: asyncio.Queue[Event] = asyncio.Queue()
        self._running = False

    def subscribe(self, event_type: EventType, handler: EventHandler) -> None:
        """
        Register a handler for a specific event type.
        The handler must be an async function that accepts an Event.
        """
        if event_type not in self._subscribers:
            self._subscribers[event_type] = []
        self._subscribers[event_type].append(handler)

    def unsubscribe(self, event_type: EventType, handler: EventHandler) -> None:
        """Remove a handler from an event type."""
        if event_type in self._subscribers:
            self._subscribers[event_type] = [
                h for h in self._subscribers[event_type] if h != handler
            ]

    async def publish(self, event: Event) -> None:
        """
        Publish an event to all subscribers of that event type.
        Handlers are called concurrently via asyncio.gather.
        """
        handlers = self._subscribers.get(event.type, [])
        if handlers:
            # Run all handlers concurrently, don't let one failure kill others
            tasks = [handler(event) for handler in handlers]
            results = await asyncio.gather(*tasks, return_exceptions=True)

            for i, result in enumerate(results):
                if isinstance(result, Exception):
                    # Log but don't crash — one bad handler shouldn't break the drone
                    import logging
                    logging.getLogger("garuda.events").error(
                        f"Event handler error for {event.type.name}: {result}"
                    )

    async def publish_nowait(self, event: Event) -> None:
        """Queue an event for later processing (non-blocking)."""
        await self._event_queue.put(event)

    async def process_queue(self) -> None:
        """Process queued events. Call this in the main loop."""
        while not self._event_queue.empty():
            event = await self._event_queue.get()
            await self.publish(event)
