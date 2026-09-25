# GarudaOne Digital Twin — Complete Implementation Guide

## How Industry & Academia Solve Each Missing Feature, and How We Build It

> This document is your single source of truth for implementing every missing
> deliverable for HackFusion 2026 Theme 3. Each section explains **what** the
> feature is, **why** judges care about it, **how** real-world systems solve it
> (with references), the **exact physics/math**, and **step-by-step instructions**
> for building it in our codebase.

---

## Table of Contents

1. [Environmental State Model](#1-environmental-state-model)
2. [Vehicle Health Model](#2-vehicle-health-model)
3. [Energy & Endurance Forecasting](#3-energy--endurance-forecasting)
4. [Autonomous Decision Engine](#4-autonomous-decision-engine)
5. [Uncertainty Quantification (Kalman Filter)](#5-uncertainty-quantification-kalman-filter)
6. [Digital Twin Dashboard](#6-digital-twin-dashboard)
7. [Scenario Demonstrations](#7-scenario-demonstrations)
8. [Updated README Structure](#8-updated-readme-structure)
9. [References & Resources](#9-references--resources)

---

## 1. Environmental State Model

**File**: `garuda/digital_twin/environment.py`

### Environment — Overview & Definition

A software model that simulates the atmospheric conditions around the drone
in real time — wind speed, wind direction, turbulence, air density, and ambient
temperature. These conditions change over time and directly affect how much
energy the drone uses, how stable it flies, and whether it is safe to continue.

### Environment — Hackathon Scoring Impact

> *"Environmental and degradation modelling quality"* is a standalone judging
> criterion. Without this module, you score zero on that axis.

### Environment — Industry Solutions & Standards

| Method | Used By | Complexity |
| --- | --- | --- |
| **Dryden Wind Turbulence Model** (MIL-F-8785C) | NASA, MATLAB Simulink, PX4 SITL wind plugin | Medium — gold standard for UAV simulation |
| **Von Kármán Turbulence Model** | Military flight certification, EU EASA | High — more accurate at low altitudes |
| **ISA Atmosphere** (ICAO Standard) | Every aviation system worldwide | Low — simple equations, universally accepted |
| **Ornstein-Uhlenbeck (OU) Process** | Academic papers on stochastic wind | Medium — models mean-reverting random wind |

**Our approach**: Combine ISA atmosphere (for density/temperature) with a
simplified Dryden model (for wind/turbulence). This gives us the best
accuracy-to-complexity ratio for a hackathon.

### Environment — Governing Physics & Mathematics

#### 1A. ISA Atmosphere — Temperature & Air Density vs. Altitude

The International Standard Atmosphere defines how temperature and air density
change with altitude. Think of it like this: the higher you fly, the colder
and thinner the air gets, and thinner air means the rotors have to work
harder to generate the same lift.

```text
Temperature at altitude h:
  T(h) = T₀ - L × h

  T₀ = 288.15 K    (sea-level temperature, about 15°C)
  L  = 0.0065 K/m  (temperature drops 6.5°C per 1000m)
  h  = altitude in meters

Air density at altitude h:
  ρ(h) = ρ₀ × (T(h) / T₀) ^ (g/(R×L) - 1)

  ρ₀ = 1.225 kg/m³  (sea-level density)
  g  = 9.80665 m/s² (gravity)
  R  = 287.05 J/(kg·K) (gas constant for dry air)

Simplified (for altitudes under 1000m — our drone's range):
  ρ(h) ≈ ρ₀ × (1 - 0.0000226 × h) ^ 4.256
```

**Why this matters for our drone**: Our x500 operates at Bangalore elevation
(920m ASL). At 920m, air density is about 1.10 kg/m³ instead of 1.225 — the
rotors are already 10% less efficient than at sea level before we even take off.

#### 1B. Dryden Wind Turbulence — Realistic Gusts

The Dryden model generates realistic wind gusts by passing white noise through
specially shaped filters. It is the standard used in MIL-F-8785C (the US
military specification for aircraft flight qualities).

Think of it like an audio equalizer for wind — it shapes random noise into
something that "sounds" and "feels" like real wind, with the right frequency
distribution and correlation between gusts.

```text
Wind has 3 components:
  1. Steady wind   → constant base wind (e.g., 5 m/s from the north)
  2. Gust component → random but realistic (Dryden-filtered noise)

Each axis gets its own transfer function:
  Longitudinal (u):  H_u(s) = σ_u × √(2×L_u / (π×V)) × 1/(1 + L_u×s/V)
  Lateral (v):       H_v(s) = σ_v × √(L_v / (π×V)) × (1 + √3×L_v×s/V) / (1 + L_v×s/V)²
  Vertical (w):      H_w(s) = σ_w × √(L_w / (π×V)) × (1 + √3×L_w×s/V) / (1 + L_w×s/V)²

Where:
  σ  = turbulence intensity (m/s) — scales with wind speed and altitude
  L  = turbulence scale length (m) — depends on altitude
  V  = airspeed (m/s)
  s  = Laplace variable (frequency domain)

For low altitude (h < 300m, our range):
  L_u = h / (0.177 + 0.000823×h)^1.2
  L_v = L_u
  L_w = h
  σ_w = 0.1 × W₂₀  (W₂₀ = wind speed at 20ft/6m)
  σ_u = σ_w / (0.177 + 0.000823×h)^0.4
```

**Simplified for our implementation**: We don't need to implement the full
Laplace-domain transfer functions. We use a discrete-time approximation with
an **Ornstein-Uhlenbeck process**, which gives statistically equivalent
results and is trivial to code:

```python
# Simplified Dryden-equivalent wind gust (OU process)
# Each axis independently:
def update_gust(current_gust, dt, sigma, tau):
    """
    sigma = turbulence intensity (m/s)
    tau   = correlation time (seconds) — how fast gusts change
    dt    = simulation timestep
    """
    noise = random.gauss(0, 1)
    decay = math.exp(-dt / tau)
    diffusion = sigma * math.sqrt(1 - decay**2)
    return current_gust * decay + diffusion * noise
```

#### 1C. Disturbance Injection

The simulation can inject sudden events to test the decision engine:

| Event | Implementation | Effect |
| --- | --- | --- |
| **Sudden crosswind gust** | Instantly add 10-15 m/s to lateral wind | Drone is pushed sideways, tests stability |
| **Wind shear** | Rapidly change wind direction by 90° | Tests attitude recovery |
| **Temperature spike** | Add +20°C to ambient temperature | Reduces air density → less lift |
| **Updraft/downdraft** | Add ±5 m/s to vertical wind | Tests altitude hold |

### Environment — Implementation Blueprint

```python
# garuda/digital_twin/environment.py

class EnvironmentModel:
    """
    Simulates atmospheric conditions around the drone.
    Updates every simulation tick (10-50 Hz).
    """

    def __init__(self, home_altitude_m=920.0):
        # ISA constants
        self.T0 = 288.15        # Sea-level temp (K)
        self.rho0 = 1.225       # Sea-level density (kg/m³)
        self.L = 0.0065         # Lapse rate (K/m)
        self.g = 9.80665
        self.R = 287.05

        self.home_altitude = home_altitude_m

        # Wind state (Ornstein-Uhlenbeck process for each axis)
        self.wind_steady = [0.0, 0.0, 0.0]    # [N, E, D] m/s
        self.wind_gust = [0.0, 0.0, 0.0]       # [N, E, D] m/s
        self.turbulence_intensity = 0.3         # 0=calm, 1=severe
        self.gust_tau = 5.0                     # Correlation time (seconds)

        # Ambient overrides
        self.temp_offset_C = 0.0                # Disturbance injection

    def get_temperature_K(self, altitude_agl_m):
        """ISA temperature at altitude (above ground level)."""
        h = self.home_altitude + altitude_agl_m
        return self.T0 - self.L * h + self.temp_offset_C

    def get_air_density(self, altitude_agl_m):
        """ISA air density at altitude."""
        T = self.get_temperature_K(altitude_agl_m)
        exponent = (self.g / (self.R * self.L)) - 1.0
        return self.rho0 * (T / self.T0) ** exponent

    def get_wind_vector(self):
        """Total wind = steady + gust. Returns [N, E, D] m/s."""
        return [s + g for s, g in zip(self.wind_steady, self.wind_gust)]

    def get_wind_speed(self):
        """Horizontal wind magnitude in m/s."""
        w = self.get_wind_vector()
        return math.sqrt(w[0]**2 + w[1]**2)

    def step(self, dt):
        """Advance the environment simulation by dt seconds."""
        sigma = self.turbulence_intensity * 3.0  # scale to m/s
        for i in range(3):
            self.wind_gust[i] = update_gust(
                self.wind_gust[i], dt, sigma, self.gust_tau
            )

    # --- Disturbance injection for scenarios ---
    def inject_crosswind(self, speed_ms=12.0):
        self.wind_steady[1] = speed_ms  # East component

    def inject_temperature_spike(self, delta_C=20.0):
        self.temp_offset_C += delta_C

    def inject_downdraft(self, speed_ms=5.0):
        self.wind_steady[2] = speed_ms  # Down component (NED)
```

### Environment — Open-Source References

- **[radlab-sketch/drydenModelPython](https://github.com/radlab-sketch/drydenModelPython)** — Direct Python Dryden implementation
- **[RotorPy](https://github.com/spencerfolk/rotorpy)** — Multirotor simulator with built-in Dryden wind
- **[ambiance PyPI](https://pypi.org/project/ambiance/)** — ISA atmosphere calculations

---

## 2. Vehicle Health Model

**File**: `garuda/digital_twin/vehicle_health.py`

### Vehicle Health — Overview & Definition

Tracks the physical health of every major component on the drone: battery
temperature, charge level, each rotor's efficiency, motor wear, payload mass,
and cumulative structural stress. This is the "body" of the digital twin.

### Vehicle Health — Hackathon Scoring Impact

> *"Physical-state estimation accuracy"* and *"Vehicle health modelling
> quality"* are two separate judging criteria. This module addresses both.

### Vehicle Health — Industry Solutions & Standards

| Component | Industry Method | Reference |
| --- | --- | --- |
| **Battery SoC** | Coulomb counting + OCV (Open Circuit Voltage) correction | Every BMS (Battery Management System) |
| **Battery temperature** | Lumped thermal model (1st-order ODE) | Tesla, DJI battery packs |
| **Rotor efficiency** | Thrust coefficient vs RPM lookup + air density correction | NASA rotor databases |
| **Motor degradation** | Linear or exponential efficiency decay over operating hours | Predictive maintenance ML literature |
| **Structural stress** | Cumulative G-force exposure tracking | Aerospace fatigue life monitoring |
| **Payload** | Direct mass measurement or mission-profile scheduling | Delivery drones (Wing, Zipline) |

### Vehicle Health — Governing Physics & Mathematics

#### 2A. Battery Thermal Model (Lumped ODE)

The battery heats up when current flows through it (because of internal
resistance), and cools down from airflow. It is like a cup of coffee — the
heater (current) warms it, and the breeze (airflow) cools it.

```text
Temperature rate of change:
  dT_bat/dt = (Q_gen - Q_cool) / (m_bat × Cp)

Where:
  Q_gen  = I² × R_internal     (heat generated by current flow, Watts)
  Q_cool = h × A × (T_bat - T_ambient)  (heat lost to airflow)

  I     = current draw (Amps)
  R_internal = battery internal resistance (≈ 0.05-0.15 Ω for 3S LiPo)
  h     = convective heat transfer coefficient (≈ 10-30 W/m²·K, higher when flying)
  A     = battery surface area (≈ 0.003 m² for our 450mAh pack)
  m_bat = battery mass (≈ 0.035 kg)
  Cp    = specific heat capacity (≈ 1000 J/kg·K for LiPo)

Temperature effect on capacity:
  Effective capacity = rated_capacity × (1 - 0.01 × max(0, 25 - T_bat_C))
  (Capacity drops ~1% per degree below 25°C)
```

**Critical thresholds** (from LiPo safety data):

- Below 0°C: Do not charge, severely reduced capacity
- 20-45°C: Optimal operating range
- Above 55°C: WARNING — thermal runaway risk
- Above 65°C: CRITICAL — fire/explosion danger

#### 2B. Battery State of Charge (Coulomb Counting)

```text
SoC(t) = SoC(t-1) - (I × dt) / (Capacity × 3600)

Where:
  I        = current draw (Amps)
  dt       = timestep (seconds)
  Capacity = effective capacity (Ah), affected by temperature
  3600     = seconds per hour conversion
```

#### 2C. Rotor Efficiency Model

Each rotor's actual thrust depends on its mechanical condition and the
air it is working in:

```text
Actual thrust per rotor:
  T_actual = T_ideal × η_rotor × η_air × η_motor

Where:
  T_ideal   = base thrust at current RPM (from motor KV and voltage)
  η_rotor   = rotor efficiency factor (1.0 = perfect, degrades over time)
  η_air     = air density ratio = ρ(altitude) / ρ₀ (thinner air = less thrust)
  η_motor   = motor efficiency (degrades with bearing wear)
```

#### 2D. Motor Degradation

```text
Motor efficiency over time:
  η_motor(t) = η₀ × (1 - degradation_rate × flight_hours / rated_lifespan)

  η₀             = initial efficiency (typically 0.85-0.92 for BLDC motors)
  degradation_rate = 0.15 (15% efficiency loss over rated lifespan)
  rated_lifespan   = ~500-2000 hours for small BLDC motors
  flight_hours     = cumulative operating time (simulated)
```

Each motor can degrade independently. This lets us simulate single-motor
failure scenarios.

#### 2E. Structural Stress Accumulator

```text
Cumulative stress:
  stress_total += |acceleration - g| × dt

  acceleration = measured from IMU (m/s²)
  g            = 9.81 m/s²
  dt           = timestep

Thresholds:
  stress_total > 1000 → Inspection recommended
  stress_total > 5000 → Mission abort recommended
```

### Vehicle Health — Implementation Blueprint

```python
# garuda/digital_twin/vehicle_health.py

class BatteryModel:
    def __init__(self, capacity_ah=0.45, cells=3, internal_resistance=0.08):
        self.capacity = capacity_ah
        self.cells = cells
        self.R_int = internal_resistance
        self.soc = 1.0                # 100%
        self.temperature_C = 25.0      # Ambient start
        self.voltage = cells * 4.2     # Fully charged
        self.mass_kg = 0.035
        self.surface_area = 0.003
        self.Cp = 1000.0

    def step(self, current_A, ambient_temp_C, airspeed_ms, dt):
        # Thermal model
        h = 10.0 + 2.0 * airspeed_ms  # Convection increases with airspeed
        Q_gen = current_A**2 * self.R_int
        Q_cool = h * self.surface_area * (self.temperature_C - ambient_temp_C)
        dT = (Q_gen - Q_cool) / (self.mass_kg * self.Cp) * dt
        self.temperature_C += dT

        # Coulomb counting
        temp_factor = 1.0 - 0.01 * max(0, 25 - self.temperature_C)
        effective_capacity = self.capacity * max(0.5, temp_factor)
        self.soc -= (current_A * dt) / (effective_capacity * 3600)
        self.soc = max(0.0, min(1.0, self.soc))

        # Voltage model (simplified linear)
        self.voltage = self.cells * (3.3 + 0.9 * self.soc)

    @property
    def percent(self):
        return self.soc * 100.0


class RotorModel:
    def __init__(self, motor_id, initial_efficiency=0.90):
        self.id = motor_id
        self.base_efficiency = initial_efficiency
        self.degradation = 0.0         # 0.0 = new, 1.0 = dead
        self.flight_hours = 0.0

    def step(self, dt):
        self.flight_hours += dt / 3600.0
        # Natural degradation: 15% loss over 1000 hours
        self.degradation = min(1.0, self.flight_hours / 1000.0 * 0.15)

    @property
    def efficiency(self):
        return self.base_efficiency * (1.0 - self.degradation)

    def inject_failure(self, severity=0.4):
        """Simulate sudden bearing wear or blade damage."""
        self.degradation = min(1.0, self.degradation + severity)


class VehicleHealthModel:
    def __init__(self):
        self.battery = BatteryModel()
        self.rotors = [RotorModel(i) for i in range(4)]
        self.payload_kg = 0.0
        self.drone_mass_kg = 0.249     # Sub-250g target
        self.structural_stress = 0.0
        self.g_force_history = []

    @property
    def total_mass_kg(self):
        return self.drone_mass_kg + self.payload_kg

    @property
    def avg_rotor_efficiency(self):
        return sum(r.efficiency for r in self.rotors) / 4.0

    @property
    def min_rotor_efficiency(self):
        return min(r.efficiency for r in self.rotors)

    def step(self, current_A, ambient_temp_C, airspeed_ms, accel_ms2, dt):
        self.battery.step(current_A, ambient_temp_C, airspeed_ms, dt)
        for rotor in self.rotors:
            rotor.step(dt)
        # Structural stress
        g_excess = abs(accel_ms2 - 9.81)
        self.structural_stress += g_excess * dt
```

---

## 3. Energy & Endurance Forecasting

**File**: `garuda/digital_twin/energy_model.py`

### Energy Forecasting — Overview & Definition

Predicts how much power the drone is using right now, how long it can keep
flying, whether it has enough energy to complete its mission, and what the
maximum safe operating boundaries are (max altitude, max range, max speed).

### Energy Forecasting — Hackathon Scoring Impact

> *"Energy/endurance prediction accuracy"* is a direct judging criterion.

### Energy Forecasting — Industry Solutions & Standards

The standard approach uses **Momentum Theory** (also called Actuator Disk
Theory) from helicopter aerodynamics. Every DJI drone, every delivery drone
uses a variation of this.

### Energy Forecasting — Governing Physics & Mathematics

#### 3A. Power Consumption Model

Total power at any moment is the sum of three components:

```text
P_total = P_induced + P_profile + P_parasitic

1. Induced Power (power to generate lift):
   P_induced = k × T^1.5 / √(2 × ρ × A × n_rotors)

   k = induced power correction factor (1.15 typical)
   T = total thrust needed = (m_total × g) / cos(tilt_angle)
   ρ = air density at current altitude
   A = single rotor disk area = π × R²
   R = propeller radius (0.0254 m for 2-inch props)
   n_rotors = 4

2. Profile Power (power to spin blades against air friction):
   P_profile = n_rotors × (Cd0 × ρ × A_blade × (Ω × R)³) / 8

   Cd0 = blade drag coefficient (≈ 0.01)
   A_blade = blade planform area
   Ω = rotational speed (rad/s)

3. Parasitic Power (power to push airframe through air):
   P_parasitic = 0.5 × ρ × Cd_frame × A_frontal × V³

   Cd_frame = frame drag coefficient (≈ 1.0 for quadrotor)
   A_frontal = frontal area of drone (≈ 0.01 m²)
   V = forward airspeed (m/s)

Simplified hover power (most common case):
   P_hover = √((m × g)³ / (2 × ρ × A_total))
   A_total = 4 × π × R² (total disk area)
```

**For our drone** (249g, 2-inch props, 3S LiPo):

- Hover power ≈ 25-35W
- Forward flight at 5 m/s ≈ 30-40W
- Aggressive maneuvering ≈ 50-80W

#### 3B. Remaining Endurance

```text
Remaining flight time:
  t_remaining = (SoC × Capacity × V_nominal) / P_current

  SoC = current state of charge (0-1)
  Capacity = effective capacity in Ah (temperature-adjusted)
  V_nominal = nominal battery voltage
  P_current = current power draw in Watts

Safety margins:
  t_usable = t_remaining - t_RTB_reserve - t_landing_reserve

  t_RTB_reserve = distance_to_home / cruise_speed × P_cruise / P_hover
  t_landing_reserve = 30 seconds (fixed buffer)
```

#### 3C. Safe Operating Envelope

The envelope defines the boundaries within which the drone can safely operate
given its current health and environment:

```text
Max altitude = altitude where thrust = weight
  → Solve: 4 × T_max(ρ(h)) × η_rotor = m × g

Max speed = speed where power = max available power
  → Solve: P_total(V) = V_bat × I_max

Max range = distance achievable with remaining energy
  → range = (SoC × Capacity × V_nominal - E_RTB - E_reserve) / P_cruise × V_cruise

Max hover time = remaining energy / hover power
```

### Energy Forecasting — Implementation Blueprint

```python
# garuda/digital_twin/energy_model.py

class EnergyModel:
    def __init__(self, vehicle_health, environment):
        self.health = vehicle_health
        self.env = environment

        # Drone physical constants
        self.prop_radius = 0.0254       # 2-inch props
        self.n_rotors = 4
        self.disk_area = math.pi * self.prop_radius**2
        self.total_disk_area = self.n_rotors * self.disk_area
        self.Cd_frame = 1.0
        self.A_frontal = 0.01
        self.k_induced = 1.15

    def power_hover(self, altitude_agl=0):
        rho = self.env.get_air_density(altitude_agl)
        m = self.health.total_mass_kg
        eta = self.health.avg_rotor_efficiency
        T = m * 9.81  # Total thrust = weight
        P = self.k_induced * T**1.5 / math.sqrt(2 * rho * self.total_disk_area)
        return P / eta

    def power_forward(self, speed_ms, altitude_agl=0):
        P_hover = self.power_hover(altitude_agl)
        rho = self.env.get_air_density(altitude_agl)
        P_parasitic = 0.5 * rho * self.Cd_frame * self.A_frontal * speed_ms**3
        # In forward flight, induced power decreases slightly
        P_induced_factor = max(0.6, 1.0 - speed_ms * 0.03)
        return P_hover * P_induced_factor + P_parasitic

    def current_draw(self, power_w):
        return power_w / self.health.battery.voltage

    def remaining_endurance_s(self, current_power_w):
        cap = self.health.battery.capacity  # Ah
        soc = self.health.battery.soc
        volt = self.health.battery.voltage
        energy_remaining_wh = soc * cap * volt
        if current_power_w <= 0:
            return float('inf')
        return (energy_remaining_wh * 3600) / current_power_w

    def can_complete_mission(self, dist_remaining_m, dist_home_m, cruise_speed=5.0):
        P_cruise = self.power_forward(cruise_speed)
        t_mission = dist_remaining_m / cruise_speed
        t_rtb = dist_home_m / cruise_speed
        t_reserve = 30.0
        t_needed = t_mission + t_rtb + t_reserve
        t_available = self.remaining_endurance_s(P_cruise)
        return t_available > t_needed, t_available, t_needed

    def safe_envelope(self, altitude_agl=0):
        return {
            "max_endurance_s": self.remaining_endurance_s(self.power_hover(altitude_agl)),
            "hover_power_w": self.power_hover(altitude_agl),
            "max_speed_ms": 10.0 * self.health.avg_rotor_efficiency,
            "battery_percent": self.health.battery.percent,
            "battery_temp_C": self.health.battery.temperature_C,
            "air_density": self.env.get_air_density(altitude_agl),
            "wind_speed_ms": self.env.get_wind_speed(),
        }
```

---

## 4. Autonomous Decision Engine

**File**: `garuda/digital_twin/decision_engine.py`

### Decision Engine — Overview & Definition

The "brain" of the digital twin. It takes inputs from the environment model,
vehicle health, and energy forecasting, and makes safety-critical decisions:
continue the mission, slow down, change altitude, reroute, return to base,
or abort immediately.

### Decision Engine — Hackathon Scoring Impact

> *"Effectiveness of safety and control decisions"* is a direct judging criterion.
> This is where you show that the digital twin actually DOES something useful.

### Decision Engine — Industry Solutions & Standards

| Approach | Used By | Our Use |
| --- | --- | --- |
| **Hierarchical Finite State Machine (HFSM)** | DJI, Skydio, ArduPilot | ✅ Primary — we already have a state machine in `orchestrator.py` |
| **Rule-based decision trees** | PX4 failsafe logic, QGroundControl | ✅ For simple threshold checks |
| **Model Predictive Control (MPC)** | Academic research, Waymo | ❌ Too complex for hackathon |
| **Reinforcement Learning** | ETH Zurich drone labs | ❌ Needs training data |

**Our approach**: Extend our existing state machine (`orchestrator.py`) with
physics-informed guard conditions from the digital twin models.

### Decision Engine — Multi-Priority Decision Matrix

Every simulation tick, the decision engine evaluates these conditions in
priority order (highest priority first):

```text
Priority 1 — ABORT MISSION (Emergency)
  IF battery_temp > 60°C                         → ABORT
  IF min_rotor_efficiency < 0.3                   → ABORT
  IF structural_stress > 5000                     → ABORT
  IF remaining_endurance < 60s                    → ABORT

Priority 2 — RETURN TO BASE
  IF battery_temp > 50°C                         → RTB
  IF remaining_endurance < RTB_time + 120s        → RTB
  IF battery_soc < 15%                            → RTB
  IF avg_rotor_efficiency < 0.5                   → RTB
  IF wind_speed > 8 m/s (sustained)               → RTB

Priority 3 — ALTER ALTITUDE
  IF air_density < 0.95 kg/m³ AND altitude > 50m → DESCEND to denser air
  IF vertical_wind_shear > 3 m/s                 → CHANGE altitude band

Priority 4 — REDUCE SPEED
  IF turbulence_intensity > 0.6                  → REDUCE speed by 50%
  IF wind_speed > 5 m/s AND in crosswind         → REDUCE speed by 30%
  IF motor_efficiency_delta > 0.1 (imbalanced)   → REDUCE speed

Priority 5 — MODIFY TRAJECTORY
  IF headwind > 0.5 × cruise_speed               → REROUTE to sheltered path
  IF wind_direction_change > 60° in 10s          → ADJUST heading

Priority 6 — CONTINUE
  IF all conditions nominal                      → CONTINUE mission
```

### Decision Engine — Interpretable Evidence Trail

Every decision must produce a **structured evidence log** that judges can
read. This is what makes the system "interpretable":

```python
decision_log = {
    "timestamp": "2026-09-26T01:23:45",
    "decision": "RETURN_TO_BASE",
    "confidence": 0.92,
    "triggers": [
        {"param": "battery_temp_C", "value": 52.3, "threshold": 50.0, "severity": "WARNING"},
        {"param": "remaining_endurance_s", "value": 185.0, "threshold": 200.0, "severity": "CRITICAL"},
    ],
    "alternatives_considered": ["REDUCE_SPEED", "ALTER_ALTITUDE"],
    "reason": "Battery temperature exceeding safe threshold combined with low endurance reserves",
    "physics_evidence": {
        "hover_power_w": 38.5,
        "air_density": 1.08,
        "wind_speed_ms": 6.2,
    }
}
```

### Decision Engine — Implementation Blueprint

```python
# garuda/digital_twin/decision_engine.py

from enum import Enum
from dataclasses import dataclass, field
from typing import List
import time

class Decision(Enum):
    CONTINUE = "CONTINUE"
    MODIFY_TRAJECTORY = "MODIFY_TRAJECTORY"
    REDUCE_SPEED = "REDUCE_SPEED"
    ALTER_ALTITUDE = "ALTER_ALTITUDE"
    RETURN_TO_BASE = "RETURN_TO_BASE"
    ABORT_MISSION = "ABORT_MISSION"

@dataclass
class DecisionRecord:
    timestamp: float
    decision: Decision
    confidence: float
    triggers: list
    reason: str
    physics_snapshot: dict

class DecisionEngine:
    def __init__(self, environment, vehicle_health, energy_model):
        self.env = environment
        self.health = vehicle_health
        self.energy = energy_model
        self.history: List[DecisionRecord] = []
        self.last_decision = Decision.CONTINUE

    def evaluate(self, altitude_agl=0, dist_home_m=0) -> DecisionRecord:
        triggers = []
        bat = self.health.battery
        env = self.env

        # Priority 1: ABORT
        if bat.temperature_C > 60:
            triggers.append({"param": "battery_temp_C", "value": bat.temperature_C,
                            "threshold": 60, "severity": "CRITICAL"})
        if self.health.min_rotor_efficiency < 0.3:
            triggers.append({"param": "min_rotor_efficiency",
                            "value": self.health.min_rotor_efficiency,
                            "threshold": 0.3, "severity": "CRITICAL"})

        if any(t["severity"] == "CRITICAL" for t in triggers):
            return self._record(Decision.ABORT_MISSION, 0.98, triggers,
                              "Critical system failure detected")

        # Priority 2: RETURN TO BASE
        if bat.temperature_C > 50:
            triggers.append({"param": "battery_temp_C", "value": bat.temperature_C,
                            "threshold": 50, "severity": "WARNING"})
        if bat.percent < 15:
            triggers.append({"param": "battery_soc", "value": bat.percent,
                            "threshold": 15, "severity": "WARNING"})
        if env.get_wind_speed() > 8.0:
            triggers.append({"param": "wind_speed", "value": env.get_wind_speed(),
                            "threshold": 8.0, "severity": "WARNING"})

        if len(triggers) >= 2 or any(t["severity"] == "WARNING" and
               t["param"] == "battery_soc" for t in triggers):
            return self._record(Decision.RETURN_TO_BASE, 0.90, triggers,
                              "Multiple warning conditions or critical battery")

        # Priority 3-4: REDUCE SPEED / ALTER ALTITUDE
        if env.turbulence_intensity > 0.6:
            triggers.append({"param": "turbulence", "value": env.turbulence_intensity,
                            "threshold": 0.6, "severity": "CAUTION"})
            return self._record(Decision.REDUCE_SPEED, 0.75, triggers,
                              "High turbulence detected")

        # Priority 6: CONTINUE
        return self._record(Decision.CONTINUE, 0.95, [], "All systems nominal")

    def _record(self, decision, confidence, triggers, reason):
        record = DecisionRecord(
            timestamp=time.time(),
            decision=decision,
            confidence=confidence,
            triggers=triggers,
            reason=reason,
            physics_snapshot=self.energy.safe_envelope()
        )
        self.history.append(record)
        self.last_decision = decision
        return record
```

---

## 5. Uncertainty Quantification (Kalman Filter)

**File**: `garuda/digital_twin/state_estimator.py`

### Uncertainty — Overview & Definition

A Kalman Filter that combines the physics model predictions with sensor
measurements to produce the "best estimate" of the drone's true state,
along with a **confidence number** (uncertainty) for each estimate.

### Uncertainty — Hackathon Scoring Impact

> *"Quantify uncertainty in state and endurance predictions"* is explicitly
> listed as an advanced requirement. This is what separates a good submission
> from a great one.

### Uncertainty — How It Works in Plain English

Imagine you have two friends telling you where the drone is:

- **Friend 1 (Physics Model)**: "Based on the speed and direction, the drone
  should be at position X." This friend is smart but sometimes wrong because
  the wind model isn't perfect.
- **Friend 2 (GPS Sensor)**: "The GPS says the drone is at position Y." This
  friend has direct measurement but GPS has noise.

The Kalman Filter combines both opinions, weighting each by how confident
you are in them. If the GPS signal is noisy, it trusts the physics model more.
If the physics model hasn't been calibrated recently, it trusts GPS more.

The **covariance matrix** is the uncertainty — bigger numbers mean less
confidence in that state variable.

### Uncertainty — Implementation Blueprint

```python
# Simplified scalar Kalman filter for each state variable
class SimpleKalmanFilter:
    def __init__(self, initial_value, process_noise, measurement_noise):
        self.x = initial_value           # State estimate
        self.P = 1.0                      # Estimate uncertainty (covariance)
        self.Q = process_noise            # How much we expect the state to change
        self.R = measurement_noise        # How noisy the sensor is

    def predict(self, dt, model_prediction=None):
        """Physics model prediction step."""
        if model_prediction is not None:
            self.x = model_prediction
        self.P += self.Q * dt             # Uncertainty grows over time

    def update(self, measurement):
        """Sensor measurement correction step."""
        K = self.P / (self.P + self.R)    # Kalman gain
        self.x += K * (measurement - self.x)
        self.P *= (1 - K)                 # Uncertainty shrinks after measurement

    @property
    def uncertainty(self):
        return math.sqrt(self.P)          # Standard deviation
```

We create one filter for each state variable: position (N, E, D), battery
SoC, wind speed estimate, etc. The dashboard shows these as ± error bars.

---

## 6. Digital Twin Dashboard

**File**: New Next.js or plain HTML project deployed to Vercel

### Dashboard — Overview & Definition

A web page that judges visit at a URL. It shows the digital twin running in
real time with all telemetry, physics state, decisions, and uncertainty
visualized.

### Dashboard — Hackathon Scoring Impact

> *"Dashboard displaying simulated telemetry, physical state, uncertainty,
> environmental conditions, and decisions"* is a mandatory deliverable.
> *"The deployed version must be functional during evaluation"* is mandatory.

### Dashboard — Architecture Options

| Option | Pros | Cons | Time to Build |
| --- | --- | --- | --- |
| **Option A: Pure HTML + Chart.js + CSS** | Simple, no build step, deploy as static site | Less polished, no 3D | 3-4 hours |
| **Option B: Next.js + React Three Fiber** | Professional, 3D drone model, impressive | More complex setup | 6-8 hours |
| **Option C: Streamlit** | Fastest to code, Python-native | Looks basic, limited real-time | 2-3 hours |

**Recommended: Option A** (HTML + Chart.js) — maximum impact in minimum time.
Deploy as a static site on Vercel or Firebase Hosting.

### Dashboard — 7-Panel Monitoring Layout

```text
┌──────────────────────────────────────────────────┐
│               GARUDAONE DIGITAL TWIN              │
│          Physics-Informed Flight Monitor           │
├─────────────┬──────────────┬─────────────────────┤
│ TELEMETRY   │ ENVIRONMENT  │ VEHICLE HEALTH       │
│ Alt: 45.2m  │ Wind: 6.3m/s │ Batt: 72% (38.2°C)  │
│ Speed: 5.1  │ ↗ NNE        │ Motor 1: 88% ■■■■□  │
│ GPS: 3D Fix │ ρ: 1.08kg/m³ │ Motor 2: 90% ■■■■□  │
│ Heading: N  │ Turb: 0.4    │ Motor 3: 62% ■■■□□  │
│ Lat/Lng     │ Temp: 28°C   │ Motor 4: 89% ■■■■□  │
├─────────────┼──────────────┤ Payload: 0g          │
│ ENERGY      │ SAFE ENVELOPE│ Stress: 234/5000     │
│ Power: 35W  │ Max Alt: 120m├─────────────────────┤
│ Endure: 14m │ Max Spd: 8m/s│ DECISION LOG         │
│ RTB: 3m     │ Range: 850m  │ 01:23 CONTINUE ✓    │
│ ████████░░  │ ██████████░  │ 01:24 REDUCE_SPEED ⚠│
│ Feasible ✓  │              │ 01:25 RTB ⛔         │
│ ±2.1 min    │              │ Evidence: Batt 52°C  │
│ (uncertainty)│              │ + Wind 8.2 m/s       │
└─────────────┴──────────────┴─────────────────────┘
```

### Dashboard — Real-Time Telemetry Data Flow

```text
Python Simulation Engine (runs locally or on server)
  ├── Runs EnvironmentModel.step()
  ├── Runs VehicleHealthModel.step()
  ├── Runs EnergyModel calculations
  ├── Runs DecisionEngine.evaluate()
  └── Outputs JSON snapshot every 500ms
        │
        ├── Option A: Write to a JSON file → Dashboard reads via fetch()
        ├── Option B: WebSocket stream → Dashboard receives real-time
        └── Option C: REST API endpoint → Dashboard polls every 1s
```

### Dashboard — Hosting & Deployment

```bash
# For static HTML dashboard:
# 1. Create the HTML/CSS/JS files
# 2. Deploy to Vercel:
npx -y vercel --prod

# Or deploy to Firebase Hosting:
firebase init hosting
firebase deploy
```

---

## 7. Scenario Demonstrations

**File**: `scripts/scenarios.py`

### Scenarios — Overview & Purpose

Pre-scripted test sequences that inject failures and disturbances into the
simulation, forcing the decision engine to react. Judges watch the dashboard
while scenarios play out.

### Scenarios — The 5 Prescribed Failure Injections

| # | Name | What Happens | Expected Decision Chain | Duration |
| --- | --- | --- | --- | --- |
| 1 | **Sudden Crosswind** | 12 m/s east wind appears at t=30s | CONTINUE → REDUCE_SPEED → MODIFY_TRAJECTORY | 60s |
| 2 | **Motor Bearing Failure** | Motor #3 efficiency drops to 60% at t=20s | CONTINUE → REDUCE_SPEED → RTB | 90s |
| 3 | **Battery Overheat** | Battery temp rises to 58°C during aggressive maneuver | CONTINUE → RTB → ABORT | 45s |
| 4 | **Payload Release** | Payload mass drops from 50g to 0g mid-flight | Recalculate envelope → CONTINUE (with updated params) | 30s |
| 5 | **Combined Stress** | Wind increases + battery dropping + high altitude simultaneously | ALTER_ALTITUDE → REDUCE_SPEED → RTB | 120s |

### Scenarios — Implementation Blueprint

```python
# scripts/scenarios.py

async def scenario_sudden_crosswind(twin):
    """Scenario 1: Sudden crosswind gust during forward flight."""
    print("[SCENARIO] Normal flight for 30 seconds...")
    await asyncio.sleep(30)

    print("[SCENARIO] INJECTING: 12 m/s crosswind from East!")
    twin.environment.inject_crosswind(speed_ms=12.0)

    # Decision engine should detect and react within 2-5 seconds
    await asyncio.sleep(30)

    print("[SCENARIO] Wind subsiding...")
    twin.environment.wind_steady[1] = 3.0

    print("[SCENARIO] Complete. Check decision log for response chain.")


async def scenario_motor_failure(twin):
    """Scenario 2: Motor #3 bearing wear."""
    print("[SCENARIO] Normal flight for 20 seconds...")
    await asyncio.sleep(20)

    print("[SCENARIO] INJECTING: Motor #3 efficiency drop to 60%!")
    twin.vehicle_health.rotors[2].inject_failure(severity=0.33)

    await asyncio.sleep(70)
    print("[SCENARIO] Complete.")
```

---

## 8. Updated README Structure

The README needs to be completely rewritten for Theme 3. Here is the structure:

```markdown
# GarudaOne — Physics-Informed Drone Digital Twin

> HackFusion 2026 | Theme 3 | IEEE Robotics & Automation Society

## 🔗 Live Demo
**Dashboard URL**: [https://garuda-twin.vercel.app](https://garuda-twin.vercel.app)

## 🏗️ Architecture
[Architecture diagram — use Mermaid or image]

## 🧪 Key Features
1. ✅ Environmental State Model (Dryden wind + ISA atmosphere)
2. ✅ Vehicle Health Model (battery thermal + rotor degradation)
3. ✅ Energy & Endurance Forecasting (momentum theory)
4. ✅ Safe Operating Envelope Prediction
5. ✅ Autonomous Decision Engine (6 decision types)
6. ✅ Uncertainty Quantification (Kalman Filter)
7. ✅ Real-Time Dashboard with 7 panels
8. ✅ 5 Failure Scenario Demonstrations
9. ⭐ Voice-Controlled AI Copilot (OpenAI + Smallest.ai TTS)
10. ⭐ GPS-Denied Flight Capability (EKF2 Vision Fusion)

## 📐 Physics Models & Assumptions
[Document every equation, reference MIL-F-8785C, ISA, momentum theory]

## 🚀 Quick Start
[Setup instructions]

## 📊 Scenario Results
[Table of scenarios with screenshots/logs]

## 👥 Team
| Name | Role |
| --- | --- |
| ... | ... |

## 📝 License
```

---

## 9. References & Resources

### Academic Papers & Standards

| Reference | What It's For |
| --- | --- |
| **MIL-F-8785C** — US Military Flying Qualities Specification | Dryden wind turbulence model parameters |
| **ICAO Standard Atmosphere (ISA)** | Air density and temperature vs altitude |
| **Actuator Disk Theory / Momentum Theory** | Hover power and induced velocity |
| **Coulomb Counting + Equivalent Circuit Model** | Battery SoC estimation |
| **Extended Kalman Filter (EKF)** | State estimation with uncertainty |

### Open-Source Code References

| Repository | Use |
| --- | --- |
| [radlab-sketch/drydenModelPython](https://github.com/radlab-sketch/drydenModelPython) | Dryden wind turbulence in Python |
| [spencerfolk/rotorpy](https://github.com/spencerfolk/rotorpy) | Multirotor simulator with wind models |
| [learnsyslab/gym-pybullet-drones](https://github.com/learnsyslab/gym-pybullet-drones) | Quadrotor dynamics + RL |
| [UniCT-ARSLab/Twinflie](https://github.com/UniCT-ARSLab/Twinflie) | UAV digital twin orchestrator |
| [ambiance PyPI](https://pypi.org/project/ambiance/) | ISA atmosphere calculations |
| [PX4-Autopilot](https://github.com/PX4/PX4-Autopilot) | Flight controller firmware |

### Python Libraries Needed

```bash
pip install numpy scipy   # Already have these
# No additional heavy libraries required — all models are pure math
```

---

> **Bottom line**: Every module above is pure Python math — no heavy ML
> training, no GPU, no complex dependencies. The physics equations are
> well-established and can be implemented in straightforward functions.
> The dashboard is the biggest time investment but can be done with plain
> HTML + Chart.js and deployed to Vercel in hours.
