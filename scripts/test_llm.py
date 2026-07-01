#!/usr/bin/env python3
"""
GarudaOne — LLM Engine Test Script
===================================
Tests the LFM-2.5-230M language model for command understanding.

Usage:
    python scripts/test_llm.py                           # Test stub backend
    python scripts/test_llm.py --command "follow me"     # Test specific command
    python scripts/test_llm.py --benchmark               # Benchmark inference speed
"""

import argparse
import asyncio
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from garuda.core.config import Config
from garuda.brain.llm_engine import LLMEngine


async def test_commands():
    """Test the LLM with various commands."""
    print("\n" + "=" * 60)
    print("  Testing LLM Engine")
    print("=" * 60)

    config = Config()
    from garuda.core.events import EventBus
    bus = EventBus()

    engine = LLMEngine(config, bus)
    engine.load_model()

    print(f"\n  Backend: {engine._backend}")
    print(f"  Model: {engine._model_path.name}")
    print(f"  Model exists: {engine._model_path.exists()}")

    test_commands = [
        "take off",
        "follow me",
        "orbit around me",
        "film me from the left while I walk toward the bridge",
        "stop",
        "go home",
        "do a dramatic reveal shot",
    ]

    print("\n  Processing commands:")
    print("  " + "-" * 56)

    for cmd in test_commands:
        start = time.time()
        result = await engine.process_command(cmd)
        elapsed = time.time() - start

        if result:
            tool = result.get("tool", "?")
            args = result.get("args", {})
            print(f"  \"{cmd}\"")
            print(f"    → tool={tool}, args={args} ({elapsed*1000:.0f}ms)")
        else:
            print(f"  \"{cmd}\"")
            print(f"    → FAILED ({elapsed*1000:.0f}ms)")
        print()

    print("  ✓ LLM test complete")


async def test_single_command(command: str):
    """Test a single command."""
    print("\n" + "=" * 60)
    print(f"  Testing LLM: \"{command}\"")
    print("=" * 60)

    config = Config()
    from garuda.core.events import EventBus
    bus = EventBus()

    engine = LLMEngine(config, bus)
    engine.load_model()

    print(f"\n  Backend: {engine._backend}")

    start = time.time()
    result = await engine.process_command(command)
    elapsed = time.time() - start

    print(f"\n  Result: {result}")
    print(f"  Time: {elapsed*1000:.0f}ms")
    print("  ✓ Command test complete")


async def benchmark():
    """Benchmark LLM inference speed."""
    print("\n" + "=" * 60)
    print("  Benchmarking LLM Engine")
    print("=" * 60)

    config = Config()
    from garuda.core.events import EventBus
    bus = EventBus()

    engine = LLMEngine(config, bus)
    engine.load_model()

    print(f"\n  Backend: {engine._backend}")
    if engine._backend == "stub":
        print("  ⚠ Stub mode — benchmarking stub response time only")
        print("    Install llama-cpp-python for real inference")

    # Warm up
    await engine.process_command("test")

    # Benchmark
    commands = ["take off", "follow me", "orbit", "stop", "go home"]
    times = []

    for _ in range(3):  # 3 rounds
        for cmd in commands:
            start = time.time()
            await engine.process_command(cmd)
            elapsed = time.time() - start
            times.append(elapsed)

    avg_ms = (sum(times) / len(times)) * 1000
    min_ms = min(times) * 1000
    max_ms = max(times) * 1000

    print(f"\n  Results ({len(times)} samples):")
    print(f"    Average: {avg_ms:.0f}ms")
    print(f"    Min:     {min_ms:.0f}ms")
    print(f"    Max:     {max_ms:.0f}ms")
    print(f"    Target:  <500ms (LFM-2.5-230M @ 42 tok/s)")
    print("  ✓ Benchmark complete")


def main():
    parser = argparse.ArgumentParser(description="Test LLM engine")
    parser.add_argument("--command", type=str, help="Test specific command")
    parser.add_argument("--benchmark", action="store_true", help="Benchmark speed")
    args = parser.parse_args()

    if args.command:
        asyncio.run(test_single_command(args.command))
    elif args.benchmark:
        asyncio.run(benchmark())
    else:
        asyncio.run(test_commands())


if __name__ == "__main__":
    main()
