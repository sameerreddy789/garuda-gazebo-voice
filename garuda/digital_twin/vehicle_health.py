"""
Vehicle Health Model
Simulates battery thermal dynamics (Joule heating + convective cooling ODE),
Coulomb counting state-of-charge with temperature derating, rotor bearing
wear/degradation, payload mass variations, and cumulative structural stress.
"""

from typing import Dict, List, Any, Optional


class BatteryModel:
    """
    1st-Order Lumped Thermal and Electrochemical Model for Lithium-Polymer (LiPo) Battery.
    """

    def __init__(
        self,
        capacity_ah: float = 0.45,
        cells: int = 3,
        internal_resistance: float = 0.08,
        ambient_temp_C: float = 25.0
    ):
        self.capacity_nominal = float(capacity_ah)     # Rated capacity in Ah
        self.cells = int(cells)                        # 3S configuration
        self.R_int = float(internal_resistance)        # Internal resistance in Ohms
        
        # State variables
        self.soc: float = 1.0                          # State of Charge (0.0 to 1.0)
        self.temperature_C: float = float(ambient_temp_C)
        self.voltage: float = self.cells * 4.2         # 12.6V fully charged for 3S
        
        # Physical thermal properties
        self.mass_kg: float = 0.035                    # 35g for 450mAh 3S pack
        self.surface_area_m2: float = 0.003            # Surface area exposed to convective airflow
        self.Cp: float = 1000.0                        # Specific heat capacity (J/(kg*K))

    @property
    def percent(self) -> float:
        """Returns battery percentage (0.0% to 100.0%)."""
        return max(0.0, min(100.0, self.soc * 100.0))

    @property
    def is_warning_temp(self) -> bool:
        """Battery exceeds 50°C (thermal throttling / RTB threshold)."""
        return self.temperature_C >= 50.0

    @property
    def is_critical_temp(self) -> bool:
        """Battery exceeds 60°C (thermal runaway risk / emergency abort)."""
        return self.temperature_C >= 60.0

    def step(
        self,
        current_A: float,
        ambient_temp_C: float,
        airspeed_ms: float = 0.0,
        dt: float = 0.1
    ) -> None:
        """
        Advances the battery state by dt seconds.
        - Calculates internal Joule heating (I^2 * R)
        - Calculates convective cooling based on airspeed
        - Updates temperature via 1st-order differential equation
        - Performs Coulomb counting for charge depletion
        """
        if dt <= 0:
            return

        current_A = max(0.0, float(current_A))
        airspeed_ms = max(0.0, float(airspeed_ms))

        # 1. Thermal Dynamics: dT/dt = (Q_gen - Q_cool) / (m * Cp)
        # Joule heat generation (Watts)
        Q_gen = (current_A ** 2) * self.R_int

        # Convective heat transfer coefficient increases with airflow over the drone
        h_conv = 10.0 + 2.5 * airspeed_ms  # W/(m^2*K)
        Q_cool = h_conv * self.surface_area_m2 * (self.temperature_C - ambient_temp_C)

        dT = ((Q_gen - Q_cool) / (self.mass_kg * self.Cp)) * dt
        self.temperature_C += dT

        # 2. Coulomb Counting with Temperature Derating
        # LiPo capacity drops ~1% per degree C below 25°C; elevated temps accelerate discharge
        temp_derate = 1.0 - 0.01 * max(0.0, 25.0 - self.temperature_C)
        effective_capacity = self.capacity_nominal * max(0.5, temp_derate)

        # Delta SoC = (Current * time) / Total Amp-seconds
        d_soc = (current_A * dt) / (effective_capacity * 3600.0)
        self.soc = max(0.0, min(1.0, self.soc - d_soc))

        # 3. Voltage Discharge Curve (Standard LiPo 3.3V empty to 4.2V full)
        # Incorporates internal resistance voltage drop: V_terminal = V_ocv - I * R_int
        v_cell_ocv = 3.30 + 0.90 * (self.soc ** 0.8)
        self.voltage = max(self.cells * 3.0, (self.cells * v_cell_ocv) - (current_A * self.R_int))

    def snapshot(self) -> Dict[str, Any]:
        return {
            "soc_percent": round(self.percent, 1),
            "voltage_v": round(self.voltage, 2),
            "temperature_C": round(self.temperature_C, 1),
            "is_warning": self.is_warning_temp,
            "is_critical": self.is_critical_temp,
        }


class RotorModel:
    """
    Tracks motor bearing wear, blade aerodynamic efficiency, and operational degradation.
    """

    def __init__(self, rotor_id: int, base_efficiency: float = 0.90):
        self.id = int(rotor_id)
        self.base_efficiency = float(base_efficiency)
        self.degradation: float = 0.0      # 0.0 (pristine) to 1.0 (dead/stalled)
        self.flight_hours: float = 0.0     # Cumulative operating hours

    @property
    def efficiency(self) -> float:
        """Effective mechanical efficiency of the motor/rotor assembly (0.0 to 1.0)."""
        return max(0.05, self.base_efficiency * (1.0 - self.degradation))

    def step(self, dt: float = 0.1) -> None:
        """Accumulates normal flight hours and mechanical bearing fatigue."""
        if dt <= 0:
            return
        self.flight_hours += dt / 3600.0
        # Baseline wear: 15% efficiency reduction per 1000 operational flight hours
        natural_wear = (self.flight_hours / 1000.0) * 0.15
        self.degradation = max(self.degradation, min(0.95, natural_wear))

    def inject_failure(self, severity: float = 0.35) -> None:
        """
        Simulates sudden bearing wear, bent propeller blade, or motor winding damage.
        severity: 0.35 reduces a 90% efficient rotor down to ~58% efficiency.
        """
        self.degradation = min(0.95, self.degradation + float(severity))

    def reset(self) -> None:
        """Replaces rotor assembly with brand new component."""
        self.degradation = 0.0
        self.flight_hours = 0.0


class VehicleHealthModel:
    """
    Comprehensive physical state and health tracker for the entire drone platform.
    Coordinates battery chemistry, 4 brushless motors, payload, and structural stress.
    """

    def __init__(self, drone_dry_mass_kg: float = 0.249, payload_kg: float = 0.0):
        self.drone_dry_mass_kg = float(drone_dry_mass_kg)  # Sub-250g baseline
        self.payload_kg = float(payload_kg)
        
        self.battery = BatteryModel()
        self.rotors: List[RotorModel] = [RotorModel(i) for i in range(4)]

        # Cumulative structural stress from vibration and high-G maneuvers
        self.structural_stress: float = 0.0

    @property
    def total_mass_kg(self) -> float:
        """Total current vehicle weight (drone + active payload)."""
        return self.drone_dry_mass_kg + self.payload_kg

    @property
    def avg_rotor_efficiency(self) -> float:
        """Average efficiency across all 4 lift motors."""
        return sum(r.efficiency for r in self.rotors) / len(self.rotors)

    @property
    def min_rotor_efficiency(self) -> float:
        """Lowest individual rotor efficiency (critical for asymmetric motor failure detection)."""
        return min(r.efficiency for r in self.rotors)

    @property
    def rotor_imbalance_delta(self) -> float:
        """Delta between best and worst rotor. High delta indicates severe asymmetry."""
        effs = [r.efficiency for r in self.rotors]
        return max(effs) - min(effs)

    def set_payload(self, mass_kg: float) -> None:
        """Attaches or updates carried payload mass."""
        self.payload_kg = max(0.0, float(mass_kg))

    def release_payload(self) -> float:
        """
        Simulates in-flight package delivery or release.
        Returns the mass of the released package.
        """
        dropped = self.payload_kg
        self.payload_kg = 0.0
        return dropped

    def step(
        self,
        current_A: float,
        ambient_temp_C: float,
        airspeed_ms: float = 0.0,
        accel_ms2: float = 9.80665,
        dt: float = 0.1
    ) -> None:
        """
        Advances all vehicle health models by dt seconds.
        """
        if dt <= 0:
            return

        # 1. Advance Battery
        self.battery.step(current_A, ambient_temp_C, airspeed_ms, dt)

        # 2. Advance Rotors
        for rotor in self.rotors:
            rotor.step(dt)

        # 3. Accumulate Structural G-Force Stress: integral(|accel - g| * dt)
        g_deviation = abs(float(accel_ms2) - 9.80665)
        self.structural_stress += g_deviation * dt

    def inject_motor_failure(self, motor_idx: int = 2, severity: float = 0.35) -> None:
        """Simulates bearing or propeller failure on a designated motor (0 to 3)."""
        if 0 <= motor_idx < len(self.rotors):
            self.rotors[motor_idx].inject_failure(severity)

    def inject_battery_overheat(self, target_temp_C: float = 58.0) -> None:
        """Artificially spikes battery temperature to test thermal failsafes."""
        self.battery.temperature_C = float(target_temp_C)

    def reset_health(self) -> None:
        """Restores vehicle health to factory new state."""
        self.battery = BatteryModel()
        for r in self.rotors:
            r.reset()
        self.structural_stress = 0.0

    def snapshot(self) -> Dict[str, Any]:
        """Telemetry snapshot of vehicle physical health."""
        return {
            "total_mass_kg": round(self.total_mass_kg, 3),
            "payload_kg": round(self.payload_kg, 3),
            "battery": self.battery.snapshot(),
            "rotor_efficiencies": [round(r.efficiency, 3) for r in self.rotors],
            "avg_rotor_efficiency": round(self.avg_rotor_efficiency, 3),
            "min_rotor_efficiency": round(self.min_rotor_efficiency, 3),
            "rotor_imbalance_delta": round(self.rotor_imbalance_delta, 3),
            "structural_stress": round(self.structural_stress, 1),
        }
