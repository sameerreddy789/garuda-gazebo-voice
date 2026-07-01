"""
Tests for the Mission Orchestrator state machine.
Verifies all valid and invalid state transitions.
"""

import pytest

from garuda.core.config import Config
from garuda.core.events import EventBus
from garuda.core.orchestrator import DroneState, Orchestrator, VALID_TRANSITIONS


@pytest.fixture
def orchestrator():
    """Create an orchestrator with test config."""
    config = Config()
    bus = EventBus()
    orch = Orchestrator(config, bus)
    return orch


class TestStateTransitions:
    """Test that the state machine enforces valid transitions."""

    def test_initial_state_is_boot(self, orchestrator):
        """Orchestrator starts in BOOT state."""
        assert orchestrator.state == DroneState.BOOT

    def test_boot_to_idle(self, orchestrator):
        """BOOT → IDLE is valid (normal startup)."""
        assert orchestrator.transition_to(DroneState.IDLE) is True
        assert orchestrator.state == DroneState.IDLE

    def test_idle_to_preflight(self, orchestrator):
        """IDLE → PREFLIGHT is valid (preparing to fly)."""
        orchestrator.transition_to(DroneState.IDLE)
        assert orchestrator.transition_to(DroneState.PREFLIGHT) is True
        assert orchestrator.state == DroneState.PREFLIGHT

    def test_invalid_boot_to_takeoff(self, orchestrator):
        """BOOT → TAKEOFF is INVALID (can't take off during boot)."""
        assert orchestrator.transition_to(DroneState.TAKEOFF) is False
        assert orchestrator.state == DroneState.BOOT

    def test_invalid_idle_to_tracking(self, orchestrator):
        """IDLE → TRACKING is INVALID (must arm and take off first)."""
        orchestrator.transition_to(DroneState.IDLE)
        assert orchestrator.transition_to(DroneState.TRACKING) is False
        assert orchestrator.state == DroneState.IDLE

    def test_hover_to_tracking(self, orchestrator):
        """HOVER → TRACKING is valid (start following subject)."""
        # Walk through valid path to HOVER
        orchestrator.transition_to(DroneState.IDLE)
        orchestrator.transition_to(DroneState.PREFLIGHT)
        orchestrator.transition_to(DroneState.ARMED)
        orchestrator.transition_to(DroneState.TAKEOFF)
        orchestrator.transition_to(DroneState.HOVER)

        assert orchestrator.transition_to(DroneState.TRACKING) is True
        assert orchestrator.state == DroneState.TRACKING

    def test_tracking_to_orbit(self, orchestrator):
        """TRACKING → ORBIT is valid (switch shot mode)."""
        # Walk through valid path
        orchestrator.transition_to(DroneState.IDLE)
        orchestrator.transition_to(DroneState.PREFLIGHT)
        orchestrator.transition_to(DroneState.ARMED)
        orchestrator.transition_to(DroneState.TAKEOFF)
        orchestrator.transition_to(DroneState.HOVER)
        orchestrator.transition_to(DroneState.TRACKING)

        assert orchestrator.transition_to(DroneState.ORBIT) is True
        assert orchestrator.state == DroneState.ORBIT

    def test_any_state_to_emergency(self, orchestrator):
        """Any state → EMERGENCY is ALWAYS valid (safety critical)."""
        for start_state in DroneState:
            if start_state == DroneState.EMERGENCY:
                continue
            orch = Orchestrator(Config(), EventBus())
            orch.state = start_state  # Force state for testing
            assert orch.transition_to(DroneState.EMERGENCY) is True
            assert orch.state == DroneState.EMERGENCY

    def test_rtl_to_landing(self, orchestrator):
        """RTL → LANDING is valid (arrived home, now land)."""
        orchestrator.transition_to(DroneState.IDLE)
        orchestrator.transition_to(DroneState.PREFLIGHT)
        orchestrator.transition_to(DroneState.ARMED)
        orchestrator.transition_to(DroneState.TAKEOFF)
        orchestrator.transition_to(DroneState.HOVER)
        orchestrator.transition_to(DroneState.RTL)

        assert orchestrator.transition_to(DroneState.LANDING) is True

    def test_landing_to_disarmed(self, orchestrator):
        """LANDING → DISARMED is valid (touched down, safe)."""
        orchestrator.transition_to(DroneState.IDLE)
        orchestrator.transition_to(DroneState.PREFLIGHT)
        orchestrator.transition_to(DroneState.ARMED)
        orchestrator.transition_to(DroneState.TAKEOFF)
        orchestrator.transition_to(DroneState.HOVER)
        orchestrator.transition_to(DroneState.RTL)
        orchestrator.transition_to(DroneState.LANDING)

        assert orchestrator.transition_to(DroneState.DISARMED) is True

    def test_all_valid_transitions_match_definition(self):
        """Verify every defined valid transition actually works."""
        for source_state, valid_targets in VALID_TRANSITIONS.items():
            for target_state in valid_targets:
                orch = Orchestrator(Config(), EventBus())
                orch.state = source_state
                result = orch.transition_to(target_state)
                assert result is True, (
                    f"Expected {source_state.name} → {target_state.name} "
                    f"to be valid, but it was rejected"
                )
