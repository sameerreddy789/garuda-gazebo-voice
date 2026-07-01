"""
GarudaOne DroneOS — Tool Router (Needle 26M)
==============================================
Ultra-fast command routing for simple commands.

The problem: LFM-2.5-230M runs at 42 tok/s. That's fast for complex
commands, but overkill for "Stop" or "Land". You don't want to wait
500ms for a stop command.

The solution: Needle 26M (14MB, INT4) runs at 1,200 tok/s. It handles
simple commands in under 20ms. Complex commands are forwarded to the LFM.

Decision flow:
  Voice command → Needle 26M
    ├── Simple command? → Direct tool call (< 20ms)
    └── Complex command? → Forward to LFM-2.5-230M (200-500ms)
"""

import json
from typing import Optional

from garuda.core.config import Config
from garuda.core.events import Event, EventBus, EventType
from garuda.utils.logger import get_logger

log = get_logger("router")


# Simple commands that Needle handles directly (no LFM needed)
SIMPLE_COMMANDS = {
    "stop":             {"tool": "hover", "args": {}},
    "halt":             {"tool": "hover", "args": {}},
    "hover":            {"tool": "hover", "args": {}},
    "land":             {"tool": "land", "args": {}},
    "come down":        {"tool": "land", "args": {}},
    "take off":         {"tool": "takeoff", "args": {"altitude": 3.0}},
    "takeoff":          {"tool": "takeoff", "args": {"altitude": 3.0}},
    "go home":          {"tool": "rtl", "args": {}},
    "come home":        {"tool": "rtl", "args": {}},
    "return home":      {"tool": "rtl", "args": {}},
    "come back":        {"tool": "rtl", "args": {}},
    "follow me":        {"tool": "track_subject", "args": {"distance": 5.0, "framing": "medium"}},
    "follow":           {"tool": "track_subject", "args": {"distance": 5.0, "framing": "medium"}},
    "orbit":            {"tool": "orbit", "args": {"radius": 8.0, "speed": 2.0, "direction": "clockwise"}},
    "circle":           {"tool": "orbit", "args": {"radius": 8.0, "speed": 2.0, "direction": "clockwise"}},
    "chase":            {"tool": "chase", "args": {"distance": 5.0}},
    "record":           {"tool": "start_recording", "args": {}},
    "start recording":  {"tool": "start_recording", "args": {}},
    "stop recording":   {"tool": "stop_recording", "args": {}},
    "cut":              {"tool": "stop_recording", "args": {}},
    "reveal":           {"tool": "reveal", "args": {"speed": 2.0, "distance": 15.0}},
    "emergency":        {"tool": "emergency_stop", "args": {}},
    "emergency stop":   {"tool": "emergency_stop", "args": {}},
    "kill":             {"tool": "emergency_stop", "args": {}},
}


class ToolRouter:
    """
    Fast-path command router.

    Step 1: Check if the command matches a simple keyword → instant dispatch
    Step 2: If not simple, send to Needle 26M for classification
    Step 3: If Needle can't handle it, forward to LFM-2.5-230M
    """

    def __init__(self, config: Config, event_bus: EventBus):
        self.config = config
        self.bus = event_bus

        # Needle model state
        self._needle_model = None
        self._needle_loaded = False

        # Reference to LLM engine (set later)
        self._llm_engine = None

        log.info(f"Tool router initialized — {len(SIMPLE_COMMANDS)} fast commands")

    def set_llm_engine(self, llm_engine) -> None:
        """Set reference to the LLM engine for complex command forwarding."""
        self._llm_engine = llm_engine

    def load_needle_model(self) -> bool:
        """Load Needle 26M for command classification.

        Tries llama-cpp-python first (fast, in-memory), then falls back
        to keyword-only matching if the model isn't available.
        """
        model_path = self.config.models_dir / self.config.get(
            "tool_router.model_file", "needle-26m.Q4_0.gguf"
        )

        if not model_path.exists():
            log.info(
                f"Needle 26M not found ({model_path.name}) — "
                f"using keyword matching only"
            )
            return True  # Non-fatal

        # Try llama-cpp-python
        try:
            from llama_cpp import Llama

            self._needle_model = Llama(
                model_path=str(model_path),
                n_ctx=512,  # Needle needs tiny context for classification
                n_threads=2,
                n_gpu_layers=0,
                verbose=False,
            )
            self._needle_loaded = True
            log.info(f"✓ Needle 26M loaded via llama-cpp-python")
            return True
        except ImportError:
            log.info(
                "llama-cpp-python not installed — Needle 26M disabled. "
                "Install: pip install llama-cpp-python"
            )
        except Exception as e:
            log.warning(f"Needle 26M load failed: {e}")

        return True  # Non-fatal

    async def route_command(self, text: str) -> Optional[dict]:
        """
        Route a voice command to the appropriate handler.

        Fast path (< 5ms): keyword match → direct tool call
        Medium path (< 20ms): Needle 26M classification
        Slow path (200-500ms): LFM-2.5-230M full language understanding

        Args:
            text: Transcribed voice command

        Returns:
            Tool call dict: {"tool": "...", "args": {...}}
        """
        text_lower = text.lower().strip()

        # ── Step 1: Fast keyword match ─────────────────────────────────
        for keyword, tool_call in SIMPLE_COMMANDS.items():
            if keyword in text_lower:
                log.info(f"Fast route: \"{text}\" → {tool_call['tool']}")
                await self._dispatch(tool_call)
                return tool_call

        # ── Step 2: Needle 26M (if loaded) ─────────────────────────────
        if self._needle_loaded:
            result = await self._needle_classify(text)
            if result:
                log.info(f"Needle route: \"{text}\" → {result['tool']}")
                await self._dispatch(result)
                return result

        # ── Step 3: Forward to LFM ─────────────────────────────────────
        if self._llm_engine:
            log.info(f"Complex command — forwarding to LFM: \"{text}\"")
            result = await self._llm_engine.process_command(text)
            return result

        log.warning(f"Could not route command: \"{text}\"")
        return None

    async def _needle_classify(self, text: str) -> Optional[dict]:
        """Classify command using Needle 26M.

        Formats the command as a classification prompt and parses the
        model's response into a tool call dict. Needle runs in a thread
        to avoid blocking the async loop.
        """
        if self._needle_model is None:
            return None

        # Build classification prompt
        # Needle is small but can do few-shot classification
        prompt = self._build_needle_prompt(text)

        try:
            loop = asyncio.get_event_loop()
            response = await loop.run_in_executor(
                None, self._needle_infer, prompt
            )

            if response:
                return self._parse_needle_response(response)
        except Exception as e:
            log.warning(f"Needle classification failed: {e}")

        return None

    def _build_needle_prompt(self, text: str) -> str:
        """Build a few-shot classification prompt for Needle 26M."""
        # Few-shot examples help the small model classify accurately
        examples = (
            "Classify the drone command into one tool.\n\n"
            "Command: take off\nTool: takeoff\n\n"
            "Command: land now\nTool: land\n\n"
            "Command: come home\nTool: rtl\n\n"
            "Command: stop moving\nTool: hover\n\n"
            "Command: follow me\nTool: track_subject\n\n"
            "Command: orbit around me\nTool: orbit\n\n"
            "Command: chase me\nTool: chase\n\n"
            "Command: do a reveal\nTool: reveal\n\n"
            "Command: start recording\nTool: start_recording\n\n"
            f"Command: {text}\nTool:"
        )
        return examples

    def _needle_infer(self, prompt: str) -> Optional[str]:
        """Synchronous Needle inference (called from executor)."""
        try:
            response = self._needle_model(
                prompt,
                max_tokens=10,  # Tool name is short
                temperature=0.0,  # Deterministic for classification
                stop=["\n", "Command:"],
                echo=False,
            )
            if "choices" in response and len(response["choices"]) > 0:
                return response["choices"][0]["text"].strip()
        except Exception as e:
            log.warning(f"Needle inference error: {e}")
        return None

    def _parse_needle_response(self, response: str) -> Optional[dict]:
        """Parse Needle's tool name response into a tool call dict."""
        response_lower = response.lower().strip()

        # Map tool names to default args
        tool_defaults = {
            "takeoff": {"tool": "takeoff", "args": {"altitude": 3.0}},
            "land": {"tool": "land", "args": {}},
            "rtl": {"tool": "rtl", "args": {}},
            "hover": {"tool": "hover", "args": {}},
            "track_subject": {"tool": "track_subject", "args": {"distance": 5.0}},
            "orbit": {"tool": "orbit", "args": {"radius": 8.0, "speed": 2.0}},
            "chase": {"tool": "chase", "args": {"distance": 5.0}},
            "reveal": {"tool": "reveal", "args": {"speed": 2.0, "distance": 15.0}},
            "start_recording": {"tool": "start_recording", "args": {}},
            "stop_recording": {"tool": "stop_recording", "args": {}},
            "emergency_stop": {"tool": "emergency_stop", "args": {}},
        }

        # Find the matching tool
        for tool_name, tool_call in tool_defaults.items():
            if tool_name in response_lower:
                return tool_call

        return None

    async def _dispatch(self, tool_call: dict) -> None:
        """Publish the tool call event to the event bus."""
        await self.bus.publish(Event(
            type=EventType.TOOL_CALL_REQUESTED,
            data=tool_call,
            source="router",
        ))
