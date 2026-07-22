"""
GarudaOne — Vision Injector Unit Tests
======================================
Pure-function tests for the GPS-denied vision pose source (no MAVSDK, no SITL),
so they run in the standard Windows suite.

    python -m pytest tests/test_vision_injector.py -v
"""

import time

import pytest

from garuda.flight.vision_injector import (
    GPS_DENIED_EKF2_PARAMS_INT,
    LoopbackPoseSource,
)


class TestLoopbackPoseSource:
    def test_bootstrap_reports_ground_origin(self):
        """Before any telemetry, it must emit (0,0,0,0) to bootstrap EKF2."""
        src = LoopbackPoseSource(drone=None)
        assert src.get_pose() == (0.0, 0.0, 0.0, 0.0)

    def test_returns_cached_pose(self):
        src = LoopbackPoseSource(drone=None)
        src._n, src._e, src._d, src._yaw = 1.0, 2.0, -3.0, 0.5
        assert src.get_pose() == (1.0, 2.0, -3.0, 0.5)

    def test_drift_accumulates_over_time(self):
        src = LoopbackPoseSource(drone=None)
        src.set_drift(north_mps=1.0)
        # Simulate 2 seconds elapsed since drift started.
        src._drift_t0 = time.monotonic() - 2.0
        n, e, d, _ = src.get_pose()
        assert n == pytest.approx(2.0, abs=0.2)   # ~1 m/s * 2 s
        assert e == pytest.approx(0.0, abs=1e-9)
        assert d == pytest.approx(0.0, abs=1e-9)

    def test_zero_noise_is_deterministic(self):
        src = LoopbackPoseSource(drone=None, noise_std_m=0.0)
        src._n, src._e, src._d = 5.0, -4.0, -2.0
        assert src.get_pose() == (5.0, -4.0, -2.0, 0.0)

    def test_noise_stays_within_reasonable_bounds(self):
        src = LoopbackPoseSource(drone=None, noise_std_m=0.05)
        src._n = 10.0
        # Over many samples the noisy value should hover near the true value.
        vals = [src.get_pose()[0] for _ in range(200)]
        avg = sum(vals) / len(vals)
        assert abs(avg - 10.0) < 0.05


class TestGpsDeniedParams:
    def test_param_values_match_verified_ekf2_semantics(self):
        # EKF2_EV_CTRL bit0 Hpos + bit1 Vpos = 3 (heading from magnetometer)
        assert GPS_DENIED_EKF2_PARAMS_INT["EKF2_EV_CTRL"] == 0b0011
        # GPS aiding fully disabled
        assert GPS_DENIED_EKF2_PARAMS_INT["EKF2_GPS_CTRL"] == 0
        # Height reference = Vision (enum value 3)
        assert GPS_DENIED_EKF2_PARAMS_INT["EKF2_HGT_REF"] == 3
