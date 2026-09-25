"""
HackFusion 2026 — Theme 3: Failure & Disturbance Demonstration Suite
Executes 5 prescribed real-world failure injection scenarios:
1. Sudden Crosswind Gust (12 m/s East)
2. Motor #3 Bearing Failure & Mechanical Degradation
3. Battery Thermal Runaway (52C Warning -> 62C Emergency Abort)
4. In-Flight Package Delivery / Payload Drop
5. Multi-Variable Compound Stress (High Alt + Low Density + Downdraft + Battery Depletion)
"""

import sys
import os
import time
import argparse
from typing import Dict, Any, List

# Ensure workspace root is in sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from garuda.digital_twin.twin_runner import DigitalTwinRunner
from garuda.digital_twin.decision_engine import Decision


def print_banner(title: str):
    width = 75
    print("\n" + "=" * width)
    print(f"  {title.center(width - 4)}")
    print("=" * width)


def format_evidence_box(decision_rec: Dict[str, Any]):
    print("  +----------------- AUTONOMOUS DECISION EVIDENCE -----------------+")
    print(f"  | Action:      {decision_rec['decision']:<50} |")
    print(f"  | Confidence:  {decision_rec['confidence']*100:.0f}%{' '*46} |")
    print(f"  | Reason:      {decision_rec['reason'][:48]:<48} |")
    if decision_rec.get("triggers"):
        print("  | Triggers:                                                      |")
        for trig in decision_rec["triggers"]:
            desc = f"- [{trig['severity']}] {trig['parameter']}={trig['value']:.1f} (thresh: {trig['threshold']:.1f})"
            print(f"  |   {desc:<60} |")
    print("  +----------------------------------------------------------------+")


# -----------------------------------------------------------------------------
# SCENARIO 1: SUDDEN CROSSWIND GUST
# -----------------------------------------------------------------------------
def run_scenario_crosswind(runner: DigitalTwinRunner, fast: bool = False):
    print_banner("SCENARIO 1: SUDDEN CROSSWIND GUST & ESCALATION")
    print("Objective: Drone encounters increasing lateral crosswinds (6.5 m/s -> 12 m/s).")
    print("Expected:  CONTINUE -> REDUCE_SPEED (moderate crosswind) -> RETURN_TO_BASE (gale wind).\n")

    runner.environment.reset_disturbances()
    runner.airspeed_ms = 6.0
    sleep_dt = 0.01 if fast else 0.1

    print("[0.0s] Nominal flight: Calm conditions, cruising at 6.0 m/s...")
    for _ in range(15):
        snap = runner.step(dt=0.1)
        time.sleep(sleep_dt)

    assert snap['decision']['decision'] == "CONTINUE"
    print(f"  State: Wind = {snap['environment']['wind_speed_ms']:.1f} m/s | Decision = {snap['decision']['decision']}")

    print("\n[!] STAGE 1: Injecting Moderate 6.5 m/s Lateral Crosswind...")
    runner.environment.inject_crosswind(speed_ms=6.5)
    for _ in range(15):
        snap = runner.step(dt=0.1)
        time.sleep(sleep_dt)

    print(f"  Stage 1 State: Wind = {snap['environment']['wind_speed_ms']:.1f} m/s | Decision = {snap['decision']['decision']}")
    assert snap['decision']['decision'] in ["REDUCE_SPEED", "MODIFY_TRAJECTORY"]

    print("\n[!] STAGE 2: Wind escalates to severe 12.0 m/s East Crosswind Gust!")
    runner.environment.inject_crosswind(speed_ms=12.0)
    for step_i in range(20):
        snap = runner.step(dt=0.1)
        time.sleep(sleep_dt)
        if step_i % 10 == 0:
            print(f"[{snap['sim_time_s']:.1f}s] Wind = {snap['environment']['wind_speed_ms']:.1f} m/s | "
                  f"Airspeed = {snap['telemetry']['airspeed_ms']:.1f} m/s | "
                  f"Decision = {snap['decision']['decision']}")

    format_evidence_box(snap["decision"])
    assert snap['decision']['decision'] == "RETURN_TO_BASE"
    print("\n>>> SCENARIO 1 PASSED: Demonstrated two-stage speed reduction and RTB escalation! [PASS]")


# -----------------------------------------------------------------------------
# SCENARIO 2: MOTOR BEARING FAILURE
# -----------------------------------------------------------------------------
def run_scenario_motor_failure(runner: DigitalTwinRunner, fast: bool = False):
    print_banner("SCENARIO 2: MOTOR #3 BEARING FAILURE & DEGRADATION")
    print("Objective: Motor #3 suffers sudden mechanical bearing damage; efficiency drops to ~58%.")
    print("Expected:  CONTINUE -> REDUCE_SPEED (imbalance) -> RETURN_TO_BASE (critical health).\n")

    runner.environment.reset_disturbances()
    runner.vehicle_health.reset_health()
    sleep_dt = 0.01 if fast else 0.1

    print("[0.0s] Nominal flight: All 4 brushless motors operating at 90% efficiency...")
    for _ in range(20):
        snap = runner.step(dt=0.1)
        time.sleep(sleep_dt)

    assert snap['decision']['decision'] == "CONTINUE"

    print("\n[!] INJECTING: Severe bearing wear on Motor #3 (35% efficiency drop)!")
    runner.vehicle_health.inject_motor_failure(motor_idx=2, severity=0.35)

    for step_i in range(30):
        snap = runner.step(dt=0.1)
        time.sleep(sleep_dt)
        if step_i % 10 == 0:
            effs = snap['vehicle_health']['rotor_efficiencies']
            print(f"[{snap['sim_time_s']:.1f}s] Rotors = {effs} | "
                  f"Imbalance = {snap['vehicle_health']['rotor_imbalance_delta']:.2f} | "
                  f"Decision = {snap['decision']['decision']}")

    format_evidence_box(snap["decision"])
    assert snap['decision']['decision'] == "RETURN_TO_BASE"
    print("\n>>> SCENARIO 2 PASSED: Digital twin detected motor failure and triggered RTB! [PASS]")


# -----------------------------------------------------------------------------
# SCENARIO 3: BATTERY THERMAL RUNAWAY
# -----------------------------------------------------------------------------
def run_scenario_battery_thermal(runner: DigitalTwinRunner, fast: bool = False):
    print_banner("SCENARIO 3: BATTERY OVERHEAT & THERMAL RUNAWAY")
    print("Objective: High current draw raises battery past 50C warning, then past 60C critical runaway.")
    print("Expected:  CONTINUE -> RETURN_TO_BASE (50C warning) -> ABORT_MISSION (60C critical).\n")

    runner.environment.reset_disturbances()
    runner.vehicle_health.reset_health()
    sleep_dt = 0.01 if fast else 0.1

    print("[0.0s] Baseline temperature: 25.0C...")
    for _ in range(10):
        runner.step(dt=0.1)

    print("\n[!] STAGE 1: Heating battery to 52.0C (Thermal Warning Threshold)...")
    runner.vehicle_health.inject_battery_overheat(52.0)
    for _ in range(15):
        snap = runner.step(dt=0.1)
        time.sleep(sleep_dt)

    print(f"  Battery Temp = {snap['vehicle_health']['battery']['temperature_C']}C | Decision = {snap['decision']['decision']}")
    assert snap['decision']['decision'] == "RETURN_TO_BASE"

    print("\n[!] STAGE 2: Core temperature climbs to 62.0C (Thermal Runaway Emergency)!")
    runner.vehicle_health.inject_battery_overheat(62.0)
    for _ in range(15):
        snap = runner.step(dt=0.1)
        time.sleep(sleep_dt)

    print(f"  Battery Temp = {snap['vehicle_health']['battery']['temperature_C']}C | Decision = {snap['decision']['decision']}")
    format_evidence_box(snap["decision"])
    assert snap['decision']['decision'] == "ABORT_MISSION"
    assert snap['flight_phase'] == "EMERGENCY_LAND"
    print("\n>>> SCENARIO 3 PASSED: Thermal runaway detected; emergency landing executed! [PASS]")


# -----------------------------------------------------------------------------
# SCENARIO 4: IN-FLIGHT PAYLOAD DROP
# -----------------------------------------------------------------------------
def run_scenario_payload_drop(runner: DigitalTwinRunner, fast: bool = False):
    print_banner("SCENARIO 4: IN-FLIGHT PAYLOAD RELEASE")
    print("Objective: Drone carrying 50g package releases payload mid-flight; envelope recalculates.")
    print("Expected:  Total mass drops 299g -> 249g, hover power drops, flight continues safely.\n")

    runner.environment.reset_disturbances()
    runner.vehicle_health.reset_health()
    runner.vehicle_health.set_payload(0.050)  # 50g
    sleep_dt = 0.01 if fast else 0.1

    print("[0.0s] Flying with 50g payload (Total Mass = 299g)...")
    for _ in range(20):
        snap = runner.step(dt=0.1)
        time.sleep(sleep_dt)

    p_with_payload = snap["energy"]["current_power_w"]
    print(f"  Power with payload: {p_with_payload:.1f} W | Mass: {snap['vehicle_health']['total_mass_kg']*1000:.0f}g")

    print("\n[!] RELEASING PAYLOAD: Package dropped at destination waypoint!")
    dropped = runner.vehicle_health.release_payload()

    for _ in range(20):
        snap = runner.step(dt=0.1)
        time.sleep(sleep_dt)

    p_without_payload = snap["energy"]["current_power_w"]
    print(f"  Power post-release: {p_without_payload:.1f} W | Mass: {snap['vehicle_health']['total_mass_kg']*1000:.0f}g")
    print(f"  Power savings: {p_with_payload - p_without_payload:.2f} W saved!")

    assert snap['vehicle_health']['total_mass_kg'] == 0.249
    assert p_without_payload < p_with_payload
    assert snap['decision']['decision'] == "CONTINUE"
    print("\n>>> SCENARIO 4 PASSED: Safe operating envelope dynamically updated! [PASS]")


# -----------------------------------------------------------------------------
# SCENARIO 5: MULTI-VARIABLE COMPOUND STRESS
# -----------------------------------------------------------------------------
def run_scenario_combined_stress(runner: DigitalTwinRunner, fast: bool = False):
    print_banner("SCENARIO 5: MULTI-VARIABLE COMPOUND STRESS")
    print("Objective: High altitude (thin air) + vertical downdraft + low battery SoC.")
    print("Expected:  ALTER_ALTITUDE -> REDUCE_SPEED -> RETURN_TO_BASE.\n")

    runner.environment.reset_disturbances()
    runner.vehicle_health.reset_health()
    runner.altitude_agl_m = 65.0  # High altitude
    runner.dist_target_m = 120.0
    runner.dist_home_m = 40.0
    sleep_dt = 0.01 if fast else 0.1

    print("[0.0s] High altitude flight at 65m AGL (thin air density)...")
    for _ in range(15):
        snap = runner.step(dt=0.1)
        time.sleep(sleep_dt)

    print(f"  Altitude: {snap['telemetry']['altitude_agl_m']}m | Density: {snap['environment']['air_density_kg_m3']} kg/m^3")

    print("\n[!] INJECTING: 4.0 m/s vertical downdraft shear!")
    runner.environment.inject_downdraft(4.0)
    for _ in range(15):
        snap = runner.step(dt=0.1)
        time.sleep(sleep_dt)

    print(f"  Vertical Wind: {snap['environment']['wind_vector_ms'][2]} m/s | Decision: {snap['decision']['decision']}")
    assert snap['decision']['decision'] in ["ALTER_ALTITUDE", "REDUCE_SPEED"]

    print("\n[!] INJECTING: Rapid battery depletion (SoC drops to 14%)...")
    runner.vehicle_health.battery.soc = 0.14
    for _ in range(15):
        snap = runner.step(dt=0.1)
        time.sleep(sleep_dt)

    print(f"  Battery SoC: {snap['vehicle_health']['battery']['soc_percent']}% | Decision: {snap['decision']['decision']}")
    format_evidence_box(snap["decision"])
    assert snap['decision']['decision'] == "RETURN_TO_BASE"
    print("\n>>> SCENARIO 5 PASSED: Handled cascading multi-variable atmospheric and electrical stress! [PASS]")


# -----------------------------------------------------------------------------
# MAIN CLI HARNESS
# -----------------------------------------------------------------------------
def main():
    parser = argparse.ArgumentParser(description="GarudaOne Digital Twin — HackFusion Theme 3 Scenarios")
    parser.add_argument("--scenario", choices=["crosswind", "motor", "thermal", "payload", "combined", "all"],
                        default="all", help="Which test scenario to execute")
    parser.add_argument("--fast", action="store_true", help="Speed up simulation execution without delays")
    args = parser.parse_args()

    runner = DigitalTwinRunner()

    print("=" * 75)
    print("   GARUDAONE PHYSICS-INFORMED DIGITAL TWIN SCENARIO DEMONSTRATIONS   ")
    print("   HackFusion 2026 | IEEE Robotics & Automation Society Theme 3      ")
    print("=" * 75)

    if args.scenario in ["crosswind", "all"]:
        run_scenario_crosswind(runner, fast=args.fast)
    if args.scenario in ["motor", "all"]:
        run_scenario_motor_failure(runner, fast=args.fast)
    if args.scenario in ["thermal", "all"]:
        run_scenario_battery_thermal(runner, fast=args.fast)
    if args.scenario in ["payload", "all"]:
        run_scenario_payload_drop(runner, fast=args.fast)
    if args.scenario in ["combined", "all"]:
        run_scenario_combined_stress(runner, fast=args.fast)

    print("\n" + "=" * 75)
    print("   ALL 5 STRESS SCENARIO DEMONSTRATIONS PASSED FLAWLESSLY! [OK]      ")
    print("=" * 75 + "\n")


if __name__ == "__main__":
    main()
