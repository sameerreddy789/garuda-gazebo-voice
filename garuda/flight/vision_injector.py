"""
GarudaOne DroneOS — GPS-Denied External-Vision Injection (PX4 EKF2 via MAVSDK)
==============================================================================
Feeds ``VISION_POSITION_ESTIMATE`` into PX4 so EKF2 can hold position with GPS
aiding disabled. This is the foundation for GPS-denied industrial/indoor
flight: the estimator's only horizontal reference becomes the injected pose.

Design seam:
  The pose comes from a pluggable :class:`VisionPoseSource`. Today that's a
  mock (:class:`LoopbackPoseSource`) so we can validate the EKF2 external-vision
  FUSION path deterministically. Later a real VIO/SLAM backend (OpenVINS,
  ORB-SLAM3, ...) implements the same interface and drops in unchanged.

EKF2 configuration (verified against PX4 v1.18 params_external_vision.yaml /
module.yaml in this build):
  EKF2_GPS_CTRL   = 0   -> disable all GPS aiding (force GPS-denied)
  EKF2_EV_CTRL    = 3   -> bitmask: Horizontal pos(1) + Vertical pos(2). Heading
                          comes from the magnetometer (needs no GPS); enabling EV
                          yaw with a looped-back pose leaves heading invalid and
                          blocks arming. A real VIO can add EV yaw (bit3) later.
  EKF2_HGT_REF    = 3   -> height reference = Vision
  EKF2_EV_NOISE_MD= 1   -> use EKF2_EV*_NOISE params (ignore message covariance)
  (these are ParamExt/estimator params and take effect after a reboot)

Injection is done through MAVSDK's Mocap plugin (``set_vision_position_estimate``),
keeping the whole thing on the same MAVSDK foundation as the swarm work — no
raw pymavlink, no ROS 2.
"""

import asyncio
import math
import random
import time
from typing import Any, Optional, Tuple

from garuda.utils.logger import get_logger

log = get_logger("vision")

# Integer EKF2 params for GPS-denied external-vision flight.
GPS_DENIED_EKF2_PARAMS_INT = {
    "EKF2_GPS_CTRL": 0,       # disable GPS aiding
    "EKF2_EV_CTRL": 0b0011,   # Hpos + Vpos (heading from magnetometer, GPS-free)
    "EKF2_HGT_REF": 3,        # height reference = Vision
    "EKF2_EV_NOISE_MD": 1,    # use param noise, not message covariance
}
# Float EKF2 params (tight-ish external-vision noise for a clean sim hold).
GPS_DENIED_EKF2_PARAMS_FLOAT = {
    "EKF2_EVP_NOISE": 0.1,    # EV position noise (m)
    "EKF2_EVA_NOISE": 0.05,   # EV angle noise (rad)
}

# NED pose tuple: (north_m, east_m, down_m, yaw_rad)
Pose = Tuple[float, float, float, float]


class VisionPoseSource:
    """Interface for anything that can supply a local NED pose.

    Implementations: a mock now, a real VIO/SLAM backend later. All that the
    injector needs is a current pose (or None if not yet available).
    """

    async def start(self) -> None:
        pass

    async def stop(self) -> None:
        pass

    def get_pose(self) -> Optional[Pose]:
        raise NotImplementedError


class LoopbackPoseSource(VisionPoseSource):
    """Mock pose source: re-emits the vehicle's own local NED + yaw as "vision".

    It subscribes to the autopilot's local position and attitude, caches them,
    and returns them (optionally corrupted by injected drift and Gaussian
    noise) as the vision observation.

    IMPORTANT (honest caveat): this loops the estimator's local position back
    as the observation, so it is NOT an independent localization source. It is
    a deterministic rig for validating two things: (a) that PX4 accepts and
    fuses external vision with GPS off, and (b) that the vehicle RESPONDS to
    vision drift. Real localization quality is the job of a VIO/SLAM backend
    implementing this same interface.
    """

    def __init__(self, drone: Any, noise_std_m: float = 0.0):
        self.drone = drone
        self.noise_std_m = noise_std_m

        self._n = 0.0
        self._e = 0.0
        self._d = 0.0
        self._yaw = 0.0
        self._have_pos = False

        self._drift_mps = (0.0, 0.0, 0.0)
        self._drift_t0: Optional[float] = None

        self._tasks: list[asyncio.Task] = []

    def set_drift(self, north_mps: float = 0.0, east_mps: float = 0.0,
                  down_mps: float = 0.0) -> None:
        """Start injecting a constant velocity drift into the reported pose."""
        self._drift_mps = (north_mps, east_mps, down_mps)
        self._drift_t0 = time.monotonic()
        log.info(f"vision drift set to {self._drift_mps} m/s")

    async def start(self) -> None:
        self._tasks.append(asyncio.create_task(self._pos_loop()))
        self._tasks.append(asyncio.create_task(self._att_loop()))

    async def _pos_loop(self) -> None:
        try:
            async for p in self.drone.telemetry.position_velocity_ned():
                self._n = p.position.north_m
                self._e = p.position.east_m
                self._d = p.position.down_m
                self._have_pos = True
        except asyncio.CancelledError:
            raise
        except Exception as e:  # noqa: BLE001
            log.debug(f"position stream ended: {e}")

    async def _att_loop(self) -> None:
        try:
            async for a in self.drone.telemetry.attitude_euler():
                self._yaw = math.radians(a.yaw_deg)
        except asyncio.CancelledError:
            raise
        except Exception as e:  # noqa: BLE001
            log.debug(f"attitude stream ended: {e}")

    def get_pose(self) -> Optional[Pose]:
        # Before the local-position stream is live (GPS-denied bootstrap), the
        # cached values are the ground origin (0,0,0), which is the true pose
        # on the pad. Emitting it immediately gives EKF2 an initial vision fix
        # to converge on, avoiding a no-position / no-vision deadlock.
        dn = de = dd = 0.0
        if self._drift_t0 is not None:
            dt = time.monotonic() - self._drift_t0
            dn = self._drift_mps[0] * dt
            de = self._drift_mps[1] * dt
            dd = self._drift_mps[2] * dt

        s = self.noise_std_m
        if s > 0.0:
            nn, ne, nd = random.gauss(0, s), random.gauss(0, s), random.gauss(0, s)
        else:
            nn = ne = nd = 0.0

        return (self._n + dn + nn, self._e + de + ne, self._d + dd + nd, self._yaw)

    async def stop(self) -> None:
        for t in self._tasks:
            t.cancel()
        for t in self._tasks:
            try:
                await t
            except asyncio.CancelledError:
                pass
        self._tasks.clear()


class VisionInjector:
    """Streams ``VISION_POSITION_ESTIMATE`` to PX4 at a fixed rate."""

    def __init__(self, drone: Any, source: VisionPoseSource, rate_hz: float = 30.0):
        self.drone = drone
        self.source = source
        self.period = 1.0 / rate_hz
        self.sent = 0
        self._task: Optional[asyncio.Task] = None

    async def start(self) -> None:
        await self.source.start()
        self._task = asyncio.create_task(self._loop())
        log.info(f"vision injector started ({1.0 / self.period:.0f} Hz)")

    async def _loop(self) -> None:
        from mavsdk.mocap import (
            AngleBody,
            Covariance,
            PositionBody,
            VisionPositionEstimate,
        )

        # With EKF2_EV_NOISE_MD=1, PX4 ignores this covariance and uses params.
        unknown_cov = Covariance([float("nan")] * 21)

        try:
            while True:
                pose = self.source.get_pose()
                if pose is not None:
                    n, e, d, yaw = pose
                    estimate = VisionPositionEstimate(
                        int(time.time() * 1e6),
                        PositionBody(n, e, d),            # NED: x=N, y=E, z=D
                        AngleBody(0.0, 0.0, yaw),
                        unknown_cov,
                    )
                    try:
                        await self.drone.mocap.set_vision_position_estimate(estimate)
                        self.sent += 1
                    except Exception as e:  # noqa: BLE001
                        log.debug(f"set_vision_position_estimate failed: {e}")
                await asyncio.sleep(self.period)
        except asyncio.CancelledError:
            raise

    async def stop(self) -> None:
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None
        await self.source.stop()
        log.info(f"vision injector stopped (sent {self.sent} estimates)")


async def set_gps_denied_params(drone: Any) -> None:
    """Configure EKF2 for GPS-denied external-vision flight.

    NOTE: these are estimator params — a reboot is required for them to take
    full effect. The caller is responsible for rebooting + reconnecting.
    """
    for name, value in GPS_DENIED_EKF2_PARAMS_INT.items():
        await drone.param.set_param_int(name, value)
        log.info(f"set {name} = {value}")
    for name, value in GPS_DENIED_EKF2_PARAMS_FLOAT.items():
        try:
            await drone.param.set_param_float(name, value)
            log.info(f"set {name} = {value}")
        except Exception as e:  # noqa: BLE001
            log.warning(f"could not set {name}: {e}")
