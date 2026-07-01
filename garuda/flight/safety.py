"""
GarudaOne DroneOS — Safety Watchdog
====================================
Monitors critical systems and triggers failsafes.

Safety layers (defense in depth):
  1. This watchdog (software, runs on RPi5)
  2. PX4 internal failsafes (firmware, runs on MicoAir H743)
  3. RC transmitter kill switch (hardware, on Radiomaster ELRS)

If ALL three fail, physics handles it (the drone falls and the props stop).
"""

import asyncio
import time

from garuda.core.config import Config
from garuda.core.events import Event, EventBus, EventType
from garuda.utils.logger import get_logger

log = get_logger("safety")


class SafetyWatchdog:
    """
    Monitors battery, heartbeat, geofence, and connection status.
    Triggers appropriate failsafe actions when limits are breached.
    """

    def __init__(self, config: Config, event_bus: EventBus):
        self.config = config
        self.bus = event_bus

        # Thresholds from config
        self._heartbeat_timeout = config.get("safety.heartbeat_timeout_s", 3.0)
        self._max_radius = config.get("geofence.max_radius_m", 100.0)
        self._max_altitude = config.get("geofence.max_altitude_m", 30.0)
        self._battery_land = config.get("safety.battery_land_percent", 10)

        # State tracking
        self._last_heartbeat_time = time.time()
        self._running = False

        log.info(
            f"Safety watchdog initialized — "
            f"heartbeat timeout={self._heartbeat_timeout}s, "
            f"geofence radius={self._max_radius}m, "
            f"max alt={self._max_altitude}m"
        )

    async def run(self, flight_bridge) -> None:
        """
        Safety monitoring loop. Runs at 2Hz (every 500ms).
        Checks all safety conditions and triggers failsafes.
        """
        self._running = True
        self._flight = flight_bridge

        log.info("Safety watchdog started (2Hz)")

        while self._running:
            await self._check_heartbeat()
            await self._check_geofence()
            await self._check_battery_emergency()
            await asyncio.sleep(0.5)  # 2Hz

    async def stop(self) -> None:
        """Stop the safety watchdog."""
        self._running = False
        log.info("Safety watchdog stopped")

    def heartbeat_received(self) -> None:
        """Call this whenever a valid heartbeat is received from PX4."""
        self._last_heartbeat_time = time.time()

    async def _check_heartbeat(self) -> None:
        """Check if we've lost contact with the flight controller."""
        if not self._flight or not self._flight.is_connected:
            return

        # Skip heartbeat check in simulation/stub mode (no real PX4)
        # The simulated telemetry loop updates _last_heartbeat itself
        if not hasattr(self._flight, '_drone') or self._flight._drone is None:
            return

        elapsed = time.time() - self._last_heartbeat_time
        if elapsed > self._heartbeat_timeout and self._flight.is_armed:
            log.critical(
                f"HEARTBEAT LOST -- no response for {elapsed:.1f}s "
                f"(timeout: {self._heartbeat_timeout}s)"
            )
            await self.bus.publish(Event(
                type=EventType.HEARTBEAT_LOST,
                data={"elapsed_s": elapsed},
                source="safety",
            ))

    async def _check_geofence(self) -> None:
        """Check if drone has breached the geofence."""
        if not self._flight or not self._flight.is_armed:
            return

        pos = self._flight.position_ned
        distance_from_home = (pos.north**2 + pos.east**2) ** 0.5
        altitude = -pos.down  # NED: positive down

        if distance_from_home > self._max_radius:
            log.warning(
                f"GEOFENCE BREACH — distance: {distance_from_home:.1f}m "
                f"(max: {self._max_radius}m)"
            )
            await self.bus.publish(Event(
                type=EventType.GEOFENCE_BREACH,
                data={"distance_m": distance_from_home, "type": "radius"},
                source="safety",
            ))

        if altitude > self._max_altitude:
            log.warning(
                f"GEOFENCE BREACH — altitude: {altitude:.1f}m "
                f"(max: {self._max_altitude}m)"
            )
            await self.bus.publish(Event(
                type=EventType.GEOFENCE_BREACH,
                data={"altitude_m": altitude, "type": "altitude"},
                source="safety",
            ))

    async def _check_battery_emergency(self) -> None:
        """Force landing if battery is critically low."""
        if not self._flight or not self._flight.is_armed:
            return

        if self._flight.battery_percent <= self._battery_land:
            log.critical(
                f"BATTERY EMERGENCY — {self._flight.battery_percent:.0f}% "
                f"(threshold: {self._battery_land}%)"
            )
            await self.bus.publish(Event(
                type=EventType.BATTERY_CRITICAL,
                data={"percent": self._flight.battery_percent, "action": "land"},
                source="safety",
            ))
