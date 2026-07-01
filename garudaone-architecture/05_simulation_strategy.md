# GarudaOne: Simulation Strategy

## Stack: NVIDIA Isaac Sim + Pegasus Simulator + PX4 SITL

### Why This Combo
- **Isaac Sim (Omniverse):** Photorealistic RTX ray-tracing. Domain randomization for robust AI training.
- **Pegasus Simulator:** Built natively for PX4. Drone-specific physics and control modules.
- **PX4 SITL:** The exact same PX4 firmware that runs on the MicoAir H743, running on a desktop. Zero code changes between sim and real.

### Hardware Requirements
- **Simulation Host:** Cloud GPU (Modal accounts — NVIDIA A10G/A100)
- **Streaming Client:** Intel Core Ultra 7 255H laptop (Omniverse Streaming Client)
- **Code Development:** Intel laptop (write Python, run MAVSDK scripts)

### The Sim-to-Real Pipeline
1. Isaac Sim generates the 3D world + camera feed
2. Python script runs PicoDet on the simulated camera feed → bounding box
3. CfC LNN processes bounding box + depth → velocity command
4. MAVSDK sends velocity to PX4 SITL → drone moves in simulation
5. **Deploy to real drone:** Change one line (SITL address → serial port). Done.

### Domain Randomization (Closing the Sim-to-Real Gap)
- Randomized wind vectors and turbulence
- Gaussian noise injected into simulated IMU
- ISO grain, motion blur, lens flares on simulated camera
- Varied lighting (harsh sun, shadows, overcast, golden hour)
- Randomized textures and object placement

### Real-World Data Integration
- Import Betaflight PID data from `C:\Projects\DroneOS\PID-data\`
- Configure exact drone mass (249g), motor thrust curves (QPT 1404), frame inertia (FlyLens 85)
- Simulated drone flies with the same characteristics as the physical prototype

### Simulation Telemetry Stub (Hardware Constraint Fallback)
Due to heavy hardware requirements for Isaac Sim (RTX 4080+ needed), a local simulated telemetry stub is implemented.
If the `mavlink_bridge` connection times out waiting for PX4 SITL (default 10s timeout via `udpin://:14540`), the system automatically switches to generating fake telemetry data (GPS, Battery drain, Attitude).
- Enables the full DroneOS boot sequence (all 7 steps) on constrained hardware without hanging.
- Configurable via `config/simulation.yaml` for setting starting coordinates, battery drain rates, and GPS noise.
- Works perfectly for testing High-Level logic (State Machine, Brain, Perception wiring) entirely locally without any GPU acceleration.

---

## Local SITL Development Setup (WSL2 + PX4 SITL + Gazebo)

For full flight dynamics testing without Isaac Sim, we use **PX4 SITL** (Software-In-The-Loop) running inside WSL2 Ubuntu on Windows. This runs the exact same PX4 firmware as the real MicoAir H743, just with motor outputs going to Gazebo instead of real ESCs.

### Why PX4 SITL Instead of Isaac Sim for Development
| | PX4 SITL + Gazebo | Isaac Sim + Pegasus |
|---|---|---|
| **GPU Required** | ❌ No (CPU-only) | ✅ NVIDIA RTX 4080+ |
| **Real PX4 Firmware** | ✅ Yes (exact same binary) | ✅ Yes |
| **Real Flight Dynamics** | ✅ Yes (Gazebo physics) | ✅ Yes (Isaac physics) |
| **Photorealistic Camera** | ❌ Basic (sufficient for detection) | ✅ RTX ray-tracing |
| **Setup Time** | ~30 min | ~2 hours + cloud setup |
| **Best For** | Logic testing, state machine, control loops | AI training, domain randomization |

### The SITL Architecture
```
┌─────────────────────────── WINDOWS ───────────────────────────┐
│                                                                │
│  GarudaOne DroneOS  ──UDP 14540──►  WSL2 Network Bridge       │
│  (Python, GARUDA_MODE=sim)                                      │
│                                                                │
└────────────────────────────────┬───────────────────────────────┘
                                 │
┌────────────────────────────────▼───────────────────────────────┐
│                         WSL2 UBUNTU                             │
│                                                                 │
│  PX4 SITL  ◄──shared memory──►  Gazebo Simulator                │
│  (real firmware)                 (3D physics + camera + sensors)│
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

### Quick Start
1. **Setup (one-time):** See `docs/sitl_setup_guide.md` for complete instructions
2. **Launch PX4 SITL:** `wsl bash scripts/launch_sitl.sh`
3. **Run DroneOS:** `GARUDA_MODE=simulation make run-sim`
4. **Watch in QGroundControl:** Auto-discovers on UDP 14550

### Connection Modes (Automatic)
The `MAVLinkBridge` automatically determines the connection mode:

| Config | Behavior |
|--------|----------|
| `GARUDA_MODE=simulation` + SITL running | **SITL mode** — real PX4 flight dynamics |
| `GARUDA_MODE=simulation` + no SITL | **Stub mode** — fake telemetry, for logic testing |
| No `GARUDA_MODE` (default) | **Hardware mode** — UART to MicoAir H743 |

### Sim-to-Real Connection Pipeline
Switching between simulation and real hardware requires changing **one line**:

```yaml
# config/simulation.yaml — controls SITL connection
px4_sitl:
  enabled: true      # Development: connect to PX4 SITL
                     # Production:  set to false or delete file
```

The MAVLink bridge reads this and connects to either:
- `udp://localhost:14540` (SITL)
- `serial:///dev/ttyAMA0:921600` (real hardware)

**The rest of the code is identical** — this is the power of PX4 SITL.

---

## AI Model Integration Status

The simulation environment supports both stubbed and real AI inference:

| Model | Stub Mode | Real Inference | How to Enable |
|-------|-----------|----------------|---------------|
| **PicoDet-S** (detection) | Fake bbox at frame center | ncnn or OpenCV DNN | Download model: `python scripts/download_models.py` |
| **LFM-2.5-230M** (brain) | Keyword-based responses | llama-cpp-python | `pip install llama-cpp-python` + download GGUF |
| **Needle 26M** (router) | Keyword fast-path only | llama-cpp-python | `pip install llama-cpp-python` + download GGUF |
| **Whisper-tiny** (STT) | No voice input | faster-whisper INT8 | `pip install faster-whisper sounddevice` |
| **Piper TTS** | Log only | Piper subprocess | Install Piper binary + voice model |
| **CfC LNN** (controller) | PID fallback | ncps library | Train model or use pre-trained weights |
| **SVO2** (visual odometry) | Random depth/pose | C++ SVO2 process | Build from source (advanced) |

All stubs allow the full system to boot and run without any model files — this is a deliberate design choice for rapid development.
