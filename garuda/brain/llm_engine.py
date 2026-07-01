"""
GarudaOne DroneOS — LLM Engine (LFM-2.5-230M via llama.cpp)
=============================================================
The "director" brain of the drone. Understands complex natural language
commands and outputs structured JSON tool calls.

Example:
  Input:  "Film me from the left while I walk toward the bridge"
  Output: {"tool": "track_subject", "args": {"offset_angle": 90, "distance": 5.0}}

LFM-2.5-230M is a 230-million parameter Liquid Foundation Model by Liquid AI.
It runs at 42 tokens/second on the RPi5 via llama.cpp in GGUF format.
The 32K context window lets it remember the entire mission history.

For simple commands ("Stop", "Land"), Needle 26M handles them instantly
without waking up the heavy LFM — see tool_router.py.
"""

import asyncio
import json
import subprocess
import os
from typing import Optional

from garuda.core.config import Config
from garuda.core.events import Event, EventBus, EventType
from garuda.utils.logger import get_logger

log = get_logger("brain")


# System prompt that defines the drone's "personality" and available tools
SYSTEM_PROMPT = """You are GarudaOne, an autonomous AI cinematography drone.
You receive voice commands from a content creator and output JSON tool calls.

Available tools:
- takeoff(altitude: float) — Take off to specified altitude in meters
- land() — Land at current position
- rtl() — Return to launch position and land
- hover() — Hold current position
- track_subject(distance: float, framing: str) — Follow the subject
  - distance: follow distance in meters (2-20)
  - framing: "tight", "medium", "wide"
- orbit(radius: float, speed: float, direction: str) — Orbit around subject
  - radius: orbit radius in meters
  - speed: orbit speed in m/s
  - direction: "clockwise" or "counterclockwise"
- chase(distance: float) — Follow behind the subject
- reveal(speed: float, distance: float) — Cinematic reveal shot (pull back + rise)
- start_recording() — Start recording video
- stop_recording() — Stop recording video
- emergency_stop() — Kill all motors immediately

Respond ONLY with a JSON object: {"tool": "<name>", "args": {<arguments>}}
If you don't understand the command, respond: {"tool": "hover", "args": {}}
"""


class LLMEngine:
    """
    LFM-2.5-230M language model interface via llama.cpp.

    Runs the model as a subprocess using the llama-cli binary.
    Keeps the process alive between commands to avoid reload overhead.
    """

    def __init__(self, config: Config, event_bus: EventBus):
        self.config = config
        self.bus = event_bus

        # Model settings
        models_dir = config.models_dir
        self._model_path = models_dir / config.get(
            "llm.model_file", "lfm-2.5-230m.Q4_K_M.gguf"
        )
        self._context_length = config.get("llm.context_length", 32768)
        self._max_tokens = config.get("llm.max_tokens", 512)
        self._temperature = config.get("llm.temperature", 0.1)
        self._threads = config.get("llm.threads", 4)

        # Process state
        self._process: Optional[subprocess.Popen] = None
        self._loaded = False

        # Conversation history (for context window)
        self._history: list[dict] = []

        log.info(f"LLM engine initialized — model: {self._model_path.name}")

    def load_model(self) -> bool:
        """
        Check if the model file exists. The actual llama.cpp process
        is started on first inference to avoid unnecessary memory usage.
        """
        if self._model_path.exists():
            self._loaded = True
            log.info(f"✓ LLM model found: {self._model_path.name}")
            return True
        else:
            log.warning(
                f"LLM model not found at {self._model_path} — "
                f"run 'python scripts/download_models.py' to download"
            )
            self._loaded = False
            return False

    async def process_command(self, text: str) -> Optional[dict]:
        """
        Process a voice command through the LLM.

        Args:
            text: Transcribed voice command text

        Returns:
            Parsed tool call dict: {"tool": "...", "args": {...}}
            or None if processing failed
        """
        if not self._loaded:
            log.warning("LLM not loaded — falling back to intent parser")
            return None

        log.info(f"LLM processing: \"{text}\"")

        # Build prompt
        prompt = self._build_prompt(text)

        # Run inference
        response = await self._infer(prompt)

        if response:
            # Parse JSON tool call from response
            tool_call = self._parse_tool_call(response)

            if tool_call:
                log.info(f"LLM tool call: {tool_call}")

                # Add to history
                self._history.append({"role": "user", "content": text})
                self._history.append({"role": "assistant", "content": response})

                # Trim history to keep within context window
                self._trim_history()

                # Publish tool call event
                await self.bus.publish(Event(
                    type=EventType.TOOL_CALL_REQUESTED,
                    data=tool_call,
                    source="brain",
                ))

                return tool_call

        log.warning(f"LLM failed to parse command: \"{text}\"")
        return None

    def _build_prompt(self, user_text: str) -> str:
        """Build the full prompt with system instructions and history."""
        parts = [f"<|system|>\n{SYSTEM_PROMPT}\n"]

        # Add conversation history (for multi-turn context)
        for msg in self._history[-10:]:  # Last 10 exchanges
            role = msg["role"]
            content = msg["content"]
            parts.append(f"<|{role}|>\n{content}\n")

        parts.append(f"<|user|>\n{user_text}\n")
        parts.append("<|assistant|>\n")

        return "".join(parts)

    async def _infer(self, prompt: str) -> Optional[str]:
        """
        Run inference via llama.cpp subprocess.

        Uses llama-cli (the llama.cpp command-line tool) which
        loads the GGUF model and runs inference on CPU.
        """
        try:
            # Find llama-cli binary
            llama_bin = self._find_llama_binary()
            if not llama_bin:
                log.warning("llama-cli binary not found — using stub response")
                return self._stub_response(prompt)

            cmd = [
                llama_bin,
                "-m", str(self._model_path),
                "-p", prompt,
                "-n", str(self._max_tokens),
                "-t", str(self._threads),
                "--temp", str(self._temperature),
                "--ctx-size", str(min(self._context_length, 4096)),
                "--no-display-prompt",
                "--log-disable",
            ]

            # Run as async subprocess
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )

            stdout, stderr = await asyncio.wait_for(
                proc.communicate(), timeout=30.0
            )

            if proc.returncode == 0:
                return stdout.decode("utf-8").strip()
            else:
                log.error(f"llama-cli error: {stderr.decode('utf-8')}")
                return None

        except asyncio.TimeoutError:
            log.error("LLM inference timed out (>30s)")
            return None
        except Exception as e:
            log.error(f"LLM inference failed: {e}")
            return None

    def _find_llama_binary(self) -> Optional[str]:
        """Find the llama-cli binary on the system."""
        # Check common locations
        candidates = [
            "llama-cli",
            "/usr/local/bin/llama-cli",
            os.path.expanduser("~/llama.cpp/build/bin/llama-cli"),
            os.path.expanduser("~/llama.cpp/llama-cli"),
        ]

        for candidate in candidates:
            if os.path.isfile(candidate) and os.access(candidate, os.X_OK):
                return candidate

        return None

    def _stub_response(self, prompt: str) -> str:
        """
        Stub LLM response for development without the model.
        Extracts basic intent from the prompt using keyword matching.
        """
        prompt_lower = prompt.lower()

        if "orbit" in prompt_lower or "circle" in prompt_lower:
            return '{"tool": "orbit", "args": {"radius": 8.0, "speed": 2.0, "direction": "clockwise"}}'
        elif "follow" in prompt_lower or "track" in prompt_lower:
            return '{"tool": "track_subject", "args": {"distance": 5.0, "framing": "medium"}}'
        elif "take off" in prompt_lower or "takeoff" in prompt_lower:
            return '{"tool": "takeoff", "args": {"altitude": 3.0}}'
        elif "land" in prompt_lower:
            return '{"tool": "land", "args": {}}'
        elif "reveal" in prompt_lower:
            return '{"tool": "reveal", "args": {"speed": 2.0, "distance": 15.0}}'
        elif "stop" in prompt_lower:
            return '{"tool": "hover", "args": {}}'
        elif "home" in prompt_lower or "return" in prompt_lower:
            return '{"tool": "rtl", "args": {}}'
        elif "record" in prompt_lower:
            return '{"tool": "start_recording", "args": {}}'
        else:
            return '{"tool": "hover", "args": {}}'

    def _parse_tool_call(self, response: str) -> Optional[dict]:
        """Parse a JSON tool call from the LLM response text."""
        # Try to extract JSON from the response
        try:
            # Direct JSON parse
            result = json.loads(response)
            if "tool" in result:
                return result
        except json.JSONDecodeError:
            pass

        # Try to find JSON within the response text
        try:
            start = response.index("{")
            end = response.rindex("}") + 1
            json_str = response[start:end]
            result = json.loads(json_str)
            if "tool" in result:
                return result
        except (ValueError, json.JSONDecodeError):
            pass

        return None

    def _trim_history(self) -> None:
        """Trim conversation history to stay within context limits."""
        # Simple approach: keep last 20 exchanges
        max_history = 40  # 20 user + 20 assistant
        if len(self._history) > max_history:
            self._history = self._history[-max_history:]
