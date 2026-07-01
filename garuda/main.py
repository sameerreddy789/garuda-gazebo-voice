"""
GarudaOne DroneOS — Main Entry Point
======================================
Initializes all modules in the correct order and starts the
main event loop. This is what runs when you type 'garuda' or
'python -m garuda.main'.

Boot Sequence:
  1. Load configuration
  2. Initialize camera feed
  3. Load AI models (detector, LLM, voice)
  4. Connect to flight controller (PX4 via MAVSDK)
  5. Start safety watchdog
  6. Start voice pipeline
  7. Start main orchestrator loop
  8. Wait for shutdown signal

The entire system is async — modules run concurrently via asyncio.
"""

import asyncio
import os
import signal
import sys

from garuda import __version__
from garuda.brain.llm_engine import LLMEngine
from garuda.brain.tool_router import ToolRouter
from garuda.camera.skydroid import CameraFeed
from garuda.control.cfc_controller import FlightController
from garuda.control.gimbal import GimbalController
from garuda.control.path_smoother import PathSmoother
from garuda.core.config import Config
from garuda.core.events import EventBus
from garuda.core.orchestrator import Orchestrator
from garuda.flight.mavlink_bridge import MAVLinkBridge
from garuda.flight.safety import SafetyWatchdog
from garuda.perception.detector import PicoDetector
from garuda.perception.tracker import SubjectTracker
from garuda.perception.visual_odom import VisualOdometry
from garuda.utils.logger import get_logger
from garuda.utils.profiler import profiler
from garuda.voice.pipeline import VoicePipeline

log = get_logger("main")


BANNER = r"""
   ____                      _        ___
  / ___| __ _ _ __ _   _  __| | __ _ / _ \ _ __   ___
 | |  _ / _` | '__| | | |/ _` |/ _` | | | | '_ \ / _ \
 | |_| | (_| | |  | |_| | (_| | (_| | |_| | | | |  __/
  \____|\__,_|_|   \__,_|\__,_|\__,_|\___/|_| |_|\___|

  DroneOS v{version} -- Autonomous AI Cinematography
  -----------------------------------------------------
"""


async def boot() -> None:
    """
    Full system boot sequence.
    Initializes every module in dependency order.
    """
    print(BANNER.format(version=__version__))
    log.info(f"GarudaOne DroneOS v{__version__} starting...")
    log.info(f"Mode: {os.environ.get('GARUDA_MODE', 'hardware')}")

    # ── Step 1: Configuration ─────────────────────────────────────────
    log.info("=== Step 1/7: Loading configuration ===")
    config = Config()

    # ── Step 2: Event Bus ─────────────────────────────────────────────
    log.info("=== Step 2/7: Initializing event bus ===")
    bus = EventBus()

    # ── Step 3: Camera ────────────────────────────────────────────────
    log.info("=== Step 3/7: Starting camera feed ===")
    camera = CameraFeed(config)
    camera.start(source="auto")

    # ── Step 4: AI Models ─────────────────────────────────────────────
    log.info("=== Step 4/7: Loading AI models ===")

    # Perception
    detector = PicoDetector(config)
    detector.load_model()

    tracker = SubjectTracker(config, bus)
    visual_odom = VisualOdometry()
    visual_odom.initialize()

    # Control
    controller = FlightController(config)
    controller.load_cfc_model()  # Will use PID fallback if no CfC model
    smoother = PathSmoother()
    gimbal = GimbalController(config)
    gimbal.connect()
    controller.set_gimbal_controller(gimbal)  # Wire gimbal into controller

    # Brain
    llm_engine = LLMEngine(config, bus)
    llm_engine.load_model()

    tool_router = ToolRouter(config, bus)
    tool_router.load_needle_model()
    tool_router.set_llm_engine(llm_engine)

    # Voice
    voice = VoicePipeline(config, bus)
    voice.initialize()

    # ── Step 5: Flight Controller ─────────────────────────────────────
    log.info("=== Step 5/7: Connecting to PX4 ===")
    flight = MAVLinkBridge(config, bus)
    await flight.connect()

    # Safety watchdog
    safety = SafetyWatchdog(config, bus)

    # ── Step 6: Orchestrator ──────────────────────────────────────────
    log.info("=== Step 6/7: Initializing orchestrator ===")
    orchestrator = Orchestrator(config, bus)

    # Create a lightweight module interface for the orchestrator
    class PerceptionInterface:
        """Wraps perception modules for orchestrator access."""
        def __init__(self):
            self.current_bbox = None
            self.current_depth = None

    class BrainInterface:
        """Wraps brain modules for orchestrator access."""
        def __init__(self, router):
            self._router = router

        async def process_command(self, text):
            return await self._router.route_command(text)

    class VoiceInterface:
        """Wraps voice for orchestrator access."""
        def __init__(self, pipeline):
            self._pipeline = pipeline

        async def speak(self, text):
            await self._pipeline.speak(text)

    perception_iface = PerceptionInterface()
    brain_iface = BrainInterface(tool_router)
    voice_iface = VoiceInterface(voice)

    orchestrator.set_modules(
        flight=flight,
        perception=perception_iface,
        control=controller,
        voice=voice_iface,
        brain=brain_iface,
        camera=camera,
    )

    # ── Step 7: Start ─────────────────────────────────────────────────
    log.info("=== Step 7/7: Starting main loop ===")
    log.info("All systems GO [OK]")

    # Create async tasks for all concurrent modules
    tasks = [
        asyncio.create_task(orchestrator.run(), name="orchestrator"),
        asyncio.create_task(safety.run(flight), name="safety"),
        asyncio.create_task(voice.run(), name="voice"),
        asyncio.create_task(
            _perception_loop(camera, detector, tracker, visual_odom,
                             perception_iface, smoother),
            name="perception",
        ),
    ]

    # Handle shutdown signals (compatible with Windows)
    shutdown_event = asyncio.Event()

    def signal_handler(*args):
        log.info("Shutdown signal received")
        shutdown_event.set()

    # Use signal.signal which works on all platforms including Windows
    signal.signal(signal.SIGINT, signal_handler)
    try:
        signal.signal(signal.SIGTERM, signal_handler)
    except (OSError, AttributeError):
        pass  # SIGTERM not available on Windows

    # Wait for shutdown
    try:
        await shutdown_event.wait()
    except KeyboardInterrupt:
        log.info("Keyboard interrupt received")

    # ── Shutdown ──────────────────────────────────────────────────────
    log.info("=== Shutting down ===")
    await orchestrator.stop()
    await safety.stop()
    await voice.stop()
    camera.stop()

    # Cancel remaining tasks
    for task in tasks:
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

    # Final performance report
    profiler.report()
    log.info("GarudaOne DroneOS shutdown complete. Fly safe!")


async def _perception_loop(
    camera: CameraFeed,
    detector: PicoDetector,
    tracker: SubjectTracker,
    visual_odom: VisualOdometry,
    perception_iface,
    smoother: PathSmoother,
) -> None:
    """
    Perception loop -- runs at camera FPS (~30Hz).
    Reads frames, detects subjects, tracks them, and estimates depth.
    Velocity commands are smoothed through PathSmoother before being
    made available to the flight controller.
    """
    log.info("Perception loop started")

    while True:
        try:
            # Read camera frame
            frame = camera.read_frame()
            if frame is None:
                await asyncio.sleep(0.01)
                continue

            # Detect objects
            detections = detector.detect(frame)

            # Track subject
            bbox = await tracker.update(detections)
            perception_iface.current_bbox = bbox

            # Visual odometry (pose + depth)
            pose, depth = visual_odom.process_frame(frame)
            perception_iface.current_depth = depth

            # Store smoother reference so orchestrator can use it
            perception_iface.smoother = smoother

            # Yield to event loop
            await asyncio.sleep(0.001)

        except asyncio.CancelledError:
            break
        except Exception as e:
            log.error(f"Perception loop error: {e}")
            await asyncio.sleep(0.1)

    log.info("Perception loop stopped")


def main():
    """CLI entry point."""
    try:
        asyncio.run(boot())
    except KeyboardInterrupt:
        print("\nGarudaOne DroneOS stopped.")


if __name__ == "__main__":
    main()
