# GarudaOne — Betaflight → PX4 Migration Guide

## Overview

Your MicoAir H743 AIO is currently running **Betaflight 2025.12.5-alpha**.
The DroneOS companion computer software requires **PX4 Autopilot** for
OFFBOARD mode (velocity-controlled autonomous flight).

> ⚠️ **This is a one-way operation during the flash.** Back up your
> Betaflight settings first (CLI `diff all` → save to file).

---

## Step 1: Backup Betaflight Config

1. Connect FC to computer via USB
2. Open Betaflight Configurator
3. Go to **CLI** tab
4. Type `diff all` and press Enter
5. Copy ALL output to a text file: `betaflight_backup.txt`
6. Save the file in `config/betaflight_backup.txt`

Your PID values are already captured in `config/drone.yaml`.

---

## Step 2: Download PX4 Firmware

The MicoAir H743 AIO uses the **STM32H743** MCU. PX4 supports this board.

### Option A: Pre-built Firmware (Recommended)
```bash
# Download from PX4 releases
wget https://github.com/PX4/PX4-Autopilot/releases/latest/download/micoair743_default.px4
```

### Option B: Build from Source
```bash
git clone https://github.com/PX4/PX4-Autopilot.git --recursive
cd PX4-Autopilot
make micoair743_default
# Output: build/micoair743_default/micoair743_default.px4
```

---

## Step 3: Flash PX4

### Using QGroundControl (Recommended)
1. Download [QGroundControl](https://docs.qgroundcontrol.com/master/en/getting_started/download_and_install.html)
2. Open QGC → Vehicle Setup → Firmware
3. Connect FC via USB (QGC will detect it)
4. Select **PX4 Pro** as firmware
5. Choose **Custom firmware file** → select the .px4 file
6. Click Flash

### Using command line
```bash
# Install px4-upload tool
pip install pyserial
# Flash (FC in DFU mode: hold BOOT button while connecting USB)
python -m px4.upload --port /dev/ttyACM0 micoair743_default.px4
```

---

## Step 4: PX4 Initial Configuration

After flashing, configure via QGroundControl:

### Airframe
- Vehicle type: **Quadrotor**
- Frame: **Generic Quadcopter** (or closest match to your frame)

### Sensors
- Calibrate: **Accelerometer**, **Gyroscope**, **Compass** (Level calibration)
- Board alignment: Roll 180°, Pitch 0°, Yaw 135° (matches your Betaflight config)

### Radio
- Protocol: **CRSF** (for ELRS receiver)
- Calibrate sticks

### Flight Modes (Channel mapping)
- Position mode (GPS hold)
- Altitude mode
- Manual/Stabilized mode
- Kill switch (CRITICAL for safety)
- OFFBOARD mode switch

### Battery
- Cell count: 3S
- Full voltage: 4.2V per cell
- Empty voltage: 3.3V per cell
- Voltage divider: Calibrate with multimeter

### Companion Computer Link
```
MAV_1_CONFIG = TELEM 2 (or whichever UART connects to RPi5)
MAV_1_MODE = Onboard
SER_TEL2_BAUD = 921600
MAV_COMP_ID = 1
```

---

## Step 5: Enable OFFBOARD Mode

Set these PX4 parameters for companion computer OFFBOARD control:

```
# OFFBOARD mode settings
COM_OBL_ACT = 0        # Action on OFFBOARD loss: Land
COM_OBL_RC_ACT = 0     # RC failsafe in OFFBOARD: Position mode
COM_OF_LOSS_T = 3.0     # OFFBOARD loss timeout (seconds)
COM_RC_OVERRIDE = 1     # Allow RC override during OFFBOARD

# Companion computer
MAV_COMP_ID = 1
MAV_SYS_ID = 1
MAV_TYPE = 2            # Quadrotor

# Safety
COM_ARM_WO_GPS = 0      # Require GPS for arming
COM_DISARM_LAND = 3     # Auto-disarm after landing (3 seconds)
```

---

## Step 6: PID Tuning

PX4 uses a different PID structure than Betaflight. You'll need to re-tune.

### Quick Auto-Tune (Recommended)
1. Fly in manual/stabilized mode
2. Switch to Position mode
3. Trigger MC_AT_START via QGC parameters
4. The drone will oscillate and auto-tune itself
5. Land and save parameters

### Manual Starting Point
Based on your Betaflight PIDs (Roll P=45, I=80, D=30), suggested PX4 starting values:
```
MC_ROLLRATE_P = 0.15
MC_ROLLRATE_I = 0.20
MC_ROLLRATE_D = 0.003
MC_PITCHRATE_P = 0.15
MC_PITCHRATE_I = 0.20
MC_PITCHRATE_D = 0.003
MC_YAWRATE_P = 0.20
MC_YAWRATE_I = 0.10
```

> These are STARTING POINTS only. Real PID values must be tuned by flying.

---

## Step 7: Test OFFBOARD from RPi5

After PX4 is configured:

```bash
# On RPi5
source ~/.venvs/garuda/bin/activate

# Quick test: connect and read telemetry
python -c "
import asyncio
from mavsdk import System

async def test():
    drone = System()
    await drone.connect(system_address='serial:///dev/ttyAMA0:921600')
    async for state in drone.core.connection_state():
        if state.is_connected:
            print('Connected to PX4!')
            break
    async for battery in drone.telemetry.battery():
        print(f'Battery: {battery.remaining_percent*100:.0f}%')
        break

asyncio.run(test())
"
```

If you see `Connected to PX4!` and battery info, the link is working.

---

## Troubleshooting

| Issue | Solution |
|-------|----------|
| QGC doesn't detect FC | Hold BOOT button while connecting USB (DFU mode) |
| No serial on RPi5 | Check `ls /dev/ttyAMA0`, run setup_rpi5.sh |
| OFFBOARD rejected | Must send setpoints BEFORE switching to OFFBOARD mode |
| Motors don't spin | Check ESC protocol in QGC (should be DShot300) |
| GPS not working | Check wiring, ensure Foxeer M10Q is on correct UART |
| Compass interference | Do outdoor calibration, away from motors |
