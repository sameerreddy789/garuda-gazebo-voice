"""
Autonomous Decision Engine
Evaluates physics-informed vehicle health, environmental disturbances, energy
forecasting, and uncertainty estimates to trigger safety-critical decisions:
CONTINUE, REDUCE_SPEED, ALTER_ALTITUDE, MODIFY_TRAJECTORY, RETURN_TO_BASE, ABORT_MISSION.
Produces human-interpretable evidence trails with explicit triggers and physics snapshots.
"""

import time
from enum import Enum
from dataclasses import dataclass, field, asdict
from typing import Dict, List, Any, Optional

from garuda.digital_twin.environment import EnvironmentModel
from garuda.digital_twin.vehicle_health import VehicleHealthModel
from garuda.digital_twin.energy_model import EnergyModel
from garuda.digital_twin.state_estimator import DigitalTwinStateEstimator


class Decision(str, Enum):
    CONTINUE = "CONTINUE"
    MODIFY_TRAJECTORY = "MODIFY_TRAJECTORY"
    REDUCE_SPEED = "REDUCE_SPEED"
    ALTER_ALTITUDE = "ALTER_ALTITUDE"
    RETURN_TO_BASE = "RETURN_TO_BASE"
    ABORT_MISSION = "ABORT_MISSION"


@dataclass
class TriggerCondition:
    parameter: str
    value: float
    threshold: float
    severity: str  # "CAUTION", "WARNING", "CRITICAL"
    description: str


@dataclass
class DecisionRecord:
    timestamp: float
    decision: Decision
    confidence: float
    triggers: List[Dict[str, Any]]
    reason: str
    alternatives_considered: List[str]
    physics_snapshot: Dict[str, Any]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "timestamp": round(self.timestamp, 2),
            "decision": self.decision.value,
            "confidence": round(self.confidence, 2),
            "triggers": self.triggers,
            "reason": self.reason,
            "alternatives_considered": self.alternatives_considered,
            "physics_snapshot": self.physics_snapshot,
        }


class DecisionEngine:
    """
    Hierarchical physics-informed failsafe decision engine.
    Continuously audits drone safety against operational boundaries and generates
    verifiable evidence trails for human operators and flight logs.
    """

    def __init__(
        self,
        environment: EnvironmentModel,
        vehicle_health: VehicleHealthModel,
        energy_model: EnergyModel,
        state_estimator: Optional[DigitalTwinStateEstimator] = None
    ):
        self.env = environment
        self.health = vehicle_health
        self.energy = energy_model
        self.estimator = state_estimator or DigitalTwinStateEstimator()

        self.history: List[DecisionRecord] = []
        self.last_decision: Decision = Decision.CONTINUE
        self.decision_count: int = 0

    def evaluate(
        self,
        altitude_agl_m: float = 10.0,
        dist_target_m: float = 100.0,
        dist_home_m: float = 50.0,
        current_airspeed_ms: float = 5.0
    ) -> DecisionRecord:
        """
        Executes a 6-tier hierarchical safety evaluation based on live physics states.
        Evaluates from highest severity (ABORT_MISSION) down to nominal (CONTINUE).
        """
        triggers: List[TriggerCondition] = []
        bat = self.health.battery
        env = self.env
        energy = self.energy

        # Derived physics metrics
        p_hover = energy.power_hover(altitude_agl_m)
        p_cruise = energy.power_forward(current_airspeed_ms, altitude_agl_m)
        endurance_s = energy.remaining_endurance_s(p_cruise)
        air_density = env.get_air_density(altitude_agl_m)
        wind_speed = env.get_wind_speed()
        wind_vec = env.get_wind_vector()
        crosswind_speed = abs(wind_vec[1])
        min_rotor_eff = self.health.min_rotor_efficiency
        imbalance = self.health.rotor_imbalance_delta

        # ---------------------------------------------------------------------
        # TIER 1: EMERGENCY ABORT (Imminent Loss of Vehicle / Thermal Runaway)
        # ---------------------------------------------------------------------
        if bat.temperature_C >= 60.0:
            triggers.append(TriggerCondition(
                parameter="battery_temperature_C",
                value=bat.temperature_C,
                threshold=60.0,
                severity="CRITICAL",
                description="Battery core temperature exceeds 60C thermal runaway threshold."
            ))

        if min_rotor_eff < 0.30:
            triggers.append(TriggerCondition(
                parameter="min_rotor_efficiency",
                value=min_rotor_eff,
                threshold=0.30,
                severity="CRITICAL",
                description=f"Critical rotor failure (efficiency={min_rotor_eff:.2f} < 0.30). Loss of hover authority."
            ))

        if self.health.structural_stress > 5000.0:
            triggers.append(TriggerCondition(
                parameter="structural_stress",
                value=self.health.structural_stress,
                threshold=5000.0,
                severity="CRITICAL",
                description="Excessive structural G-force vibration fatigue limit exceeded."
            ))

        if endurance_s < 45.0:
            triggers.append(TriggerCondition(
                parameter="remaining_endurance_s",
                value=endurance_s,
                threshold=45.0,
                severity="CRITICAL",
                description="Imminent battery exhaustion (< 45s reserve). Immediate forced landing required."
            ))

        if triggers:
            return self._commit(
                Decision.ABORT_MISSION,
                confidence=0.98,
                triggers=triggers,
                reason="Critical emergency threshold breached; executing immediate emergency landing.",
                alternatives=["RETURN_TO_BASE", "REDUCE_SPEED"],
                altitude_agl_m=altitude_agl_m
            )

        # ---------------------------------------------------------------------
        # TIER 2: RETURN TO BASE (Critical Health / Energy Depletion / Excessive Wind)
        # ---------------------------------------------------------------------
        # Energy reserve check for Return To Home (RTH)
        t_to_home = (dist_home_m / max(1.0, current_airspeed_ms)) + 45.0  # travel + 45s safety buffer
        if endurance_s < t_to_home:
            triggers.append(TriggerCondition(
                parameter="energy_rtb_feasibility",
                value=endurance_s,
                threshold=t_to_home,
                severity="WARNING",
                description=f"Remaining endurance ({endurance_s:.0f}s) insufficient for safe RTB + landing ({t_to_home:.0f}s)."
            ))

        if bat.percent <= 18.0:
            triggers.append(TriggerCondition(
                parameter="battery_soc_percent",
                value=bat.percent,
                threshold=18.0,
                severity="WARNING",
                description=f"Battery SoC depleted below critical return threshold ({bat.percent:.1f}% <= 18%)."
            ))

        if bat.temperature_C >= 50.0:
            triggers.append(TriggerCondition(
                parameter="battery_temperature_C",
                value=bat.temperature_C,
                threshold=50.0,
                severity="WARNING",
                description=f"Battery temperature ({bat.temperature_C:.1f}C) exceeds warning threshold (50C)."
            ))

        if min_rotor_eff < 0.65 or self.health.avg_rotor_efficiency < 0.70:
            triggers.append(TriggerCondition(
                parameter="rotor_health_degradation",
                value=min_rotor_eff,
                threshold=0.65,
                severity="WARNING",
                description=f"Motor bearing degradation detected (min rotor efficiency={min_rotor_eff:.2f})."
            ))

        if wind_speed >= 8.5:
            triggers.append(TriggerCondition(
                parameter="sustained_wind_speed_ms",
                value=wind_speed,
                threshold=8.5,
                severity="WARNING",
                description=f"Wind speed ({wind_speed:.1f} m/s) exceeds maximum safe operational limit."
            ))

        # Check mission feasibility
        is_feasible, t_avail, t_needed = energy.can_complete_mission(
            dist_target_m, dist_home_m, current_airspeed_ms, altitude_agl_m
        )
        if not is_feasible:
            triggers.append(TriggerCondition(
                parameter="mission_completion_feasibility",
                value=t_avail,
                threshold=t_needed,
                severity="WARNING",
                description=f"Mission energy infeasible: need {t_needed:.0f}s, only {t_avail:.0f}s remaining."
            ))

        if triggers:
            return self._commit(
                Decision.RETURN_TO_BASE,
                confidence=0.92,
                triggers=triggers,
                reason="Vehicle health degradation or energy reserve constraints mandate immediate Return to Launch.",
                alternatives=["REDUCE_SPEED", "ALTER_ALTITUDE"],
                altitude_agl_m=altitude_agl_m
            )

        # ---------------------------------------------------------------------
        # TIER 3: ALTER ALTITUDE (Atmospheric Air Density / Vertical Downdraft)
        # ---------------------------------------------------------------------
        if air_density < 0.98 and altitude_agl_m > 40.0:
            triggers.append(TriggerCondition(
                parameter="air_density_kg_m3",
                value=air_density,
                threshold=0.98,
                severity="CAUTION",
                description=f"Air density ({air_density:.3f} kg/m^3) too thin for efficient lift; descend to denser air."
            ))

        if abs(env.vertical_shear_ms) >= 3.0 or abs(wind_vec[2]) >= 3.5:
            triggers.append(TriggerCondition(
                parameter="vertical_wind_shear_ms",
                value=abs(wind_vec[2]),
                threshold=3.0,
                severity="CAUTION",
                description="Severe vertical downdraft / wind shear detected; altering altitude layer."
            ))

        if triggers:
            return self._commit(
                Decision.ALTER_ALTITUDE,
                confidence=0.85,
                triggers=triggers,
                reason="Atmospheric density reduction or downdraft shear requires vertical flight level change.",
                alternatives=["REDUCE_SPEED", "CONTINUE"],
                altitude_agl_m=altitude_agl_m
            )

        # ---------------------------------------------------------------------
        # TIER 4: REDUCE SPEED (Turbulence / Crosswinds / Moderate Imbalance)
        # ---------------------------------------------------------------------
        if env.turbulence_intensity >= 0.50:
            triggers.append(TriggerCondition(
                parameter="turbulence_intensity",
                value=env.turbulence_intensity,
                threshold=0.50,
                severity="CAUTION",
                description=f"Elevated atmospheric turbulence ({env.turbulence_intensity:.2f}) requires velocity reduction."
            ))

        if crosswind_speed >= 5.5:
            triggers.append(TriggerCondition(
                parameter="crosswind_speed_ms",
                value=crosswind_speed,
                threshold=5.5,
                severity="CAUTION",
                description=f"Strong lateral crosswind ({crosswind_speed:.1f} m/s) strains attitude control; slowing down."
            ))

        if imbalance >= 0.15:
            triggers.append(TriggerCondition(
                parameter="rotor_imbalance_delta",
                value=imbalance,
                threshold=0.15,
                severity="CAUTION",
                description=f"Asymmetric motor load detected (delta={imbalance:.2f}); reducing cruise speed to unload motors."
            ))

        if triggers:
            return self._commit(
                Decision.REDUCE_SPEED,
                confidence=0.88,
                triggers=triggers,
                reason="Atmospheric turbulence or asymmetric aerodynamic stress warrants cruise speed reduction.",
                alternatives=["MODIFY_TRAJECTORY", "CONTINUE"],
                altitude_agl_m=altitude_agl_m
            )

        # ---------------------------------------------------------------------
        # TIER 5: MODIFY TRAJECTORY (Adverse Headwinds / Shelter Paths)
        # ---------------------------------------------------------------------
        # Strong forward headwind pushing against flight direction
        headwind = max(0.0, wind_vec[0])
        if headwind >= 0.60 * current_airspeed_ms and headwind >= 4.0:
            triggers.append(TriggerCondition(
                parameter="headwind_resistance_ms",
                value=headwind,
                threshold=0.60 * current_airspeed_ms,
                severity="CAUTION",
                description=f"Headwind ({headwind:.1f} m/s) severely lowers ground speed; rerouting to sheltered corridor."
            ))
            return self._commit(
                Decision.MODIFY_TRAJECTORY,
                confidence=0.82,
                triggers=triggers,
                reason="Persistent headwind causing excessive battery drain per distance; altering trajectory waypoint path.",
                alternatives=["REDUCE_SPEED", "CONTINUE"],
                altitude_agl_m=altitude_agl_m
            )

        # ---------------------------------------------------------------------
        # TIER 6: CONTINUE (All Parameters Nominal)
        # ---------------------------------------------------------------------
        return self._commit(
            Decision.CONTINUE,
            confidence=0.96,
            triggers=[],
            reason="All environmental, vehicle health, and energy reserve states are within nominal safety envelopes.",
            alternatives=[],
            altitude_agl_m=altitude_agl_m
        )

    def _commit(
        self,
        decision: Decision,
        confidence: float,
        triggers: List[TriggerCondition],
        reason: str,
        alternatives: List[str],
        altitude_agl_m: float
    ) -> DecisionRecord:
        """
        Constructs and records the verifiable decision log entry with physics snapshot.
        """
        record = DecisionRecord(
            timestamp=time.time(),
            decision=decision,
            confidence=confidence,
            triggers=[asdict(t) for t in triggers],
            reason=reason,
            alternatives_considered=alternatives,
            physics_snapshot={
                "altitude_agl_m": round(altitude_agl_m, 1),
                "air_density_kg_m3": round(self.env.get_air_density(altitude_agl_m), 4),
                "wind_speed_ms": round(self.env.get_wind_speed(), 2),
                "wind_vector_ms": [round(w, 2) for w in self.env.get_wind_vector()],
                "battery_temp_C": round(self.health.battery.temperature_C, 1),
                "battery_soc_percent": round(self.health.battery.percent, 1),
                "hover_power_w": round(self.energy.power_hover(altitude_agl_m), 1),
                "remaining_endurance_min": round(self.energy.remaining_endurance_s(self.energy.power_hover(altitude_agl_m)) / 60.0, 1),
                "rotor_efficiencies": [round(r.efficiency, 3) for r in self.health.rotors],
                "rotor_imbalance_delta": round(self.health.rotor_imbalance_delta, 3),
            }
        )

        self.history.append(record)
        self.last_decision = decision
        self.decision_count += 1
        return record
