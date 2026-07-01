"""
GarudaOne DroneOS — Performance Profiler
========================================
Tracks CPU usage, memory, FPS, and latency per module.
Essential for validating that the concurrent workload
(PicoDet + SVO2 + LFM + voice) fits within RPi5's budget.
"""

import time
from collections import deque
from dataclasses import dataclass, field

from garuda.utils.logger import get_logger

log = get_logger("profiler")


@dataclass
class ModuleStats:
    """Performance statistics for a single module."""
    name: str
    frame_times: deque = field(default_factory=lambda: deque(maxlen=100))
    _start_time: float = 0.0

    @property
    def avg_ms(self) -> float:
        if not self.frame_times:
            return 0.0
        return sum(self.frame_times) / len(self.frame_times) * 1000

    @property
    def fps(self) -> float:
        avg = self.avg_ms
        return 1000.0 / avg if avg > 0 else 0.0

    @property
    def max_ms(self) -> float:
        return max(self.frame_times) * 1000 if self.frame_times else 0.0


class Profiler:
    """
    Per-module performance profiler.

    Usage:
        profiler = Profiler()

        # Option 1: Context manager
        with profiler.measure("perception"):
            result = detector.detect(frame)

        # Option 2: Manual start/stop
        profiler.start("brain")
        response = llm.generate(prompt)
        profiler.stop("brain")

        # Print stats
        profiler.report()
    """

    def __init__(self):
        self._modules: dict[str, ModuleStats] = {}

    def _get_module(self, name: str) -> ModuleStats:
        if name not in self._modules:
            self._modules[name] = ModuleStats(name=name)
        return self._modules[name]

    def start(self, module_name: str) -> None:
        """Start timing a module."""
        mod = self._get_module(module_name)
        mod._start_time = time.perf_counter()

    def stop(self, module_name: str) -> float:
        """Stop timing and record the duration. Returns elapsed seconds."""
        mod = self._get_module(module_name)
        elapsed = time.perf_counter() - mod._start_time
        mod.frame_times.append(elapsed)
        return elapsed

    def measure(self, module_name: str):
        """Context manager for timing a block of code."""
        return _MeasureContext(self, module_name)

    def get_stats(self, module_name: str) -> ModuleStats:
        """Get stats for a specific module."""
        return self._get_module(module_name)

    def report(self) -> str:
        """Generate a human-readable performance report."""
        lines = ["-- GarudaOne Performance Report --"]
        lines.append(f"{'Module':<20} {'Avg (ms)':<12} {'Max (ms)':<12} {'FPS':<10}")
        lines.append("-" * 54)

        for name, stats in sorted(self._modules.items()):
            lines.append(
                f"{name:<20} {stats.avg_ms:<12.2f} {stats.max_ms:<12.2f} {stats.fps:<10.1f}"
            )

        report = "\n".join(lines)
        log.info(f"\n{report}")
        return report


class _MeasureContext:
    """Context manager wrapper for the profiler."""

    def __init__(self, profiler: Profiler, module_name: str):
        self._profiler = profiler
        self._name = module_name

    def __enter__(self):
        self._profiler.start(self._name)
        return self

    def __exit__(self, *args):
        self._profiler.stop(self._name)


# Global profiler instance — shared across all modules
profiler = Profiler()
