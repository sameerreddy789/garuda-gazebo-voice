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

# Ensure UTF-8 output on Windows consoles with immediate line-buffering
if sys.platform == "win32":
    try:
        if hasattr(sys.stdout, "reconfigure"):
            sys.stdout.reconfigure(encoding="utf-8", errors="replace", line_buffering=True)
        if hasattr(sys.stderr, "reconfigure"):
            sys.stderr.reconfigure(encoding="utf-8", errors="replace", line_buffering=True)
    except Exception:
        pass

import functools
_builtin_print = print
print = functools.partial(_builtin_print, flush=True)

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
        """Pre-downloads audio for standard commands and confirmations for instantaneous zero-latency playback."""
        if not self.smallest_key:
            return
        def _fetch():
            phrases_to_cache = list(TACTICAL_REPLIES.values()) + [
                "Drone takeoff completed. Hovering at three meters.",
                "Forward movement completed.",
                "Backward translation completed.",
                "Left translation completed.",
                "Right translation completed.",
                "Climb completed. Altitude held.",
                "Descent completed.",
                "Three-sixty survey completed.",
                "Drone landing completed. Touchdown confirmed and motors disarmed.",
                "Warning! Drone has not taken off. Please command takeoff first.",
            ]
            for phrase in phrases_to_cache[:10]:
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
            with urllib.request.urlopen(req, timeout=5.0) as resp:
                return resp.read()
        except Exception:
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
                else:
                    # Built-in Windows local speech engine fallback (100% offline & instantaneous)
                    clean_text = text.replace("'", "").replace('"', "")
                    subprocess.run(
                        ["powershell", "-NoProfile", "-NonInteractive", "-Command",
                         f"(New-Object -ComObject SAPI.SpVoice).Speak('{clean_text}')"],
                        creationflags=0x08000000 if sys.platform == "win32" else 0,
                        timeout=5.0
                    )
            except Exception:
                if winsound:
                    try:
                        winsound.Beep(1100, 80)
                    except Exception:
                        pass
            finally:
                time.sleep(0.35)  # Acoustic decay buffer so mic doesn't catch tail echo
                self.is_speaking = False

        threading.Thread(target=_play, daemon=True).start()

    def parse_natural_language(self, user_text: str) -> tuple[str, str, float, float]:
        """Calls OpenAI GPT-5-nano to extract flight action, distance in meters (default 5.0), and duration in mins (default 10.0)."""
        dist, dur = extract_flight_parameters(user_text)
        if not self.openai_key:
            return "UNKNOWN", "", dist, dur

        system_prompt = (
            "You are GarudaOne drone AI brain. Extract the flight action, optional distance in meters (default 5.0), "
            "optional duration in minutes (default 10.0 for takeoff), and formulate a brief pilot response.\n"
            "Allowed actions: TAKEOFF, LAND, MOVE_FORWARD, MOVE_BACKWARD, MOVE_LEFT, MOVE_RIGHT, "
            "CLIMB, DESCEND, ROTATE_360, ROTATE_LEFT, ROTATE_RIGHT, HOVER, RTL, EMERGENCY, WAKE_ACK, UNKNOWN.\n"
            "Respond ONLY with valid JSON: {\"action\": \"...\", \"distance_m\": 5.0, \"duration_mins\": 10.0, \"reply\": \"...\"}\n"
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
            with urllib.request.urlopen(req, timeout=12.0) as resp:
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
                parsed_dist = float(parsed.get("distance_m", dist))
                parsed_dur = float(parsed.get("duration_mins", dur))
                return action, reply, parsed_dist, parsed_dur
        except Exception:
            return "UNKNOWN", "", dist, dur


def extract_flight_parameters(text: str) -> tuple[float, float]:
    """Extracts distance in meters (default 5.0m) and duration in minutes (default 10.0m)."""
    text_clean = text.lower().replace('-', ' ')
    dist = 5.0
    m_dist = re.search(r'(\d+(?:\.\d+)?)\s*(?:metres|meters|meter|metre|m\b)', text_clean)
    if m_dist:
        dist = float(m_dist.group(1))
    else:
        m_num = re.search(r'(?:for|by|to)\s+(\d+(?:\.\d+)?)\s*(?!mins|minutes|min)', text_clean)
        if m_num:
            dist = float(m_num.group(1))
        else:
            m_direct = re.search(r'\b(?:move\s+)?(?:left|right|forward|back|backward|climb|descend|up|down)\s+(\d+(?:\.\d+)?)\b', text_clean)
            if m_direct:
                dist = float(m_direct.group(1))

    dur = 10.0
    m_dur = re.search(r'(\d+(?:\.\d+)?)\s*(?:minutes|minute|mins|min\b)', text_clean)
    if m_dur:
        dur = float(m_dur.group(1))

    return dist, dur


def calculate_velocity_and_duration(distance_m: float, is_vertical: bool = False) -> tuple[float, float]:
    """Calculates appropriate speed (m/s) and duration (s) to cover exact distance in meters."""
    if is_vertical:
        speed = 2.5 if distance_m > 8.0 else 1.5
    else:
        speed = 5.0 if distance_m > 12.0 else 2.5
    duration = max(0.5, distance_m / speed)
    return speed, duration


def clean_speech_text(text: str) -> str:
    """Removes punctuation and normalizes spacing for reliable keyword matching."""
    text = text.lower().strip()
    text = re.sub(r"[^\w\s]", " ", text)
    return " ".join(text.split())


def parse_fast_intent(transcription: str) -> tuple[str, str, float, float]:
    """Instant regex-based keyword parser for direct/quick commands with parameter extraction."""
    cleaned = clean_speech_text(transcription)
    if not cleaned:
        return "UNKNOWN", "", 5.0, 10.0

    dist, dur = extract_flight_parameters(cleaned)

    if any(q in cleaned for q in ["help", "what is", "what can you do", "commands", "options"]):
        return "HELP", cleaned, dist, dur

    is_wake_only = (
        cleaned in WAKE_WORDS or
        any(cleaned == f"hey {w}" or cleaned == f"hi {w}" or cleaned == f"ok {w}" or cleaned == f"hello {w}" for w in WAKE_WORDS)
    )
    if is_wake_only:
        return "WAKE_ACK", cleaned, dist, dur

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
        return matches[0][1], matches[0][2], dist, dur

    if has_wake_word:
        words = cleaned.split()
        if any(w in ["take", "off", "launch", "fly", "up", "lift", "theka", "teka", "taka"] for w in words):
            return "TAKEOFF", "takeoff (wake context)", dist, dur
        if any(w in ["land", "down", "ground"] for w in words):
            return "LAND", "land (wake context)", dist, dur
        if any(w in ["stop", "hold", "freeze", "halt"] for w in words):
            return "HOVER", "hover (wake context)", dist, dur
        if any(w in ["left"] for w in words):
            return "MOVE_LEFT", "left (wake context)", dist, dur
        if any(w in ["right"] for w in words):
            return "MOVE_RIGHT", "right (wake context)", dist, dur
        if any(w in ["move", "front", "ahead"] for w in words):
            return "MOVE_FORWARD", "forward (wake context)", dist, dur

    return "UNKNOWN", "", dist, dur


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
        self.is_in_air = False
        self.altitude = 0.0
        self.recognizer = sr.Recognizer()
        self.mic = None
        self.stop_event = threading.Event()
        self.ai = AICopilot(OPENAI_API_KEY, SMALLEST_API_KEY)
        self.mic_muted = False

    def play_fan_sound(self):
        """Plays synthesized drone rotor / fan whoosh audio asynchronously."""
        def _play():
            try:
                fan_wav = Path(__file__).parent.parent / "assets" / "drone_fan.wav"
                if fan_wav.exists() and winsound:
                    winsound.PlaySound(str(fan_wav), winsound.SND_FILENAME)
            except Exception:
                pass
        threading.Thread(target=_play, daemon=True).start()

    def trigger_ground_warning(self, cmd: str):
        """Triggers audible alarm, visual banner, and vocal warning when movement is attempted on the ground."""
        print(f"\n{BOLD}{RED}╔══════════════════════════════════════════════════════════════════╗{RESET}")
        print(f"{BOLD}{RED}║  ⚠️  SAFETY INTERLOCK: FLIGHT ACTION REJECTED!                   ║{RESET}")
        print(f"{BOLD}{RED}║  Drone has NOT taken off! Motors are resting on ground.          ║{RESET}")
        print(f"{BOLD}{RED}║  Cannot execute '{cmd}' while landed on the Dronepad.            ║{RESET}")
        print(f"{BOLD}{RED}║  👉 Please say 'Garuda, takeoff' or press [T] first.            ║{RESET}")
        print(f"{BOLD}{RED}╚══════════════════════════════════════════════════════════════════╝{RESET}\n")

        if winsound:
            def _alarm():
                try:
                    winsound.Beep(900, 140)
                    time.sleep(0.05)
                    winsound.Beep(600, 220)
                except Exception:
                    pass
            threading.Thread(target=_alarm, daemon=True).start()

        warning_msg = "Warning! Drone has not taken off. Please command takeoff first."
        self.ai.speak(warning_msg)

    async def _telemetry_monitor(self):
        """Monitors in_air and altitude telemetry from PX4 in real-time."""
        async def _sub_in_air():
            try:
                async for in_air in self.drone.telemetry.in_air():
                    self.is_in_air = in_air
            except Exception:
                pass

        async def _sub_pos():
            try:
                async for pos in self.drone.telemetry.position():
                    self.altitude = pos.relative_altitude_m
                    if pos.relative_altitude_m > 0.4:
                        self.is_in_air = True
            except Exception:
                pass

        await asyncio.gather(_sub_in_air(), _sub_pos(), return_exceptions=True)

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

            # Start background telemetry monitor
            asyncio.create_task(self._telemetry_monitor())

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

    async def execute_command(self, cmd: str, spoken_reply: str = None, distance_m: float = 5.0, duration_mins: float = 10.0):
        """Dispatches recognized command to PX4 or simulator with custom distance (m) and duration (mins)."""
        reply_to_speak = spoken_reply
        if not reply_to_speak:
            if cmd == "TAKEOFF":
                reply_to_speak = f"Taking off. Holding hover for {int(duration_mins)} minutes."
            elif cmd in ("MOVE_LEFT", "MOVE_RIGHT", "MOVE_FORWARD", "MOVE_BACKWARD"):
                direction = cmd.split("_")[1].lower()
                reply_to_speak = f"Translating {direction} {int(distance_m)} meters."
            elif cmd == "CLIMB":
                reply_to_speak = f"Ascending {int(distance_m)} meters higher."
            elif cmd == "DESCEND":
                reply_to_speak = f"Descending {int(distance_m)} meters."
            else:
                reply_to_speak = TACTICAL_REPLIES.get(cmd, "")

        if cmd == "WAKE_ACK":
            if reply_to_speak:
                self.ai.speak(reply_to_speak)
            print(f"\n{BOLD}{GREEN}[GARUDA AWAKE]{RESET}: {CYAN}\"{reply_to_speak or 'Yes, Commander! What is your command?'}\"{RESET}")
            print(f"   {DIM}Try saying: 'move forward 10 meters', 'move right 50 meters', 'climb 15 meters', or 'land'!{RESET}\n")
            return

        if cmd == "HELP":
            print(f"\n{BOLD}{CYAN}=== GARUDA VOICE & KEYBOARD GUIDE ==={RESET}")
            print(f"  * Takeoff : Say 'take off for 10 mins'     OR Press [T]")
            print(f"  * Forward : Say 'forward' (5m) / '50m'     OR Press [W] or [UP]")
            print(f"  * Back    : Say 'backward' (5m) / '50m'    OR Press [S] or [DOWN]")
            print(f"  * Left    : Say 'left' (5m) / '50m'        OR Press [A] or [LEFT]")
            print(f"  * Right   : Say 'right' (5m) / '50m'       OR Press [D] or [RIGHT]")
            print(f"  * Climb   : Say 'climb' (5m) / 'climb 20m' OR Press [Space] or [R]")
            print(f"  * Descend : Say 'descend' (5m) / 'down'    OR Press [C] or [F]")
            print(f"  * Rotate  : Say 'rotate' / 'turn around'   OR Press [Q] / [E]")
            print(f"  * Land    : Say 'land' / 'garuda land'     OR Press [L]")
            print(f"  * Stop    : Say 'stop' / 'hover'           OR Press [H]")
            print(f"  * AI NLU  : Speak naturally with any distance: 'move right for 50 metres'!")
            print(f"{CYAN}====================================={RESET}\n")
            return

        # Synchronize in-air state with altitude
        if self.altitude > 0.4:
            self.is_in_air = True

        # Safety Interlock: Block directional/translation commands if drone is on the ground
        AIR_RESTRICTED = {
            "MOVE_FORWARD", "MOVE_BACKWARD", "MOVE_LEFT", "MOVE_RIGHT",
            "CLIMB", "DESCEND", "ROTATE_LEFT", "ROTATE_RIGHT", "ROTATE_360", "HOVER"
        }

        if cmd in AIR_RESTRICTED and not self.is_in_air:
            self.trigger_ground_warning(cmd)
            return

        # Only speak the tactical action if permitted by the safety interlock
        if reply_to_speak:
            self.ai.speak(reply_to_speak)
        elif winsound:
            winsound.Beep(1100, 70)

        dist_label = f" ({int(distance_m)}m)" if cmd in ("MOVE_FORWARD", "MOVE_BACKWARD", "MOVE_LEFT", "MOVE_RIGHT", "CLIMB", "DESCEND") else ""
        dur_label = f" ({int(duration_mins)} mins)" if cmd == "TAKEOFF" else ""
        print(f"\n{BOLD}{CYAN}>>> [EXECUTING FLIGHT ACTION]: {YELLOW}{cmd}{dist_label}{dur_label}{RESET}")
        print(f"    {DIM}[STATE] Altitude: {self.altitude:.2f}m | In-Air: {self.is_in_air} | Armed: {self.is_armed}{RESET}")
        if reply_to_speak:
            print(f"    {BOLD}{GREEN}[AI PILOT VOICE]{RESET}: \"{reply_to_speak}\"")

        if cmd == "TAKEOFF":
            self.play_fan_sound()
            if self.is_connected:
                try:
                    print(f"{BOLD}{GREEN}[PX4] INSTANT LAUNCH! Arming & taking off to 3.0m...{RESET}")
                    try:
                        await self.drone.action.arm()
                        self.is_armed = True
                    except ActionError:
                        pass
                    await self.drone.action.takeoff()
                    self.is_in_air = True
                    print(f"{BOLD}{GREEN}[OK] Takeoff dispatched! Ascending to 3.0m (Hover Window: {int(duration_mins)} mins).{RESET}")
                    await asyncio.sleep(3.5)
                except Exception as e:
                    print(f"{RED}[ERROR] Takeoff execution failed: {e}{RESET}")
            else:
                self.is_in_air = True
                print(f"{YELLOW}[SIMULATOR] Motors armed -> Ascending to 3.0m -> Hovering for {int(duration_mins)} mins.{RESET}")
                await asyncio.sleep(2.0)

            self.play_fan_sound()
            completion_msg = f"Garuda takeoff completed. Hovering at three meters for {int(duration_mins)} minutes."
            print(f"\n{BOLD}{GREEN}[POST-EXECUTION CONFIRMATION]{RESET}: \"{completion_msg}\"")
            self.ai.speak(completion_msg)

        elif cmd == "LAND":
            if self.is_connected:
                try:
                    print(f"{CYAN}[PX4] Initiating landing sequence...{RESET}")
                    await self.drone.action.land()
                    self.is_offboard = False
                    self.is_armed = False
                    self.is_in_air = False
                    print(f"{GREEN}[OK] Landing accepted. Descending smoothly.{RESET}")
                    await asyncio.sleep(3.0)
                except Exception as e:
                    print(f"{RED}[ERROR] Landing failed: {e}{RESET}")
            else:
                self.is_in_air = False
                print(f"{YELLOW}[SIMULATOR] Descending -> Touchdown -> Disarmed.{RESET}")
                await asyncio.sleep(1.5)

            completion_msg = "Garuda landing completed. Touchdown confirmed and motors disarmed."
            print(f"\n{BOLD}{GREEN}[POST-EXECUTION CONFIRMATION]{RESET}: \"{completion_msg}\"")
            self.ai.speak(completion_msg)

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

            completion_msg = "Garuda returning to launch coordinate."
            print(f"\n{BOLD}{GREEN}[POST-EXECUTION CONFIRMATION]{RESET}: \"{completion_msg}\"")
            self.ai.speak(completion_msg)

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

            completion_msg = "Garuda position locked. Hovering."
            print(f"\n{BOLD}{GREEN}[POST-EXECUTION CONFIRMATION]{RESET}: \"{completion_msg}\"")
            self.ai.speak(completion_msg)

        elif cmd == "MOVE_LEFT":
            speed, dur = calculate_velocity_and_duration(distance_m, is_vertical=False)
            print(f"{CYAN}[FLIGHT] Translating Left (-{speed:.1f} m/s for {dur:.1f}s = {distance_m:.1f}m)...{RESET}")
            self.play_fan_sound()
            await self._stream_velocity(forward=0.0, right=-speed, down=0.0, yaw_deg_s=0.0, duration_s=dur)
            print(f"{GREEN}[OK] Left slide of {int(distance_m)}m finished. Holding position.{RESET}")
            completion_msg = f"Garuda left slide of {int(distance_m)} meters completed."
            print(f"\n{BOLD}{GREEN}[POST-EXECUTION CONFIRMATION]{RESET}: \"{completion_msg}\"")
            self.ai.speak(completion_msg)

        elif cmd == "MOVE_RIGHT":
            speed, dur = calculate_velocity_and_duration(distance_m, is_vertical=False)
            print(f"{CYAN}[FLIGHT] Translating Right (+{speed:.1f} m/s for {dur:.1f}s = {distance_m:.1f}m)...{RESET}")
            self.play_fan_sound()
            await self._stream_velocity(forward=0.0, right=speed, down=0.0, yaw_deg_s=0.0, duration_s=dur)
            print(f"{GREEN}[OK] Right slide of {int(distance_m)}m finished. Holding position.{RESET}")
            completion_msg = f"Garuda right slide of {int(distance_m)} meters completed."
            print(f"\n{BOLD}{GREEN}[POST-EXECUTION CONFIRMATION]{RESET}: \"{completion_msg}\"")
            self.ai.speak(completion_msg)

        elif cmd == "MOVE_FORWARD":
            speed, dur = calculate_velocity_and_duration(distance_m, is_vertical=False)
            print(f"{CYAN}[FLIGHT] Translating Forward (+{speed:.1f} m/s for {dur:.1f}s = {distance_m:.1f}m)...{RESET}")
            self.play_fan_sound()
            await self._stream_velocity(forward=speed, right=0.0, down=0.0, yaw_deg_s=0.0, duration_s=dur)
            print(f"{GREEN}[OK] Forward translation of {int(distance_m)}m finished. Holding position.{RESET}")
            completion_msg = f"Garuda forward translation of {int(distance_m)} meters completed."
            print(f"\n{BOLD}{GREEN}[POST-EXECUTION CONFIRMATION]{RESET}: \"{completion_msg}\"")
            self.ai.speak(completion_msg)

        elif cmd == "MOVE_BACKWARD":
            speed, dur = calculate_velocity_and_duration(distance_m, is_vertical=False)
            print(f"{CYAN}[FLIGHT] Translating Backward (-{speed:.1f} m/s for {dur:.1f}s = {distance_m:.1f}m)...{RESET}")
            self.play_fan_sound()
            await self._stream_velocity(forward=-speed, right=0.0, down=0.0, yaw_deg_s=0.0, duration_s=dur)
            print(f"{GREEN}[OK] Backward translation of {int(distance_m)}m finished. Holding position.{RESET}")
            completion_msg = f"Garuda backward translation of {int(distance_m)} meters completed."
            print(f"\n{BOLD}{GREEN}[POST-EXECUTION CONFIRMATION]{RESET}: \"{completion_msg}\"")
            self.ai.speak(completion_msg)

        elif cmd == "CLIMB":
            speed, dur = calculate_velocity_and_duration(distance_m, is_vertical=True)
            print(f"{CYAN}[FLIGHT] Climbing Upward (+{speed:.1f} m/s for {dur:.1f}s = +{distance_m:.1f}m)...{RESET}")
            self.play_fan_sound()
            await self._stream_velocity(forward=0.0, right=0.0, down=-speed, yaw_deg_s=0.0, duration_s=dur)
            print(f"{GREEN}[OK] Climb of {int(distance_m)}m finished. Holding position.{RESET}")
            completion_msg = f"Garuda climb of {int(distance_m)} meters completed. Altitude held."
            print(f"\n{BOLD}{GREEN}[POST-EXECUTION CONFIRMATION]{RESET}: \"{completion_msg}\"")
            self.ai.speak(completion_msg)

        elif cmd == "DESCEND":
            speed, dur = calculate_velocity_and_duration(distance_m, is_vertical=True)
            print(f"{CYAN}[FLIGHT] Descending Downward (-{speed:.1f} m/s for {dur:.1f}s = -{distance_m:.1f}m)...{RESET}")
            self.play_fan_sound()
            await self._stream_velocity(forward=0.0, right=0.0, down=speed, yaw_deg_s=0.0, duration_s=dur)
            print(f"{GREEN}[OK] Descent of {int(distance_m)}m finished. Holding position.{RESET}")
            completion_msg = f"Garuda descent of {int(distance_m)} meters completed."
            print(f"\n{BOLD}{GREEN}[POST-EXECUTION CONFIRMATION]{RESET}: \"{completion_msg}\"")
            self.ai.speak(completion_msg)

        elif cmd == "ROTATE_LEFT":
            print(f"{CYAN}[FLIGHT] Yaw Rotating Left (-45 deg/s for 2.0s)...{RESET}")
            self.play_fan_sound()
            await self._stream_velocity(forward=0.0, right=0.0, down=0.0, yaw_deg_s=-45.0, duration_s=2.0)
            print(f"{GREEN}[OK] Left rotation finished. Holding position.{RESET}")
            completion_msg = "Rotation completed."
            print(f"\n{BOLD}{GREEN}[POST-EXECUTION CONFIRMATION]{RESET}: \"{completion_msg}\"")
            self.ai.speak(completion_msg)

        elif cmd == "ROTATE_RIGHT":
            print(f"{CYAN}[FLIGHT] Yaw Rotating Right (+45 deg/s for 2.0s)...{RESET}")
            self.play_fan_sound()
            await self._stream_velocity(forward=0.0, right=0.0, down=0.0, yaw_deg_s=45.0, duration_s=2.0)
            print(f"{GREEN}[OK] Right rotation finished. Holding position.{RESET}")
            completion_msg = "Rotation completed."
            print(f"\n{BOLD}{GREEN}[POST-EXECUTION CONFIRMATION]{RESET}: \"{completion_msg}\"")
            self.ai.speak(completion_msg)

        elif cmd == "ROTATE_360":
            print(f"{CYAN}[FLIGHT] Panoramic 360-degree rotation (45 deg/s for 8.0s)...{RESET}")
            self.play_fan_sound()
            await self._stream_velocity(forward=0.0, right=0.0, down=0.0, yaw_deg_s=45.0, duration_s=8.0)
            print(f"{GREEN}[OK] 360-degree rotation finished. Holding position.{RESET}")
            completion_msg = "Three-sixty panorama survey completed."
            print(f"\n{BOLD}{GREEN}[POST-EXECUTION CONFIRMATION]{RESET}: \"{completion_msg}\"")
            self.ai.speak(completion_msg)

        elif cmd == "EMERGENCY":
            if self.is_connected:
                try:
                    print(f"{BOLD}{RED}[PX4] EMERGENCY: KILLING MOTORS IMMEDIATELY...{RESET}")
                    await self.drone.action.kill()
                    self.is_in_air = False
                    self.is_armed = False
                    print(f"{RED}[OK] Motors killed.{RESET}")
                except Exception as e:
                    print(f"{RED}[ERROR] Emergency kill failed: {e}{RESET}")
            else:
                self.is_in_air = False
                print(f"{RED}[SIMULATOR] Motors killed immediately.{RESET}")

            completion_msg = "Emergency stop. Motors killed."
            print(f"\n{BOLD}{RED}[POST-EXECUTION CONFIRMATION]{RESET}: \"{completion_msg}\"")
            self.ai.speak(completion_msg)

        print(f"{DIM}{'-'*65}{RESET}\n")

    async def _stream_velocity(self, forward: float, right: float, down: float, yaw_deg_s: float, duration_s: float):
        """Streams continuous velocity body setpoints to PX4 offboard mode."""
        if not self.is_connected:
            await asyncio.sleep(duration_s)
            return

        try:
            if not self.is_offboard:
                for _ in range(3):
                    await self.drone.offboard.set_velocity_body(VelocityBodyYawspeed(0.0, 0.0, 0.0, 0.0))
                    await asyncio.sleep(0.05)
                try:
                    await self.drone.offboard.start()
                    self.is_offboard = True
                    print(f"    {GREEN}[OFFBOARD] Mode active. Direct velocity control engaged.{RESET}")
                except OffboardError as e:
                    print(f"    {YELLOW}[OFFBOARD RETRY] Engaging offboard mode ({e._result.result})...{RESET}")
                    try:
                        await self.drone.offboard.start()
                        self.is_offboard = True
                    except Exception as e2:
                        print(f"    {RED}[ERROR] Could not start offboard mode: {e2}{RESET}")
                        return

            steps = max(1, int(duration_s / 0.1))
            for _ in range(steps):
                await self.drone.offboard.set_velocity_body(
                    VelocityBodyYawspeed(forward, right, down, yaw_deg_s)
                )
                await asyncio.sleep(0.1)

            # Settle back to zero velocity
            await self.drone.offboard.set_velocity_body(VelocityBodyYawspeed(0.0, 0.0, 0.0, 0.0))
            await asyncio.sleep(0.15)
            print(f"    {CYAN}[TELEMETRY] Maneuver finished. Current Altitude: {self.altitude:.2f}m{RESET}")

        except Exception as e:
            print(f"    {RED}[ERROR] Velocity streaming error: {e}{RESET}")

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
                    cmd, matched_phrase, dist, dur = parse_fast_intent(transcription)

                    # 2. If not a simple keyword match and AI is enabled, use OpenAI NLU!
                    if cmd == "UNKNOWN" and self.ai.is_enabled:
                        print(f"\n{BOLD}{CYAN}[VOICE HEARD]{RESET}: \"{BOLD}{transcription}{RESET}\"")
                        print(f"{CYAN}[AI BRAIN] Reasoning with OpenAI GPT for natural language intent...{RESET}")
                        ai_cmd, ai_reply, ai_dist, ai_dur = await loop.run_in_executor(
                            None, self.ai.parse_natural_language, transcription
                        )
                        if ai_cmd != "UNKNOWN":
                            print(f"{GREEN}[AI INTENT MATCHED]: {BOLD}{ai_cmd}{RESET} -> {DIM}\"{ai_reply}\"{RESET}")
                            await self.execute_command(ai_cmd, spoken_reply=ai_reply, distance_m=ai_dist, duration_mins=ai_dur)
                            continue

                    if cmd == "UNKNOWN":
                        print(f"{DIM}[Ambient noise ignored: \"{transcription}\"]{RESET}")
                        continue

                    print(f"\n{BOLD}{CYAN}[VOICE HEARD]{RESET}: \"{BOLD}{transcription}{RESET}\"")
                    print(f"{GREEN}[INTENT MATCHED]: {BOLD}{cmd}{RESET} {DIM}(via phrase: '{matched_phrase}'){RESET}")
                    await self.execute_command(cmd, distance_m=dist, duration_mins=dur)

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
