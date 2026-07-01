# GarudaOne — The Complete Project Brief

---

## What Is GarudaOne?

GarudaOne is an autonomous, voice-controlled, AI-powered cinematography drone designed and engineered in India. It is built to be a content creator's invisible camera crew — a sub-250g flying machine that listens to natural voice commands, autonomously tracks subjects, gracefully navigates obstacles, and captures DJI-level 4K cinematic footage without requiring any piloting skill.

The user throws it in the air, says "Follow me, stay wide," and the drone does the rest.

---

## The Problem

Content creators — YouTubers, vloggers, wedding videographers, travel creators — need cinematic aerial footage. Today, their options are:

1. **DJI drones:** The gold standard in camera quality, but **banned from import in India** since Feb 2022. Available only through grey markets at ₹90K–₹1.2L+ with zero warranty and legal risk.
2. **Indian drone brands (IZI etc.):** Legally available, but most advertise "4K" while using cheap sensors that produce muddy, over-processed footage. They require manual piloting via remote controllers.
3. **HoverAir X1 (and similar):** Self-flying, but limited intelligence — basic pre-programmed flight paths, no voice control, no real obstacle awareness, and not available through official channels in India.

No product on the market combines true autonomous intelligence, voice control, cinematic camera quality, and legal availability in India — at a price point creators can justify.

---

## The Solution

GarudaOne is a sub-250g (no license required in India) autonomous drone that combines:

- **A voice-controlled AI brain** powered by a Liquid Foundation Model running locally on-device
- **Real-time subject tracking** at 45–55 FPS using optimized edge vision models
- **Cinematic obstacle flow** — the drone doesn't "avoid" obstacles, it flows around them like a professional camera operator
- **True 4K footage** from a 3-axis gimbal-stabilized camera with a Sony IMX678 sensor
- **Zero piloting required** — the user interacts through natural language, not joysticks

---

## The Core Innovation: 3-Layer Liquid AI Architecture

GarudaOne does not use a GPU. It does not use cloud processing. Everything runs locally on a Raspberry Pi 5 (8GB) using a novel 3-layer architecture:

### Layer 1: The Cognitive Brain
- **LFM-2.5-230M** — A 230-million parameter Liquid Foundation Model by Liquid AI, running at 42 tokens/second via `llama.cpp`. It understands complex natural language commands ("Film me from the left while I walk toward the bridge"), maintains mission context across a 32K token window, and outputs structured tool calls.
- **Needle 26M** — A 14MB ultra-fast tool router running at 1,200 tokens/second. Handles simple commands ("Stop", "Land", "Come back") instantly without invoking the heavier LFM.

### Layer 2: Perception & Continuous Control
- **PicoDet-S** — A mobile-optimized object detector running at 45–55 FPS on the Pi 5's ARM CPU via the `ncnn` inference engine. Detects and tracks the subject's bounding box.
- **SVO2 / ARM-VO** — Semi-direct visual odometry providing spatial awareness, sparse depth mapping, and drone pose estimation. Built for micro-aerial vehicles. Uses ARM NEON SIMD for hardware-accelerated performance.
- **CfC Liquid Neural Network** — A 19–50 neuron continuous-time neural controller (from MIT CSAIL's `ncps` library). Trained via imitation learning to output smooth, cinematic velocity commands. It doesn't just avoid obstacles — it arcs around them gracefully while the gimbal counter-rotates to maintain subject framing. The viewer never sees the maneuver.

### Layer 3: Hard Real-Time Flight
- **PX4 Autopilot** — Running on the MicoAir H743 AIO flight controller under the NuttX RTOS. Handles 400Hz PID motor control, sensor fusion (GPS + IMU + optical flow + barometer), and safety failsafes. If the AI layer crashes, PX4 automatically returns home or lands safely.
- **Communication:** MAVSDK-Python sends velocity setpoints from the Pi 5 to PX4's OFFBOARD mode over UART serial using MAVLink v2.

### Why This Matters
This architecture achieves GPU-level autonomous intelligence on a CPU-only power budget. No Nvidia Jetson. No cloud dependency. No heavy GPU drawing battery. The result is a lighter, cheaper, longer-flying drone that thinks for itself.

---

## Voice Interface

The drone has a complete, 100% offline voice pipeline:

1. **Wake Word Detection:** `openWakeWord` — listens for "Garuda" at 3–8% CPU usage
2. **Speech-to-Text:** `Moonshine Tiny` or `whisper.cpp` — converts spoken commands to text (27MB model, runs locally)
3. **Language Understanding:** LFM-2.5-230M parses intent and maps it to a tool call
4. **Tool Routing:** Needle 26M instantly dispatches to the correct function
5. **Text-to-Speech:** `Piper TTS` — the drone talks back ("Starting orbit mode", "Battery low, heading home")

No audio ever leaves the device. Full privacy.

---

## Obstacle Navigation

GarudaOne does not "avoid" obstacles. It flows around them.

- **Primary sensor:** The Skydroid camera feed + SVO2 visual odometry provides 3D spatial awareness of textured obstacles (trees, buildings, people, cars) at 10–20m range.
- **Secondary sensor (optional):** TMF8828 multi-zone ToF (8×8 grid, 5m range, 1 gram) for edge cases like glass, white walls, and thin poles. Added only after real-world testing proves the need.
- **Controller:** The CfC Liquid Neural Network outputs smooth velocity vectors trained from human expert pilot demonstrations. A cubic B-spline smoother guarantees continuous-curvature trajectories.
- **Secret weapon:** The 3-axis gimbal counter-rotates during maneuvers. When the drone banks right around a tree, the camera stays locked on the subject. The viewer sees a perfect shot.

---

## Hardware

### Prototype (Current)
| Component | Purpose | Cost |
|---|---|---|
| MicoAir H743 AIO 35A AM32 | Flight Controller + ESC (PX4) | ₹6,299 |
| Flywoo FlyLens 85 Lite Frame | Sub-250g carbon fiber frame | ₹2,214 |
| QPT 1404-4500KV Motors (×4) | Propulsion | ₹5,600 |
| Skydroid C10 Pro 3-Axis Gimbal Camera | Stabilized imaging (reverse-engineered feed) | ₹17,135 |
| Raspberry Pi 5 (8GB) | AI companion computer | ₹9,618 |
| Foxeer M10Q GPS + Compass | GNSS navigation | ₹2,394 |
| MicoAir Optical Flow + Ranging Sensor | Indoor position/altitude hold | ₹4,420 |
| + Batteries, props, receiver, cooling, misc | Supporting hardware | ~₹20,000 |
| **Total Prototype BOM** | | **~₹90,000** |

### Production Target (10,000+ units)
| | |
|---|---|
| **Estimated BOM** | ₹8,300–₹10,000 per unit |
| **Key change** | Single custom PCB with SoC (RK3588S or Ambarella CV52S) integrating CPU + NPU + FC MCU |
| **Camera upgrade** | True 4K with Sony IMX678 sensor |
| **Frame** | Injection-molded plastic (replaces carbon fiber) |

---

## Software Stack (Fully Validated)

| Component | Tool | Performance |
|---|---|---|
| Object Detection | PicoDet-S (ncnn, INT8) | 45–55 FPS @ 320×320 |
| Language Brain | LFM-2.5-230M (llama.cpp) | 42 tok/s |
| Tool Router | Needle 26M (INT4) | 1,200 tok/s |
| Visual Odometry | SVO2 / ARM-VO | Lightweight, ARM NEON optimized |
| Flight Controller | CfC LNN (ncps, 19–50 neurons) | Near-zero latency |
| Path Smoothing | Cubic B-spline | Guarantees smooth trajectories |
| Wake Word | openWakeWord | 3–8% CPU |
| Speech-to-Text | Moonshine Tiny / whisper.cpp | 27 MB, edge-optimized |
| Text-to-Speech | Piper TTS | Near-instant |
| FC Communication | MAVSDK-Python | PX4 OFFBOARD, async |
| Autopilot | PX4 (NuttX RTOS, BSD license) | 400Hz control loops |
| Companion OS | Ubuntu 24.04 LTS (ARM) | Standard Linux |

---

## Simulation

- **Engine:** NVIDIA Isaac Sim (Omniverse, photorealistic RTX ray-tracing)
- **Drone Plugin:** Pegasus Simulator (native PX4 SITL support)
- **Host:** Cloud GPU via Modal (A10G/A100 instances)
- **Client:** Omniverse Streaming Client on Intel Core Ultra 7 laptop
- **Sim-to-Real:** Same Python code controls both the simulated and real drone. Change one connection string.
- **Domain Randomization:** Wind, sensor noise, lighting, textures — all randomized to close the sim-to-real gap.

---

## Market & Business

### Target Market
- **Primary:** Indian content creators (YouTube, Instagram, wedding/event videography)
- **Secondary:** Global creator market (US, EU, SEA expansion)

### Competitive Landscape
| Competitor | Price | Status in India | GarudaOne Advantage |
|---|---|---|---|
| DJI Mini series | ₹90K–₹1.2L (grey) | Banned import, no warranty | Half the price, legal, AI brain |
| IZI drones | ₹32K–₹70K | Available | True 4K sensor, autonomous AI, voice control |
| HoverAir X1 | ~₹29K | Not officially available | On-device LFM, obstacle flow, voice commands |

### Pricing
- **Target retail:** ₹49,999–₹54,999
- **Production BOM:** ₹8,300–₹10,000
- **Gross margin:** ~80%

### Regulatory Advantage
- Sub-250g = **Nano category** under DGCA Drone Rules 2021
- No Unique Identification Number (UIN) required
- No Remote Pilot Certificate (license) required
- No mandatory insurance
- No Type Certification required
- Made in India = full domestic warranty + support

---

## Funding

| | |
|---|---|
| **Source** | SISFS (Startup India Seed Fund Scheme) |
| **Amount** | ₹20,00,000 |
| **Structure** | Convertible Debenture (CCD) |
| **Dilution** | Zero (CCD converts at next priced round) |
| **Prototype spend** | ~₹90,000 (4.5% of total) |
| **Remaining runway** | ~₹19,10,000 |

### Go-to-Market Roadmap
| Phase | Timeline | Milestone |
|---|---|---|
| Prototype + Demo | Months 1–4 | Autonomous tracking + voice commands working |
| Demo Video + Accelerators | Months 4–6 | Apply to T-Hub, IIT incubators, Nasscom DeepTech |
| Seed Round | Months 6–9 | Raise ₹50L–1Cr. CCD converts. |
| Production + Ship | Months 9–14 | First batch manufactured and shipped. Revenue begins. |

---

## The Philosophy

The tech stack is not the product. The "aha moment" is the product.

The Liquid Neural Networks, the Foundation Models, the PX4 autopilot — these are all scaffolding. They will be replaced by better models and cheaper chips in 2–3 years. What won't change is the feeling a creator gets when they throw a drone in the air, say "Follow me," and it produces footage that looks like a Hollywood camera crew filmed it.

GarudaOne is not a drone company. It is an experience company that happens to use drones.
