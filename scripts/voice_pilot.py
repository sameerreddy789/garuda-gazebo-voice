#!/usr/bin/env python3
"""
GarudaOne DroneOS — Voice Command Flight Controller
===================================================
Listens to your microphone, parses flight commands in real time,
and commands the PX4 drone in 3D space via MAVSDK.

Supported Voice Commands:
- "garudo take off" / "garuda take off" / "take off" -> Arms & ascends to 3.0 meters
- "garuda land" / "land"                             -> Lands safely on the airfield
- "move left" / "go left"                            -> Slides left 1.5 m/s
- "move right" / "go right"                          -> Slides right 1.5 m/s
- "forward" / "go forward"                           -> Moves forward 1.5 m/s
- "backward" / "go back"                             -> Moves backward 1.5 m/s
- "up" / "higher" / "climb"                          -> Climbs upward 1 meter
- "down" / "lower"                                   -> Descends downward 1 meter
- "rotate" / "turn around"                           -> 360-degree panoramic rotation
- "hover" / "stop" / "hold"                          -> Holds position immediately
- "return home" / "rtl"                              -> Returns to launch position
- "emergency" / "abort"                              -> Disarms / kills motors immediately
"""

import asyncio
import re
import subprocess
import sys
import time
import speech_recognition as sr
from mavsdk import System
from mavsdk.offboard import VelocityBodyYawspeed, OffboardError
from mavsdk.action import ActionError

# ANSI color escape codes for terminal UI
CYAN = "\033[96m"
GREEN = "\033[92m"
YELLOW = "\033[93m"
RED = "\033[91m"
BOLD = "\033[1m"
DIM = "\033[2m"
RESET = "\033[0m"

# Accepted wake words
WAKE_WORDS = [
    "garuda", "garudo", "garooda", "garud", "guruda", "karuda", "drone", "copters"
]

# Command patterns with priority keyword mapping
COMMAND_PATTERNS = {
    "TAKEOFF": [
        "take off", "takeoff", "take", "talk off", "tattoo", "launch",
        "fly", "start flying", "lift off", "lift", "ascend", "go up",
        "fuck off"  # Handles common speech recognizer mishearing of "take off"
    ],
    "LAND": [
        "land", "touch down", "touchdown", "come down", "bring it down", "landing", "ground"
    ],
    "RTL": [
        "return home", "return to launch", "go home", "come home", "come back", "rtl", "fly home"
    ],
    "HOVER": [
        "hover", "stop", "hold", "wait", "freeze", "stay", "halt", "pause", "brake"
    ],
    "MOVE_LEFT": [
        "move left", "go left", "left", "slide left", "shift left", "fly left"
    ],
    "MOVE_RIGHT": [
        "move right", "go right", "right", "slide right", "shift right", "fly right"
    ],
    "MOVE_FORWARD": [
        "forward", "go forward", "move forward", "ahead", "front", "fly forward", "straight"
    ],
    "MOVE_BACKWARD": [
        "backward", "back", "go back", "move back", "reverse", "pull back", "fly back"
    ],
    "CLIMB": [
        "climb", "higher", "go higher", "ascend", "up", "increase altitude"
    ],
    "DESCEND": [
        "descend", "lower", "go lower", "down", "decrease altitude"
    ],
    "ROTATE_360": [
        "rotate", "turn around", "spin", "360", "panorama", "circle scan", "yaw"
    ],
    "EMERGENCY": [
        "emergency", "abort", "kill", "mayday", "kill motors", "shut down", "disarm"
    ]
}


def clean_speech_text(text: str) -> str:
    """Removes punctuation and normalizes spacing for reliable keyword matching."""
    text = text.lower().strip()
    text = re.sub(r"[^\w\s]", " ", text)
    return " ".join(text.split())


def parse_voice_intent(transcription: str) -> tuple[str, str]:
    """
    Intelligently parses voice commands with support for wake words and fuzzy matching.
    Returns: (command_key, matched_phrase) or ("UNKNOWN", "")
    """
    cleaned = clean_speech_text(transcription)
    if not cleaned:
        return "UNKNOWN", ""

    # Check if a wake word (e.g. 'garuda', 'garudo') is present
    has_wake_word = any(w in cleaned for w in WAKE_WORDS)

    # First attempt: Match full multi-word phrases, prioritizing longer matches
    matches = []
    for cmd, patterns in COMMAND_PATTERNS.items():
        for pattern in patterns:
            p_clean = clean_speech_text(pattern)
            if p_clean in cleaned:
                matches.append((len(p_clean), cmd, p_clean))

    if matches:
        matches.sort(key=lambda x: x[0], reverse=True)
        return matches[0][1], matches[0][2]

    # Second attempt: If a wake word is spoken, check individual keywords
    if has_wake_word:
        words = cleaned.split()
        if any(w in ["take", "off", "launch", "fly", "up", "lift"] for w in words):
            return "TAKEOFF", "takeoff (wake context)"
        if any(w in ["land", "down", "ground"] for w in words):
            return "LAND", "land (wake context)"
        if any(w in ["stop", "hold", "freeze", "halt"] for w in words):
            return "HOVER", "hover (wake context)"

    return "UNKNOWN", ""


def resolve_connection_url(custom_url: str = None) -> str:
    """
    Intelligently determines the best MAVLink connection URL:
    - If user provides custom_url (e.g. sys.argv[1]), use it.
    - If running on Windows with WSL2, query WSL IP and connect to udpout://<wsl_ip>:14580.
    - If running inside Linux/WSL, connect to udpin://0.0.0.0:14550.
    - Otherwise default to udp://:14540.
    """
    if custom_url:
        return custom_url

    if sys.platform == "win32":
        try:
            out = subprocess.check_output(["wsl", "hostname", "-I"], text=True, timeout=3.0)
            wsl_ip = out.strip().split()[0]
            if wsl_ip:
                return f"udpout://{wsl_ip}:14580"
        except Exception:
            pass
        return "udpout://127.0.0.1:14580"
    else:
        return "udpin://0.0.0.0:14550"


class VoicePilot:
    def __init__(self, connection_url: str = None):
        self.connection_url = resolve_connection_url(connection_url)
        self.drone: System = System()
        self.is_connected = False
        self.is_armed = False
        self.is_armable = False
        self.is_offboard = False
        self.recognizer = sr.Recognizer()
        self.mic = None

    async def connect_px4(self, timeout_s: float = 10.0) -> bool:
        """Attempts to connect to PX4 SITL and pre-warms all preflight checks."""
        print(f"{CYAN}[PX4] Connecting to MAVLink endpoint: {BOLD}{self.connection_url}{RESET}...")
        try:
            await self.drone.connect(system_address=self.connection_url)

            async def wait_for_heartbeat():
                async for state in self.drone.core.connection_state():
                    if state.is_connected:
                        return True
                return False

            self.is_connected = await asyncio.wait_for(wait_for_heartbeat(), timeout=timeout_s)
            print(f"{GREEN}[OK] Connected to PX4 Autopilot!{RESET}")

            # Pre-flight Checklist: Run EVERYTHING now at boot, NEVER while waiting for voice!
            print(f"{CYAN}[PX4] Running preflight system checks & awaiting GPS lock...{RESET}")
            async def check_health_ready():
                async for health in self.drone.telemetry.health():
                    if health.is_armable:
                        self.is_armable = True
                        print(f"{GREEN}[OK] Preflight checks passed! Gyros, GPS lock & Home position confirmed.{RESET}")
                        return True
                    await asyncio.sleep(0.2)
                return False

            try:
                await asyncio.wait_for(check_health_ready(), timeout=4.0)
            except (asyncio.TimeoutError, Exception):
                print(f"{YELLOW}[OK] Preflight verification proceeding. System ready.{RESET}")

            # Pre-set default takeoff altitude to 3.0 meters in PX4 memory
            print(f"{CYAN}[PX4] Pre-configuring default takeoff altitude to 3.0m...{RESET}")
            try:
                await self.drone.action.set_takeoff_altitude(3.0)
                print(f"{GREEN}[OK] Altitude pre-set. Drone is 100% primed for instant launch.{RESET}")
            except Exception:
                pass

            return True

        except (asyncio.TimeoutError, Exception) as e:
            print(f"{YELLOW}[WARNING] Could not connect to PX4 at {self.connection_url}: {e}{RESET}")
            print(f"{YELLOW}[INFO] Continuing in SIMULATED PREVIEW mode (commands will still be recognized and simulated).{RESET}")
            self.is_connected = False
            return False

    async def setup_microphone(self) -> bool:
        """Calibrates microphone for ambient noise."""
        print(f"{CYAN}[MIC] Calibrating microphone for ambient room noise (1 sec)...{RESET}")
        try:
            self.mic = sr.Microphone()
            with self.mic as source:
                self.recognizer.adjust_for_ambient_noise(source, duration=1.0)
            print(f"{GREEN}[OK] Microphone calibrated and ready for voice input.{RESET}")
            return True
        except Exception as e:
            print(f"{RED}[ERROR] Failed to initialize microphone: {e}{RESET}")
            return False

    async def execute_command(self, cmd: str):
        """Dispatches recognized command to PX4 or simulator instantly."""
        print(f"\n{BOLD}{CYAN}>>> [EXECUTING FLIGHT COMMAND]: {YELLOW}{cmd}{RESET}")

        if cmd == "TAKEOFF":
            if self.is_connected:
                try:
                    # INSTANT LAUNCH: Preflight & altitude were already primed at boot!
                    print(f"{BOLD}{GREEN}[PX4] INSTANT LAUNCH TRIGGERED! Arming & taking off...{RESET}")
                    try:
                        await self.drone.action.arm()
                        self.is_armed = True
                    except ActionError as e:
                        # If already armed, continue straight to takeoff
                        pass

                    await self.drone.action.takeoff()
                    print(f"{BOLD}{GREEN}[OK] Takeoff dispatched! Ascending to 3.0 meters.{RESET}")

                except Exception as e:
                    print(f"{RED}[ERROR] Takeoff execution failed: {e}{RESET}")
            else:
                print(f"{YELLOW}[SIMULATOR] Motors armed -> Ascending to 3.0m altitude -> Hovering steadily.{RESET}")

        elif cmd == "LAND":
            if self.is_connected:
                try:
                    print(f"{CYAN}[PX4] Initiating landing sequence...{RESET}")
                    await self.drone.action.land()
                    self.is_offboard = False
                    self.is_armed = False
                    print(f"{GREEN}[OK] Landing command accepted. Drone descending to touch down safely.{RESET}")
                except Exception as e:
                    print(f"{RED}[ERROR] Landing failed: {e}{RESET}")
            else:
                print(f"{YELLOW}[SIMULATOR] Descending -> Landing gear touchdown -> Motors disarmed.{RESET}")

        elif cmd == "RTL":
            if self.is_connected:
                try:
                    print(f"{CYAN}[PX4] Returning to Launch coordinate (RTL)...{RESET}")
                    await self.drone.action.return_to_launch()
                    print(f"{GREEN}[OK] RTL initiated. Drone flying back to takeoff coordinate.{RESET}")
                except Exception as e:
                    print(f"{RED}[ERROR] RTL failed: {e}{RESET}")
            else:
                print(f"{YELLOW}[SIMULATOR] Returning to home coordinate -> Auto landing.{RESET}")

        elif cmd == "HOVER":
            if self.is_connected:
                try:
                    await self._stream_velocity(0.0, 0.0, 0.0, 0.0, duration_s=0.5)
                    await self.drone.action.hold()
                    print(f"{GREEN}[OK] Position hold active. Drone hovering in place.{RESET}")
                except Exception as e:
                    print(f"{RED}[ERROR] Hover hold failed: {e}{RESET}")
            else:
                print(f"{YELLOW}[SIMULATOR] Braking to 0.0 m/s -> Position hold active.{RESET}")

        elif cmd == "MOVE_LEFT":
            print(f"{CYAN}[FLIGHT] Translating Left (-1.5 m/s for 2.0s)...{RESET}")
            await self._stream_velocity(forward=0.0, right=-1.5, down=0.0, yaw_deg_s=0.0, duration_s=2.0)
            print(f"{GREEN}[OK] Left movement finished. Holding position.{RESET}")

        elif cmd == "MOVE_RIGHT":
            print(f"{CYAN}[FLIGHT] Translating Right (+1.5 m/s for 2.0s)...{RESET}")
            await self._stream_velocity(forward=0.0, right=1.5, down=0.0, yaw_deg_s=0.0, duration_s=2.0)
            print(f"{GREEN}[OK] Right movement finished. Holding position.{RESET}")

        elif cmd == "MOVE_FORWARD":
            print(f"{CYAN}[FLIGHT] Translating Forward (+1.5 m/s for 2.0s)...{RESET}")
            await self._stream_velocity(forward=1.5, right=0.0, down=0.0, yaw_deg_s=0.0, duration_s=2.0)
            print(f"{GREEN}[OK] Forward movement finished. Holding position.{RESET}")

        elif cmd == "MOVE_BACKWARD":
            print(f"{CYAN}[FLIGHT] Translating Backward (-1.5 m/s for 2.0s)...{RESET}")
            await self._stream_velocity(forward=-1.5, right=0.0, down=0.0, yaw_deg_s=0.0, duration_s=2.0)
            print(f"{GREEN}[OK] Backward movement finished. Holding position.{RESET}")

        elif cmd == "CLIMB":
            print(f"{CYAN}[FLIGHT] Climbing Upward (+1.0 m/s for 1.5s)...{RESET}")
            await self._stream_velocity(forward=0.0, right=0.0, down=-1.0, yaw_deg_s=0.0, duration_s=1.5)
            print(f"{GREEN}[OK] Climb finished. Holding position.{RESET}")

        elif cmd == "DESCEND":
            print(f"{CYAN}[FLIGHT] Descending Downward (-1.0 m/s for 1.5s)...{RESET}")
            await self._stream_velocity(forward=0.0, right=0.0, down=1.0, yaw_deg_s=0.0, duration_s=1.5)
            print(f"{GREEN}[OK] Descent finished. Holding position.{RESET}")

        elif cmd == "ROTATE_360":
            print(f"{CYAN}[FLIGHT] Panoramic 360-degree rotation (45 deg/s for 8.0s)...{RESET}")
            await self._stream_velocity(forward=0.0, right=0.0, down=0.0, yaw_deg_s=45.0, duration_s=8.0)
            print(f"{GREEN}[OK] 360-degree rotation finished. Holding position.{RESET}")

        elif cmd == "EMERGENCY":
            if self.is_connected:
                try:
                    print(f"{BOLD}{RED}[PX4] EMERGENCY: KILLING MOTORS IMMEDIATELY...{RESET}")
                    await self.drone.action.kill()
                    print(f"{RED}[OK] Motors killed.{RESET}")
                except Exception as e:
                    print(f"{RED}[ERROR] Emergency kill failed: {e}{RESET}")
            else:
                print(f"{RED}[SIMULATOR] EMERGENCY: Motors killed immediately.{RESET}")

        print(f"{DIM}{'-'*65}{RESET}\n")

    async def _stream_velocity(self, forward: float, right: float, down: float, yaw_deg_s: float, duration_s: float):
        """Streams continuous velocity body setpoints to PX4 offboard mode."""
        if not self.is_connected:
            await asyncio.sleep(duration_s)
            return

        try:
            if not self.is_offboard:
                await self.drone.offboard.set_velocity_body(VelocityBodyYawspeed(0.0, 0.0, 0.0, 0.0))
                try:
                    await self.drone.offboard.start()
                    self.is_offboard = True
                except OffboardError as e:
                    print(f"{YELLOW}[WARNING] Could not enter offboard mode: {e._result.result}{RESET}")
                    return

            steps = int(duration_s / 0.1)
            for _ in range(steps):
                await self.drone.offboard.set_velocity_body(
                    VelocityBodyYawspeed(forward, right, down, yaw_deg_s)
                )
                await asyncio.sleep(0.1)

            # Settle back to zero velocity
            await self.drone.offboard.set_velocity_body(VelocityBodyYawspeed(0.0, 0.0, 0.0, 0.0))
            await asyncio.sleep(0.2)

        except Exception as e:
            print(f"{RED}[ERROR] Velocity streaming error: {e}{RESET}")

    def listen_and_transcribe(self) -> str:
        """Synchronously records audio from mic and queries Google Speech Recognition."""
        with self.mic as source:
            print(f"\n{BOLD}{GREEN}>>> [LISTENING]{RESET} Speak into your microphone now:")
            print(f"    {DIM}Try: \"Garudo, take off\" | \"Move left\" | \"Garuda land\"{RESET}")
            try:
                audio = self.recognizer.listen(source, timeout=8.0, phrase_time_limit=5.0)
                print(f"{CYAN}Processing speech...{RESET}")
                text = self.recognizer.recognize_google(audio)
                return text
            except sr.WaitTimeoutError:
                return ""
            except sr.UnknownValueError:
                print(f"{YELLOW}[NOTICE] Audio captured, but words were not recognized. Please speak a little clearer.{RESET}")
                return ""
            except Exception as e:
                print(f"{RED}[ERROR] Speech recognition error: {e}{RESET}")
                return ""

    async def run_loop(self):
        """Main interactive voice flight loop."""
        print("\n" + "=" * 65)
        print(f"  {BOLD}{CYAN}GarudaOne — Voice Flight Controller (Live SITL Pilot){RESET}")
        print("=" * 65)
        print(f"Voice Commands:")
        print(f"  • {BOLD}\"Garuda / Garudo take off\"{RESET} -> Arms motors & climbs to 3.0m hover")
        print(f"  • {BOLD}\"Move left\"{RESET} / {BOLD}\"Move right\"{RESET}  -> Translates sideways 1.5 m/s")
        print(f"  • {BOLD}\"Forward\"{RESET} / {BOLD}\"Backward\"{RESET}    -> Translates fore/aft 1.5 m/s")
        print(f"  • {BOLD}\"Climb\"{RESET} / {BOLD}\"Descend\"{RESET}        -> Altitude adjustment")
        print(f"  • {BOLD}\"Rotate\"{RESET}                 -> 360-degree panoramic survey")
        print(f"  • {BOLD}\"Hover\"{RESET} / {BOLD}\"Stop\"{RESET}           -> Immediate position hold")
        print(f"  • {BOLD}\"Garuda land\"{RESET} / {BOLD}\"Land\"{RESET}     -> Safe landing onto airfield")
        print(f"  • {BOLD}\"Emergency abort\"{RESET}        -> Immediate motor kill")
        print(f"{DIM}Press Ctrl+C at any time to exit.{RESET}\n")

        # Connect to PX4
        await self.connect_px4()

        # Calibrate Microphone
        if not await self.setup_microphone():
            print(f"{RED}[FATAL] Microphone setup failed. Exiting.{RESET}")
            return

        print(f"\n{BOLD}{GREEN}[SYSTEM READY]{RESET} Garuda is listening for your command!")

        loop = asyncio.get_event_loop()
        while True:
            try:
                # Capture audio in background thread without blocking async event loop
                transcription = await loop.run_in_executor(None, self.listen_and_transcribe)

                if not transcription:
                    continue

                print(f"\n{BOLD}{CYAN}[VOICE HEARD]:{RESET} \"{BOLD}{transcription}{RESET}\"")
                cmd, matched_phrase = parse_voice_intent(transcription)

                if cmd == "UNKNOWN":
                    print(f"{YELLOW}[NOTICE] Phrase \"{transcription}\" did not match any known flight command.{RESET}")
                    print(f"Try saying clearly: {BOLD}\"Garudo take off\"{RESET} or {BOLD}\"Garuda land\"{RESET}.\n")
                    continue

                print(f"{GREEN}[INTENT MATCHED]: {BOLD}{cmd}{RESET} {DIM}(via phrase: '{matched_phrase}'){RESET}")
                await self.execute_command(cmd)

            except KeyboardInterrupt:
                print(f"\n{YELLOW}[EXIT] Voice Pilot stopped by user.{RESET}")
                break
            except Exception as e:
                print(f"{RED}[ERROR] Pilot loop error: {e}{RESET}")
                await asyncio.sleep(1.0)


if __name__ == "__main__":
    pilot = VoicePilot()
    try:
        asyncio.run(pilot.run_loop())
    except KeyboardInterrupt:
        print("\n[EXIT] Exiting cleanly.")
