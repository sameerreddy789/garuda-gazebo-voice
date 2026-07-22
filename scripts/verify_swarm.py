#!/usr/bin/env python3
"""
GarudaOne — Live SwarmManager Verification against PX4 SITL
===========================================================
Connects the real ``SwarmManager`` to N running PX4 SITL instances and
verifies that each vehicle's telemetry streams in independently (proving
per-drone isolation over sequential MAVSDK UDP ports).

Intended to run INSIDE WSL (localhost) after launching the SITL swarm, so
it does not depend on Windows<->WSL UDP forwarding (NAT networking):

    ~/garuda-venv/bin/python scripts/verify_swarm.py --count 2 --scheme udpin

Exit code: 0 if all requested drones connect, 1 otherwise.
"""

import argparse
import asyncio
import os
import sys

# Make the garuda package importable regardless of CWD.
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from garuda.core.config import Config
from garuda.flight.swarm_manager import SwarmManager


async def run(args) -> int:
    config = Config()
    # Override swarm config deterministically for this verification run.
    config._data["swarm"] = {
        "drone_count": args.count,
        "base_port": args.base_port,
        "connection_scheme": args.scheme,
        "connection_host": args.host,
        "connection_timeout_s": args.timeout,
    }

    swarm = SwarmManager(config)
    print(
        f"[verify] connecting to {args.count} PX4 instance(s) via "
        f"{args.scheme}://{args.host}:{args.base_port}"
        f"..{args.base_port + args.count - 1}",
        flush=True,
    )

    connected = await swarm.connect_all()

    # Let telemetry flow so we can show each drone reporting independently.
    print(f"[verify] holding {args.telemetry_wait:.0f}s for telemetry...", flush=True)
    await asyncio.sleep(args.telemetry_wait)

    for agent in swarm.agents:
        print(
            f"[verify] drone {agent.system_id} (port {agent.udp_port}): "
            f"connected={agent.is_connected} "
            f"alt={agent.latest_altitude_m:.2f}m "
            f"pos={'yes' if agent.latest_position is not None else 'none'}",
            flush=True,
        )

    await swarm.shutdown()

    ok = connected == args.count
    print(
        f"[verify] RESULT: {connected}/{args.count} connected -> "
        f"{'PASS' if ok else 'FAIL'}",
        flush=True,
    )
    return 0 if ok else 1


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify SwarmManager vs PX4 SITL")
    parser.add_argument("--count", type=int, default=2)
    parser.add_argument("--base-port", type=int, default=14540)
    parser.add_argument(
        "--scheme", default="udpin", choices=["udpin", "udpout", "udp"]
    )
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--timeout", type=float, default=30.0)
    parser.add_argument("--telemetry-wait", type=float, default=6.0)
    args = parser.parse_args()
    return asyncio.run(run(args))


if __name__ == "__main__":
    sys.exit(main())
