# 11 - 3D City Simulation & Voice-Piloted Offboard Flight Dynamics

**Status:** Validated in Gazebo Harmonic & PX4 v1.14 SITL  
**Date:** September 2026  
**Related Components:** `models/city.sdf`, `models/dronepad/`, `scripts/voice_pilot.py`

---

## 1. Overview

This document specifies the autonomous 3D urban simulation environment and the multi-modal voice flight control layer developed for the GarudaOne drone operating system.

```
       +-------------------------------------------------------------+
       |               PILOT VOICE / HOTKEY INTERFACE                |
       |  - 10-Minute Takeoff Hover Window                           |
       |  - 5-Meter Default Translation (Left, Right, Climb, etc.)   |
       |  - Dynamic Metric Parameter Parsing (e.g. 50m sprint)      |
       +------------------------------+------------------------------+
                                      |
                                      v
       +-------------------------------------------------------------+
       |                   MAVSDK OFFBOARD LAYER                     |
       |  - Velocity Body Setpoints (vx, vy, vz, yaw_rate)           |
       |  - Ground Safety Interlock (<0.4m translation rejection)    |
       |  - Acoustic Feedback (Dual Alarms + Rotor Harmonics)        |
       +------------------------------+------------------------------+
                                      |
                                      v
       +-------------------------------------------------------------+
       |                 GAZEBO HARMONIC 3D CITY WORLD               |
       |  - 4 Skyscraper Quadrants (30m to 75m)                      |
       |  - Central Plaza + 32m Boulevards                           |
       |  - Dual "D" Dronepads (Ground Origin + 50.25m Rooftop)      |
       +-------------------------------------------------------------+
```

---

## 2. 3D Urban Simulation Architecture (`city.sdf`)

The urban operational envelope is rendered in Gazebo Harmonic featuring:
- **Quadrant Skyscrapers:** Multi-level commercial, residential, and communication towers ranging from 30m to 75m high with distinct optical reflectivity and lidar signatures.
- **Urban Boulevards:** 32-meter wide cross-axial avenues designed for high-speed GPS-denied navigation tests.
- **Custom "D" Dronepads:** High-contrast landing targets replacing legacy helipads:
  - **Ground Pad:** Positioned at $(0, 0, 0.05)$ for takeoff and return-to-launch (RTL).
  - **Tower Alpha Pad:** Elevated rooftop landing platform at $(0, 48, 50.25)$ for aerial staging and high-rise payload delivery.

---

## 3. Offboard Velocity Vector Controller

All translational flight maneuvers are commanded via MAVSDK's `VelocityBodyYawspeed` protocol:

$$\mathbf{v}_{\text{body}} = \begin{bmatrix} v_x \\ v_y \\ v_z \\ \dot{\psi} \end{bmatrix} \quad \begin{cases} 
v_x = \text{forward/backward velocity (m/s)} \\
v_y = \text{right/left velocity (m/s)} \\
v_z = \text{down/up velocity (m/s)} \\
\dot{\psi} = \text{body yaw rate (deg/s)}
\end{cases}$$

### Speed vs. Distance Dynamic Scaling
To balance precision and responsiveness:
- **Short Translations ($d \le 12\text{m}$):** Controlled at $2.5\text{ m/s}$ ($t = d / 2.5$). Default 5m moves execute smoothly in 2.0 seconds.
- **Long Translations ($d > 12\text{m}$):** Sprint velocity stepped up to $5.0\text{ m/s}$ ($t = d / 5.0$). A 50-meter transit executes in exactly 10.0 seconds.

---

## 4. Multi-Modal Copilot & Safety Interlocks

1. **Ground Safety Interlock:** Telemetry actively tracks `in_air` status and relative altitude ($h > 0.4\text{m}$). Any translation requested while grounded triggers an acoustic dual-tone alarm ($900\text{Hz} \to 600\text{Hz}$), a red warning banner, and vocal guidance to take off first.
2. **Post-Execution Vocal Affirmations:** Every maneuver concludes with a clear vocal confirmation:
   - *"Garuda takeoff completed. Hovering at three meters for 10 minutes."*
   - *"Garuda right slide of 50 meters completed."*
3. **Rotor Acoustics:** High-fidelity quadcopter motor harmonics (`assets/drone_fan.wav`) play on motor spool-up and dynamic translation maneuvers.
