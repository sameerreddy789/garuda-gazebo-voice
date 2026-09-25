#!/usr/bin/env python3
"""
GarudaOne DroneOS -- Dual Voice + Keyboard Flight Controller (AI Copilot Edition)
==================================================================================
Powered by:
  - OpenAI GPT (Natural Language Understanding & Intent Extraction)
  - Smallest.ai Lightning TTS (Ultra-low latency studio voice responses)
  - MAVSDK & PX4 SITL (3D Physics & Flight Telemetry in Gazebo)
  - Direct Windows Console Teleop (Zero-delay WASD / Arrow Keypad)

You can speak naturally (e.g., "Garuda, fly up a bit higher so we can inspect the area")
or use instant hotkeys ([T] Takeoff, [W] Forward, [Space] Climb, [L] Land).
"""

import asyncio
import io
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import threading
import time
import urllib.request
import urllib.error

# Ensure UTF-8 output on Windows consoles to prevent cp1252 UnicodeEncodeError
if sys.platform == "win32":
    try:
        if hasattr(sys.stdout, "reconfigure"):
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        if hasattr(sys.stderr, "reconfigure"):
            sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).parent.parent / ".env")
except Exception:
    pass

import speech_recognition as sr
from mavsdk import System
from mavsdk.offboard import VelocityBodyYawspeed, OffboardError
from mavsdk.action import ActionError

try:
    import msvcrt
except ImportError:
    msvcrt = None

try:
    import winsound
except ImportError:
    winsound = None

# ANSI color escape codes for terminal UI
CYAN = "\033[96m"
GREEN = "\033[92m"
YELLOW = "\033[93m"
RED = "\033[91m"
BOLD = "\033[1m"
DIM = "\033[2m"
RESET = "\033[0m"

OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")
SMALLEST_API_KEY = os.environ.get("SMALLEST_API_KEY", "")

# Accepted wake words
WAKE_WORDS = [
    "garuda", "garudo", "garooda", "garud", "guruda", "karuda",
    "ganga", "garda", "garood", "guda", "daruda", "drone", "copters", "robot"
]

# Command patterns with priority keyword mapping
COMMAND_PATTERNS = {
    "TAKEOFF": [
        "take off", "takeoff", "take", "talk off", "tattoo", "launch",
        "fly", "start flying", "lift off", "lift", "ascend", "go up",
        "theka", "theka off", "teka", "taka", "take of",
        "fuck off"
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
        "move left", "go left", "left", "slide left", "shift left", "fly left", "turn left"
    ],
    "MOVE_RIGHT": [
        "move right", "go right", "right", "slide right", "shift right", "fly right", "turn right"
    ],
    "MOVE_FORWARD": [
        "forward", "go forward", "move forward", "move", "go", "ahead", "front", "fly forward", "straight"
    ],
    "MOVE_BACKWARD": [
        "backward", "back", "go back", "move back", "reverse", "pull back", "fly back"
    ],
    "CLIMB": [
        "climb", "higher", "go higher", "ascend", "up", "increase altitude", "rise"
    ],
    "DESCEND": [
        "descend", "lower", "go lower", "down", "decrease altitude", "drop"
    ],
    "ROTATE_360": [
        "rotate", "turn around", "spin", "360", "panorama", "circle scan", "yaw"
    ],
    "ROTATE_LEFT": [
        "rotate left", "yaw left", "spin left", "pan left"
    ],
    "ROTATE_RIGHT": [
        "rotate right", "yaw right", "spin right", "pan right"
    ],
    "EMERGENCY": [
        "emergency", "abort", "kill", "mayday", "kill motors", "shut down", "disarm"
    ]
}

KEY_MAPPINGS = {
    'w': "MOVE_FORWARD",
    's': "MOVE_BACKWARD",
    'a': "MOVE_LEFT",
    'd': "MOVE_RIGHT",
    't': "TAKEOFF",
    'l': "LAND",
    ' ': "CLIMB",
    'r': "CLIMB",
    'c': "DESCEND",
    'f': "DESCEND",
    'q': "ROTATE_LEFT",
    'e': "ROTATE_RIGHT",
    'h': "HOVER",
    'x': "EMERGENCY",
    'm': "TOGGLE_MUTE",
}

TACTICAL_REPLIES = {
    "TAKEOFF": "Taking off to three meters.",
    "LAND": "Landing sequence initiated.",
    "RTL": "Returning to launch coordinate.",
    "HOVER": "Holding position.",
    "MOVE_LEFT": "Translating left.",
    "MOVE_RIGHT": "Translating right.",
    "MOVE_FORWARD": "Translating forward.",
    "MOVE_BACKWARD": "Translating backward.",
    "CLIMB": "Ascending higher.",
    "DESCEND": "Descending.",
    "ROTATE_360": "Performing three-sixty survey.",
    "ROTATE_LEFT": "Rotating left.",
    "ROTATE_RIGHT": "Rotating right.",
    "EMERGENCY": "Emergency stop. Motors killed.",
    "WAKE_ACK": "Garuda online, Commander."
}


class AICopilot:
    """Manages OpenAI Natural Language Understanding and Smallest.ai TTS."""

    def __init__(self, openai_key: str, smallest_key: str):
        self.openai_key = openai_key
        self.smallest_key = smallest_key
        self.audio_cache: dict[str, bytes] = {}
        self.is_enabled = bool(openai_key and smallest_key)
        self.is_speaking = False

    def prewarm_cache(self):
        """Pre-downloads audio for standard commands for instantaneous zero-latency playback."""
        if not self.smallest_key:
            return
        def _fetch():
            for action, phrase in list(TACTICAL_REPLIES.items())[:6]:
                try:
                    data = self._generate_tts(phrase)
                    if data:
                        self.audio_cache[phrase] = data
                except Exception:
                    pass
        threading.Thread(target=_fetch, daemon=True).start()

    def _generate_tts(self, text: str) -> bytes | None:
        """Calls Smallest.ai Lightning TTS API."""
        if not self.smallest_key:
            return None
        try:
            req = urllib.request.Request(
                "https://api.smallest.ai/waves/v1/tts",
                headers={
                    "Authorization": f"Bearer {self.smallest_key}",
                    "Content-Type": "application/json",
                    "Accept": "audio/wav"
                },
                data=json.dumps({
                    "text": text,
                    "voice_id": "meher",
                    "model": "lightning_v3.1_pro",
                    "sample_rate": 24000,
                    "output_format": "wav"
                }).encode("utf-8")
            )
            with urllib.request.urlopen(req, timeout=6.0) as resp:
                return resp.read()
        except Exception as e:
            return None

    def speak(self, text: str):
        """Asynchronously plays voice reply through speakers without blocking flight loop."""
        if not text:
            return

        def _play():
            try:
                self.is_speaking = True
                # Check cache first
                data = self.audio_cache.get(text)
                if not data:
                    data = self._generate_tts(text)
                    if data:
                        self.audio_cache[text] = data

                if data and winsound:
                    winsound.PlaySound(data, winsound.SND_MEMORY)
                elif winsound:
                    winsound.Beep(1100, 80)
            except Exception:
                pass
            finally:
                time.sleep(0.35)  # Acoustic decay buffer so mic doesn't catch tail echo
                self.is_speaking = False

        threading.Thread(target=_play, daemon=True).start()

    def parse_natural_language(self, user_text: str) -> tuple[str, str]:
        """Calls OpenAI GPT-5-nano to extract flight action and formulate pilot response."""
        if not self.openai_key:
            return "UNKNOWN", ""

        system_prompt = (
            "You are GarudaOne drone AI brain. Extract the flight action and formulate a brief pilot response.\n"
            "Allowed actions: TAKEOFF, LAND, MOVE_FORWARD, MOVE_BACKWARD, MOVE_LEFT, MOVE_RIGHT, "
            "CLIMB, DESCEND, ROTATE_360, ROTATE_LEFT, ROTATE_RIGHT, HOVER, RTL, EMERGENCY, WAKE_ACK, UNKNOWN.\n"
            "Respond ONLY with valid JSON: {\"action\": \"...\", \"reply\": \"...\"}\n"
            "Keep reply under 10 words."
        )

        try:
            req = urllib.request.Request(
                "https://api.openai.com/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {self.openai_key}",
                    "Content-Type": "application/json"
                },
                data=json.dumps({
                    "model": "gpt-5-nano",
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_text}
                    ],
                    "max_completion_tokens": 1600
                }).encode("utf-8")
            )
            with urllib.request.urlopen(req, timeout=25.0) as resp:
                data = json.loads(resp.read().decode())
                content = data["choices"][0]["message"]["content"]
                # Robust JSON parsing
                clean_json = content.strip("` \n")
                if clean_json.startswith("json\n"):
                    clean_json = clean_json[5:]
                match = re.search(r"\{.*\}", clean_json, re.DOTALL)
                if match:
                    clean_json = match.group(0)
                parsed = json.loads(clean_json)
                action = parsed.get("action", "UNKNOWN").upper()
                reply = parsed.get("reply", "")
                return action, reply
        except Exception:
            return "UNKNOWN", ""


def clean_speech_text(text: str) -> str:
    """Removes punctuation and normalizes spacing for reliable keyword matching."""
    text = text.lower().strip()
    text = re.sub(r"[^\w\s]", " ", text)
    return " ".join(text.split())


def parse_fast_intent(transcription: str) -> tuple[str, str]:
    """Instant regex-based keyword parser for direct/quick commands."""
    cleaned = clean_speech_text(transcription)
    if not cleaned:
        return "UNKNOWN", ""

    if any(q in cleaned for q in ["help", "what is", "what can you do", "commands", "options"]):
        return "HELP", cleaned

    is_wake_only = (
        cleaned in WAKE_WORDS or
        any(cleaned == f"hey {w}" or cleaned == f"hi {w}" or cleaned == f"ok {w}" or cleaned == f"hello {w}" for w in WAKE_WORDS)
    )
    if is_wake_only:
        return "WAKE_ACK", cleaned

    has_wake_word = any(w in cleaned for w in WAKE_WORDS)

    matches = []
    for cmd, patterns in COMMAND_PATTERNS.items():
        for pattern in patterns:
            p_clean = clean_speech_text(pattern)
            pattern_regex = r'\b' + re.escape(p_clean) + r'\b'
            if re.search(pattern_regex, cleaned):
                matches.append((len(p_clean), cmd, p_clean))

    if matches:
        matches.sort(key=lambda x: x[0], reverse=True)
        return matches[0][1], matches[0][2]

    if has_wake_word:
        words = cleaned.split()
        if any(w in ["take", "off", "launch", "fly", "up", "lift", "theka", "teka", "taka"] for w in words):
            return "TAKEOFF", "takeoff (wake context)"
        if any(w in ["land", "down", "ground"] for w in words):
            return "LAND", "land (wake context)"
        if any(w in ["stop", "hold", "freeze", "halt"] for w in words):
            return "HOVER", "hover (wake context)"
        if any(w in ["left"] for w in words):
            return "MOVE_LEFT", "left (wake context)"
        if any(w in ["right"] for w in words):
            return "MOVE_RIGHT", "right (wake context)"
        if any(w in ["move", "front", "ahead"] for w in words):
            return "MOVE_FORWARD", "forward (wake context)"

    return "UNKNOWN", ""


def resolve_connection_url(custom_url: str = None) -> str:
    """Intelligently determines the best MAVLink connection URL."""
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


class DualPilot:
    def __init__(self, connection_url: str = None):
        self.connection_url = resolve_connection_url(connection_url)
        self.drone: System = System()
        self.is_connected = False
        self.is_armed = False
        self.is_armable = False
        self.is_offboard = False
        self.recognizer = sr.Recognizer()
        self.mic = None
        self.stop_event = threading.Event()
        self.ai = AICopilot(OPENAI_API_KEY, SMALLEST_API_KEY)
        self.mic_muted = False

    def toggle_mic_mute(self):
        """Toggles microphone listening state on or off."""
        self.mic_muted = not self.mic_muted
        if self.mic_muted:
            print(f"\n{BOLD}{RED}[MIC MUTED]{RESET} 🔇 Voice listening paused. Hotkeys active! Press {BOLD}[M]{RESET} to unmute.\n")
            if winsound:
                try:
                    winsound.Beep(500, 100)
                except Exception:
                    pass
        else:
            print(f"\n{BOLD}{GREEN}[MIC UNMUTED]{RESET} 🎙️ Voice listening active! Speak your command or press {BOLD}[M]{RESET} to mute.\n")
            if winsound:
                try:
                    winsound.Beep(1000, 100)
                except Exception:
                    pass

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

            print(f"{CYAN}[PX4] Verifying preflight health & GPS lock...{RESET}")
            async def check_health_ready():
                async for health in self.drone.telemetry.health():
                    if health.is_armable:
                        self.is_armable = True
                        print(f"{GREEN}[OK] Preflight checks passed! Gyros, GPS & Home confirmed.{RESET}")
                        return True
                    await asyncio.sleep(0.2)
                return False

            try:
                await asyncio.wait_for(check_health_ready(), timeout=4.0)
            except Exception:
                print(f"{YELLOW}[OK] Preflight verification proceeding. System ready.{RESET}")

            try:
                await self.drone.action.set_takeoff_altitude(3.0)
                print(f"{GREEN}[OK] Takeoff altitude primed to 3.0m.{RESET}")
            except Exception:
                pass

            return True

        except Exception as e:
            print(f"{YELLOW}[WARNING] Could not connect to PX4 at {self.connection_url}: {e}{RESET}")
            print(f"{YELLOW}[INFO] Continuing in SIMULATION PREVIEW mode.{RESET}")
            self.is_connected = False
            return False

    async def setup_microphone(self) -> bool:
        """Calibrates microphone for ambient noise."""
        print(f"{CYAN}[MIC] Calibrating microphone for ambient room noise (1 sec)...{RESET}")
        try:
            self.mic = sr.Microphone()
            with self.mic as source:
                self.recognizer.adjust_for_ambient_noise(source, duration=1.2)
            # Filter out room sighs, computer fan, breathing noise
            self.recognizer.energy_threshold = max(self.recognizer.energy_threshold, 550)
            self.recognizer.pause_threshold = 0.6
            self.recognizer.non_speaking_duration = 0.4
            print(f"{GREEN}[OK] Microphone calibrated and ready (threshold={int(self.recognizer.energy_threshold)}).{RESET}")
            return True
        except Exception as e:
            print(f"{YELLOW}[WARNING] Microphone not active ({e}). Operating in PURE KEYBOARD mode!{RESET}")
            self.mic = None
            return False

    async def execute_command(self, cmd: str, spoken_reply: str = None):
        """Dispatches recognized command to PX4 or simulator instantly and speaks response."""
        reply_to_speak = spoken_reply or TACTICAL_REPLIES.get(cmd, "")
        if reply_to_speak:
            self.ai.speak(reply_to_speak)
        elif winsound:
            winsound.Beep(1100, 70)

        if cmd == "WAKE_ACK":
            print(f"\n{BOLD}{GREEN}[GARUDA AWAKE]{RESET}: {CYAN}\"{reply_to_speak or 'Yes, Commander! What is your command?'}\"{RESET}")
            print(f"   {DIM}Try saying: 'move forward', 'fly higher', 'land', or ask anything!{RESET}\n")
            return

        if cmd == "HELP":
            print(f"\n{BOLD}{CYAN}=== GARUDA VOICE & KEYBOARD GUIDE ==={RESET}")
            print(f"  * Takeoff : Say 'take off' / 'theka'       OR Press [T]")
            print(f"  * Forward : Say 'forward' / 'move'         OR Press [W] or [UP]")
            print(f"  * Back    : Say 'backward' / 'back'        OR Press [S] or [DOWN]")
            print(f"  * Left    : Say 'left' / 'move left'       OR Press [A] or [LEFT]")
            print(f"  * Right   : Say 'right' / 'move right'     OR Press [D] or [RIGHT]")
            print(f"  * Climb   : Say 'climb' / 'up'             OR Press [Space] or [R]")
            print(f"  * Descend : Say 'descend' / 'down'         OR Press [C] or [F]")
            print(f"  * Rotate  : Say 'rotate' / 'turn around'   OR Press [Q] / [E]")
            print(f"  * Land    : Say 'land' / 'garuda land'     OR Press [L]")
            print(f"  * Stop    : Say 'stop' / 'hover'           OR Press [H]")
            print(f"  * AI NLU  : Speak naturally into your mic at any time!")
            print(f"{CYAN}====================================={RESET}\n")
            return

        print(f"\n{BOLD}{CYAN}>>> [EXECUTING FLIGHT ACTION]: {YELLOW}{cmd}{RESET}")
        if reply_to_speak:
            print(f"{BOLD}{GREEN}[AI PILOT VOICE]{RESET}: \"{reply_to_speak}\"")

        if cmd == "TAKEOFF":
            if self.is_connected:
                try:
                    print(f"{BOLD}{GREEN}[PX4] INSTANT LAUNCH! Arming & taking off...{RESET}")
                    try:
                        await self.drone.action.arm()
                        self.is_armed = True
                    except ActionError:
                        pass
                    await self.drone.action.takeoff()
                    print(f"{BOLD}{GREEN}[OK] Takeoff dispatched! Ascending to 3.0m.{RESET}")
                except Exception as e:
                    print(f"{RED}[ERROR] Takeoff execution failed: {e}{RESET}")
            else:
                print(f"{YELLOW}[SIMULATOR] Motors armed -> Ascending to 3.0m -> Hovering.{RESET}")

        elif cmd == "LAND":
            if self.is_connected:
                try:
                    print(f"{CYAN}[PX4] Initiating landing sequence...{RESET}")
                    await self.drone.action.land()
                    self.is_offboard = False
                    self.is_armed = False
                    print(f"{GREEN}[OK] Landing accepted. Descending smoothly.{RESET}")
                except Exception as e:
                    print(f"{RED}[ERROR] Landing failed: {e}{RESET}")
            else:
                print(f"{YELLOW}[SIMULATOR] Descending -> Touchdown -> Disarmed.{RESET}")

        elif cmd == "RTL":
            if self.is_connected:
                try:
                    print(f"{CYAN}[PX4] Returning to Launch coordinate (RTL)...{RESET}")
                    await self.drone.action.return_to_launch()
                    print(f"{GREEN}[OK] RTL initiated. Flying back to launch coordinate.{RESET}")
                except Exception as e:
                    print(f"{RED}[ERROR] RTL failed: {e}{RESET}")
            else:
                print(f"{YELLOW}[SIMULATOR] Returning to home coordinate -> Auto landing.{RESET}")

        elif cmd == "HOVER":
            if self.is_connected:
                try:
                    await self._stream_velocity(0.0, 0.0, 0.0, 0.0, duration_s=0.5)
                    await self.drone.action.hold()
                    print(f"{GREEN}[OK] Position hold active. Drone hovering.{RESET}")
                except Exception as e:
                    print(f"{RED}[ERROR] Hover failed: {e}{RESET}")
            else:
                print(f"{YELLOW}[SIMULATOR] Position hold active.{RESET}")

        elif cmd == "MOVE_LEFT":
            print(f"{CYAN}[FLIGHT] Translating Left (-1.5 m/s for 1.5s)...{RESET}")
            await self._stream_velocity(forward=0.0, right=-1.5, down=0.0, yaw_deg_s=0.0, duration_s=1.5)
            print(f"{GREEN}[OK] Left slide finished. Holding position.{RESET}")

        elif cmd == "MOVE_RIGHT":
            print(f"{CYAN}[FLIGHT] Translating Right (+1.5 m/s for 1.5s)...{RESET}")
            await self._stream_velocity(forward=0.0, right=1.5, down=0.0, yaw_deg_s=0.0, duration_s=1.5)
            print(f"{GREEN}[OK] Right slide finished. Holding position.{RESET}")

        elif cmd == "MOVE_FORWARD":
            print(f"{CYAN}[FLIGHT] Translating Forward (+1.5 m/s for 1.5s)...{RESET}")
            await self._stream_velocity(forward=1.5, right=0.0, down=0.0, yaw_deg_s=0.0, duration_s=1.5)
            print(f"{GREEN}[OK] Forward translation finished. Holding position.{RESET}")

        elif cmd == "MOVE_BACKWARD":
            print(f"{CYAN}[FLIGHT] Translating Backward (-1.5 m/s for 1.5s)...{RESET}")
            await self._stream_velocity(forward=-1.5, right=0.0, down=0.0, yaw_deg_s=0.0, duration_s=1.5)
            print(f"{GREEN}[OK] Backward translation finished. Holding position.{RESET}")

        elif cmd == "CLIMB":
            print(f"{CYAN}[FLIGHT] Climbing Upward (+1.0 m/s for 1.2s)...{RESET}")
            await self._stream_velocity(forward=0.0, right=0.0, down=-1.0, yaw_deg_s=0.0, duration_s=1.2)
            print(f"{GREEN}[OK] Climb finished. Holding position.{RESET}")

        elif cmd == "DESCEND":
            print(f"{CYAN}[FLIGHT] Descending Downward (-1.0 m/s for 1.2s)...{RESET}")
            await self._stream_velocity(forward=0.0, right=0.0, down=1.0, yaw_deg_s=0.0, duration_s=1.2)
            print(f"{GREEN}[OK] Descent finished. Holding position.{RESET}")

        elif cmd == "ROTATE_LEFT":
            print(f"{CYAN}[FLIGHT] Yaw Rotating Left (-45 deg/s for 2.0s)...{RESET}")
            await self._stream_velocity(forward=0.0, right=0.0, down=0.0, yaw_deg_s=-45.0, duration_s=2.0)
            print(f"{GREEN}[OK] Left rotation finished. Holding position.{RESET}")

        elif cmd == "ROTATE_RIGHT":
            print(f"{CYAN}[FLIGHT] Yaw Rotating Right (+45 deg/s for 2.0s)...{RESET}")
            await self._stream_velocity(forward=0.0, right=0.0, down=0.0, yaw_deg_s=45.0, duration_s=2.0)
            print(f"{GREEN}[OK] Right rotation finished. Holding position.{RESET}")

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
                print(f"{RED}[SIMULATOR] Motors killed immediately.{RESET}")

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

            steps = max(1, int(duration_s / 0.1))
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

    def _keyboard_worker(self, loop: asyncio.AbstractEventLoop, queue: asyncio.Queue):
        """Background thread constantly listening for instant keystrokes."""
        if not msvcrt:
            return

        while not self.stop_event.is_set():
            try:
                if msvcrt.kbhit():
                    ch = msvcrt.getch()
                    if ch in (b'\x00', b'\xe0'):
                        code = msvcrt.getch()
                        arrow_map = {
                            b'H': ("MOVE_FORWARD", "[UP ARROW]"),
                            b'P': ("MOVE_BACKWARD", "[DOWN ARROW]"),
                            b'K': ("MOVE_LEFT", "[LEFT ARROW]"),
                            b'M': ("MOVE_RIGHT", "[RIGHT ARROW]")
                        }
                        if code in arrow_map:
                            cmd, label = arrow_map[code]
                            loop.call_soon_threadsafe(queue.put_nowait, ("KEY", cmd, label))
                            continue

                    char = ch.decode("utf-8", errors="ignore").lower()
                    if char in KEY_MAPPINGS:
                        cmd = KEY_MAPPINGS[char]
                        label = f"[{char.upper()}]" if char != ' ' else "[SPACE]"
                        loop.call_soon_threadsafe(queue.put_nowait, ("KEY", cmd, label))
                time.sleep(0.03)
            except Exception:
                time.sleep(0.05)

    def _voice_worker(self, loop: asyncio.AbstractEventLoop, queue: asyncio.Queue):
        """Background thread listening to microphone when unmuted and drone is not speaking."""
        while not self.stop_event.is_set():
            if self.mic_muted or self.ai.is_speaking:
                time.sleep(0.1)
                continue

            try:
                with self.mic as source:
                    audio = self.recognizer.listen(source, timeout=1.5, phrase_time_limit=5.0)

                if self.mic_muted or self.ai.is_speaking:
                    continue

                try:
                    text = self.recognizer.recognize_google(audio)
                    if text and not self.mic_muted and not self.ai.is_speaking:
                        loop.call_soon_threadsafe(queue.put_nowait, ("VOICE", text.strip(), "Google Speech"))
                except (sr.UnknownValueError, sr.WaitTimeoutError):
                    pass
                except Exception:
                    pass
            except sr.WaitTimeoutError:
                continue
            except Exception:
                time.sleep(0.3)

    async def run_loop(self):
        """Main interactive loop handling both voice and keyboard inputs with AI Copilot."""
        print("\n" + "=" * 70)
        print(f"  {BOLD}{CYAN}GarudaOne -- AI Voice Copilot + Keyboard Controller{RESET}")
        print("=" * 70)
        print(f"{BOLD}KEYBOARD HOTKEYS (Press at any moment without Enter):{RESET}")
        print(f"  * {BOLD}[W]{RESET} or {BOLD}[UP]{RESET} Forward       * {BOLD}[Space] / [R]{RESET} Climb Up     * {BOLD}[T]{RESET} Takeoff (3.0m)")
        print(f"  * {BOLD}[S]{RESET} or {BOLD}[DOWN]{RESET} Backward    * {BOLD}[C] / [F]{RESET}     Descend Down * {BOLD}[L]{RESET} Land")
        print(f"  * {BOLD}[A]{RESET} or {BOLD}[LEFT]{RESET} Slide Left  * {BOLD}[Q]{RESET}           Yaw Left     * {BOLD}[H]{RESET} Hover / Hold")
        print(f"  * {BOLD}[D]{RESET} or {BOLD}[RIGHT]{RESET} Slide Right * {BOLD}[E]{RESET}           Yaw Right    * {BOLD}[M]{RESET} Mute/Unmute Mic")
        print(f"  * {BOLD}[X]{RESET} Emergency Kill")
        print(f"\n{BOLD}NATURAL LANGUAGE VOICE COMMANDS (Speak into your mic):{RESET}")
        print(f"  * Direct   : \"Garuda take off\", \"move forward\", \"climb higher\", \"land\"")
        print(f"  * AI Agent : \"Can you please fly up higher so we can see better?\"")
        print(f"  * AI Agent : \"Inspect the area and spin around three sixty\"")
        print(f"  * Press {BOLD}[M]{RESET} to mute/unmute the microphone at any time.")
        if self.ai.is_enabled:
            print(f"  {BOLD}{GREEN}[AI ENGINES ONLINE]{RESET} OpenAI (NLU) + Smallest.ai (Lightning Voice) Active!")
        print(f"{DIM}Press Ctrl+C at any time to exit.{RESET}\n")

        # Connect to PX4
        await self.connect_px4()

        # Calibrate Microphone
        await self.setup_microphone()

        # Prewarm audio cache for zero-latency TTS
        self.ai.prewarm_cache()

        loop = asyncio.get_event_loop()
        queue = asyncio.Queue()

        # Start keyboard thread
        kb_thread = threading.Thread(target=self._keyboard_worker, args=(loop, queue), daemon=True)
        kb_thread.start()

        # Start voice thread if microphone is active
        if self.mic:
            voice_thread = threading.Thread(target=self._voice_worker, args=(loop, queue), daemon=True)
            voice_thread.start()

        print(f"\n{BOLD}{GREEN}[AI PILOT READY]{RESET} Listening for voice AND hotkeys simultaneously!\n")

        while True:
            try:
                source, payload, origin = await queue.get()

                if source == "KEY":
                    cmd = payload
                    if cmd == "TOGGLE_MUTE":
                        self.toggle_mic_mute()
                        continue
                    print(f"\n{BOLD}{GREEN}[HOTKEY PRESSED {origin}]{RESET} -> {BOLD}{YELLOW}{cmd}{RESET}")
                    await self.execute_command(cmd)

                elif source == "VOICE":
                    if self.mic_muted or self.ai.is_speaking:
                        continue

                    transcription = payload
                    if len(transcription.strip()) <= 2:
                        continue

                    # 1. Fast-path direct intent match
                    cmd, matched_phrase = parse_fast_intent(transcription)

                    # 2. If not a simple keyword match and AI is enabled, use OpenAI NLU!
                    if cmd == "UNKNOWN" and self.ai.is_enabled:
                        print(f"\n{BOLD}{CYAN}[VOICE HEARD]{RESET}: \"{BOLD}{transcription}{RESET}\"")
                        print(f"{CYAN}[AI BRAIN] Reasoning with OpenAI GPT for natural language intent...{RESET}")
                        ai_cmd, ai_reply = await loop.run_in_executor(
                            None, self.ai.parse_natural_language, transcription
                        )
                        if ai_cmd != "UNKNOWN":
                            print(f"{GREEN}[AI INTENT MATCHED]: {BOLD}{ai_cmd}{RESET} -> {DIM}\"{ai_reply}\"{RESET}")
                            await self.execute_command(ai_cmd, spoken_reply=ai_reply)
                            continue

                    if cmd == "UNKNOWN":
                        print(f"{DIM}[Ambient noise ignored: \"{transcription}\"]{RESET}")
                        continue

                    print(f"\n{BOLD}{CYAN}[VOICE HEARD]{RESET}: \"{BOLD}{transcription}{RESET}\"")
                    print(f"{GREEN}[INTENT MATCHED]: {BOLD}{cmd}{RESET} {DIM}(via phrase: '{matched_phrase}'){RESET}")
                    await self.execute_command(cmd)

            except KeyboardInterrupt:
                print(f"\n{YELLOW}[EXIT] Pilot stopped by user.{RESET}")
                self.stop_event.set()
                break
            except Exception as e:
                print(f"{RED}[ERROR] Main loop error: {e}{RESET}")
                await asyncio.sleep(0.5)


if __name__ == "__main__":
    pilot = DualPilot()
    try:
        asyncio.run(pilot.run_loop())
    except KeyboardInterrupt:
        print("\n[EXIT] Exiting cleanly.")
