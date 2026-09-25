"""
Energy & Endurance Forecasting Model
Implements Actuator Disk Momentum Theory to predict hover power, forward flight
aerodynamic drag power, current draw, remaining battery endurance, safe flight
operating envelopes, and mission completion feasibility.
"""

import math
from typing import Dict, Any, Tuple
from garuda.digital_twin.environment import EnvironmentModel
from garuda.digital_twin.vehicle_health import VehicleHealthModel


class EnergyModel:
    """
    Physics-grounded power consumption and endurance calculator for multirotor UAVs.
    """

    def __init__(
        self,
        environment: EnvironmentModel,
        vehicle_health: VehicleHealthModel,
        prop_radius_m: float = 0.0254,     # 2-inch propellers (radius = 1 inch = 0.0254m)
        num_rotors: int = 4,
        frame_drag_coeff: float = 1.05,
        frontal_area_m2: float = 0.012,
        induced_power_factor: float = 1.15
    ):
        self.env = environment
        self.health = vehicle_health

        # Aerodynamic and airframe geometry
        self.prop_radius_m = float(prop_radius_m)
        self.num_rotors = int(num_rotors)
        self.single_disk_area = math.pi * (self.prop_radius_m ** 2)
        self.total_disk_area = self.num_rotors * self.single_disk_area

        self.Cd_frame = float(frame_drag_coeff)
        self.A_frontal = float(frontal_area_m2)
        self.k_induced = float(induced_power_factor)

    # -------------------------------------------------------------------------
    # Momentum Theory Power Calculations
    # -------------------------------------------------------------------------

    def power_hover(self, altitude_agl_m: float = 0.0) -> float:
        """
        Calculates theoretical aerodynamic hover power using Actuator Disk Theory.
        P_ideal = sqrt(T^3 / (2 * rho * A_total))
        P_electrical = (k_induced * P_ideal) / eta_avg
        """
        rho = self.env.get_air_density(altitude_agl_m)
        total_mass = self.health.total_mass_kg
        eta_avg = max(0.20, self.health.avg_rotor_efficiency)

        # Total thrust required to hover = vehicle weight (N)
        thrust_n = total_mass * 9.80665

        # Induced hover power (Watts)
        p_ideal = math.sqrt((thrust_n ** 3) / (2.0 * rho * self.total_disk_area))
        return (self.k_induced * p_ideal) / eta_avg

    def power_forward(self, airspeed_ms: float, altitude_agl_m: float = 0.0) -> float:
        """
        Calculates total power in steady forward flight.
        In forward flight:
          - Translational lift reduces induced power requirements slightly.
          - Parasitic profile and airframe drag power increases with the cube of airspeed (0.5 * rho * Cd * A * v^3).
        """
        airspeed_ms = max(0.0, float(airspeed_ms))
        p_hover = self.power_hover(altitude_agl_m)
        rho = self.env.get_air_density(altitude_agl_m)

        # Translational lift reduction (induced velocity decreases as air flows faster through disk)
        induced_factor = max(0.65, 1.0 - (0.028 * airspeed_ms))

        # Parasitic airframe drag power: P_drag = F_drag * v = (0.5 * rho * Cd * A * v^2) * v
        p_parasitic = 0.5 * rho * self.Cd_frame * self.A_frontal * (airspeed_ms ** 3)

        return (p_hover * induced_factor) + p_parasitic

    def current_draw(self, power_w: float) -> float:
        """
        Estimates total electrical current draw (Amperes) from battery voltage.
        I = Power / Voltage
        """
        voltage = max(6.0, self.health.battery.voltage)
        return max(0.0, power_w / voltage)

    # -------------------------------------------------------------------------
    # Endurance and Mission Feasibility
    # -------------------------------------------------------------------------

    def remaining_endurance_s(self, power_draw_w: float) -> float:
        """
        Estimates remaining flight time in seconds at the specified power draw.
        Usable energy = SoC * Capacity (Ah) * Voltage (V) [Watt-hours].
        """
        if power_draw_w <= 0.0:
            return float("inf")

        battery = self.health.battery
        # Effective capacity in Ah derated by temperature
        temp_derate = 1.0 - 0.01 * max(0.0, 25.0 - battery.temperature_C)
        effective_capacity_ah = battery.capacity_nominal * max(0.5, temp_derate)
        
        # Energy remaining in Watt-hours
        energy_wh = battery.soc * effective_capacity_ah * battery.voltage
        # Convert Watt-hours / Watts to seconds: (Wh / W) * 3600
        return (energy_wh / power_draw_w) * 3600.0

    def can_complete_mission(
        self,
        dist_remaining_target_m: float,
        dist_home_m: float,
        cruise_speed_ms: float = 5.0,
        altitude_agl_m: float = 0.0,
        reserve_buffer_s: float = 30.0
    ) -> Tuple[bool, float, float]:
        """
        Evaluates whether the drone can reach its target, return to launch (RTL),
        and safely land with a reserve buffer.

        Returns:
            (is_feasible, time_available_s, time_required_s)
        """
        cruise_speed = max(1.0, float(cruise_speed_ms))
        p_cruise = self.power_forward(cruise_speed, altitude_agl_m)

        # Flight time needed to finish mission path and return to home
        t_to_target = dist_remaining_target_m / cruise_speed
        t_to_home = dist_home_m / cruise_speed
        t_total_needed = t_to_target + t_to_home + float(reserve_buffer_s)

        t_available = self.remaining_endurance_s(p_cruise)
        is_feasible = t_available >= t_total_needed

        return is_feasible, t_available, t_total_needed

    # -------------------------------------------------------------------------
    # Safe Operating Envelope Boundaries
    # -------------------------------------------------------------------------

    def safe_envelope(self, altitude_agl_m: float = 0.0) -> Dict[str, Any]:
        """
        Calculates dynamic flight boundary limits given current vehicle health
        and environmental atmospheric density / wind conditions.
        """
        p_hov = self.power_hover(altitude_agl_m)
        max_airspeed = 10.0 * self.health.min_rotor_efficiency

        # Theoretical altitude ceiling where air density drops to point where
        # 100% throttle thrust equals vehicle weight (T/W = 1.0)
        # Approximate: altitude where density drops below 0.85 kg/m^3
        max_altitude_agl = max(20.0, min(150.0, 120.0 * (self.health.min_rotor_efficiency / 0.90)))

        # Maximum flight range at 5 m/s cruise speed (meters)
        p_cruise = self.power_forward(5.0, altitude_agl_m)
        endurance_s = self.remaining_endurance_s(p_cruise)
        max_range_m = max(0.0, endurance_s * 5.0)

        return {
            "hover_power_w": round(p_hov, 1),
            "cruise_power_5ms_w": round(p_cruise, 1),
            "max_safe_airspeed_ms": round(max_airspeed, 1),
            "max_safe_altitude_m": round(max_altitude_agl, 1),
            "max_range_m": round(max_range_m, 1),
            "hover_endurance_s": round(self.remaining_endurance_s(p_hov), 1),
            "hover_endurance_min": round(self.remaining_endurance_s(p_hov) / 60.0, 1),
        }
