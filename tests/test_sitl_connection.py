"""
GarudaOne — SITL Connection Integration Test
=============================================
Tests that the MAVLink bridge correctly connects to PX4 SITL (if running)
or falls back to stub telemetry.

This test is integration-level — it actually attempts a MAVSDK connection.
Run with: python -m pytest tests/test_sitl_connection.py -v

Requirements:
    - mavsdk installed: pip install mavsdk
    - PX4 SITL running for "connected" tests (optional — most tests use stub)

Note: Tests that exercise the MAVSDK connection path are marked with
@pytest.mark.sitl and are skipped by default. Run them with:
    pytest tests/test_sitl_connection.py -v -m sitl
"""

import asyncio
import sys
from unittest.mock import patch, MagicMock

import pytest

from garuda.core.config import Config
from garuda.core.events import EventBus
from garuda.flight.mavlink_bridge import MAVLinkBridge


@pytest.fixture
def sim_config():
    """Config in simulation mode."""
    import os
    os.environ["GARUDA_MODE"] = "simulation"
    cfg = Config()
    # Force a very short SITL connection timeout so tests don't hang
    if "px4_sitl" not in cfg._data:
        cfg._data["px4_sitl"] = {}
    cfg._data["px4_sitl"]["connection_timeout_s"] = 1.0
    cfg._data["px4_sitl"]["enabled"] = True
    return cfg


@pytest.fixture
def event_bus():
    return EventBus()


# ── Config tests (no MAVSDK involved) ──────────────────────────────


@pytest.mark.asyncio
async def test_sim_config_loads(sim_config):
    """Test that simulation.yaml config is loaded correctly."""
    assert sim_config.is_simulation, "Should be in simulation mode"

    sitl_enabled = sim_config.get("px4_sitl.enabled", True)
    assert isinstance(sitl_enabled, bool)

    connection_url = sim_config.get("px4_sitl.connection_url", "")
    assert "udp" in connection_url, f"Expected UDP URL, got: {connection_url}"


@pytest.mark.asyncio
async def test_home_position_config(sim_config):
    """Test that home position is configured for Bangalore."""
    lat = sim_config.get("simulation.home_position.latitude_deg")
    lon = sim_config.get("simulation.home_position.longitude_deg")

    assert lat is not None, "Home latitude not configured"
    assert lon is not None, "Home longitude not configured"
    assert 12.0 < lat < 13.0, f"Expected Bangalore latitude (~12.97), got {lat}"
    assert 77.0 < lon < 78.0, f"Expected Bangalore longitude (~77.59), got {lon}"


@pytest.mark.asyncio
async def test_mavlink_bridge_initialization(sim_config, event_bus):
    """Test that MAVLink bridge initializes correctly in simulation mode."""
    bridge = MAVLinkBridge(sim_config, event_bus)
    assert bridge is not None
    assert bridge.connection_mode in ("hardware", "sitl", "stub")


# ── Stub fallback tests (mock MAVSDK import to force stub) ──────────
# These tests patch out MAVSDK so the bridge falls back to stub mode
# without actually trying to connect to a MAVSDK subprocess.


@pytest.mark.asyncio
async def test_stub_fallback_on_import_error(sim_config, event_bus):
    """Test that bridge falls back to stub when MAVSDK is not installed."""
    with patch.dict("sys.modules", {"mavsdk": None}):
        bridge = MAVLinkBridge(sim_config, event_bus)
        result = await bridge.connect()

        assert result is True
        assert bridge.is_connected is True
        assert bridge.connection_mode == "stub"

        # Give telemetry task a moment
        await asyncio.sleep(0.3)

        # Stub telemetry should be initialized
        assert bridge.battery_percent > 0
        assert bridge.gps_fix_type >= 0

        # Clean up
        bridge._is_connected = False
        await asyncio.sleep(0.1)


@pytest.mark.asyncio
async def test_stub_takeoff_altitude_tracking(sim_config, event_bus):
    """Test that takeoff sets target altitude in stub mode."""
    with patch.dict("sys.modules", {"mavsdk": None}):
        bridge = MAVLinkBridge(sim_config, event_bus)
        await bridge.connect()

        target_alt = 5.0
        await bridge.takeoff(target_alt)
        assert bridge._target_altitude == target_alt

        bridge._is_connected = False
        await asyncio.sleep(0.1)


@pytest.mark.asyncio
async def test_stub_velocity_command(sim_config, event_bus):
    """Test that velocity commands don't crash in stub mode."""
    from garuda.utils.transforms import VelocityNED

    with patch.dict("sys.modules", {"mavsdk": None}):
        bridge = MAVLinkBridge(sim_config, event_bus)
        await bridge.connect()

        velocity = VelocityNED(north=1.0, east=0.5, down=0.0)
        await bridge.set_velocity_ned(velocity)
        await bridge.hold_position()

        bridge._is_connected = False
        await asyncio.sleep(0.1)


@pytest.mark.asyncio
async def test_stub_landing_sets_landed(sim_config, event_bus):
    """Test that landing sets is_landed=True after simulated delay."""
    with patch.dict("sys.modules", {"mavsdk": None}):
        bridge = MAVLinkBridge(sim_config, event_bus)
        await bridge.connect()

        await bridge.takeoff(3.0)
        assert bridge._is_landed is False, "Should be airborne after takeoff"

        await bridge.land()

        # Simulated landing takes ~3 seconds
        await asyncio.sleep(3.5)
        assert bridge._is_landed is True, "Should be landed after landing"

        bridge._is_connected = False
        await asyncio.sleep(0.1)


# ── Real SITL tests (only run when PX4 SITL is actually running) ────


@pytest.mark.sitl
@pytest.mark.asyncio
async def test_real_sitl_connection(sim_config, event_bus):
    """Test connection to a real PX4 SITL instance.

    Requires PX4 SITL running: make sitl
    Skip with: pytest -m "not sitl"
    """
    bridge = MAVLinkBridge(sim_config, event_bus)
    result = await bridge.connect()

    if bridge.connection_mode == "stub":
        pytest.skip("PX4 SITL not running — skipping real connection test")
        return

    assert result is True
    assert bridge.connection_mode == "sitl"
    assert bridge.is_connected is True

    bridge._is_connected = False
    await asyncio.sleep(0.1)


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s", "-m", "not sitl"])
