# PID Tuning & Velocity Control Calibration Report

**System:** GarudaOne Quadrotor Platform  
**Environment:** Physical Bench Test & PX4 SITL Simulation (`city.sdf`)  
**Revision Date:** September 2026  

---

## 1. Physical Hardware Bench Telemetry

The images captured in this directory document bench testing and hardware PID parameter verification for the GarudaOne propulsion subassembly:
- **Motor / ESC Dynamic Balance:** Bench testing of four brushless motors with dual-blade composite propellers.
- **Vibration Isolation:** Analysis of accelerometer spectral noise profiles before and after silicone dampening.

---

## 2. Velocity Loop Controller Calibration

MAVSDK body velocity commands stream continuous linear velocity and yaw rate vectors directly to the PX4 flight stack:

| Parameter | Proportional ($K_p$) | Integral ($K_i$) | Derivative ($K_d$) | Velocity Limit | Max Duration |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **Horizontal ($v_x, v_y$) - Micro** | 1.80 | 0.15 | 0.04 | $2.5\text{ m/s}$ | $\le 4.8\text{ s}$ |
| **Horizontal ($v_x, v_y$) - Sprint**| 2.20 | 0.20 | 0.06 | $5.0\text{ m/s}$ | $\le 10.0\text{ s}$ |
| **Vertical ($v_z$) Climb/Descend**   | 1.40 | 0.10 | 0.02 | $2.5\text{ m/s}$ | $\le 6.0\text{ s}$ |
| **Yaw Rate ($\dot{\psi}$)**         | 2.80 | 0.05 | 0.01 | $45^\circ/\text{s}$| $\le 8.0\text{ s}$ |

---

## 3. Dynamic Maneuver Performance

- **5-Meter Default Translation:** Completed in $2.0\text{ s}$ at $2.5\text{ m/s}$ with $< 0.15\text{ m}$ position overshoot upon lock.
- **50-Meter Parametric Translation:** Completed in $10.0\text{ s}$ at $5.0\text{ m/s}$ with aerodynamic fan thrust sound feedback.
- **In-Air Safety Threshold:** Altitudes $< 0.4\text{ m}$ actively lock out translational setpoints to prevent ground strike.
