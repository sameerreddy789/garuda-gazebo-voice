"""
GarudaOne DroneOS — Mission Orchestrator
=========================================
The central state machine that controls the drone's entire lifecycle.

Think of this as the "director" of the drone — it decides what the drone
should be doing at any moment based on events from all other modules.

State Transitions:
  BOOT → IDLE → PREFLIGHT → ARMED → TAKEOFF → HOVER
  HOVER ↔ TRACKING ↔ ORBIT ↔ CHASE ↔ REVEAL
  Any state → RTL → LANDING → DISARMED
  Any state → EMERGENCY (immediate motor kill)
"""

import asyncio
from enum import Enum, auto

from garuda.core.config import Config
from garuda.core.events import Event, EventBus, EventType
from garuda.utils.logger import get_logger
from garuda.utils.profiler import profiler

log = get_logger("orchestrator")


class DroneState(Enum):
    """All possible drone states."""
    BOOT = auto()          # System initializing
    IDLE = auto()          # All modules ready, waiting for command
    PREFLIGHT = auto()     # Running pre-flight checks
    ARMED = auto()         # Motors armed, ready for takeoff
    TAKEOFF = auto()       # Ascending to target altitude
    HOVER = auto()         # Holding position, no active mission
    TRACKING = auto()      # Following a subject (generic follow)
    ORBIT = auto()         # Orbiting around subject
    CHASE = auto()         # Chase mode (behind subject)
    REVEAL = auto()        # Reveal shot (pulling back + rising)
    RTL = auto()           # Return to launch
    LANDING = auto()       # Descending to ground
    DISARMED = auto()      # Motors disarmed, safe
    EMERGENCY = auto()     # Emergency stop, motors killed


# Valid state transitions — prevents illegal jumps
VALID_TRANSITIONS: dict[DroneState, set[DroneState]] = {
    DroneState.BOOT:       {DroneState.IDLE},
    DroneState.IDLE:       {DroneState.PREFLIGHT, DroneState.DISARMED},
    DroneState.PREFLIGHT:  {DroneState.ARMED, DroneState.IDLE},
    DroneState.ARMED:      {DroneState.TAKEOFF, DroneState.DISARMED},
    DroneState.TAKEOFF:    {DroneState.HOVER},
    DroneState.HOVER:      {DroneState.TRACKING, DroneState.ORBIT, DroneState.CHASE,
                            DroneState.REVEAL, DroneState.RTL, DroneState.LANDING},
    DroneState.TRACKING:   {DroneState.HOVER, DroneState.ORBIT, DroneState.CHASE,
                            DroneState.REVEAL, DroneState.RTL},
    DroneState.ORBIT:      {DroneState.HOVER, DroneState.TRACKING, DroneState.CHASE,
                            DroneState.REVEAL, DroneState.RTL},
    DroneState.CHASE:      {DroneState.HOVER, DroneState.TRACKING, DroneState.ORBIT,
                            DroneState.REVEAL, DroneState.RTL},
    DroneState.REVEAL:     {DroneState.HOVER, DroneState.TRACKING, DroneState.RTL},
    DroneState.RTL:        {DroneState.LANDING, DroneState.HOVER},
    DroneState.LANDING:    {DroneState.DISARMED},
    DroneState.DISARMED:   {DroneState.IDLE},
    DroneState.EMERGENCY:  {DroneState.DISARMED},
}

# Every state can transition to EMERGENCY
for state in DroneState:
    if state != DroneState.EMERGENCY:
        VALID_TRANSITIONS[state].add(DroneState.EMERGENCY)


class Orchestrator:
    """
    The mission orchestrator — controls drone lifecycle and state transitions.

    This is the main loop that runs at 50Hz (configurable). Each tick:
    1. Process any queued events
    2. Run the current state's update logic
    3. Check safety conditions
    """

    def __init__(self, config: Config, event_bus: EventBus):
        self.config = config
        self.bus = event_bus
        self.state = DroneState.BOOT
        self._running = False
        self._loop_hz = config.get("control.main_loop_hz", 50)

        # Module references (set during initialization)
        self.flight = None
        self.perception = None
        self.control = None
        self.voice = None
        self.brain = None
        self.camera = None

        # Subscribe to events
        self.bus.subscribe(EventType.VOICE_COMMAND_PARSED, self._on_voice_command)
        self.bus.subscribe(EventType.TOOL_CALL_REQUESTED, self._on_tool_call)
        self.bus.subscribe(EventType.BATTERY_CRITICAL, self._on_battery_critical)
        self.bus.subscribe(EventType.HEARTBEAT_LOST, self._on_heartbeat_lost)
        self.bus.subscribe(EventType.SUBJECT_LOST, self._on_subject_lost)
        self.bus.subscribe(EventType.EMERGENCY_STOP, self._on_emergency)

        log.info("Orchestrator initialized")

    def set_modules(self, flight, perception, control, voice, brain, camera):
        """Register all module references after initialization."""
        self.flight = flight
        self.perception = perception
        self.control = control
        self.voice = voice
        self.brain = brain
        self.camera = camera
        log.info("All modules registered with orchestrator")

    # ── State Machine ─────────────────────────────────────────────────────

    def transition_to(self, new_state: DroneState) -> bool:
        """
        Attempt a state transition. Returns True if successful.

        Only allows transitions defined in VALID_TRANSITIONS to prevent
        dangerous state jumps (e.g., BOOT → TAKEOFF).
        """
        if new_state in VALID_TRANSITIONS.get(self.state, set()):
            old_state = self.state
            self.state = new_state
            log.info(f"State: {old_state.name} → {new_state.name}")
            return True
        else:
            log.warning(
                f"Invalid transition: {self.state.name} → {new_state.name}"
            )
            return False

    # ── Main Loop ─────────────────────────────────────────────────────────

    async def run(self) -> None:
        """
        Main orchestration loop. Runs at configured Hz until shutdown.
        This is the heartbeat of the entire drone.
        """
        self._running = True
        loop_period = 1.0 / self._loop_hz

        log.info(f"Orchestrator main loop starting at {self._loop_hz}Hz")

        # Boot → Idle
        self.transition_to(DroneState.IDLE)
        await self.bus.publish(Event(
            type=EventType.SYSTEM_READY, source="orchestrator"
        ))

        while self._running:
            loop_start = asyncio.get_event_loop().time()

            with profiler.measure("orchestrator"):
                # 1. Process queued events
                await self.bus.process_queue()

                # 2. Run state-specific update
                await self._update_state()

            # 3. Sleep for remainder of loop period
            elapsed = asyncio.get_event_loop().time() - loop_start
            sleep_time = max(0, loop_period - elapsed)
            if sleep_time > 0:
                await asyncio.sleep(sleep_time)

        log.info("Orchestrator main loop stopped")

    async def stop(self) -> None:
        """Gracefully shut down the orchestrator."""
        log.info("Orchestrator shutting down...")
        self._running = False
        await self.bus.publish(Event(
            type=EventType.SYSTEM_SHUTDOWN, source="orchestrator"
        ))

    # ── State Update Logic ────────────────────────────────────────────────

    async def _update_state(self) -> None:
        """Execute the current state's logic. Called every tick."""
        match self.state:
            case DroneState.IDLE:
                pass  # Waiting for voice command or tool call

            case DroneState.PREFLIGHT:
                await self._run_preflight_checks()

            case DroneState.ARMED:
                pass  # Waiting for takeoff command

            case DroneState.TAKEOFF:
                await self._update_takeoff()

            case DroneState.HOVER:
                await self._update_hover()

            case DroneState.TRACKING:
                await self._update_tracking()

            case DroneState.ORBIT:
                await self._update_orbit()

            case DroneState.CHASE:
                await self._update_chase()

            case DroneState.REVEAL:
                await self._update_reveal()

            case DroneState.RTL:
                await self._update_rtl()

            case DroneState.LANDING:
                await self._update_landing()

            case DroneState.EMERGENCY:
                await self._update_emergency()

    async def _run_preflight_checks(self) -> None:
        """Verify all systems are go before arming."""
        checks_passed = True

        # Check flight controller connection
        if self.flight and not self.flight.is_connected:
            log.warning("Preflight FAIL: Flight controller not connected")
            checks_passed = False

        # Check GPS fix
        if self.flight and self.flight.gps_fix_type < 3:
            log.warning("Preflight FAIL: No GPS 3D fix")
            checks_passed = False

        # Check battery
        if self.flight and self.flight.battery_percent < 30:
            log.warning("Preflight FAIL: Battery below 30%")
            checks_passed = False

        # Check camera
        if self.camera and not self.camera.is_streaming:
            log.warning("Preflight WARN: Camera not streaming")

        if checks_passed:
            log.info("Preflight checks PASSED ✓")
            self.transition_to(DroneState.ARMED)
        else:
            log.error("Preflight checks FAILED — returning to IDLE")
            self.transition_to(DroneState.IDLE)

    async def _update_takeoff(self) -> None:
        """Monitor takeoff progress."""
        if self.flight and self.flight.is_at_target_altitude:
            log.info("Takeoff complete — entering HOVER")
            self.transition_to(DroneState.HOVER)
            await self.bus.publish(Event(
                type=EventType.TAKEOFF_COMPLETE, source="orchestrator"
            ))

    async def _update_hover(self) -> None:
        """Hold position. Waiting for mission command."""
        if self.flight:
            await self.flight.hold_position()

    async def _update_tracking(self) -> None:
        """Active subject tracking — the main cinematic mode."""
        if self.perception and self.control and self.flight:
            # Get latest detection
            bbox = self.perception.current_bbox
            depth_map = self.perception.current_depth

            if bbox is not None:
                # CfC controller generates smooth velocity commands
                velocity, gimbal_angle = self.control.compute(
                    bbox=bbox,
                    depth_map=depth_map,
                    mode="tracking",
                )
                await self.flight.set_velocity_ned(velocity)
                await self.control.set_gimbal(gimbal_angle)

    async def _update_orbit(self) -> None:
        """Orbit around the subject at configured radius and speed."""
        if self.control and self.flight:
            velocity, gimbal_angle = self.control.compute_orbit()
            await self.flight.set_velocity_ned(velocity)
            await self.control.set_gimbal(gimbal_angle)

    async def _update_chase(self) -> None:
        """Chase mode — follow behind the subject."""
        if self.perception and self.control and self.flight:
            bbox = self.perception.current_bbox
            depth_map = self.perception.current_depth

            if bbox is not None:
                velocity, gimbal_angle = self.control.compute(
                    bbox=bbox,
                    depth_map=depth_map,
                    mode="chase",
                )
                await self.flight.set_velocity_ned(velocity)
                await self.control.set_gimbal(gimbal_angle)

    async def _update_reveal(self) -> None:
        """Reveal shot — pull back and rise to reveal the scene."""
        if self.control and self.flight:
            velocity, gimbal_angle = self.control.compute_reveal()
            await self.flight.set_velocity_ned(velocity)
            await self.control.set_gimbal(gimbal_angle)

            if self.control.reveal_complete:
                log.info("Reveal shot complete → HOVER")
                self.transition_to(DroneState.HOVER)

    async def _update_rtl(self) -> None:
        """Return to launch — fly home autonomously."""
        if self.flight:
            await self.flight.return_to_launch()
            if self.flight.is_at_home:
                self.transition_to(DroneState.LANDING)

    async def _update_landing(self) -> None:
        """Land the drone."""
        if self.flight:
            await self.flight.land()
            if self.flight.is_landed:
                self.transition_to(DroneState.DISARMED)
                await self.bus.publish(Event(
                    type=EventType.LANDING_COMPLETE, source="orchestrator"
                ))

    async def _update_emergency(self) -> None:
        """Emergency state — motors should already be killed."""
        if self.flight:
            await self.flight.emergency_stop()

    # ── Event Handlers ────────────────────────────────────────────────────

    async def _on_voice_command(self, event: Event) -> None:
        """Handle parsed voice commands."""
        command = event.data.get("command", "")
        log.info(f"Voice command received: {command}")
        # Route to brain for tool call generation
        if self.brain:
            await self.brain.process_command(command)

    async def _on_tool_call(self, event: Event) -> None:
        """Handle tool calls from the brain."""
        tool_name = event.data.get("tool", "")
        tool_args = event.data.get("args", {})
        log.info(f"Tool call: {tool_name}({tool_args})")

        match tool_name:
            case "takeoff":
                if self.state == DroneState.IDLE:
                    self.transition_to(DroneState.PREFLIGHT)
                elif self.state == DroneState.ARMED:
                    alt = tool_args.get("altitude", 3.0)
                    if self.flight:
                        await self.flight.takeoff(alt)
                    self.transition_to(DroneState.TAKEOFF)

            case "land":
                self.transition_to(DroneState.LANDING)

            case "rtl" | "return_home":
                self.transition_to(DroneState.RTL)

            case "hover" | "stop":
                self.transition_to(DroneState.HOVER)

            case "track_subject" | "follow":
                self.transition_to(DroneState.TRACKING)

            case "orbit":
                if self.control:
                    self.control.set_orbit_params(
                        radius=tool_args.get("radius", 8.0),
                        speed=tool_args.get("speed", 2.0),
                        direction=tool_args.get("direction", "clockwise"),
                    )
                self.transition_to(DroneState.ORBIT)

            case "chase":
                self.transition_to(DroneState.CHASE)

            case "reveal":
                if self.control:
                    self.control.start_reveal(
                        speed=tool_args.get("speed", 2.0),
                        distance=tool_args.get("distance", 15.0),
                    )
                self.transition_to(DroneState.REVEAL)

            case "emergency_stop":
                self.transition_to(DroneState.EMERGENCY)

            case "start_recording":
                if self.camera:
                    self.camera.start_recording()

            case "stop_recording":
                if self.camera:
                    self.camera.stop_recording()

            case _:
                log.warning(f"Unknown tool call: {tool_name}")

    async def _on_battery_critical(self, event: Event) -> None:
        """Force RTL on critical battery."""
        log.warning("BATTERY CRITICAL — forcing RTL")
        if self.voice:
            await self.voice.speak("Battery critical. Returning home now.")
        self.transition_to(DroneState.RTL)

    async def _on_heartbeat_lost(self, event: Event) -> None:
        """Handle loss of flight controller heartbeat."""
        log.error("HEARTBEAT LOST — emergency landing")
        self.transition_to(DroneState.EMERGENCY)

    async def _on_subject_lost(self, event: Event) -> None:
        """Handle loss of subject tracking."""
        log.warning("Subject lost — hovering in place")
        if self.state in (DroneState.TRACKING, DroneState.CHASE, DroneState.ORBIT):
            self.transition_to(DroneState.HOVER)
            if self.voice:
                await self.voice.speak("I lost sight of you")

    async def _on_emergency(self, event: Event) -> None:
        """Handle emergency stop from any source."""
        log.critical("EMERGENCY STOP triggered")
        self.transition_to(DroneState.EMERGENCY)
