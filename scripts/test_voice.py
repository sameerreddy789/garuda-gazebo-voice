#!/usr/bin/env python3
"""
GarudaOne — Voice Pipeline Test Script
=======================================
Tests the voice pipeline components individually.

Usage:
    python scripts/test_voice.py                     # Test intent parser
    python scripts/test_voice.py --stt               # Test speech-to-text
    python scripts/test_voice.py --tts "Hello world" # Test text-to-speech
    python scripts/test_voice.py --listen            # Test full pipeline
"""

import argparse
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from garuda.core.config import Config
from garuda.voice.pipeline import VoicePipeline, IntentParser


def test_intent_parser():
    """Test the intent parser with various commands."""
    print("\n" + "=" * 60)
    print("  Testing Intent Parser")
    print("=" * 60)

    config = Config()
    parser = IntentParser(config)

    test_cases = [
        ("take off", "takeoff"),
        ("launch the drone", "takeoff"),
        ("land now", "land"),
        ("come down please", "land"),
        ("go home", "rtl"),
        ("return to launch", "rtl"),
        ("stop", "stop"),
        ("hover in place", "hover"),
        ("follow me", "follow"),
        ("track me", "follow"),
        ("orbit around me", "orbit"),
        ("circle", "orbit"),
        ("chase me", "chase"),
        ("do a reveal shot", "reveal"),
        ("start recording", "recording_start"),
        ("stop recording", "recording_stop"),
        ("emergency stop", "emergency_stop"),
        ("kill motors", "emergency_stop"),
        ("what time is it", None),  # Should return None
    ]

    passed = 0
    failed = 0

    for text, expected in test_cases:
        result = parser.classify(text)
        status = "✓" if result == expected else "✗"
        if result == expected:
            passed += 1
        else:
            failed += 1
        print(f"  {status} \"{text}\" → {result} (expected: {expected})")

    print(f"\n  Results: {passed} passed, {failed} failed")
    print("  ✓ Intent parser test complete" if failed == 0 else "  ✗ Some tests failed")


async def test_stt():
    """Test speech-to-text with microphone input."""
    print("\n" + "=" * 60)
    print("  Testing Speech-to-Text (say something!)")
    print("=" * 60)

    config = Config()
    pipeline = VoicePipeline(config, None)  # type: ignore — no bus needed
    pipeline.initialize()

    if pipeline._stt_model is None:
        print("\n  ⚠ faster-whisper not installed")
        print("    Install: pip install faster-whisper sounddevice")
        return

    try:
        import sounddevice as sd
        import numpy as np

        print("\n  Recording 3 seconds... Speak now!")
        print("  ", end="", flush=True)

        # Record 3 seconds of audio
        duration = 3.0
        sample_rate = 16000
        recording = sd.rec(
            int(duration * sample_rate),
            samplerate=sample_rate,
            channels=1,
            dtype="float32",
        )
        sd.wait()
        print("  Done recording.")

        # Transcribe
        print("  Transcribing...")
        text = await pipeline._transcribe(recording.flatten())
        print(f"\n  Transcribed: \"{text}\"")
        print("  ✓ STT test complete")

    except ImportError:
        print("\n  ⚠ sounddevice not installed")
        print("    Install: pip install sounddevice")
    except Exception as e:
        print(f"\n  ✗ STT test failed: {e}")


async def test_tts(text: str):
    """Test text-to-speech."""
    print("\n" + "=" * 60)
    print(f"  Testing Text-to-Speech: \"{text}\"")
    print("=" * 60)

    config = Config()

    # Create event bus mock
    from garuda.core.events import EventBus
    bus = EventBus()

    pipeline = VoicePipeline(config, bus)
    pipeline.initialize()

    print(f"\n  TTS engine: {pipeline._tts_engine}")

    if pipeline._tts_engine == "stub":
        print("  ⚠ Running in stub mode — no Piper binary found")
        print("    Install Piper: https://github.com/rhasspy/piper")

    await pipeline.speak(text)
    print("  ✓ TTS test complete")


async def test_listen():
    """Test the full voice pipeline (wake word + STT + TTS)."""
    print("\n" + "=" * 60)
    print("  Testing Full Voice Pipeline")
    print("  Say 'Garuda' then a command. Press Ctrl+C to stop.")
    print("=" * 60)

    config = Config()
    from garuda.core.events import EventBus
    bus = EventBus()

    pipeline = VoicePipeline(config, bus)
    pipeline.initialize()

    print(f"\n  Wake word: {'loaded' if pipeline._wake_word_model else 'not loaded'}")
    print(f"  STT: {'loaded' if pipeline._stt_model else 'not loaded'}")
    print(f"  TTS: {pipeline._tts_engine}")

    # Run the pipeline
    try:
        await pipeline.run()
    except KeyboardInterrupt:
        await pipeline.stop()
        print("\n  ✓ Pipeline test stopped")


def main():
    parser = argparse.ArgumentParser(description="Test voice pipeline")
    parser.add_argument("--stt", action="store_true", help="Test speech-to-text")
    parser.add_argument("--tts", type=str, help="Test text-to-speech with text")
    parser.add_argument("--listen", action="store_true", help="Test full pipeline")
    args = parser.parse_args()

    if args.stt:
        asyncio.run(test_stt())
    elif args.tts:
        asyncio.run(test_tts(args.tts))
    elif args.listen:
        asyncio.run(test_listen())
    else:
        test_intent_parser()


if __name__ == "__main__":
    main()
