"""
GarudaOne DroneOS — Cinematic Flight Controller
=================================================
CfC (Closed-form Continuous-time) Liquid Neural Network controller,
with a PID fallback for use before imitation learning training.

The CfC LNN is trained via Imitation Learning:
  1. Pilot manually flies the drone through obstacles
  2. Record: SVO2 depth + PicoDet bbox + pilot stick inputs
  3. Train 19-50 neuron CfC network to replicate the pilot's movements

Until that training data exists, we use a classical PID controller
that tracks the subject using bounding box error and depth data.
The PID output goes through the B-spline smoother (path_smoother.py)
so the footage is still smooth, just not as "cinematic" as the LNN.

The key insight: the controller doesn't just avoid obstacles — it arcs
smoothly around them while the gimbal counter-rotates to keep the
subject in frame. The viewer never sees the maneuver.
"""

import math
import time
from typing import Optional

from garuda.core.config import Config
from garuda.perception.visual_odom import DepthMap
from garuda.utils.logger import get_logger
from garuda.utils.profiler import profiler
from garuda.utils.transforms import (
    BoundingBox, VelocityNED, bbox_to_gimbal_error, angle_wrap_180
)

log = get_logger("controller")


class PIDState:
    """Single-axis PID controller state."""

    def __init__(self, kp: float, ki: float, kd: float, integral_limit: float = 2.0):
        self.kp = kp
        self.ki = ki
        self.kd = kd
        self.integral_limit = integral_limit

        self._integral = 0.0
        self._previous_error = 0.0
        self._last_time = time.time()

    def compute(self, error: float) -> float:
        """Compute PID output for a given error value."""
        now = time.time()
        dt = now - self._last_time
        self._last_time = now

        if dt <= 0 or dt > 1.0:
            dt = 0.02  # Assume 50Hz if dt is weird

        # Proportional
        p_term = self.kp * error

        # Integral (with anti-windup clamping)
        self._integral += error * dt
        self._integral = max(-self.integral_limit,
                             min(self.integral_limit, self._integral))
        i_term = self.ki * self._integral

        # Derivative
        derivative = (error - self._previous_error) / dt
        d_term = self.kd * derivative
        self._previous_error = error

        return p_term + i_term + d_term

    def reset(self) -> None:
        self._integral = 0.0
        self._previous_error = 0.0


class FlightController:
    """
    Main flight controller — generates velocity commands from perception data.

    Modes:
      - "tracking": Follow subject, keep centered in frame
      - "orbit":    Circle around subject at fixed radius
      - "chase":    Follow behind subject
      - "reveal":   Pull back and rise to reveal the scene

    Falls back to PID when CfC LNN is not trained.
    """

    def __init__(self, config: Config, gimbal=None):
        self.config = config
        self._gimbal = gimbal  # GimbalController reference (can be set later)

        # PID controllers (fallback until CfC is trained)
        pid_config = config.get("control.pid_fallback", {})

        pos_cfg = pid_config.get("position", {})
        self._pid_x = PIDState(
            kp=pos_cfg.get("kp", 0.8),
            ki=pos_cfg.get("ki", 0.05),
            kd=pos_cfg.get("kd", 0.3),
            integral_limit=pos_cfg.get("integral_limit", 2.0),
        )
        self._pid_y = PIDState(
            kp=pos_cfg.get("kp", 0.8),
            ki=pos_cfg.get("ki", 0.05),
            kd=pos_cfg.get("kd", 0.3),
            integral_limit=pos_cfg.get("integral_limit", 2.0),
        )

        alt_cfg = pid_config.get("altitude", {})
        self._pid_alt = PIDState(
            kp=alt_cfg.get("kp", 1.0),
            ki=alt_cfg.get("ki", 0.1),
            kd=alt_cfg.get("kd", 0.5),
            integral_limit=alt_cfg.get("integral_limit", 1.5),
        )

        yaw_cfg = pid_config.get("yaw", {})
        self._pid_yaw = PIDState(
            kp=yaw_cfg.get("kp", 1.2),
            ki=yaw_cfg.get("ki", 0.02),
            kd=yaw_cfg.get("kd", 0.4),
            integral_limit=yaw_cfg.get("integral_limit", 1.0),
        )

        # CfC LNN (when trained)
        self._cfc_model = None
        self._use_cfc = False

        # Orbit mode state
        self._orbit_radius = 8.0
        self._orbit_speed = 2.0
        self._orbit_direction = 1  # 1=CW, -1=CCW
        self._orbit_angle = 0.0

        # Reveal mode state
        self._reveal_speed = 2.0
        self._reveal_distance = 15.0
        self._reveal_start_time = 0.0
        self._reveal_complete = False

        # Target tracking params
        self._follow_distance = config.get("tracking.default_follow_distance_m", 5.0)
        self._target_bbox_size = config.get("tracking.target_bbox_size", 0.25)

        log.info("Flight controller initialized (PID fallback mode)")

    def load_cfc_model(self) -> bool:
        """
        Load the trained CfC LNN model.
        Returns False if no trained model exists (use PID fallback).
        """
        try:
            import torch
            from ncps.torch import CfC
            from ncps.wirings import AutoNCP

            # Check if trained model exists
            model_path = self.config.models_dir / "cfc_controller.pt"
            if not model_path.exists():
                log.info("No trained CfC model found — using PID fallback")
                return False

            # Load model
            wiring = AutoNCP(
                units=19,  # 19 neurons as per architecture
                output_size=4,  # vx, vy, vz, gimbal_yaw
            )
            self._cfc_model = CfC(
                input_size=8,  # bbox(4) + depth_summary(3) + follow_distance(1)
                wiring=wiring,
            )
            self._cfc_model.load_state_dict(torch.load(model_path))
            self._cfc_model.eval()
            self._use_cfc = True

            log.info("✓ CfC LNN model loaded")
            return True

        except ImportError:
            log.info("ncps not installed — using PID fallback")
            return False
        except Exception as e:
            log.warning(f"Failed to load CfC model: {e}")
            return False

    # ── Main Compute Methods ──────────────────────────────────────────────

    def compute(
        self,
        bbox: BoundingBox,
        depth_map: Optional[DepthMap] = None,
        mode: str = "tracking",
    ) -> tuple[VelocityNED, float]:
        """
        Compute velocity command and gimbal angle from perception data.

        Args:
            bbox: Current subject bounding box
            depth_map: Sparse depth from visual odometry (optional)
            mode: "tracking", "chase", "orbit", "reveal"

        Returns:
            (velocity_ned, gimbal_yaw_deg) — the command to send to PX4
        """
        with profiler.measure("controller"):
            if self._use_cfc and self._cfc_model:
                return self._compute_cfc(bbox, depth_map, mode)
            else:
                return self._compute_pid(bbox, depth_map, mode)

    def _compute_pid(
        self,
        bbox: BoundingBox,
        depth_map: Optional[DepthMap],
        mode: str,
    ) -> tuple[VelocityNED, float]:
        """
        PID fallback controller.

        Uses bounding box position error to generate velocity commands.
        The subject's position in the frame tells us which way to move:
          - Subject left of center → fly left (negative east velocity)
          - Subject above center → fly up (negative down velocity)
          - Subject too small → fly forward (positive north velocity)
          - Subject too large → fly backward (negative north velocity)
        """
        # Compute position error (how far is the subject from frame center)
        x_error, y_error = bbox.error_from_center()

        # Compute size error (subject should occupy target_bbox_size of frame)
        size_error = bbox.height - self._target_bbox_size

        # PID outputs
        # X error → East/West velocity (subject left = fly left)
        ve = -self._pid_x.compute(x_error) * 3.0

        # Y error → Up/Down velocity (subject above = fly up)
        vd = self._pid_y.compute(y_error) * 2.0

        # Size error → Forward/Backward velocity (too small = fly forward)
        vn = -self._pid_alt.compute(size_error) * 3.0

        # Obstacle avoidance nudge from depth map
        if depth_map and depth_map.has_data:
            obstacles = depth_map.get_obstacle_regions(threshold_m=3.0)
            if len(obstacles) > 10:
                # Simple: if obstacles detected, slow down
                vn *= 0.5
                log.debug(f"Obstacle detected — slowing down ({len(obstacles)} points)")

        # Clamp individual axes
        max_speed = self.config.get("flight.max_speed_ms", 10.0)
        vn = max(-max_speed, min(max_speed, vn))
        ve = max(-max_speed, min(max_speed, ve))
        vd = max(-max_speed / 2, min(max_speed / 2, vd))

        velocity = VelocityNED(north=vn, east=ve, down=vd)

        # Gimbal: point at the subject
        gimbal_yaw_correction, _ = bbox_to_gimbal_error(bbox)

        return velocity, gimbal_yaw_correction

    def _compute_cfc(
        self,
        bbox: BoundingBox,
        depth_map: Optional[DepthMap],
        mode: str,
    ) -> tuple[VelocityNED, float]:
        """
        CfC LNN controller (used after imitation learning training).

        Input features: [bbox_cx, bbox_cy, bbox_w, bbox_h,
                         depth_near, depth_mid, depth_far,
                         follow_distance]
        Output: [vn, ve, vd, gimbal_yaw]
        """
        import torch

        # Prepare input features
        depth_near = 5.0  # Default distances
        depth_mid = 10.0
        depth_far = 15.0

        if depth_map and depth_map.has_data:
            valid_depths = depth_map.depths[depth_map.valid_mask]
            if len(valid_depths) > 0:
                depth_near = float(valid_depths.min())
                depth_mid = float(valid_depths.mean())
                depth_far = float(valid_depths.max())

        features = torch.tensor([
            bbox.x_center, bbox.y_center, bbox.width, bbox.height,
            depth_near, depth_mid, depth_far,
            self._follow_distance,
        ], dtype=torch.float32).unsqueeze(0)

        with torch.no_grad():
            output = self._cfc_model(features)

        vn, ve, vd, gimbal_yaw = output[0].numpy()
        velocity = VelocityNED(north=float(vn), east=float(ve), down=float(vd))

        return velocity, float(gimbal_yaw)

    # ── Shot Mode Methods ─────────────────────────────────────────────────

    def set_orbit_params(
        self,
        radius: float = 8.0,
        speed: float = 2.0,
        direction: str = "clockwise",
    ) -> None:
        """Configure orbit parameters."""
        self._orbit_radius = radius
        self._orbit_speed = speed
        self._orbit_direction = 1 if direction == "clockwise" else -1
        self._orbit_angle = 0.0
        log.info(f"Orbit params: radius={radius}m, speed={speed}m/s, dir={direction}")

    def compute_orbit(self) -> tuple[VelocityNED, float]:
        """
        Compute velocity for orbit mode — fly in a circle around the subject.

        The drone moves along a circle while the gimbal always points at center.
        """
        # Advance orbit angle
        angular_speed = self._orbit_speed / self._orbit_radius  # rad/s
        dt = 0.02  # ~50Hz
        self._orbit_angle += angular_speed * dt * self._orbit_direction

        # Velocity tangent to the orbit circle
        vn = -math.sin(self._orbit_angle) * self._orbit_speed * self._orbit_direction
        ve = math.cos(self._orbit_angle) * self._orbit_speed * self._orbit_direction
        vd = 0.0

        velocity = VelocityNED(north=vn, east=ve, down=vd)

        # Gimbal points at center of orbit (opposite to movement direction)
        gimbal_yaw = math.degrees(self._orbit_angle + math.pi)
        gimbal_yaw = angle_wrap_180(gimbal_yaw)

        return velocity, gimbal_yaw

    def start_reveal(self, speed: float = 2.0, distance: float = 15.0) -> None:
        """Start a reveal shot (pull back and rise)."""
        self._reveal_speed = speed
        self._reveal_distance = distance
        self._reveal_start_time = time.time()
        self._reveal_complete = False
        log.info(f"Starting reveal: speed={speed}m/s, distance={distance}m")

    def compute_reveal(self) -> tuple[VelocityNED, float]:
        """
        Compute velocity for reveal shot — pull back and rise simultaneously.
        The camera gradually tilts down to keep the subject in frame.
        """
        elapsed = time.time() - self._reveal_start_time
        total_time = self._reveal_distance / self._reveal_speed

        if elapsed >= total_time:
            self._reveal_complete = True
            return VelocityNED(0, 0, 0), 0.0

        # Progress 0→1
        progress = elapsed / total_time

        # Pull back (negative north = backward) with ease-out
        ease = 1 - (1 - progress) ** 2  # Quadratic ease-out
        vn = -self._reveal_speed * (1 - ease * 0.5)  # Slow down near end

        # Rise (negative down = up)
        vd = -self._reveal_speed * 0.5  # Rise at half the pullback speed

        velocity = VelocityNED(north=vn, east=0.0, down=vd)

        # Gimbal tilts down as we rise to keep subject in frame
        gimbal_yaw = -progress * 30  # Tilt down 0→-30 degrees

        return velocity, gimbal_yaw

    @property
    def reveal_complete(self) -> bool:
        return self._reveal_complete

    async def set_gimbal(self, yaw_correction_deg: float) -> None:
        """Send gimbal angle command via the GimbalController."""
        if self._gimbal is not None:
            self._gimbal.look_at_subject(
                yaw_error_deg=yaw_correction_deg,
                pitch_error_deg=0.0,
            )
            self._gimbal.update()
        # If no gimbal is connected, this is silently skipped

    def set_gimbal_controller(self, gimbal) -> None:
        """Set the gimbal controller reference (can be called after init)."""
        self._gimbal = gimbal
        log.info("Gimbal controller linked to flight controller")
