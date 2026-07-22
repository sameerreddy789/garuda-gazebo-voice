#!/usr/bin/env python3
"""
GarudaOne — Coordinated Swarm Armed-Flight Test (PX4 SITL)
==========================================================
Proves coordinated OFFBOARD execution across the swarm. Reuses the verified
``SwarmManager`` (udpin connection + per-drone telemetry isolation) to connect
N vehicles, then concurrently commands each vehicle:

    wait-healthy -> arm -> start offboard -> ascend to a DISTINCT altitude
    (streaming setpoints so PX4 offboard never fail-safes) -> verify the
    altitude via the live telemetry monitor -> land.

Run INSIDE WSL (localhost) after launching the SITL swarm:
    ~/garuda-venv/bin/python scripts/swarm_flight_test.py --altitudes 10,7

Exit code 0 only if every drone reaches its target altitude and lands.
"""

import argparse
import asyncio
import os
import sys

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from garuda.core.config import Config
from garuda.flight.swarm_manager import SwarmManager
from garuda.utils.logger import get_logger

from mavsdk.offboard import OffboardError, PositionNedYaw

log = get_logger("swarm_flight")


async def _wait_healthy(agent, timeout_s: float) -> bool:
    """Wait until EKF global + home position estimates are valid."""
    async def _loop() -> bool:
        async for h in agent.drone.telemetry.health():
            if h.is_global_position_ok and h.is_home_position_ok:
                return True
        return False

    try:
        return await asyncio.wait_for(_loop(), timeout=timeout_s)
    except asyncio.TimeoutError:
        return False


async def _wait_landed(agent, timeout_s: float) -> bool:
    from mavsdk.telemetry import LandedState

    async def _loop() -> bool:
        async for st in agent.drone.telemetry.landed_state():
            if st == LandedState.ON_GROUND:
                return True
        return False

    try:
        return await asyncio.wait_for(_loop(), timeout=timeout_s)
    except asyncio.TimeoutError:
        return False


async def _arm_with_retry(agent, attempts: int = 3) -> bool:
    for i in range(attempts):
        try:
            await agent.drone.action.arm()
            return True
        except Exception as e:  # noqa: BLE001
            log.warning(f"[Drone {agent.system_id}] arm attempt {i + 1} failed: {e}")
            await asyncio.sleep(2.0)
    return False


async def fly(agent, target_alt: float, hold_s: float, health_timeout: float) -> dict:
    sid = agent.system_id
    drone = agent.drone

    log.info(f"[Drone {sid}] waiting for EKF global/home position...")
    if not await _wait_healthy(agent, health_timeout):
        return {"id": sid, "ok": False, "reason": "health-timeout"}

    log.info(f"[Drone {sid}] arming...")
    if not await _arm_with_retry(agent):
        return {"id": sid, "ok": False, "reason": "arm-failed"}

    # PX4 requires a setpoint stream BEFORE offboard is engaged.
    await drone.offboard.set_position_ned(PositionNedYaw(0.0, 0.0, 0.0, 0.0))
    try:
        await drone.offboard.start()
    except OffboardError as e:
        log.error(f"[Drone {sid}] offboard start rejected: {e}")
        try:
            await drone.action.disarm()
        except Exception:  # noqa: BLE001
            pass
        return {"id": sid, "ok": False, "reason": "offboard-start"}

    log.info(f"[Drone {sid}] ascending to {target_alt:.1f}m (NED down={-target_alt:.1f})")
    setpoint = PositionNedYaw(0.0, 0.0, -target_alt, 0.0)
    loop = asyncio.get_event_loop()
    t_end = loop.time() + hold_s
    while loop.time() < t_end:
        # Stream at ~10Hz so PX4's offboard-loss failsafe never triggers.
        await drone.offboard.set_position_ned(setpoint)
        await asyncio.sleep(0.1)

    reached = agent.latest_altitude_m  # from SwarmManager's telemetry monitor
    tolerance = max(1.0, target_alt * 0.2)
    ok = abs(reached - target_alt) <= tolerance
    log.info(
        f"[Drone {sid}] reached ~{reached:.2f}m (target {target_alt:.1f}m, "
        f"tol {tolerance:.1f}m) -> {'OK' if ok else 'OFF-TARGET'}"
    )

    # Hand back to autoland.
    try:
        await drone.offboard.stop()
    except OffboardError as e:
        log.warning(f"[Drone {sid}] offboard stop error: {e}")
    try:
        await drone.action.land()
    except Exception as e:  # noqa: BLE001
        log.warning(f"[Drone {sid}] land command error: {e}")

    landed = await _wait_landed(agent, 40.0)
    log.info(f"[Drone {sid}] landed={landed}")
    return {
        "id": sid,
        "ok": ok and landed,
        "reached_m": round(reached, 2),
        "target_m": target_alt,
        "landed": landed,
    }


async def run(args) -> int:
    altitudes = [float(x) for x in args.altitudes.split(",")]

    config = Config()
    config._data["swarm"] = {
        "drone_count": args.count,
        "base_port": args.base_port,
        "connection_scheme": args.scheme,
        "connection_host": args.host,
        "connection_timeout_s": args.connect_timeout,
    }

    swarm = SwarmManager(config)
    log.info("=== Coordinated swarm flight: connecting ===")
    connected = await swarm.connect_all()
    if connected != args.count:
        log.error(f"only {connected}/{args.count} drones connected — aborting")
        await swarm.shutdown()
        return 1

    log.info("=== All connected — commanding concurrent flight ===")
    results = await asyncio.gather(
        *(
            fly(agent, altitudes[i % len(altitudes)], args.hold, args.health_timeout)
            for i, agent in enumerate(swarm.agents)
        )
    )

    await swarm.shutdown()

    ok_all = all(r["ok"] for r in results)
    log.info("=== RESULTS ===")
    for r in results:
        log.info(f"  drone {r['id']}: {r}")
    log.info(f"SWARM FLIGHT: {'PASS' if ok_all else 'FAIL'}")
    return 0 if ok_all else 1


def main() -> int:
    p = argparse.ArgumentParser(description="Coordinated swarm flight vs PX4 SITL")
    p.add_argument("--count", type=int, default=2)
    p.add_argument("--base-port", type=int, default=14540)
    p.add_argument("--scheme", default="udpin", choices=["udpin", "udpout", "udp"])
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--altitudes", default="10,7", help="comma-separated target altitudes (m)")
    p.add_argument("--hold", type=float, default=15.0, help="seconds to hold/stream at altitude")
    p.add_argument("--health-timeout", type=float, default=60.0)
    p.add_argument("--connect-timeout", type=float, default=30.0)
    args = p.parse_args()
    return asyncio.run(run(args))


if __name__ == "__main__":
    sys.exit(main())
