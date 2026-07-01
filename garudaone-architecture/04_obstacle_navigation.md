# GarudaOne: Obstacle Navigation — "Seamless Flow"

The goal is not collision avoidance. The goal is invisible, cinematic flow around obstacles.

---

## Primary System: SVO2 (Camera-Based, Zero Additional Hardware)

SVO2 visual odometry naturally produces a sparse 3D depth map as it tracks features between frames. This handles 90% of real-world obstacles:
- Trees, buildings, cars, people, furniture, terrain — anything with visual texture
- Range: 10–20+ meters (limited by camera resolution and feature density)
- Cost: Free (already in the software stack)

## Secondary System: TMF8828 ToF (Optional, For the 10% Edge Cases)

For obstacles SVO2 cannot see (glass, white walls, thin poles):
- **Sensor:** TMF8828 multi-zone ToF
- **Resolution:** 8×8 grid (64 depth zones)
- **Range:** 5 meters (sufficient — these scenarios are always low-speed indoor/urban)
- **Refresh Rate:** 60Hz
- **Weight:** ~1 gram
- **Cost:** ~₹2,000
- **Interface:** I2C → RPi 5 GPIO
- Add only after real-world testing confirms the need.

## The Cinematic Flow Controller (CfC LNN)

Traditional obstacle avoidance: `if distance < 2m → STOP`. Ugly. Jerky.

GarudaOne approach: The CfC Liquid Neural Network is trained via Imitation Learning to **arc smoothly around obstacles** like a professional camera operator.

### Training Pipeline:
1. Pilot manually flies the drone through obstacles using Radiomaster ELRS
2. Record simultaneously: SVO2 depth map + PicoDet bounding box + pilot stick inputs
3. Train 19–50 neuron CfC network to map [depth + bbox] → [smooth velocity + gimbal angle]

### Output:
- **Drone velocity** → B-spline smoothed → MAVSDK → PX4 OFFBOARD mode
- **Gimbal angle** → Skydroid controller (counter-rotates to maintain subject framing)

## Why This Works

The 3-axis Skydroid gimbal is the secret weapon. When the drone body banks right to flow around a tree, the gimbal counter-rotates to keep the camera locked on the subject. The viewer sees a perfectly smooth dolly shot — zero evidence an obstacle was dodged.

## Sensor Coverage Matrix

| Scenario | Speed | Primary Sensor | Range | Reaction Time |
|---|---|---|---|---|
| Outdoor (trees, buildings) | 5–10 m/s | SVO2 (camera) | 10–20m | 2–4 sec ✅ |
| Indoor/urban (glass, walls) | 1–3 m/s | TMF8828 (ToF) | 5m | 1.5–5 sec ✅ |
