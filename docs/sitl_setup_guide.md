# GarudaOne — SITL Environment Setup Guide

> **Complete step-by-step guide for setting up PX4 SITL on Windows + WSL2**
> Written so anyone can follow it — no assumptions about prior PX4 experience.

---

## What You'll Have When Done

After following this guide, you'll be able to:

1. **Launch a simulated drone** that flies with real PX4 firmware physics (inside WSL2 + Gazebo)
2. **See the drone in 3D** via QGroundControl or the Gazebo window
3. **Run GarudaOne DroneOS** on Windows, connected to the simulated drone
4. **Test the full pipeline**: voice command → brain → perception → control → flight
5. **Switch to real hardware** by changing one config line

```
┌─────────────────────────────────────────────────────────────┐
│                    WINDOWS HOST                              │
│                                                              │
│  ┌──────────────────┐    ┌──────────────────────────────┐   │
│  │ GarudaOne DroneOS │    │  QGroundControl              │   │
│  │ (Python)          │    │  (Drone visualization)       │   │
│  │ GARUDA_MODE=sim   │    │                              │   │
│  └────────┬─────────┘    └──────────┬───────────────────┘   │
│           │ UDP :14540              │ UDP :14550            │
│           │ (MAVSDK)                │ (QGC)                 │
│ ══════════╪═════════════════════════╪══════════════════════ │
│           │     WSL2 PORT FORWARD    │                      │
│ ══════════╪═════════════════════════╪══════════════════════ │
│           ▼                         ▼                       │
│  ┌──────────────────────────────────────────────────────┐   │
│  │              WSL2 UBUNTU                              │   │
│  │                                                       │   │
│  │  ┌─────────────────┐    ┌────────────────────────┐   │   │
│  │  │  PX4 SITL       │◄──►│  Gazebo Simulator       │   │   │
│  │  │  (real firmware)│    │  (3D physics + camera)  │   │   │
│  │  └─────────────────┘    └────────────────────────┘   │   │
│  └──────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────┘
```

---

## Prerequisites

| Requirement | Minimum | Recommended |
|-------------|---------|-------------|
| **OS** | Windows 10 v2004+ / Windows 11 | Windows 11 |
| **RAM** | 8 GB | 16 GB+ |
| **Disk** | 20 GB free | 40 GB free |
| **CPU** | 4 cores | 8+ cores |
| **GPU** | Not required (CPU-only SITL) | GPU for Gazebo rendering |

**You do NOT need:**
- An NVIDIA GPU (CPU-only SITL works fine for logic testing)
- Any drone hardware
- Any AI model files (stubs work for initial testing)

---

## Step 1: Install WSL2 (5 minutes)

### 1.1 Check if WSL2 is already installed
Open **PowerShell as Administrator** and run:
```powershell
wsl --status
```
If you see version info, skip to Step 1.3. If you get an error, continue.

### 1.2 Install WSL2 with Ubuntu
In **PowerShell as Administrator**:
```powershell
wsl --install -d Ubuntu-24.04
```
This installs WSL2 + Ubuntu 24.04. **Restart your computer** when prompted.

### 1.3 Verify WSL2 is running
```powershell
wsl -l -v
```
You should see:
```
  NAME              STATE           VERSION
* Ubuntu-24.04      Running         2
```
**VERSION must be 2.** If it says 1, convert it:
```powershell
wsl --set-version Ubuntu-24.04 2
```

### 1.4 Set up Ubuntu
Launch Ubuntu from the Start menu. Create a username and password when prompted.
```bash
# Update packages
sudo apt update && sudo apt upgrade -y
```

---

## Step 2: Install PX4 SITL in WSL2 (20-40 minutes)

### 2.1 Copy the setup script into WSL2
From **Windows PowerShell**:
```powershell
# Navigate to your project
cd D:\Aatonovaz\DroneOS

# Run the setup script inside WSL2
wsl bash scripts/setup_sitl.sh
```

**Or manually inside WSL2:**
```bash
# From WSL2 Ubuntu terminal
cd /mnt/d/Aatonovaz/DroneOS
chmod +x scripts/setup_sitl.sh
./scripts/setup_sitl.sh
```

### 2.2 What the script does
The script automatically:
1. ✅ Installs all system dependencies (cmake, gazebo, python, etc.)
2. ✅ Downloads GeographicLib datasets (for accurate GPS)
3. ✅ Clones PX4 Autopilot from GitHub alongside DroneOS (~1.5GB)
4. ✅ Builds PX4 SITL target (10-20 minutes)
5. ✅ Installs MAVProxy and MAVLink tools
6. ✅ Creates launch scripts

### 2.3 If the build fails
```bash
# Clean and retry
cd ../PX4-Autopilot
make distclean
make px4_sitl_rtps
```

**Common issues:**
- **Out of disk space:** PX4 needs ~15GB during build. Free up space.
- **Missing dependencies:** `sudo apt update && sudo apt upgrade -y` then re-run.
- **Gazebo won't install:** See [Gazebo installation docs](http://gazebosim.org/).

---

## Step 3: Launch PX4 SITL (1 minute)

### 3.1 Start the simulator
From **WSL2 Ubuntu**:
```bash
cd ../PX4-Autopilot
make px4_sitl_rtps gazebo_x500
```

This launches:
- **PX4 SITL** — the autopilot firmware (real PX4, simulated sensors)
- **Gazebo** — the 3D physics simulator with a quadcopter model

You'll see:
- A Gazebo window showing the drone on the ground
- PX4 console output in the terminal (showing boot sequence)

### 3.2 Verify it's running
In the PX4 console, you should see:
```
INFO  [px4_init] PX4 SITL starting...
INFO  [mavlink] partner IP: 127.0.0.1
```

Leave this terminal running. Open a **new** terminal for the next steps.

---

## Step 4: Install QGroundControl on Windows (5 minutes)

QGroundControl (QGC) lets you see the simulated drone on a map and monitor its telemetry.

### 4.1 Download
1. Go to https://qgroundcontrol.com/downloads/
2. Download the Windows version
3. Extract and run `QGroundControl.exe`

### 4.2 Connect to the simulation
QGC should **automatically discover** the PX4 SITL instance.

If it doesn't connect automatically:
1. Click **Application Settings** (Q icon, top left)
2. Go to **Comm Links**
3. Click **Add**
4. Set: Type=`UDP`, Listening Port=`14550`
5. Click **Connect**

You should now see the drone on the map at Bangalore coordinates (12.97°N, 77.59°E).

---

## Step 5: Run GarudaOne DroneOS (1 minute)

### 5.1 Install Python dependencies (first time only)
From **Windows PowerShell** or **Command Prompt**:
```powershell
cd D:\Aatonovaz\DroneOS
pip install -r requirements.txt
```

### 5.2 Run in simulation mode
```powershell
# PowerShell
$env:GARUDA_MODE='simulation'
python -m garuda.main
```

**Or using the Makefile:**
```powershell
make run-sim
```

**Or Command Prompt:**
```cmd
set GARUDA_MODE=simulation
python -m garuda.main
```

### 5.3 What you'll see
The DroneOS boot sequence will show:
```
=== Step 5/7: Connecting to PX4 ===
Connecting to PX4: udp://localhost:14540
Connection mode: sitl
Waiting for drone heartbeat (15s timeout)...
[OK] Connected to PX4 flight controller
  Mode: sitl
```

If PX4 SITL is **running**: Real flight dynamics! ✅
If PX4 SITL is **NOT running**: Falls back to stub telemetry (fake data) ✅

---

## Step 6: Test Voice Commands

With DroneOS running, you can test the full voice → flight pipeline.

### 6.1 Active voice mode (requires microphone)
Install voice dependencies:
```powershell
pip install sounddevice faster-whisper openwakeword soundfile
```

Say: **"Garuda, take off"** → the simulated drone will take off to 3m.

### 6.2 Passive mode (no microphone — for testing)
If no microphone is available, the system runs in passive mode. You can inject commands by calling `process_audio_command()` directly in a test script.

See `scripts/test_voice.py` for an example.

---

## Configuration

### Switch between SITL and Hardware

Edit `config/simulation.yaml`:

```yaml
px4_sitl:
  enabled: true    # true = connect to PX4 SITL
                   # false = use stub telemetry only
```

For **real hardware** on the RPi5:
```bash
# No config change needed — just don't set GARUDA_MODE
python -m garuda.main
# Automatically uses UART serial connection
```

### Change the SITL drone model
```bash
# Inside WSL2 — different drone models:
cd ../PX4-Autopilot
make px4_sitl_rtps gazebo_x500         # Quadcopter (default)
make px4_sitl_rtps gazebo_typhoon_h480  # Hex with gimbal (closest to GarudaOne)
make px4_sitl_rtps gazebo_iris          # Standard PX4 quad
```

### Change home location
Edit `config/simulation.yaml`:
```yaml
simulation:
  home_position:
    latitude_deg: 12.9716    # Bangalore
    longitude_deg: 77.5946
    altitude_m: 920.0
```
And pass the same coords to PX4 SITL via environment variables when launching.

---

## Troubleshooting

### "MAVSDK can't connect to PX4 SITL"

**Cause:** WSL2 port forwarding issue or firewall.

**Fix 1:** Check WSL2 is running and PX4 is listening:
```bash
# In WSL2
ss -ulnp | grep 14540
```

**Fix 2:** Allow UDP through Windows Firewall:
```powershell
# Run as Administrator
New-NetFirewallRule -DisplayName "PX4 SITL UDP" -Direction Inbound -Protocol UDP -LocalPort 14540,14550 -Action Allow
```

**Fix 3:** Use explicit WSL IP:
```bash
# In WSL2, get the IP
hostname -I
# Then in Windows, update config/simulation.yaml:
# connection_url: "udp://172.x.x.x:14540"
```

### "Gazebo window doesn't appear"

**Cause:** No display server in WSL2.

**Fix:** Install WSLg (Windows 11) or use headless mode:
```bash
# Headless mode (no GUI, but SITL still works)
cd ../PX4-Autopilot
HEADLESS=1 make px4_sitl_rtps gazebo_x500
```

### "PX4 build fails with cmake errors"

**Fix:**
```bash
cd ../PX4-Autopilot
git submodule update --init --recursive
make distclean
make px4_sitl_rtps
```

### "Drone won't arm in SITL"

PX4 has safety checks. In the PX4 console, type:
```
commander arm
```
If it fails, check:
```
commander status
```
Common issue: GPS not locked yet. Wait 30 seconds after boot.

To bypass all safety checks (SITL only):
```
param set COM_ARM_WO_GPS 1
commander arm
```

### "Battery dies instantly in SITL"

Edit `config/simulation.yaml`:
```yaml
simulation:
  battery:
    drain_rate_percent_per_second: 0.001  # Much slower drain
```

---

## Architecture: How the Connection Works

```
Windows Python (MAVSDK)
    │
    │ udp://localhost:14540
    │
    ▼
WSL2 Network Bridge (auto port-forward)
    │
    │ udp://localhost:14540
    │
    ▼
PX4 SITL (listening on :14540)
    │
    │ Internal shared memory
    │
    ▼
Gazebo Simulator (3D physics, sensors)
```

**Key insight:** PX4 SITL is the **exact same firmware** that runs on the MicoAir H743 flight controller. The only difference is that motor outputs go to Gazebo instead of real ESCs. This means:
- If your code works in SITL, it works on the real drone
- The OFFBOARD mode, velocity commands, and safety logic are identical
- You're testing real PX4 behavior, not a simplified approximation

---

## File Reference

| File | Purpose |
|------|---------|
| `scripts/setup_sitl.sh` | Automated PX4 SITL setup (run in WSL2) |
| `scripts/launch_sitl.sh` | Launch PX4 SITL + Gazebo |
| `config/simulation.yaml` | SITL connection settings, telemetry rates |
| `garuda/flight/mavlink_bridge.py` | MAVSDK connection logic |
| `garuda/core/config.py` | Config loader (reads simulation.yaml) |

---

## Next Steps

Once SITL is working:

1. **Download AI models:** `python scripts/download_models.py`
2. **Test detection:** `python scripts/test_detector.py`
3. **Test voice:** `python scripts/test_voice.py`
4. **Test LLM:** `python scripts/test_llm.py`
5. **Run full system:** `GARUDA_MODE=simulation python -m garuda.main`
6. **Watch the drone fly** in Gazebo as DroneOS controls it! 🚁
