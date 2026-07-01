"""
GarudaOne DroneOS — MAVLink Bridge (PX4 OFFBOARD Mode)
=======================================================
Handles all communication with the PX4 flight controller via MAVSDK-Python.

How it works:
  The RPi5 connects to the MicoAir H743 via UART serial.
  It sends velocity setpoints (how fast to move in each direction)
  and PX4 handles the low-level motor control at 400Hz.

  PX4's OFFBOARD mode requires continuous setpoints — if we stop
  sending for more than a few seconds, PX4 automatically triggers
  a safety action (RTL or land). This is a feature, not a bug.

Key API methods:
  connect()           → Connect to PX4 via serial
  arm() / disarm()    → Motor arming
  takeoff(altitude)   → Automated takeoff
  set_velocity_ned()  → Send velocity commands (the main control method)
  land()              → Automated landing
  return_to_launch()  → RTL mode
  emergency_stop()    → Immediate motor kill
"""

import asyncio
from typing import Optional, Any

from garuda.core.config import Config
from garuda.core.events import Event, EventBus, EventType
from garuda.utils.logger import get_logger
from garuda.utils.transforms import (
    PositionGPS, PositionNED, VelocityNED, AttitudeEuler
)

log = get_logger("flight")


class MAVLinkBridge:
    """
    PX4 flight controller interface via MAVSDK-Python.

    In simulation mode, all commands are logged but not sent.
    In hardware mode, connects to the real FC via UART.
    """

    def __init__(self, config: Config, event_bus: EventBus):
        self.config = config
        self.bus = event_bus

        # Connection settings
        self._serial_port = config.get(
            "flight_controller.serial.port", "/dev/ttyAMA0"
        )
        self._baud_rate = config.get(
            "flight_controller.serial.baud_rate", 921600
        )

        # State
        self._drone: Optional[Any] = None  # MAVSDK System instance
        self._is_connected = False
        self._is_armed = False
        self._is_offboard = False
        self._is_landed = True
        self._connection_mode = "hardware"  # "hardware", "sitl", or "stub"

        # Telemetry cache
        self._position_gps = PositionGPS()
        self._position_ned = PositionNED()
        self._attitude = AttitudeEuler()
        self._home_position = PositionGPS()
        self._battery_percent = 100.0
        self._battery_voltage = 12.6
        self._gps_fix_type = 0
        self._gps_satellites = 0
        self._target_altitude = 3.0

        # Heartbeat
        self._last_heartbeat = 0.0
        self._heartbeat_timeout = config.get("safety.heartbeat_timeout_s", 3.0)

        log.info(
            f"MAVLink bridge initialized — "
            f"port={self._serial_port}, baud={self._baud_rate}"
        )

    # ── Properties ────────────────────────────────────────────────────────

    @property
    def is_connected(self) -> bool:
        return self._is_connected

    @property
    def is_armed(self) -> bool:
        return self._is_armed

    @property
    def is_offboard(self) -> bool:
        return self._is_offboard

    @property
    def is_landed(self) -> bool:
        return self._is_landed

    @property
    def is_at_target_altitude(self) -> bool:
        """Check if drone has reached takeoff altitude (within 0.5m)."""
        current_alt = -self._position_ned.down  # NED: positive down
        return abs(current_alt - self._target_altitude) < 0.5

    @property
    def is_at_home(self) -> bool:
        """Check if drone is within 2m of home position."""
        return (
            abs(self._position_ned.north) < 2.0
            and abs(self._position_ned.east) < 2.0
        )

    @property
    def position_gps(self) -> PositionGPS:
        return self._position_gps

    @property
    def position_ned(self) -> PositionNED:
        return self._position_ned

    @property
    def attitude(self) -> AttitudeEuler:
        return self._attitude

    @property
    def battery_percent(self) -> float:
        return self._battery_percent

    @property
    def gps_fix_type(self) -> int:
        return self._gps_fix_type

    # ── Connection ────────────────────────────────────────────────────────

    @property
    def connection_mode(self) -> str:
        """Current connection mode: 'hardware', 'sitl', or 'stub'."""
        return self._connection_mode

    async def connect(self) -> bool:
        """
        Connect to PX4 flight controller via MAVSDK.

        Connection strategy (in order):
          1. **Hardware mode** (GARUDA_MODE=hardware):
             Connects via UART serial to MicoAir H743 on /dev/ttyAMA0.
             If this fails, falls back to stub telemetry.

          2. **Simulation mode** (GARUDA_MODE=simulation):
             a) If px4_sitl.enabled is true (from simulation.yaml):
                Connects to PX4 SITL via UDP (default udp://localhost:14540).
                This gives REAL flight dynamics, sensor fusion, OFFBOARD mode.
             b) If PX4 SITL doesn't respond within timeout:
                Falls back to stub telemetry (fake GPS, battery, attitude).
             c) If px4_sitl.enabled is false:
                Goes directly to stub telemetry.

        In stub mode, the full system still boots and runs — all state
        machine transitions work, all event flows work. Only the actual
        motor commands are logged but not sent.
        """
        # Determine connection mode
        if self.config.is_simulation:
            sitl_enabled = self.config.get("px4_sitl.enabled", True)
            if sitl_enabled:
                self._connection_mode = "sitl"
            else:
                self._connection_mode = "stub"
                log.info("SITL disabled in config — using stub telemetry")
                self._is_connected = True
                asyncio.create_task(self._run_simulated_telemetry())
                return True
        else:
            self._connection_mode = "hardware"

        try:
            # Try importing MAVSDK — may not be installed on dev machines
            from mavsdk import System  # type: ignore

            self._drone = System()

            # Build connection URL from config
            if self._connection_mode == "sitl":
                connection_url = self.config.get(
                    "px4_sitl.connection_url", "udp://localhost:14540"
                )
            else:
                # Real hardware — UART serial
                connection_url = (
                    f"serial://{self._serial_port}:{self._baud_rate}"
                )

            # Connection timeout from config (SITL needs more time to boot)
            timeout_s = self.config.get(
                "px4_sitl.connection_timeout_s",
                10.0 if self._connection_mode == "hardware" else 15.0,
            )

            log.info(f"Connecting to PX4: {connection_url}")
            log.info(f"Connection mode: {self._connection_mode}")
            log.info(f"Heartbeat timeout: {timeout_s}s")

            await self._drone.connect(system_address=connection_url)

            # Wait for connection WITH TIMEOUT
            log.info(f"Waiting for drone heartbeat ({timeout_s}s timeout)...")
            try:
                await asyncio.wait_for(
                    self._wait_for_heartbeat(), timeout=timeout_s
                )
                log.info("[OK] Connected to PX4 flight controller")
                log.info(f"  Mode: {self._connection_mode}")
                # Start real telemetry subscriptions
                asyncio.create_task(self._subscribe_telemetry())
            except asyncio.TimeoutError:
                log.warning(
                    f"PX4 heartbeat timeout ({timeout_s}s) — "
                    f"no {'SITL' if self._connection_mode == 'sitl' else 'hardware FC'} running. "
                    "Falling back to simulated telemetry."
                )
                self._drone = None  # Release the MAVSDK System
                self._connection_mode = "stub"
                self._is_connected = True
                asyncio.create_task(self._run_simulated_telemetry())

            return True

        except ImportError:
            log.warning(
                "MAVSDK not installed -- running in stub mode. "
                "Install with: pip install mavsdk"
            )
            self._connection_mode = "stub"
            self._is_connected = True  # Pretend for dev
            asyncio.create_task(self._run_simulated_telemetry())
            return True

        except Exception as e:
            log.error(f"Failed to connect to PX4: {e}")
            log.info("Falling back to simulated telemetry.")
            self._connection_mode = "stub"
            self._is_connected = True
            asyncio.create_task(self._run_simulated_telemetry())
            return True

    async def _wait_for_heartbeat(self) -> None:
        """Wait until MAVSDK reports a connected state."""
        async for state in self._drone.core.connection_state():
            if state.is_connected:
                self._is_connected = True
                return

    async def _run_simulated_telemetry(self) -> None:
        """
        Generate fake telemetry data when no real PX4 is connected.

        Simulates realistic flight state transitions:
          - Landed on ground with GPS 3D fix
          - After arm + takeoff: gradually climbs to target altitude
          - Battery drains over time
          - Attitude wobbles like real flight (wind)
          - Position drifts slightly

        This lets the full system boot and the entire state machine
        work without any hardware or PX4 SITL.
        """
        import time as _time
        import math

        log.info("Simulated telemetry started (fake GPS, battery, attitude)")
        log.info("  This simulates a real drone — takeoff will 'work'")

        start_time = _time.time()

        # Read simulation config for home position
        home_lat = self.config.get(
            "simulation.home_position.latitude_deg", 12.9716
        )
        home_lon = self.config.get(
            "simulation.home_position.longitude_deg", 77.5946
        )
        home_alt_msl = self.config.get(
            "simulation.home_position.altitude_m", 920.0
        )

        # Drain rate from config
        drain_rate = self.config.get(
            "simulation.battery.drain_rate_percent_per_second", 0.033
        )

        # GPS noise from config
        gps_noise = self.config.get("simulation.gps.noise_meters", 0.5)

        self._home_position = PositionGPS(
            latitude_deg=home_lat,
            longitude_deg=home_lon,
            altitude_m=home_alt_msl,
        )
        self._position_gps = PositionGPS(
            latitude_deg=home_lat,
            longitude_deg=home_lon,
            altitude_m=home_alt_msl,
        )
        # NED position: relative to home. NED down is positive.
        self._position_ned = PositionNED()
        self._gps_fix_type = 3  # 3D fix
        self._gps_satellites = 12
        self._battery_percent = self.config.get(
            "simulation.battery.initial_percent", 100.0
        )
        self._battery_voltage = 12.6
        self._is_landed = True
        self._last_heartbeat = _time.time()

        # Simulated altitude tracking (for takeoff detection)
        _sim_altitude = 0.0  # Current altitude above ground (meters, negative in NED)
        _sim_climb_rate = 0.0  # m/s (positive = going up)

        while self._is_connected:
            elapsed = _time.time() - start_time

            # ── Simulate altitude changes based on state ──────────────
            if not self._is_landed and self._is_armed:
                if _sim_altitude < self._target_altitude:
                    # Climbing to target altitude at ~2 m/s
                    _sim_climb_rate = 2.0
                    _sim_altitude = min(
                        _sim_altitude + _sim_climb_rate * 0.5,  # 0.5s tick
                        self._target_altitude,
                    )
                else:
                    # Hovered at target — stay level
                    _sim_climb_rate = 0.0

                # Update NED position (negative down = positive altitude)
                self._position_ned = PositionNED(
                    north=math.sin(elapsed * 0.1) * 0.2,  # Tiny drift
                    east=math.cos(elapsed * 0.1) * 0.2,
                    down=-_sim_altitude,  # NED: down is positive
                )

                # Update GPS with simulated altitude
                self._position_gps = PositionGPS(
                    latitude_deg=home_lat + (math.sin(elapsed * 0.05) * gps_noise * 1e-5),
                    longitude_deg=home_lon + (math.cos(elapsed * 0.05) * gps_noise * 1e-5),
                    altitude_m=_sim_altitude,
                )

            # ── Battery drain ────────────────────────────────────────
            self._battery_percent = max(
                0.0, self._battery_percent - drain_rate * 0.5
            )
            self._battery_voltage = 9.9 + (self._battery_percent / 100.0) * 2.7

            # ── Attitude wobble (wind simulation) ─────────────────────
            wind_intensity = 0.5 if not self._is_landed else 0.0
            self._attitude = AttitudeEuler(
                roll_deg=math.sin(elapsed * 0.5) * (2.0 * wind_intensity),
                pitch_deg=math.cos(elapsed * 0.7) * (1.5 * wind_intensity),
                yaw_deg=(elapsed * 5.0) % 360.0 - 180.0,
            )

            # ── Heartbeat ────────────────────────────────────────────
            self._last_heartbeat = _time.time()

            # ── Publish events ───────────────────────────────────────
            await self.bus.publish_nowait(Event(
                type=EventType.BATTERY_UPDATE,
                data={
                    "percent": self._battery_percent,
                    "voltage": self._battery_voltage,
                },
                source="flight_sim",
            ))

            await self.bus.publish_nowait(Event(
                type=EventType.POSITION_UPDATE,
                data={"position": self._position_gps},
                source="flight_sim",
            ))

            await asyncio.sleep(0.5)  # 2Hz telemetry updates

    # ── Arming ────────────────────────────────────────────────────────────

    async def arm(self) -> bool:
        """Arm the motors. Returns True on success."""
        try:
            if self._drone:
                await self._drone.action.arm()
            self._is_armed = True
            # In stub mode, we're still on the ground until takeoff
            if self._connection_mode != "stub":
                self._is_landed = False
            log.info("✓ Motors armed")
            await self.bus.publish(Event(
                type=EventType.ARMED, source="flight"
            ))
            return True
        except Exception as e:
            log.error(f"Failed to arm: {e}")
            return False

    async def disarm(self) -> bool:
        """Disarm the motors. Returns True on success."""
        try:
            if self._drone:
                await self._drone.action.disarm()
            self._is_armed = False
            log.info("✓ Motors disarmed")
            await self.bus.publish(Event(
                type=EventType.DISARMED, source="flight"
            ))
            return True
        except Exception as e:
            log.error(f"Failed to disarm: {e}")
            return False

    # ── Flight Commands ───────────────────────────────────────────────────

    async def takeoff(self, altitude_m: float = 3.0) -> bool:
        """
        Take off to the specified altitude.

        In hardware/SITL mode: PX4 handles the actual ascent.
        In stub mode: the simulated telemetry will gradually climb to
        this altitude so the state machine detects takeoff completion.
        """
        self._target_altitude = altitude_m
        try:
            if self._drone:
                await self._drone.action.set_takeoff_altitude(altitude_m)
                await self._drone.action.takeoff()
            else:
                # Stub mode — signal that we're airborne
                self._is_landed = False
            log.info(f"Taking off to {altitude_m}m")
            return True
        except Exception as e:
            log.error(f"Takeoff failed: {e}")
            return False

    async def land(self) -> bool:
        """Command the drone to land at current position."""
        try:
            if self._drone:
                await self._drone.action.land()
            else:
                # Stub mode — simulate landing after a brief delay
                asyncio.create_task(self._simulate_landing())
            log.info("Landing...")
            return True
        except Exception as e:
            log.error(f"Land failed: {e}")
            return False

    async def _simulate_landing(self) -> None:
        """Simulate landing in stub mode (takes ~3 seconds)."""
        await asyncio.sleep(3.0)
        self._is_landed = True
        self._is_armed = False
        self._is_offboard = False
        log.info("Simulated landing complete — on ground")

    async def return_to_launch(self) -> bool:
        """Fly back to the takeoff position and land."""
        try:
            if self._drone:
                await self._drone.action.return_to_launch()
            log.info("Returning to launch")
            return True
        except Exception as e:
            log.error(f"RTL failed: {e}")
            return False

    async def set_velocity_ned(self, velocity: VelocityNED) -> None:
        """
        Send a velocity setpoint in NED frame.

        This is the PRIMARY control method — called every tick (10Hz+)
        during tracking, orbit, chase, and reveal modes.

        PX4 OFFBOARD mode requires continuous setpoints. If we stop
        sending, PX4 triggers its failsafe (RTL or land).
        """
        # Clamp velocity to max speed
        max_speed = self.config.get("flight.max_speed_ms", 10.0)
        velocity = velocity.clamp(max_speed)

        try:
            if self._drone and self._is_offboard:
                from mavsdk.offboard import VelocityNedYaw  # type: ignore

                await self._drone.offboard.set_velocity_ned(
                    VelocityNedYaw(
                        velocity.north,
                        velocity.east,
                        velocity.down,
                        self._attitude.yaw_deg,  # Hold current yaw
                    )
                )
        except ImportError:
            pass  # Stub mode
        except Exception as e:
            log.error(f"Set velocity failed: {e}")

    async def start_offboard(self) -> bool:
        """
        Enter PX4 OFFBOARD mode.

        Must send at least one setpoint before starting OFFBOARD,
        otherwise PX4 will reject it.
        """
        try:
            if self._drone:
                from mavsdk.offboard import VelocityNedYaw  # type: ignore

                # Send initial setpoint (hover in place)
                await self._drone.offboard.set_velocity_ned(
                    VelocityNedYaw(0.0, 0.0, 0.0, 0.0)
                )
                await self._drone.offboard.start()

            self._is_offboard = True
            log.info("✓ OFFBOARD mode started")
            await self.bus.publish(Event(
                type=EventType.OFFBOARD_STARTED, source="flight"
            ))
            return True

        except ImportError:
            self._is_offboard = True  # Stub
            return True
        except Exception as e:
            log.error(f"Failed to start OFFBOARD: {e}")
            return False

    async def hold_position(self) -> None:
        """Send zero velocity to hold current position."""
        await self.set_velocity_ned(VelocityNED(0.0, 0.0, 0.0))

    async def emergency_stop(self) -> None:
        """
        EMERGENCY: Kill all motors immediately.

        This is the nuclear option — use only when something is
        seriously wrong. The drone WILL fall from the sky.
        """
        log.critical("!!! EMERGENCY STOP — KILLING MOTORS !!!")
        try:
            if self._drone:
                await self._drone.action.kill()
            self._is_armed = False
            self._is_offboard = False
        except Exception:
            pass  # Best effort

        await self.bus.publish(Event(
            type=EventType.EMERGENCY_STOP, source="flight"
        ))

    # ── Telemetry ─────────────────────────────────────────────────────────

    async def _subscribe_telemetry(self) -> None:
        """Subscribe to PX4 telemetry streams."""
        if not self._drone:
            return

        try:
            # Position
            asyncio.create_task(self._stream_position())
            # Attitude
            asyncio.create_task(self._stream_attitude())
            # Battery
            asyncio.create_task(self._stream_battery())
            # GPS info
            asyncio.create_task(self._stream_gps_info())
            # Landed state
            asyncio.create_task(self._stream_landed_state())

            log.info("Telemetry subscriptions started")
        except Exception as e:
            log.error(f"Telemetry subscription failed: {e}")

    async def _stream_position(self) -> None:
        """Stream GPS position updates."""
        if self._drone is None:
            return
        try:
            async for position in self._drone.telemetry.position():
                self._position_gps = PositionGPS(
                    latitude_deg=position.latitude_deg,
                    longitude_deg=position.longitude_deg,
                    altitude_m=position.relative_altitude_m,
                )
                await self.bus.publish_nowait(Event(
                    type=EventType.POSITION_UPDATE,
                    data={"position": self._position_gps},
                    source="flight",
                ))
        except Exception:
            pass

    async def _stream_attitude(self) -> None:
        """Stream attitude (Euler angles) updates."""
        if self._drone is None:
            return
        try:
            async for attitude in self._drone.telemetry.attitude_euler():
                self._attitude = AttitudeEuler(
                    roll_deg=attitude.roll_deg,
                    pitch_deg=attitude.pitch_deg,
                    yaw_deg=attitude.yaw_deg,
                )
        except Exception:
            pass

    async def _stream_battery(self) -> None:
        """Stream battery status updates."""
        if self._drone is None:
            return
        try:
            async for battery in self._drone.telemetry.battery():
                self._battery_percent = battery.remaining_percent * 100
                self._battery_voltage = battery.voltage_v

                await self.bus.publish_nowait(Event(
                    type=EventType.BATTERY_UPDATE,
                    data={
                        "percent": self._battery_percent,
                        "voltage": self._battery_voltage,
                    },
                    source="flight",
                ))

                # Check battery thresholds
                warn = self.config.get("safety.battery_warn_percent", 30)
                crit = self.config.get("safety.battery_critical_percent", 15)

                if self._battery_percent <= crit:
                    await self.bus.publish(Event(
                        type=EventType.BATTERY_CRITICAL,
                        data={"percent": self._battery_percent},
                        source="flight",
                    ))
                elif self._battery_percent <= warn:
                    await self.bus.publish(Event(
                        type=EventType.BATTERY_WARNING,
                        data={"percent": self._battery_percent},
                        source="flight",
                    ))
        except Exception:
            pass

    async def _stream_gps_info(self) -> None:
        """Stream GPS fix status."""
        if self._drone is None:
            return
        try:
            async for gps in self._drone.telemetry.gps_info():
                self._gps_fix_type = gps.fix_type
                self._gps_satellites = gps.num_satellites
        except Exception:
            pass

    async def _stream_landed_state(self) -> None:
        """Stream landed state."""
        if self._drone is None:
            return
        try:
            from mavsdk.telemetry import LandedState  # type: ignore
            async for state in self._drone.telemetry.landed_state():
                self._is_landed = (state == LandedState.ON_GROUND)
        except Exception:
            pass
