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
        """Load Needle 26M for command classification."""
        model_path = self.config.models_dir / self.config.get(
            "tool_router.model_file", "needle-26m.Q4_0.gguf"
        )

        if model_path.exists():
            # TODO: Load via llama.cpp with small context
            self._needle_loaded = True
            log.info(f"✓ Needle 26M model found: {model_path.name}")
            return True
        else:
            log.info("Needle 26M not found — using keyword matching only")
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
        """Classify command using Needle 26M."""
        # TODO: Run Needle inference via llama.cpp
        # For now, return None to fall through to LFM
        return None

    async def _dispatch(self, tool_call: dict) -> None:
        """Publish the tool call event to the event bus."""
        await self.bus.publish(Event(
            type=EventType.TOOL_CALL_REQUESTED,
            data=tool_call,
            source="router",
        ))
