"""
Tests for the voice intent parser and tool router.
Verifies command → tool call mapping for all supported commands.
"""

import pytest
import asyncio

from garuda.core.config import Config
from garuda.core.events import EventBus
from garuda.brain.tool_router import ToolRouter, SIMPLE_COMMANDS
from garuda.voice.pipeline import IntentParser


@pytest.fixture
def config():
    return Config()


@pytest.fixture
def event_bus():
    return EventBus()


class TestIntentParser:
    """Test the keyword-based intent classification."""

    @pytest.fixture
    def parser(self, config):
        return IntentParser(config)

    @pytest.mark.parametrize("text,expected", [
        ("take off", "takeoff"),
        ("Take off now", "takeoff"),
        ("let's take off", "takeoff"),
        ("land", "land"),
        ("come down please", "land"),
        ("go home", "rtl"),
        ("come back", "rtl"),
        ("return home", "rtl"),
        ("hover", "hover"),
        ("stay there", "hover"),
        ("stop", "stop"),
        ("follow me", "follow"),
        ("track me", "follow"),
        ("orbit", "orbit"),
        ("circle around me", "orbit"),
        ("chase me", "chase"),
        ("reveal shot", "reveal"),
        ("start recording", "recording_start"),
        ("action", "recording_start"),
        ("cut", "recording_stop"),
        ("stop recording", "recording_stop"),
        ("emergency stop", "emergency_stop"),
        ("kill", "emergency_stop"),
    ])
    def test_keyword_matching(self, parser, text, expected):
        """Verify keyword → command mapping for all supported phrases."""
        result = parser.classify(text)
        assert result == expected, (
            f"Expected '{text}' → '{expected}', got '{result}'"
        )

    def test_unknown_command_returns_none(self, parser):
        """Unknown phrases should return None (not crash)."""
        result = parser.classify("what is the meaning of life")
        assert result is None

    def test_case_insensitive(self, parser):
        """Commands should work regardless of case."""
        assert parser.classify("TAKE OFF") == "takeoff"
        assert parser.classify("Follow Me") == "follow"
        assert parser.classify("ORBIT") == "orbit"


class TestToolRouter:
    """Test the fast-path tool routing."""

    @pytest.fixture
    def router(self, config, event_bus):
        router = ToolRouter(config, event_bus)
        return router

    def test_simple_commands_defined(self):
        """All essential commands have fast-path mappings."""
        essential = [
            "stop", "land", "take off", "go home", "follow me",
            "orbit", "emergency", "record",
        ]
        for cmd in essential:
            assert cmd in SIMPLE_COMMANDS, f"Missing fast-path: {cmd}"

    def test_simple_command_structure(self):
        """All simple commands have valid tool call structure."""
        for keyword, tool_call in SIMPLE_COMMANDS.items():
            assert "tool" in tool_call, f"Missing 'tool' in: {keyword}"
            assert "args" in tool_call, f"Missing 'args' in: {keyword}"
            assert isinstance(tool_call["args"], dict)

    @pytest.mark.asyncio
    async def test_fast_route_stop(self, router):
        """'Stop' should route to hover tool call."""
        result = await router.route_command("stop")
        assert result is not None
        assert result["tool"] == "hover"

    @pytest.mark.asyncio
    async def test_fast_route_takeoff(self, router):
        """'Take off' should route to takeoff with default altitude."""
        result = await router.route_command("take off")
        assert result is not None
        assert result["tool"] == "takeoff"
        assert result["args"]["altitude"] == 3.0

    @pytest.mark.asyncio
    async def test_fast_route_emergency(self, router):
        """'Emergency' should route to emergency_stop."""
        result = await router.route_command("emergency")
        assert result is not None
        assert result["tool"] == "emergency_stop"
