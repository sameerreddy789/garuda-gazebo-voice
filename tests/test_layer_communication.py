import pytest
import asyncio
from garuda.core.config import Config
from garuda.core.events import EventBus, Event, EventType
from garuda.core.orchestrator import Orchestrator, DroneState
from garuda.utils.transforms import BoundingBox, PositionNED, VelocityNED
from unittest.mock import AsyncMock, MagicMock

@pytest.fixture
def config():
    c = Config()
    if "control" not in c._data:
        c._data["control"] = {}
    c._data["control"]["main_loop_hz"] = 50
    return c

@pytest.fixture
def bus():
    return EventBus()

@pytest.fixture
def orchestrator(config, bus):
    """Orchestrator fixture with mocked modules, placed in HOVER state.

    The real main loop walks BOOT → IDLE → PREFLIGHT → ARMED → TAKEOFF → HOVER
    via run(). Tests here need the drone airborne (HOVER) so that operational
    states (TRACKING, RTL, etc.) are reachable transitions.
    """
    orch = Orchestrator(config, bus)
    # Walk the full valid path to HOVER
    for target in (
        DroneState.IDLE,
        DroneState.PREFLIGHT,
        DroneState.ARMED,
        DroneState.TAKEOFF,
        DroneState.HOVER,
    ):
        assert orch.transition_to(target), f"Could not reach {target.name}"

    # Mock all the interfaces so we can test the state machine purely
    flight = AsyncMock()
    flight.is_connected = True
    flight.is_armed = False
    flight.gps_fix_type = 3
    flight.battery_percent = 100

    perception = MagicMock()
    perception.current_bbox = None
    perception.current_depth = None
    perception.smoother = MagicMock()
    perception.smoother.smooth = lambda v: v # Passthrough for tests

    control = MagicMock()
    control.compute.return_value = (VelocityNED(1, 0, 0), 10.0)
    control.set_gimbal = AsyncMock()  # orchestrator awaits this

    voice = AsyncMock()
    brain = AsyncMock()
    camera = MagicMock()
    camera.is_streaming = True

    orch.set_modules(flight, perception, control, voice, brain, camera)
    return orch

@pytest.mark.asyncio
async def test_voice_to_brain_communication(orchestrator, bus):
    """Test 1: Voice command -> Brain -> EventBus -> Orchestrator state change"""
    # Orchestrator fixture is already in HOVER (airborne).

    # We pretend the VoicePipeline already triggered this event
    await bus.publish(Event(
        type=EventType.VOICE_COMMAND_PARSED,
        data={"command": "Follow me"},
        source="voice"
    ))

    # Ensure event queue processes
    await asyncio.sleep(0.01)

    # The brain interface should have been called
    orchestrator.brain.process_command.assert_called_with("Follow me")

    # Now pretend the Brain outputted a TOOL_CALL
    await bus.publish(Event(
        type=EventType.TOOL_CALL_REQUESTED,
        data={"tool": "track_subject", "args": {}},
        source="brain"
    ))

    await asyncio.sleep(0.01)

    # Orchestrator state should now be TRACKING
    assert orchestrator.state == DroneState.TRACKING


@pytest.mark.asyncio
async def test_perception_to_control_to_flight(orchestrator, bus):
    """Test 3: Perception bbox -> Controller -> VelocityNED -> MAVLink"""
    # Orchestrator fixture is in HOVER; transition to TRACKING for this test.
    orchestrator.transition_to(DroneState.TRACKING)

    # Simulate a bounding box from Perception
    bbox = BoundingBox(x_center=160, y_center=160, width=50, height=100, confidence=0.9)
    orchestrator.perception.current_bbox = bbox

    # Run one tick of the orchestrator state update
    await orchestrator._update_state()

    # Controller compute should have been called
    orchestrator.control.compute.assert_called_with(
        bbox=bbox,
        depth_map=None,
        mode="tracking"
    )

    # Flight controller should have received set_velocity_ned
    orchestrator.flight.set_velocity_ned.assert_called_once()

    # Gimbal controller should have received set_gimbal
    orchestrator.control.set_gimbal.assert_called_once_with(10.0)


@pytest.mark.asyncio
async def test_safety_battery_critical(orchestrator, bus):
    """Test 4: Safety event -> EventBus -> Orchestrator forces RTL"""
    # Orchestrator fixture is already in HOVER (airborne).

    # Trigger battery critical
    await bus.publish(Event(
        type=EventType.BATTERY_CRITICAL,
        data={"percent": 5, "action": "land"},
        source="safety"
    ))

    await asyncio.sleep(0.01)

    # Orchestrator should transition to RTL
    assert orchestrator.state == DroneState.RTL
    orchestrator.voice.speak.assert_called_with("Battery critical. Returning home now.")

@pytest.mark.asyncio
async def test_event_isolation(bus):
    """Test 6: Verify event bus publish/subscribe isolation"""
    mock_handler_1 = AsyncMock()
    mock_handler_2 = AsyncMock()
    
    bus.subscribe(EventType.SUBJECT_DETECTED, mock_handler_1)
    bus.subscribe(EventType.HEARTBEAT_LOST, mock_handler_2)
    
    # Publish only SUBJECT_DETECTED
    await bus.publish(Event(
        type=EventType.SUBJECT_DETECTED,
        data={"bbox": "fake"},
        source="perception"
    ))
    
    await asyncio.sleep(0.01)
    
    # Handler 1 should be called, Handler 2 should NOT
    mock_handler_1.assert_called_once()
    mock_handler_2.assert_not_called()
