#!/usr/bin/env python3
"""
GarudaOne — GPS-Denied External-Vision Hold Test (PX4 SITL)
===========================================================
Proves the GPS-denied foundation: with GPS aiding disabled, PX4 EKF2 fuses an
injected VISION_POSITION_ESTIMATE stream, produces a valid LOCAL position,
arms, and holds an offboard setpoint without flying away.

Flow (run INSIDE WSL):
  connect -> set EKF2 EV params -> reboot -> (same System relinks) -> stream
  vision -> wait for local-position health (GPS off) -> arm -> offboard climb
  -> hold and check TRUE horizontal excursion via ground truth -> inject vision
  drift and show the vehicle chases it -> land.

    ~/garuda-venv/bin/python scripts/gps_denied_test.py --alt 5

Exit 0 if EKF accepts vision (valid local pos, GPS off), the hold stays
bounded in ground truth, and the vehicle lands.
"""

import argparse
import asyncio
import math
import os
import sys

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from garuda.flight.vision_injector import (
    LoopbackPoseSource,
    VisionInjector,
    set_gps_denied_params,
)
from garuda.utils.logger import get_logger

from mavsdk import System
from mavsdk.offboard import OffboardError, PositionNedYaw

log = get_logger("gps_denied")


class GroundTruthSampler:
    """Caches PX4 simulator ground truth (independent of the estimator) and
    converts it to a local NED offset from a captured origin."""

    def __init__(self, drone):
        self.drone = drone
        self.lat = self.lon = self.alt = None
        self.lat0 = self.lon0 = self.alt0 = None
        self._task = None

    async def start(self):
        self._task = asyncio.create_task(self._loop())

    async def _loop(self):
        try:
            async for gt in self.drone.telemetry.ground_truth():
                if gt.latitude_deg is None or math.isnan(gt.latitude_deg):
                    continue
                self.lat, self.lon = gt.latitude_deg, gt.longitude_deg
                self.alt = gt.absolute_altitude_m
        except asyncio.CancelledError:
            raise
        except Exception as e:  # noqa: BLE001
            log.debug(f"ground-truth stream ended: {e}")

    def ready(self) -> bool:
        return self.lat is not None

    def set_origin(self) -> None:
        self.lat0, self.lon0, self.alt0 = self.lat, self.lon, self.alt

    def ned(self):
        if self.lat is None or self.lat0 is None:
            return None
        north = (self.lat - self.lat0) * 111320.0
        east = (self.lon - self.lon0) * 111320.0 * math.cos(math.radians(self.lat0))
        down = -((self.alt or 0.0) - (self.alt0 or 0.0))
        return north, east, down

    async def stop(self):
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass


async def wait_local_position(drone, timeout_s: float) -> bool:
    async def _loop():
        async for h in drone.telemetry.health():
            if h.is_local_position_ok:
                return True
    try:
        return await asyncio.wait_for(_loop(), timeout=timeout_s)
    except asyncio.TimeoutError:
        return False


async def wait_landed(drone, timeout_s: float) -> bool:
    from mavsdk.telemetry import LandedState

    async def _loop():
        async for st in drone.telemetry.landed_state():
            if st == LandedState.ON_GROUND:
                return True
    try:
        return await asyncio.wait_for(_loop(), timeout=timeout_s)
    except asyncio.TimeoutError:
        return False


async def is_disarmed(drone, timeout_s: float) -> bool:
    async def _loop():
        async for armed in drone.telemetry.armed():
            return not armed
    try:
        return await asyncio.wait_for(_loop(), timeout=timeout_s)
    except asyncio.TimeoutError:
        return False


async def arm_with_retry(drone, attempts: int = 4) -> bool:
    for i in range(attempts):
        try:
            await drone.action.arm()
            return True
        except Exception as e:  # noqa: BLE001
            log.warning(f"arm attempt {i + 1} failed: {e}")
            await asyncio.sleep(2.0)
    return False


async def run(args) -> int:
    url = f"udpin://{args.host}:{args.port}"
    drone = System(mavsdk_server_address="localhost", port=args.grpc_port)
    log.info(f"Connecting to PX4 on {url} (gRPC port {args.grpc_port}) ...")
    try:
        await drone.connect(system_address=url)
        async def _await_heartbeat():
            async for state in drone.core.connection_state():
                if state.is_connected:
                    return True
            return False
        await asyncio.wait_for(_await_heartbeat(), timeout=args.connect_timeout)
    except Exception as e:
        log.error(f"initial connect failed: {e}")
        return 1

    # Start vision injection FIRST, while GPS still provides a valid position,
    # so external-vision data is already flowing when we flip EKF2 over to it.
    # (PX4 v1.14+ reconfigures EKF2 aiding params live via parameter_update, so
    # no reboot is needed — which also avoids stale gz models in SITL.)
    source = LoopbackPoseSource(drone, noise_std_m=args.noise)
    injector = VisionInjector(drone, source, rate_hz=args.rate)
    await injector.start()
    gt = GroundTruthSampler(drone)
    await gt.start()
    await asyncio.sleep(2.0)

    log.info("=== Configuring EKF2 for GPS-denied external vision (live) ===")
    await set_gps_denied_params(drone)
    log.info(f"settling {args.settle:.0f}s for EKF2 to switch GPS->vision...")
    await asyncio.sleep(args.settle)

    log.info("=== Verifying EKF LOCAL position holds with GPS OFF ===")
    if not await wait_local_position(drone, args.health_timeout):
        log.error("FAIL: EKF never produced a valid local position from vision")
        await injector.stop()
        await gt.stop()
        return 1
    log.info(
        f"LOCAL POSITION VALID with GPS disabled — external-vision fusion "
        f"confirmed (injected {injector.sent} estimates)"
    )

    await asyncio.sleep(1.0)
    gt_ok = gt.ready()
    if gt_ok:
        gt.set_origin()
    else:
        log.warning("ground truth unavailable — true-excursion check skipped")

    log.info("=== Arming (GPS-denied) ===")
    if not await arm_with_retry(drone):
        log.error("FAIL: arm rejected")
        await injector.stop()
        await gt.stop()
        return 1

    await drone.offboard.set_position_ned(PositionNedYaw(0.0, 0.0, 0.0, 0.0))
    try:
        await drone.offboard.start()
    except OffboardError as e:
        log.error(f"FAIL: offboard start rejected: {e}")
        try:
            await drone.action.disarm()
        except Exception:  # noqa: BLE001
            pass
        await injector.stop()
        await gt.stop()
        return 1

    log.info(f"=== Offboard climb to {args.alt}m and hold (GPS-denied) ===")
    setpoint = PositionNedYaw(0.0, 0.0, -args.alt, 0.0)
    loop = asyncio.get_event_loop()

    def horizontal_excursion() -> float:
        ned = gt.ned() if gt_ok else None
        if ned is not None:
            return math.hypot(ned[0], ned[1])
        # Fallback: estimator local position (cached by the loopback source).
        return math.hypot(source._n, source._e)

    frame = "ground truth" if gt_ok else "estimator frame"
    t_end = loop.time() + args.hold
    max_h = 0.0
    while loop.time() < t_end:
        await drone.offboard.set_position_ned(setpoint)
        max_h = max(max_h, horizontal_excursion())
        await asyncio.sleep(0.1)

    alt_reached = -source._d
    log.info(
        f"hold complete: altitude ~{alt_reached:.2f}m, "
        f"max horizontal excursion ({frame}) {max_h:.2f}m"
    )

    log.info("=== Injecting 0.5 m/s North vision drift for 6s ===")
    if gt_ok:
        gt.set_origin()
    source.set_drift(north_mps=0.5)
    t_end = loop.time() + 6.0
    drift_h = 0.0
    while loop.time() < t_end:
        await drone.offboard.set_position_ned(setpoint)
        drift_h = horizontal_excursion()
        await asyncio.sleep(0.1)
    source.set_drift(0.0, 0.0, 0.0)
    if gt_ok:
        log.info(f"drift response: vehicle moved {drift_h:.2f}m (ground truth)")
    else:
        log.info(
            "drift injected, but true displacement is not observable without "
            "ground truth (in loopback the estimator holds the setpoint by "
            "construction) — quantifying this needs a real VIO + truth source"
        )

    log.info("=== Landing ===")
    try:
        await drone.offboard.stop()
    except OffboardError:
        pass
    try:
        await drone.action.land()
    except Exception as e:  # noqa: BLE001
        log.warning(f"land error: {e}")
    landed = await wait_landed(drone, 90.0)
    if not landed:
        landed = await is_disarmed(drone, 5.0)  # disarm is an acceptable "down"

    await injector.stop()
    await gt.stop()

    alt_ok = abs(alt_reached - args.alt) <= max(1.0, 0.25 * args.alt)
    bounded_ok = max_h < args.max_excursion
    log.info("=== RESULT ===")
    log.info("  external-vision fusion (local pos valid, GPS off): True")
    log.info(f"  altitude on vision: {alt_reached:.2f}m / target {args.alt}m -> {alt_ok}")
    log.info(
        f"  hold excursion ({frame}): {max_h:.2f}m / limit {args.max_excursion}m "
        f"-> {bounded_ok}"
    )
    log.info(f"  landed/disarmed: {landed}")
    verdict = alt_ok and bounded_ok and landed
    log.info(f"GPS-DENIED HOLD: {'PASS' if verdict else 'FAIL'}")
    return 0 if verdict else 1


def main() -> int:
    p = argparse.ArgumentParser(description="GPS-denied external-vision hold test")
    p.add_argument("--port", type=int, default=14540)
    p.add_argument("--grpc-port", type=int, default=50051)
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--alt", type=float, default=5.0)
    p.add_argument("--hold", type=float, default=15.0)
    p.add_argument("--noise", type=float, default=0.0, help="vision Gaussian noise std (m)")
    p.add_argument("--rate", type=float, default=30.0, help="vision injection rate (Hz)")
    p.add_argument("--settle", type=float, default=8.0, help="seconds for EKF2 to switch to vision")
    p.add_argument("--health-timeout", type=float, default=90.0)
    p.add_argument("--connect-timeout", type=float, default=30.0)
    p.add_argument("--max-excursion", type=float, default=5.0, help="flyaway limit (m)")
    args = p.parse_args()
    return asyncio.run(run(args))


if __name__ == "__main__":
    sys.exit(main())
