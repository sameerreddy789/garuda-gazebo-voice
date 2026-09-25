"""
Environmental State Model
Implements ICAO International Standard Atmosphere (ISA) for altitude-dependent
density/temperature, and Dryden Wind Turbulence Model via discrete
Ornstein-Uhlenbeck stochastic processes.
"""

import math
import random
from typing import Dict, List, Any


class EnvironmentModel:
    """
    Simulates atmospheric and wind conditions around the UAV.
    Updates in real-time (10-50 Hz) or on discrete simulation steps.
    """

    def __init__(self, home_altitude_m: float = 920.0):
        """
        Args:
            home_altitude_m: Elevation of launch site above sea level (Bangalore ~920m ASL).
        """
        # --- International Standard Atmosphere (ISA) Constants ---
        self.T0 = 288.15        # Sea-level standard temperature (Kelvin, 15°C)
        self.rho0 = 1.225       # Sea-level standard air density (kg/m^3)
        self.P0 = 101325.0      # Sea-level standard atmospheric pressure (Pa)
        self.L = 0.0065         # Troposphere temperature lapse rate (K/m)
        self.g = 9.80665        # Gravitational acceleration (m/s^2)
        self.R = 287.05         # Specific gas constant for dry air (J/(kg*K))

        self.home_altitude_m = float(home_altitude_m)

        # --- Wind Dynamics (North, East, Down in m/s) ---
        # Steady base wind vector [N, E, D]
        self.wind_steady: List[float] = [0.0, 0.0, 0.0]
        # Stochastic gust component [N, E, D] modeled via Ornstein-Uhlenbeck process
        self.wind_gust: List[float] = [0.0, 0.0, 0.0]

        # Turbulence parameters (Dryden spectrum discrete approximation)
        self.turbulence_intensity: float = 0.2  # 0.0 (dead calm) to 1.0 (severe storm)
        self.gust_tau: float = 4.0             # Correlation time constant in seconds

        # --- Active Injected Disturbances ---
        self.temp_offset_C: float = 0.0
        self.vertical_shear_ms: float = 0.0

    # -------------------------------------------------------------------------
    # Atmospheric Physics (ISA Equations)
    # -------------------------------------------------------------------------

    def get_temperature_K(self, altitude_agl_m: float = 0.0) -> float:
        """
        Calculates ambient temperature in Kelvin at a given altitude Above Ground Level (AGL).
        T(h) = T0 - L * (h_home + h_agl) + temp_offset
        """
        h_asl = self.home_altitude_m + max(0.0, altitude_agl_m)
        return (self.T0 - self.L * h_asl) + self.temp_offset_C

    def get_temperature_C(self, altitude_agl_m: float = 0.0) -> float:
        """Calculates ambient temperature in Celsius."""
        return self.get_temperature_K(altitude_agl_m) - 273.15

    def get_pressure_pa(self, altitude_agl_m: float = 0.0) -> float:
        """
        Calculates atmospheric pressure in Pascals using the barometric formula.
        P(h) = P0 * (T(h) / T0) ^ (g / (R * L))
        """
        t_k = self.get_temperature_K(altitude_agl_m)
        exponent = self.g / (self.R * self.L)
        return self.P0 * ((t_k - self.temp_offset_C) / self.T0) ** exponent

    def get_air_density(self, altitude_agl_m: float = 0.0) -> float:
        """
        Calculates air density rho in kg/m^3 at a given altitude AGL.
        rho(h) = rho0 * (T(h) / T0) ^ ((g / (R * L)) - 1)
        """
        t_k = self.get_temperature_K(altitude_agl_m)
        exponent = (self.g / (self.R * self.L)) - 1.0
        # Incorporate temperature disturbance directly into density calculation
        base_density = self.rho0 * (t_k / self.T0) ** exponent
        return max(0.1, base_density)

    # -------------------------------------------------------------------------
    # Wind and Turbulence Dynamics
    # -------------------------------------------------------------------------

    def get_wind_vector(self) -> List[float]:
        """
        Returns total wind vector [N, E, D] in m/s (Steady + Gusts + Shear).
        """
        return [
            self.wind_steady[0] + self.wind_gust[0],
            self.wind_steady[1] + self.wind_gust[1],
            self.wind_steady[2] + self.wind_gust[2] + self.vertical_shear_ms,
        ]

    def get_wind_speed(self) -> float:
        """
        Returns horizontal wind speed magnitude in m/s.
        """
        w = self.get_wind_vector()
        return math.sqrt(w[0] ** 2 + w[1] ** 2)

    def get_wind_heading_deg(self) -> float:
        """
        Returns compass direction the wind is blowing TOWARD in degrees (0-360).
        0 = North, 90 = East, 180 = South, 270 = West.
        """
        w = self.get_wind_vector()
        angle = math.degrees(math.atan2(w[1], w[0]))
        return (angle + 360.0) % 360.0

    def step(self, dt: float = 0.1) -> None:
        """
        Advances the stochastic wind environment by dt seconds using an
        Ornstein-Uhlenbeck mean-reverting process (Dryden equivalent).

        dx = -theta * x * dt + sigma * dW
        Discrete formulation:
        x(t+dt) = x(t) * exp(-dt/tau) + sigma * sqrt(1 - exp(-2*dt/tau)) * N(0,1)
        """
        if dt <= 0:
            return

        # Scale turbulence intensity to standard deviation (m/s)
        sigma = self.turbulence_intensity * 3.5
        decay = math.exp(-dt / self.gust_tau)
        diffusion = sigma * math.sqrt(max(0.0, 1.0 - decay ** 2))

        for i in range(3):
            # Vertical axis typically has 50-70% lower turbulence near ground
            axis_scale = 0.6 if i == 2 else 1.0
            noise = random.gauss(0.0, 1.0)
            self.wind_gust[i] = (self.wind_gust[i] * decay) + (diffusion * axis_scale * noise)

    # -------------------------------------------------------------------------
    # Scenario Disturbance Injections
    # -------------------------------------------------------------------------

    def inject_crosswind(self, speed_ms: float = 12.0, from_east: bool = True) -> None:
        """
        Simulates an abrupt lateral crosswind gust (e.g. 12 m/s).
        """
        self.wind_steady[1] = float(speed_ms) if from_east else -float(speed_ms)

    def inject_temperature_spike(self, delta_C: float = 20.0) -> None:
        """
        Simulates sudden ambient temperature rise (e.g., flight over industrial heat island).
        Reduces air density and strains battery thermal limits.
        """
        self.temp_offset_C = float(delta_C)

    def inject_downdraft(self, speed_ms: float = 5.0) -> None:
        """
        Simulates a vertical downdraft (+Down in NED coordinate frame).
        """
        self.wind_steady[2] = abs(float(speed_ms))

    def inject_wind_shear(self, shear_delta_ms: float = 4.0) -> None:
        """
        Simulates microburst or altitude-dependent wind shear.
        """
        self.vertical_shear_ms = float(shear_delta_ms)

    def reset_disturbances(self) -> None:
        """Resets all injected disturbances back to calm baseline."""
        self.wind_steady = [0.0, 0.0, 0.0]
        self.wind_gust = [0.0, 0.0, 0.0]
        self.temp_offset_C = 0.0
        self.vertical_shear_ms = 0.0
        self.turbulence_intensity = 0.2

    # -------------------------------------------------------------------------
    # Telemetry Snapshot
    # -------------------------------------------------------------------------

    def snapshot(self, altitude_agl_m: float = 0.0) -> Dict[str, Any]:
        """
        Returns a serializable dictionary of the current environmental state.
        """
        wind = self.get_wind_vector()
        return {
            "altitude_agl_m": round(altitude_agl_m, 2),
            "altitude_asl_m": round(self.home_altitude_m + altitude_agl_m, 2),
            "air_density_kg_m3": round(self.get_air_density(altitude_agl_m), 4),
            "temperature_C": round(self.get_temperature_C(altitude_agl_m), 2),
            "pressure_hpa": round(self.get_pressure_pa(altitude_agl_m) / 100.0, 2),
            "wind_vector_ms": [round(w, 2) for w in wind],
            "wind_speed_ms": round(self.get_wind_speed(), 2),
            "wind_heading_deg": round(self.get_wind_heading_deg(), 1),
            "turbulence_intensity": round(self.turbulence_intensity, 2),
            "temp_offset_C": round(self.temp_offset_C, 2),
        }
