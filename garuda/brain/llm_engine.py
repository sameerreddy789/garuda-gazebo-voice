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
    LFM-2.5-230M language model interface.

    Backend priority:
      1. llama-cpp-python (preferred — native Python bindings, fastest)
      2. llama-cli subprocess (fallback — if only the binary is built)
      3. Stub keyword matcher (development without model)

    The model stays loaded in memory between commands for low latency.
    Conversation history is maintained for multi-turn context.
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

        # Backend state
        self._llm = None  # llama_cpp.Llama instance
        self._backend = "none"  # "python", "subprocess", "stub"
        self._loaded = False

        # Conversation history (for context window)
        self._history: list[dict] = []

        log.info(f"LLM engine initialized — model: {self._model_path.name}")

    def load_model(self) -> bool:
        """
        Load the LFM model. Tries llama-cpp-python first (preferred),
        then checks for the llama-cli binary, then falls back to stub.

        Returns True if any backend is available.
        """
        if not self._model_path.exists():
            log.warning(
                f"LLM model not found at {self._model_path} — "
                f"run 'python scripts/download_models.py' to download"
            )
            self._loaded = True
            self._backend = "stub"
            log.info("Using STUB LLM (keyword-based responses)")
            return True

        # Attempt 1: llama-cpp-python (native bindings)
        try:
            from llama_cpp import Llama

            # Use a smaller context for actual inference to save memory
            n_ctx = min(self._context_length, 4096)
            self._llm = Llama(
                model_path=str(self._model_path),
                n_ctx=n_ctx,
                n_threads=self._threads,
                n_gpu_layers=0,  # CPU-only per architecture
                verbose=False,
            )
            self._loaded = True
            self._backend = "python"
            log.info(
                f"✓ LLM loaded via llama-cpp-python "
                f"(ctx={n_ctx}, threads={self._threads})"
            )
            return True

        except ImportError:
            log.info(
                "llama-cpp-python not installed. "
                "Install: pip install llama-cpp-python"
            )
        except Exception as e:
            log.warning(f"llama-cpp-python load failed: {e}")

        # Attempt 2: llama-cli subprocess (fallback)
        if self._find_llama_binary():
            self._loaded = True
            self._backend = "subprocess"
            log.info("✓ LLM will use llama-cli subprocess")
            return True

        # Attempt 3: Stub
        self._loaded = True
        self._backend = "stub"
        log.info("Using STUB LLM (keyword-based responses)")
        return True

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
        Run inference using the active backend.

        Dispatches to:
          - _infer_python()  for llama-cpp-python
          - _infer_subprocess() for llama-cli binary
          - _stub_response() for development without model
        """
        if self._backend == "python":
            return await self._infer_python(prompt)
        elif self._backend == "subprocess":
            return await self._infer_subprocess(prompt)
        else:
            return self._stub_response(prompt)

    async def _infer_python(self, prompt: str) -> Optional[str]:
        """Run inference via llama-cpp-python (native bindings).

        Runs in a thread executor to avoid blocking the asyncio loop
        during CPU-bound inference.
        """
        try:
            loop = asyncio.get_event_loop()
            response = await loop.run_in_executor(
                None, self._infer_python_sync, prompt
            )
            return response
        except Exception as e:
            log.error(f"Python LLM inference failed: {e}")
            return None

    def _infer_python_sync(self, prompt: str) -> Optional[str]:
        """Synchronous llama-cpp-python inference (called from executor)."""
        try:
            response = self._llm(
                prompt,
                max_tokens=self._max_tokens,
                temperature=self._temperature,
                stop=["<|user|>", "<|system|>"],
                echo=False,
            )
            # Extract text from response
            if "choices" in response and len(response["choices"]) > 0:
                return response["choices"][0]["text"].strip()
            return None
        except Exception as e:
            log.error(f"llama-cpp-python inference error: {e}")
            return None

    async def _infer_subprocess(self, prompt: str) -> Optional[str]:
        """Run inference via llama-cli subprocess (fallback backend)."""
        try:
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
