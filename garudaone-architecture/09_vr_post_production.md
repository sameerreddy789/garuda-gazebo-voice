# Layer 4: Desktop VR Post-Production (Concept)

## The Limitation of Edge Hardware
GarudaOne operates on a strict power and weight budget. Mounting a dedicated 360° VR camera (like an Insta360) adds significant aerodynamic drag, reduces flight time, and disrupts the drone's center of gravity. Furthermore, the onboard Raspberry Pi 5 does not have the compute required to run heavy video diffusion models. 

Therefore, GarudaOne relies on a single forward-facing rectilinear (flat) camera for both perception and cinematography.

## The Solution: AI-Powered Outpainting
Inspired by the **VR-360-Outpaint (LTX2.3 IC-LoRA)** model architecture, GarudaOne offloads VR 360 generation entirely to a **Desktop Companion App** running in post-production. 

Instead of capturing true 360° video in the air, the drone captures standard 16:9 4K flat footage. After the flight, this footage is passed through an automated AI pipeline on a powerful desktop GPU to mathematically and generatively expand the footage into a full 360° equirectangular sphere.

## Pipeline Architecture

```
[ Drone (Edge) ]
   1. Captures standard flat video during tracking/orbiting missions.
   2. Logs precise pitch/roll/yaw (IMU data) and camera FOV.
         |
    (SD Card Transfer)
         ↓
[ Desktop Companion App (Host GPU) ]
   3. Geometry Node: 
      Applies an inverse gnomonic projection using the drone's FOV and IMU data.
      Maps the flat video onto the exact angular position of a blank equirectangular canvas.
         ↓
   4. Diffusion Node:
      Passes the projected canvas to a Video Diffusion Model (e.g., LTX-2.3-22B with VR-360-Outpaint IC-LoRA).
      The model, running via ComfyUI backend, outpaints the missing pixels.
         ↓
   5. Output:
      A seamless, full 360° spherical cinematic drone shot.
```

## Impact on Flight Control
By deferring 360° generation to post-production, the drone's cinematic flight planner (the CfC LNN) can operate differently when recording "Virtual VR" shots:
- **Reduced Panning/Tilting:** VR viewers experience motion sickness from aggressive camera movements. When "VR Mode" is activated, the drone will lock its gimbal and rely purely on smooth translation (moving forward/backward) rather than panning.
- **Center-Framing Priority:** The drone will keep the subject strictly in the center of the FOV to provide the cleanest "seed" data for the inverse gnomonic projection.
