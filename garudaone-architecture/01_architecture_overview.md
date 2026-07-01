# GarudaOne: 3-Layer Liquid AI Architecture

## Overview
GarudaOne uses a novel 3-layer hybrid architecture that achieves GPU-level autonomy on a CPU power budget by combining Liquid Foundation Models, Liquid Neural Networks, and classic edge vision — all orchestrated through PX4's OFFBOARD mode.

---

## Layer 1: Cognitive & Agentic Brain
- **Hardware:** Raspberry Pi 5 (8GB RAM)
- **Models:**
  - **LFM-2.5-230M** (`llama.cpp`, GGUF) — 42 tok/s. Parses complex voice commands, holds mission context (32K window), outputs structured JSON tool calls.
  - **Needle 26M** (14MB, INT4) — 1,200 tok/s. Ultra-fast tool router. Simple commands bypass LFM entirely.
- **Role:** The "Director". Receives text summaries from Layer 2, makes high-level cinematic decisions, dispatches tool calls.

## Layer 2: Perception & Continuous Control
- **Hardware:** Raspberry Pi 5 (CPU)
- **Components:**
  - **PicoDet-S** (`ncnn`, INT8) — 45–55 FPS @ 320x320. Subject detection and bounding box tracking.
  - **SVO2 / ARM-VO** — Lightweight visual odometry. Sparse depth map + drone pose estimation. Obstacle awareness for textured surfaces.
  - **CfC LNN** (`ncps` library, 19–50 neurons) — Cinematic flow controller trained via Imitation Learning. Outputs smooth velocity vectors + gimbal compensation angles.
  - **TMF8828 ToF** (optional) — 8×8 depth grid at 5m, 60Hz. Catches glass/featureless/thin obstacles.
- **Role:** The "Fast-Twitch Muscle". Processes the camera feed in real-time, tracks subjects, builds spatial awareness, and generates continuous MAVLink velocity commands.

## Layer 3: Hard Real-Time Flight Control
- **Hardware:** MicoAir H743 AIO 35A (STM32H7 Cortex-M7)
- **Software:** **PX4 Autopilot** (NuttX RTOS)
- **Ground Station:** QGroundControl
- **Mode:** OFFBOARD (receives continuous velocity setpoints from Pi 5)
- **Sensors Fused:** Foxeer M10Q GPS + Compass, MicoAir Optical Flow + ToF (downward), Internal IMU
- **Role:** The "Safety Net". 400Hz PID loops. If Pi 5 crashes or disconnects, PX4 triggers automatic Return-to-Launch (RTL) or safe landing.

---

## Communication Bridge
- **Protocol:** MAVLink v2
- **Library:** MAVSDK-Python (PX4's official async Python SDK) on the Pi 5
- **Transport:** UART serial (Pi 5 GPIO → MicoAir H743 TELEM port)
- **Key Message:** `SET_POSITION_TARGET_LOCAL_NED` (velocity setpoints in NED frame)

---

## Data Flow
```
Voice Command ("Follow me, stay wide")
    → openWakeWord triggers
    → Moonshine Tiny transcribes
    → LFM-2.5-230M parses intent
    → Needle 26M routes to tool: track_subject(distance=5m, framing=wide)

Skydroid Camera Feed (30fps, reverse-engineered)
    → PicoDet-S: [Person, X:140, Y:200, Conf:0.95]
    → SVO2: Sparse depth map + pose
    → Text summary: "Target center-left, obstacle 4m ahead-right"

CfC LNN (19 neurons):
    Input: BBox coords + depth costmap + tool params
    Output: velocity_ned(vx=2.1, vy=-0.3, vz=0) + gimbal_yaw(-12°)
    → B-spline smoothing
    → MAVSDK → PX4 OFFBOARD mode
    → Gimbal command → Skydroid controller
```

---

## Licensing
- **PX4:** BSD 3-Clause (proprietary modifications allowed)
- **All AI models:** Open-source (Apache-2.0 / MIT)
- **GarudaOne application code:** Proprietary (protected)
