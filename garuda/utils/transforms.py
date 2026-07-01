"""
GarudaOne DroneOS — Coordinate Transforms
==========================================
NED ↔ Body frame, GPS ↔ Local NED, and gimbal angle math.

Coordinate Systems:
  - NED (North-East-Down): PX4's reference frame. X=North, Y=East, Z=Down.
  - Body: Relative to drone. X=Forward, Y=Right, Z=Down.
  - GPS: WGS84 latitude/longitude/altitude.
  - Frame: Image coordinates (0,0 = top-left, normalized 0-1).
"""

import math
from dataclasses import dataclass


# ── Data Classes ─────────────────────────────────────────────────────────────

@dataclass
class VelocityNED:
    """Velocity in NED frame (meters/second)."""
    north: float = 0.0
    east: float = 0.0
    down: float = 0.0

    def magnitude(self) -> float:
        return math.sqrt(self.north**2 + self.east**2 + self.down**2)

    def clamp(self, max_speed: float) -> "VelocityNED":
        mag = self.magnitude()
        if mag > max_speed and mag > 0:
            scale = max_speed / mag
            return VelocityNED(
                self.north * scale, self.east * scale, self.down * scale
            )
        return self


@dataclass
class PositionNED:
    """Position in local NED frame (meters from home)."""
    north: float = 0.0
    east: float = 0.0
    down: float = 0.0

    def distance_to(self, other: "PositionNED") -> float:
        return math.sqrt(
            (self.north - other.north) ** 2
            + (self.east - other.east) ** 2
            + (self.down - other.down) ** 2
        )


@dataclass
class PositionGPS:
    """GPS position in WGS84."""
    latitude_deg: float = 0.0
    longitude_deg: float = 0.0
    altitude_m: float = 0.0


@dataclass
class AttitudeEuler:
    """Euler angles in degrees."""
    roll_deg: float = 0.0
    pitch_deg: float = 0.0
    yaw_deg: float = 0.0


@dataclass
class BoundingBox:
    """Detection bounding box in normalized frame coordinates [0, 1]."""
    x_center: float = 0.5
    y_center: float = 0.5
    width: float = 0.0
    height: float = 0.0
    confidence: float = 0.0
    class_id: int = 0

    @property
    def area(self) -> float:
        return self.width * self.height

    def error_from_center(self) -> tuple[float, float]:
        """Returns (x_error, y_error) from center. Positive = right/down."""
        return (self.x_center - 0.5, self.y_center - 0.5)


# ── Transform Functions ──────────────────────────────────────────────────────

def body_to_ned(vx_body: float, vy_body: float, vz_body: float,
                yaw_rad: float) -> VelocityNED:
    """
    Convert body-frame velocity to NED frame.

    In plain English: the drone thinks in terms of "forward/right/down"
    relative to where it's pointing. PX4 thinks in terms of "North/East/Down".
    This function rotates between them using the drone's current yaw angle.

    Args:
        vx_body: Forward velocity (m/s, positive = forward)
        vy_body: Right velocity (m/s, positive = right)
        vz_body: Down velocity (m/s, positive = down)
        yaw_rad: Current drone yaw angle in radians (0 = North, π/2 = East)
    """
    cos_yaw = math.cos(yaw_rad)
    sin_yaw = math.sin(yaw_rad)

    vn = vx_body * cos_yaw - vy_body * sin_yaw
    ve = vx_body * sin_yaw + vy_body * cos_yaw
    vd = vz_body

    return VelocityNED(north=vn, east=ve, down=vd)


def ned_to_body(vn: float, ve: float, vd: float,
                yaw_rad: float) -> tuple[float, float, float]:
    """
    Convert NED velocity to body frame.
    Returns (vx_forward, vy_right, vz_down).
    """
    cos_yaw = math.cos(yaw_rad)
    sin_yaw = math.sin(yaw_rad)

    vx = vn * cos_yaw + ve * sin_yaw
    vy = -vn * sin_yaw + ve * cos_yaw

    return (vx, vy, vd)


def gps_to_ned(current: PositionGPS, home: PositionGPS) -> PositionNED:
    """
    Convert GPS position to local NED relative to home position.

    Uses a simple equirectangular approximation — accurate enough for
    distances under 1km (our geofence is 100m).
    """
    EARTH_RADIUS_M = 6371000.0

    home_lat_rad = math.radians(home.latitude_deg)

    dlat = math.radians(current.latitude_deg - home.latitude_deg)
    dlon = math.radians(current.longitude_deg - home.longitude_deg)

    north = dlat * EARTH_RADIUS_M
    east = dlon * EARTH_RADIUS_M * math.cos(home_lat_rad)
    down = -(current.altitude_m - home.altitude_m)  # NED: positive down

    return PositionNED(north=north, east=east, down=down)


def bbox_to_gimbal_error(bbox: BoundingBox,
                         target_x: float = 0.5,
                         target_y: float = 0.5) -> tuple[float, float]:
    """
    Compute gimbal correction angles from bounding box position error.

    Returns (yaw_error_deg, pitch_error_deg) needed to center the subject.
    Positive yaw = rotate right, positive pitch = tilt down.

    Args:
        bbox: Detected subject bounding box
        target_x: Desired horizontal position (0.5 = center)
        target_y: Desired vertical position (0.5 = center)
    """
    # Approximate camera FOV (Skydroid C10 Pro ~ 95° horizontal, ~70° vertical)
    HFOV_DEG = 95.0
    VFOV_DEG = 70.0

    x_error = bbox.x_center - target_x  # Positive = subject is right of target
    y_error = bbox.y_center - target_y  # Positive = subject is below target

    yaw_correction = x_error * HFOV_DEG
    pitch_correction = y_error * VFOV_DEG

    return (yaw_correction, pitch_correction)


def angle_wrap_180(angle_deg: float) -> float:
    """Wrap angle to [-180, 180] range."""
    while angle_deg > 180:
        angle_deg -= 360
    while angle_deg < -180:
        angle_deg += 360
    return angle_deg


def degrees_to_radians(deg: float) -> float:
    return deg * math.pi / 180.0


def radians_to_degrees(rad: float) -> float:
    return rad * 180.0 / math.pi
