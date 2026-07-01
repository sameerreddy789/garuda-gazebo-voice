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
