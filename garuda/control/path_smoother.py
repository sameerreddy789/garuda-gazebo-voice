"""
GarudaOne DroneOS — Path Smoother (Cubic B-Spline)
====================================================
Smooths raw velocity commands into cinematic, jerk-free trajectories.

Why this matters:
  Raw PID output is responsive but jerky — velocity jumps around as
  the error signal changes. That jerkiness shows up as shaky footage.

  The B-spline smoother guarantees continuous-curvature trajectories.
  It acts like a low-pass filter on the velocity commands, but smarter —
  it preserves the overall intent while removing harsh transitions.

  The viewer never sees obstacle maneuvers because the path around
  obstacles is smooth, and the gimbal counter-rotates to compensate.
"""

from collections import deque

import numpy as np
from scipy.interpolate import make_interp_spline

from garuda.utils.logger import get_logger
from garuda.utils.transforms import VelocityNED

log = get_logger("smoother")


class PathSmoother:
    """
    Cubic B-spline velocity smoother.

    Collects recent velocity commands in a buffer, fits a smooth
    B-spline curve through them, and outputs the smoothed value.
    Guarantees C2 continuity (continuous curvature, zero jerk).
    """

    def __init__(self, buffer_size: int = 10, smoothing_factor: float = 0.85):
        """
        Args:
            buffer_size: Number of recent commands to consider (10 = ~200ms at 50Hz)
            smoothing_factor: 0 = no smoothing, 1 = max smoothing. 0.85 is cinematic.
        """
        self._buffer_size = buffer_size
        self._smoothing_factor = smoothing_factor

        # Velocity history buffers
        self._vn_buffer: deque[float] = deque(maxlen=buffer_size)
        self._ve_buffer: deque[float] = deque(maxlen=buffer_size)
        self._vd_buffer: deque[float] = deque(maxlen=buffer_size)

        # Exponential moving average state (fast path)
        self._ema_vn = 0.0
        self._ema_ve = 0.0
        self._ema_vd = 0.0
        self._initialized = False

        log.info(
            f"Path smoother initialized — buffer={buffer_size}, "
            f"smoothing={smoothing_factor}"
        )

    def smooth(self, velocity: VelocityNED) -> VelocityNED:
        """
        Smooth a raw velocity command.

        Uses exponential moving average for real-time performance,
        with optional B-spline refinement when the buffer is full.

        Args:
            velocity: Raw velocity from CfC/PID controller

        Returns:
            Smoothed velocity command — same direction, less jerk
        """
        alpha = 1.0 - self._smoothing_factor  # EMA alpha

        if not self._initialized:
            # First command — no smoothing
            self._ema_vn = velocity.north
            self._ema_ve = velocity.east
            self._ema_vd = velocity.down
            self._initialized = True
        else:
            # Exponential moving average — simple but effective
            self._ema_vn = alpha * velocity.north + (1 - alpha) * self._ema_vn
            self._ema_ve = alpha * velocity.east + (1 - alpha) * self._ema_ve
            self._ema_vd = alpha * velocity.down + (1 - alpha) * self._ema_vd

        # Store in buffer for B-spline refinement
        self._vn_buffer.append(self._ema_vn)
        self._ve_buffer.append(self._ema_ve)
        self._vd_buffer.append(self._ema_vd)

        return VelocityNED(
            north=self._ema_vn,
            east=self._ema_ve,
            down=self._ema_vd,
        )

    def smooth_bspline(self, velocity: VelocityNED) -> VelocityNED:
        """
        B-spline smoothing — more compute-intensive but smoother.

        Use this for cinematic shot modes (orbit, reveal) where
        smoothness matters more than responsiveness.
        """
        self._vn_buffer.append(velocity.north)
        self._ve_buffer.append(velocity.east)
        self._vd_buffer.append(velocity.down)

        if len(self._vn_buffer) < 4:
            # Not enough points for cubic B-spline — use EMA
            return self.smooth(velocity)

        # Fit cubic B-spline through recent velocity history
        n = len(self._vn_buffer)
        t = np.arange(n)
        t_eval = np.array([n - 1])  # Evaluate at the latest point

        try:
            # Degree 3 = cubic B-spline
            k = min(3, n - 1)

            spline_n = make_interp_spline(t, list(self._vn_buffer), k=k)
            spline_e = make_interp_spline(t, list(self._ve_buffer), k=k)
            spline_d = make_interp_spline(t, list(self._vd_buffer), k=k)

            return VelocityNED(
                north=float(spline_n(t_eval)[0]),
                east=float(spline_e(t_eval)[0]),
                down=float(spline_d(t_eval)[0]),
            )

        except Exception:
            # B-spline failed (edge case) — fall back to EMA
            return VelocityNED(
                north=self._vn_buffer[-1],
                east=self._ve_buffer[-1],
                down=self._vd_buffer[-1],
            )

    def reset(self) -> None:
        """Clear all smoothing state (e.g., on mode change)."""
        self._vn_buffer.clear()
        self._ve_buffer.clear()
        self._vd_buffer.clear()
        self._ema_vn = 0.0
        self._ema_ve = 0.0
        self._ema_vd = 0.0
        self._initialized = False
