"""
Automated Physics Verification Test
Validates EnvironmentModel (ISA + Dryden) and VehicleHealthModel (Battery ODE + Rotors).
"""

import sys
import os
import math

# Ensure workspace root is in sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from garuda.digital_twin.environment import EnvironmentModel
from garuda.digital_twin.vehicle_health import VehicleHealthModel
from garuda.digital_twin.energy_model import EnergyModel
from garuda.digital_twin.state_estimator import ScalarKalmanFilter, DigitalTwinStateEstimator
from garuda.digital_twin.decision_engine import DecisionEngine, Decision


def test_environment_isa():
    print("[TEST] 1. Testing ISA Atmosphere...")
    env = EnvironmentModel(home_altitude_m=920.0)  # Bangalore

    rho_ground = env.get_air_density(altitude_agl_m=0.0)
    rho_1000m = env.get_air_density(altitude_agl_m=1000.0)

    print(f"       Bangalore ground density (920m ASL): {rho_ground:.4f} kg/m^3")
    print(f"       High altitude density (1920m ASL):    {rho_1000m:.4f} kg/m^3")

    assert 1.05 < rho_ground < 1.15, f"Unexpected ground density: {rho_ground}"
    assert rho_1000m < rho_ground, "Air density did not decrease with altitude!"
    print("       [PASS] ISA atmosphere validated.")


def test_dryden_wind_and_disturbances():
    print("\n[TEST] 2. Testing Dryden Stochastic Wind & Disturbance Injections...")
    env = EnvironmentModel()

    # Step simulation 50 times (5.0s)
    for _ in range(50):
        env.step(dt=0.1)

    wind_speed = env.get_wind_speed()
    print(f"       Calm stochastic wind speed: {wind_speed:.2f} m/s")
    assert wind_speed < 8.0, "Calm wind unexpectedly high!"

    # Inject sudden crosswind
    env.inject_crosswind(speed_ms=12.0)
    crosswind = env.get_wind_speed()
    print(f"       Injected Crosswind magnitude: {crosswind:.2f} m/s")
    assert 10.0 <= crosswind <= 14.0, f"Crosswind injection failed: {crosswind}"

    # Inject temperature spike
    t_before = env.get_temperature_C(0.0)
    env.inject_temperature_spike(delta_C=20.0)
    t_after = env.get_temperature_C(0.0)
    print(f"       Temp spike: {t_before:.1f}C -> {t_after:.1f}C")
    assert t_after - t_before == 20.0, "Temp spike injection failed!"
    print("       [PASS] Dryden wind & disturbance injections validated.")


def test_battery_thermal_and_coulomb():
    print("\n[TEST] 3. Testing Battery Thermal ODE & Coulomb Counting...")
    health = VehicleHealthModel()

    initial_soc = health.battery.percent
    initial_temp = health.battery.temperature_C
    print(f"       Start SoC: {initial_soc:.1f}%, Temp: {initial_temp:.1f}C")

    # Simulate heavy current draw (12A hover) for 30 seconds
    for _ in range(300):
        # 12 Amps, 25C ambient, 4 m/s airflow, 0.1s dt
        health.step(current_A=12.0, ambient_temp_C=25.0, airspeed_ms=4.0, dt=0.1)

    end_soc = health.battery.percent
    end_temp = health.battery.temperature_C
    print(f"       After 30s @ 12A -> SoC: {end_soc:.1f}%, Temp: {end_temp:.1f}C")

    assert end_soc < initial_soc, "Battery SoC failed to decrement!"
    assert end_temp > initial_temp, "Battery Joule heating failed to heat the pack!"
    print("       [PASS] Battery thermal dynamics & Coulomb counting validated.")


def test_rotor_degradation_and_payload():
    print("\n[TEST] 4. Testing Rotor Degradation, Asymmetry & Payload...")
    health = VehicleHealthModel(drone_dry_mass_kg=0.249, payload_kg=0.050)

    print(f"       Total mass with 50g payload: {health.total_mass_kg:.3f} kg")
    assert math.isclose(health.total_mass_kg, 0.299, rel_tol=1e-3)

    # Initial rotor state
    assert health.min_rotor_efficiency >= 0.89
    assert health.rotor_imbalance_delta < 0.05

    # Inject motor 2 bearing failure
    health.inject_motor_failure(motor_idx=2, severity=0.35)
    print("       Injected failure on Motor #2:")
    print(f"       Rotor efficiencies: {[round(r.efficiency, 3) for r in health.rotors]}")
    print(f"       Motor imbalance delta: {health.rotor_imbalance_delta:.3f}")

    assert health.rotors[2].efficiency < 0.65, "Motor failure injection failed!"
    assert health.rotor_imbalance_delta > 0.25, "Motor imbalance failed to reflect failure!"

    # Release payload
    dropped = health.release_payload()
    print(f"       Payload dropped: {dropped*1000:.0f}g. New mass: {health.total_mass_kg:.3f} kg")
    assert health.total_mass_kg == 0.249
    print("       [PASS] Rotor degradation & payload dynamics validated.")


def test_energy_model_hover_and_forward():
    print("\n[TEST] 5. Testing Actuator Disk Momentum Theory Energy Model...")
    env = EnvironmentModel()
    health = VehicleHealthModel()
    energy = EnergyModel(env, health)

    # Hover power calculation
    p_hover = energy.power_hover(altitude_agl_m=0.0)
    print(f"       Theoretical hover power: {p_hover:.2f} W")
    assert 20.0 < p_hover < 50.0, f"Hover power outside realistic bounds: {p_hover}"

    # Forward flight power at 5 m/s
    p_forward = energy.power_forward(airspeed_ms=5.0, altitude_agl_m=0.0)
    print(f"       Forward flight power (5 m/s): {p_forward:.2f} W")
    assert 15.0 < p_forward < 65.0

    # Current draw at 11.1V nominal
    curr_hover = energy.current_draw(p_hover)
    print(f"       Hover current draw: {curr_hover:.2f} A")
    assert 1.5 < curr_hover < 5.0

    # Remaining endurance in minutes
    endurance_min = energy.remaining_endurance_s(p_hover) / 60.0
    print(f"       Hover endurance @ 100% SoC: {endurance_min:.1f} minutes")
    assert 5.0 < endurance_min < 25.0

    # Mission feasibility: Target 100m away vs 20,000m away
    feasible_short, t_avail, t_needed = energy.can_complete_mission(dist_remaining_target_m=100.0, dist_home_m=50.0)
    print(f"       Short mission (100m): Feasible={feasible_short} (Avail={t_avail:.0f}s, Need={t_needed:.0f}s)")
    assert feasible_short is True

    feasible_long, _, _ = energy.can_complete_mission(dist_remaining_target_m=20000.0, dist_home_m=15000.0)
    print(f"       Impossible mission (20km): Feasible={feasible_long}")
    assert feasible_long is False

    # Safe operating envelope snapshot
    envelope = energy.safe_envelope()
    assert "max_safe_airspeed_ms" in envelope
    assert "max_safe_altitude_m" in envelope
    print(f"       Safe envelope limits: Max Airspeed={envelope['max_safe_airspeed_ms']} m/s, Max Alt={envelope['max_safe_altitude_m']} m")
    print("       [PASS] Energy model & Actuator Disk theory validated.")


def test_kalman_uncertainty_quantification():
    print("\n[TEST] 6. Testing Kalman Filter Uncertainty Quantification...")
    kf = ScalarKalmanFilter(initial_value=50.0, initial_variance=1.0, process_noise_q=0.02, measurement_noise_r=0.20)

    # Uncertainty should grow over 10 prediction steps without measurements
    init_uncert = kf.standard_deviation
    for _ in range(10):
        kf.predict(dt=0.1)
    grown_uncert = kf.standard_deviation
    print(f"       Initial 1-sigma uncertainty: {init_uncert:.3f} -> After blind predictions: {grown_uncert:.3f}")
    assert grown_uncert > init_uncert

    # Measurement updates should shrink uncertainty
    for _ in range(5):
        kf.update(measurement=52.0)
    shrunk_uncert = kf.standard_deviation
    print(f"       After 5 sensor updates: Estimate={kf.x:.2f}, Uncertainty={shrunk_uncert:.3f}")
    assert shrunk_uncert < grown_uncert

    # Test full DigitalTwinStateEstimator
    estimator = DigitalTwinStateEstimator()
    estimator.predict_physics(predicted_alt_m=45.0, predicted_airspeed_ms=5.0, predicted_wind_ms=3.0, predicted_soc=85.0, predicted_endurance_s=720.0, dt=0.1)
    estimator.update_sensor_telemetry(measured_alt_m=45.2, measured_airspeed_ms=5.1, measured_soc=84.8)

    snapshot = estimator.snapshot()
    print(f"       Estimator Altitude: {snapshot['altitude']['estimate_m']}m +/- {snapshot['altitude']['uncertainty_m']}m (95% CI: {snapshot['altitude']['ci_95']})")
    print(f"       Estimator Endurance: {snapshot['endurance']['estimate_min']} min +/- {snapshot['endurance']['uncertainty_min']} min")

    assert snapshot['altitude']['ci_95'][0] <= 45.2 <= snapshot['altitude']['ci_95'][1]
    print("       [PASS] Kalman state estimation & uncertainty bounds validated.")


def test_autonomous_decision_engine():
    print("\n[TEST] 7. Testing Autonomous Decision Engine (6-Tier Hierarchy)...")
    env = EnvironmentModel()
    health = VehicleHealthModel()
    energy = EnergyModel(env, health)
    engine = DecisionEngine(env, health, energy)

    # 1. Nominal flight -> CONTINUE
    rec_nominal = engine.evaluate(altitude_agl_m=15.0, dist_target_m=100.0, dist_home_m=50.0, current_airspeed_ms=5.0)
    print(f"       Scenario A (Nominal): Decision = {rec_nominal.decision.value} (Confidence: {rec_nominal.confidence*100:.0f}%)")
    assert rec_nominal.decision == Decision.CONTINUE

    # 2. Injected Crosswind -> REDUCE_SPEED
    env.inject_crosswind(speed_ms=8.0)
    rec_crosswind = engine.evaluate(altitude_agl_m=15.0, dist_target_m=100.0, dist_home_m=50.0)
    print(f"       Scenario B (Crosswind 8 m/s): Decision = {rec_crosswind.decision.value} (Reason: {rec_crosswind.reason})")
    assert rec_crosswind.decision == Decision.REDUCE_SPEED
    env.reset_disturbances()

    # 3. Severe Headwind along path -> MODIFY_TRAJECTORY
    env.wind_steady[0] = 5.0  # 5 m/s headwind vs 5 m/s cruise
    rec_headwind = engine.evaluate(altitude_agl_m=15.0, dist_target_m=200.0, dist_home_m=100.0, current_airspeed_ms=5.0)
    print(f"       Scenario C (Severe Headwind): Decision = {rec_headwind.decision.value} (Reason: {rec_headwind.reason})")
    assert rec_headwind.decision == Decision.MODIFY_TRAJECTORY
    env.reset_disturbances()

    # 4. Severe Downdraft -> ALTER_ALTITUDE
    env.inject_downdraft(speed_ms=4.0)
    rec_downdraft = engine.evaluate(altitude_agl_m=20.0, dist_target_m=100.0, dist_home_m=50.0)
    print(f"       Scenario D (Downdraft 4 m/s): Decision = {rec_downdraft.decision.value} (Reason: {rec_downdraft.reason})")
    assert rec_downdraft.decision == Decision.ALTER_ALTITUDE
    env.reset_disturbances()

    # 5. Motor Bearing Failure (Motor 3 down to 60%) -> RETURN_TO_BASE
    health.inject_motor_failure(motor_idx=2, severity=0.33)
    rec_rtb = engine.evaluate(altitude_agl_m=15.0, dist_target_m=200.0, dist_home_m=100.0)
    print(f"       Scenario E (Motor Bearing Wear): Decision = {rec_rtb.decision.value} (Triggers: {[t['parameter'] for t in rec_rtb.triggers]})")
    assert rec_rtb.decision == Decision.RETURN_TO_BASE

    # 6. Thermal Runaway (Battery hits 62C) -> ABORT_MISSION
    health.inject_battery_overheat(target_temp_C=62.0)
    rec_abort = engine.evaluate(altitude_agl_m=15.0, dist_target_m=200.0, dist_home_m=100.0)
    print(f"       Scenario F (Battery Runaway 62C): Decision = {rec_abort.decision.value} (Reason: {rec_abort.reason})")
    assert rec_abort.decision == Decision.ABORT_MISSION

    # Verify structured evidence log export
    evidence_dict = rec_abort.to_dict()
    assert "triggers" in evidence_dict
    assert "physics_snapshot" in evidence_dict
    assert evidence_dict["physics_snapshot"]["battery_temp_C"] == 62.0
    print("       [PASS] Autonomous decision hierarchy & evidence logs validated.")


if __name__ == "__main__":
    print("==================================================")
    print("  RUNNING GARUDAONE DIGITAL TWIN PHYSICS TESTS    ")
    print("==================================================")
    test_environment_isa()
    test_dryden_wind_and_disturbances()
    test_battery_thermal_and_coulomb()
    test_rotor_degradation_and_payload()
    test_energy_model_hover_and_forward()
    test_kalman_uncertainty_quantification()
    test_autonomous_decision_engine()
    print("\n==================================================")
    print("  ALL PHYSICS MODULE TESTS PASSED PERFECTLY! [OK] ")
    print("==================================================")
