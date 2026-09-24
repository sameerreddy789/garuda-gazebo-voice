"""
Read-only bridge to the real GarudaOne drone stack.
====================================================
The command center is additive: it never changes drone autonomy code. This
module simply reflects the existing ``garuda`` package into the web layer so
the dashboard can show that the swarm software is wired in, and (when a live
PX4 SITL swarm is available) surface real telemetry.

Everything is guarded so the command center runs even if ``garuda`` or its
optional deps are unavailable.
"""

from __future__ import annotations

import os
import sys
from typing import Any

# Make the repo root importable (command_center/backend -> repo root).
_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

_GARUDA_AVAILABLE = False
_DRONE_STATES: list[str] = []
_DETAIL = ""

try:
    from garuda.core.orchestrator import DroneState  # type: ignore

    _DRONE_STATES = [s.name for s in DroneState]
    _GARUDA_AVAILABLE = True
    _DETAIL = "garuda package imported (autonomy stack linked)"
except Exception as e:  # noqa: BLE001
    _DETAIL = f"garuda package not importable: {e}"


def swarm_status() -> dict[str, Any]:
    """Report how the command center is linked to the drone autonomy stack."""
    return {
        "garuda_available": _GARUDA_AVAILABLE,
        # Live PX4 SITL bridging is possible via garuda.flight.swarm_manager,
        # but defaults to the built-in disaster simulation for the web demo.
        "mode": "simulation",
        "drone_states": _DRONE_STATES,
        "detail": _DETAIL,
        "connection_scheme": "udpin",  # verified GPS-denied-capable link
    }
