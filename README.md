# GarudaOne DroneOS

## Autonomous AI-Powered Cinematography Drone — Companion Computer Software

> "Throw it in the air, say 'Follow me', get DJI-level cinematic footage."

---

## Architecture

```text
┌──────────────────────────────────────────────────┐
│  LAYER 1: Cognitive Brain (RPi5)                  │
│  LFM-2.5-230M → Complex command understanding     │
│  Needle 26M → Fast command routing (< 20ms)       │
│  Voice Pipeline → Wake Word + STT + TTS           │
└──────────────────────────────────────────────────┘
              ↕ Events (async pub/sub)
┌──────────────────────────────────────────────────┐
│  LAYER 2: Perception & Control (RPi5)             │
│  PicoDet-S → Person detection @ 45-55 FPS         │
│  SVO2 → Visual odometry + sparse depth            │
│  CfC LNN → Smooth velocity + gimbal commands      │
│  B-spline → Zero-jerk trajectory smoothing        │
└──────────────────────────────────────────────────┘
              ↕ MAVSDK-Python (UART MAVLink v2)
┌──────────────────────────────────────────────────┐
│  LAYER 3: Flight Control (MicoAir H743)           │
│  PX4 Autopilot (NuttX RTOS, 400Hz PID)           │
│  Sensor fusion: GPS + IMU + Optical Flow + Baro   │
│  Safety: Auto-RTL on companion disconnect         │
└──────────────────────────────────────────────────┘
```

## Hardware

| Component | Model |
| --- | --- |
| Companion Computer | Raspberry Pi 5 (8GB) |
| Flight Controller | MicoAir H743 AIO 35A |
| Camera | Skydroid C10 Pro 3-axis gimbal |
| GPS | Foxeer M10Q |
| Sensors | MicoAir MTF01 (rangefinder) + MT (optical flow) |
| IMU | BMI270 |
| Radio | Zerodrag Nexus ELRS 2.4GHz |
| Battery | LAVA 3S 450mAh |
| Target Weight | Sub-250g |

## Quick Start

### 1. Setup (on RPi5)

```bash
chmod +x scripts/setup_rpi5.sh
./scripts/setup_rpi5.sh
```

### 2. Download AI Models

```bash
python scripts/download_models.py
```

### 3. Flash PX4 (if still on Betaflight)

See [scripts/flash_px4.md](scripts/flash_px4.md)

### 4. Run

```bash
make run
```

### Development (on any machine)

```bash
pip install -r requirements.txt
GARUDA_MODE=simulation make run   # Runs completely offline using Telemetry Stub Fallback
make test                          # Run tests
```

## Simulation Development (PX4 SITL)

For full flight dynamics testing, use PX4 SITL (Software-In-The-Loop) running
inside WSL2 on Windows. This runs the **exact same PX4 firmware** as the real
MicoAir H743 flight controller.

### Quick Start (Windows + WSL2)

```bash
# 1. Setup PX4 SITL in WSL2 (one-time, ~30 minutes)
wsl bash scripts/setup_sitl.sh

# 2. Launch PX4 SITL + Gazebo (in a separate WSL2 terminal)
wsl bash scripts/launch_sitl.sh

# 3. Run DroneOS connected to the simulated drone
make run-sitl
```

### What You Get

- 🚁 **Real PX4 firmware** with actual flight physics
- 🎥 **3D visualization** via Gazebo and QGroundControl
- 🔄 **Same code** for simulation and real hardware (change one config line)
- 🧠 **All AI modules** can run with real models or stubs

See [`docs/sitl_setup_guide.md`](docs/sitl_setup_guide.md) for the complete guide.

### Connection Modes

| Mode | How to Enable | Behavior |
| --- | --- | --- |
| **SITL** | `GARUDA_MODE=simulation` + PX4 SITL running | Real PX4 flight dynamics |
| **Stub** | `GARUDA_MODE=simulation` (no SITL running) | Fake telemetry for logic testing |
| **Hardware** | (default, no env var) | UART connection to real flight controller |

## Voice Commands

| Say | Action |
| --- | --- |
| "Garuda, take off" | Take off to 3m altitude |
| "Follow me" | Active subject tracking |
| "Orbit" | Circle around subject (8m radius) |
| "Chase me" | Follow from behind |
| "Reveal" | Cinematic pull-back + rise |
| "Start recording" | Begin video recording |
| "Stop" / "Hover" | Hold position |
| "Go home" | Return to launch + land |
| "Emergency" | Kill motors immediately |

## Project Structure

```text
garuda/
├── main.py              # Entry point + boot sequence
├── core/                # Mission orchestrator + event bus
├── brain/               # LLM engine + tool routing
├── perception/          # Object detection + tracking + VO
├── control/             # CfC controller + path smoother + gimbal
├── flight/              # PX4 MAVSDK bridge + safety
├── voice/               # Voice pipeline (wake word + STT + TTS)
├── camera/              # Camera feed capture
└── utils/               # Logging, transforms, profiler
```

## License

Proprietary — GarudaOne Team
