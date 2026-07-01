"""
GarudaOne DroneOS — Gimbal Controller
=======================================
Controls the Skydroid C10 Pro 3-axis gimbal.

The gimbal is GarudaOne's "secret weapon":
  When the drone banks right to flow around a tree, the gimbal
  counter-rotates LEFT to keep the camera locked on the subject.
  The viewer sees a perfectly smooth dolly shot — zero evidence
  an obstacle was dodged.

The Skydroid C10 uses a proprietary protocol over UART.
This module handles the gimbal communication + counter-rotation math.
"""

import math
import time

from garuda.core.config import Config
from garuda.utils.logger import get_logger

log = get_logger("gimbal")


class GimbalController:
    """
    Skydroid C10 Pro 3-axis gimbal controller.

    Provides:
      - Direct angle control (pitch, yaw, roll)
      - Counter-rotation during drone maneuvers
      - Smooth interpolation between angles
      - Subject-locked tracking
    """

    def __init__(self, config: Config):
        self.config = config

        # Gimbal limits
        self._pitch_min = config.get("gimbal.pitch_min_deg", -90)
        self._pitch_max = config.get("gimbal.pitch_max_deg", 30)
        self._yaw_range = config.get("gimbal.yaw_range_deg", 330)
        self._smoothing = config.get("gimbal.smoothing_factor", 0.85)
        self._counter_rotate = config.get("gimbal.counter_rotate_enabled", True)

        # Current angles
        self._current_pitch = config.get("gimbal.default_pitch_deg", -15)
        self._current_yaw = 0.0
        self._current_roll = 0.0

        # Target angles (smoothly interpolated toward these)
        self._target_pitch = self._current_pitch
        self._target_yaw = 0.0
        self._target_roll = 0.0

        # Serial connection to Skydroid (proprietary protocol)
        self._serial = None
        self._connected = False

        log.info(
            f"Gimbal controller initialized — "
            f"pitch=[{self._pitch_min}°, {self._pitch_max}°], "
            f"counter-rotate={'ON' if self._counter_rotate else 'OFF'}"
        )

    def connect(self) -> bool:
        """Connect to the Skydroid gimbal via UART."""
        try:
            # TODO: Implement Skydroid proprietary protocol connection
            # The protocol has been reverse-engineered by the hardware team
            self._connected = True
            log.info("Gimbal connected (stub mode)")
            return True
        except Exception as e:
            log.error(f"Gimbal connection failed: {e}")
            return False

    def set_angle(self, pitch_deg: float = 0.0, yaw_deg: float = 0.0) -> None:
        """
        Set target gimbal angles. Smoothly interpolated each update().

        Args:
            pitch_deg: -90 = straight down, 0 = horizon, 30 = above
            yaw_deg: Relative yaw from drone heading
        """
        self._target_pitch = max(self._pitch_min, min(self._pitch_max, pitch_deg))
        self._target_yaw = max(-self._yaw_range / 2,
                               min(self._yaw_range / 2, yaw_deg))

    def apply_counter_rotation(
        self, drone_roll_deg: float, drone_yaw_rate_dps: float
    ) -> None:
        """
        Counter-rotate the gimbal to compensate for drone body movement.

        This is what makes the footage look like it was shot from a
        steady dolly, not a banking drone. When the drone tilts right,
        the gimbal tilts left by the same amount.

        Args:
            drone_roll_deg: Current drone roll angle
            drone_yaw_rate_dps: Current drone yaw rate (degrees/second)
        """
        if not self._counter_rotate:
            return

        # Roll compensation: gimbal roll = -drone roll
        self._target_roll = -drone_roll_deg

        # Yaw rate compensation: during turns, counter-rotate yaw
        # to keep the camera pointing at the original target
        dt = 0.02  # ~50Hz
        yaw_compensation = -drone_yaw_rate_dps * dt
        self._target_yaw += yaw_compensation

    def update(self) -> None:
        """
        Update gimbal angles — call this every tick (50Hz).
        Smoothly interpolates current angles toward targets.
        """
        alpha = 1.0 - self._smoothing

        self._current_pitch += alpha * (self._target_pitch - self._current_pitch)
        self._current_yaw += alpha * (self._target_yaw - self._current_yaw)
        self._current_roll += alpha * (self._target_roll - self._current_roll)

        # Send to hardware
        if self._connected:
            self._send_command(
                self._current_pitch,
                self._current_yaw,
                self._current_roll,
            )

    def _send_command(self, pitch: float, yaw: float, roll: float) -> None:
        """
        Send gimbal angle command via Skydroid protocol.
        TODO: Implement actual protocol bytes.
        """
        # Skydroid C10 Pro uses a proprietary UART protocol
        # that the hardware team has reverse-engineered.
        # Format: [HEADER][PITCH_MSB][PITCH_LSB][YAW_MSB][YAW_LSB][ROLL_MSB][ROLL_LSB][CRC]
        pass

    def look_at_subject(self, yaw_error_deg: float, pitch_error_deg: float) -> None:
        """
        Point the gimbal at the detected subject.

        Args:
            yaw_error_deg: How far left/right the subject is from center
            pitch_error_deg: How far up/down the subject is from center
        """
        self._target_yaw += yaw_error_deg * 0.3  # Gain factor
        self._target_pitch += pitch_error_deg * 0.3

    def center(self) -> None:
        """Return gimbal to forward-looking default position."""
        self._target_pitch = self.config.get("gimbal.default_pitch_deg", -15)
        self._target_yaw = 0.0
        self._target_roll = 0.0

    @property
    def angles(self) -> tuple[float, float, float]:
        """Current gimbal angles (pitch, yaw, roll) in degrees."""
        return (self._current_pitch, self._current_yaw, self._current_roll)
