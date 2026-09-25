"""
GarudaOne Digital Twin Simulation Engine Runner
Coordinates the continuous execution of the Environment Model, Vehicle Health Model,
Energy Model, State Estimator (Kalman Filter), and Autonomous Decision Engine.
Outputs synchronized telemetry snapshots at 10-20 Hz.
"""

import time
import json
import os
import random
from typing import Dict, Any, Optional, Callable

from garuda.digital_twin.environment import EnvironmentModel
from garuda.digital_twin.vehicle_health import VehicleHealthModel
from garuda.digital_twin.energy_model import EnergyModel
from garuda.digital_twin.state_estimator import DigitalTwinStateEstimator
from garuda.digital_twin.decision_engine import DecisionEngine, Decision, DecisionRecord


class DigitalTwinRunner:
    """
    Master simulation executive. Advances physical states and executes decision support.
    """

    def __init__(
        self,
        home_altitude_m: float = 920.0,
        initial_payload_kg: float = 0.0,
        telemetry_log_path: Optional[str] = None
    ):
        self.home_altitude_m = float(home_altitude_m)
        self.telemetry_log_path = telemetry_log_path or os.path.join("logs", "digital_twin_telemetry.json")

        # Initialize Core Modules
        self.environment = EnvironmentModel(home_altitude_m=self.home_altitude_m)
        self.vehicle_health = VehicleHealthModel(drone_dry_mass_kg=0.249, payload_kg=initial_payload_kg)
        self.energy_model = EnergyModel(self.environment, self.vehicle_health)
        self.state_estimator = DigitalTwinStateEstimator()
        self.decision_engine = DecisionEngine(
            self.environment, self.vehicle_health, self.energy_model, self.state_estimator
        )

        # Drone Kinematic & Mission State
        self.sim_time: float = 0.0
        self.altitude_agl_m: float = 15.0
        self.airspeed_ms: float = 5.0
        self.heading_deg: float = 45.0
        self.lat: float = 12.971600     # Bangalore reference coordinates
        self.lon: float = 77.594600
        self.dist_target_m: float = 250.0
        self.dist_home_m: float = 40.0

        # Flight mode / status
        self.flight_phase: str = "CRUISE"  # TAKEOFF, CRUISE, HOVER, RTL, LANDING, EMERGENCY_LAND
        self.latest_decision_record: Optional[DecisionRecord] = None
        self.running: bool = False

        # Ensure logs directory exists
        log_dir = os.path.dirname(self.telemetry_log_path)
        if log_dir and not os.path.exists(log_dir):
            os.makedirs(log_dir, exist_ok=True)

    def step(self, dt: float = 0.1) -> Dict[str, Any]:
        """
        Single simulation tick:
        1. Advance stochastic atmosphere & wind
        2. Calculate aerodynamic power demand & current draw
        3. Advance battery thermal state & Coulomb counting
        4. Advance motor degradation & vibration stress
        5. Update Kalman Filter state estimation & uncertainty
        6. Evaluate Autonomous Decision Engine
        7. Update kinematic positions
        8. Return consolidated telemetry snapshot
        """
        self.sim_time += dt

        # 1. Environment tick
        self.environment.step(dt)
        ambient_temp_C = self.environment.get_temperature_C(self.altitude_agl_m)

        # 2. Power & Electrical draw
        power_w = self.energy_model.power_forward(self.airspeed_ms, self.altitude_agl_m)
        current_A = self.energy_model.current_draw(power_w)

        # 3. Vehicle Health tick (Battery thermal ODE + Coulomb counting + Rotors)
        # Normal vertical acceleration ~9.81 m/s^2 plus wind-induced turbulence vibration
        turb_accel = 9.80665 + random.gauss(0.0, self.environment.turbulence_intensity * 1.5)
        self.vehicle_health.step(
            current_A=current_A,
            ambient_temp_C=ambient_temp_C,
            airspeed_ms=self.airspeed_ms,
            accel_ms2=turb_accel,
            dt=dt
        )

        # 4. Kalman State Estimator (Physics Prediction + Noisy Sensor Update)
        predicted_endurance = self.energy_model.remaining_endurance_s(power_w)
        self.state_estimator.predict_physics(
            predicted_alt_m=self.altitude_agl_m,
            predicted_airspeed_ms=self.airspeed_ms,
            predicted_wind_ms=self.environment.get_wind_speed(),
            predicted_soc=self.vehicle_health.battery.percent,
            predicted_endurance_s=predicted_endurance,
            dt=dt
        )
        # Simulate noisy sensor observations (GPS/Barometer/Current sensor)
        noisy_alt = self.altitude_agl_m + random.gauss(0.0, 0.25)
        noisy_speed = self.airspeed_ms + random.gauss(0.0, 0.20)
        noisy_soc = self.vehicle_health.battery.percent + random.gauss(0.0, 0.30)
        self.state_estimator.update_sensor_telemetry(
            measured_alt_m=noisy_alt,
            measured_airspeed_ms=noisy_speed,
            measured_soc=noisy_soc
        )

        # 5. Evaluate Autonomous Decision Engine
        record = self.decision_engine.evaluate(
            altitude_agl_m=self.altitude_agl_m,
            dist_target_m=self.dist_target_m,
            dist_home_m=self.dist_home_m,
            current_airspeed_ms=self.airspeed_ms
        )
        self.latest_decision_record = record

        # React to autonomous decisions (Autonomous Closed-Loop Simulation)
        if record.decision == Decision.REDUCE_SPEED:
            self.airspeed_ms = max(2.5, self.airspeed_ms * 0.95)
        elif record.decision == Decision.ALTER_ALTITUDE:
            # Descend to denser air or climb above shear
            self.altitude_agl_m = max(10.0, self.altitude_agl_m - (1.5 * dt))
        elif record.decision == Decision.RETURN_TO_BASE:
            self.flight_phase = "RTL"
            self.dist_home_m = max(0.0, self.dist_home_m - (self.airspeed_ms * dt))
        elif record.decision == Decision.ABORT_MISSION:
            self.flight_phase = "EMERGENCY_LAND"
            self.altitude_agl_m = max(0.0, self.altitude_agl_m - (3.0 * dt))
            self.airspeed_ms = max(0.0, self.airspeed_ms * 0.8)
        else:
            # Normal forward progress
            if self.flight_phase == "CRUISE":
                self.dist_target_m = max(0.0, self.dist_target_m - (self.airspeed_ms * dt))
                self.dist_home_m += (self.airspeed_ms * 0.3 * dt)

        # 6. Generate Telemetry Snapshot
        snapshot = self.get_telemetry_snapshot()

        # Save to disk for web dashboard polling
        try:
            with open(self.telemetry_log_path, "w") as f:
                json.dump(snapshot, f, indent=2)
        except Exception:
            pass

        return snapshot

    def get_telemetry_snapshot(self) -> Dict[str, Any]:
        """
        Builds a comprehensive, unified telemetry packet containing:
        - Kinematics (Alt, Speed, Heading, Lat/Lon)
        - Environment (Wind, Density, Temp, Turbulence)
        - Vehicle Health (Battery Temp, Voltage, Motor Efficiencies, Structural Stress)
        - Energy & Envelope (Power draw, remaining endurance, safe envelope boundaries)
        - Uncertainty Bands (Kalman Filter estimates with ± confidence bounds)
        - Latest Autonomous Decision & Evidence Trail
        """
        p_cruise = self.energy_model.power_forward(self.airspeed_ms, self.altitude_agl_m)
        envelope = self.energy_model.safe_envelope(self.altitude_agl_m)
        estimator_state = self.state_estimator.snapshot()

        return {
            "timestamp": round(time.time(), 3),
            "sim_time_s": round(self.sim_time, 2),
            "flight_phase": self.flight_phase,
            "telemetry": {
                "altitude_agl_m": round(self.altitude_agl_m, 2),
                "altitude_asl_m": round(self.home_altitude_m + self.altitude_agl_m, 2),
                "airspeed_ms": round(self.airspeed_ms, 2),
                "heading_deg": round(self.heading_deg, 1),
                "latitude": round(self.lat, 6),
                "longitude": round(self.lon, 6),
                "distance_to_target_m": round(self.dist_target_m, 1),
                "distance_to_home_m": round(self.dist_home_m, 1),
            },
            "environment": self.environment.snapshot(self.altitude_agl_m),
            "vehicle_health": self.vehicle_health.snapshot(),
            "energy": {
                "current_power_w": round(p_cruise, 1),
                "current_draw_A": round(self.energy_model.current_draw(p_cruise), 2),
                "remaining_endurance_s": round(self.energy_model.remaining_endurance_s(p_cruise), 1),
                "remaining_endurance_min": round(self.energy_model.remaining_endurance_s(p_cruise) / 60.0, 1),
                "safe_envelope": envelope,
            },
            "uncertainty": estimator_state,
            "decision": self.latest_decision_record.to_dict() if self.latest_decision_record else None,
        }
