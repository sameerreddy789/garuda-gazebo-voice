# GarudaOne: Optimized Software Stack

All components stress-tested and validated. Each was evaluated against alternatives for compute efficiency on Raspberry Pi 5 (CPU-only).

---

## Object Detection
| | |
|---|---|
| **Component** | PicoDet-S |
| **Framework** | ncnn (Tencent, ARM-optimized) |
| **Quantization** | INT8 |
| **Input Resolution** | 320×320 |
| **FPS on RPi 5 CPU** | 45–55 FPS |
| **Model Size** | ~4 MB |
| **Why chosen** | 3–4× faster than YOLOv8n on ARM. Sufficient accuracy for single-subject bounding box tracking against landscape backgrounds. |
| **Replaced** | YOLOv8n (10–15 FPS) |

---

## Agentic Brain (Language)
| | |
|---|---|
| **Component** | LFM-2.5-230M |
| **Framework** | llama.cpp (GGUF format) |
| **Speed** | 42 tokens/sec decode |
| **Context Window** | 32K tokens |
| **RAM Usage** | <300 MB |
| **Why chosen** | Best-in-class agentic tool-calling at this parameter count. No alternative matches speed + context window on ARM CPU. |

---

## Fast Tool Router
| | |
|---|---|
| **Component** | Needle 26M |
| **Size** | 14 MB (INT4) |
| **Speed** | 1,200 tokens/sec |
| **Why chosen** | Ultra-fast single-shot tool routing. Handles simple commands ("Stop", "Land") without invoking LFM. Outperforms models 25× its size at function selection. |
| **Added** | New component (not in original plan) |

---

## Visual Odometry / Spatial Awareness
| | |
|---|---|
| **Component** | SVO2 (Semi-direct Visual Odometry) or ARM-VO |
| **Why chosen** | SVO2 designed for micro-aerial vehicles at ETH Zurich. ARM-VO uses NEON SIMD for RPi optimization. Both use ~50% less CPU than ORB-SLAM3. |
| **Replaced** | ORB-SLAM3 (too heavy for concurrent workloads on Pi 5 CPU) |

---

## Cinematic Flow Controller
| | |
|---|---|
| **Component** | CfC LNN (Closed-form Continuous-time) |
| **Library** | `ncps` (pip install ncps) — Apache-2.0 |
| **Neurons** | 19–50 |
| **Training** | Imitation Learning (record manual flights, learn cinematic stick movements) |
| **Why chosen** | MIT CSAIL proven. Adapts continuously to wind/disturbances. Maps bounding box + depth → smooth velocity commands. |

---

## Path Smoothing
| | |
|---|---|
| **Component** | Cubic B-spline smoother |
| **Why chosen** | Guarantees continuous-curvature trajectories. Zero jerk. Viewer never sees obstacle maneuvers. |

---

## Voice Pipeline
| Component | Tool | Size | Notes |
|---|---|---|---|
| Wake Word | openWakeWord | ~3 MB | 3–8% CPU. Custom wake word ("Garuda"). |
| Speech-to-Text | Moonshine Tiny or whisper.cpp | ~27 MB | Faster + more accurate than Whisper-tiny at edge. |
| Text-to-Speech | Piper TTS | ~20 MB | Natural voice. "Starting orbit mode." |

---

## Communication Layer
| | |
|---|---|
| **Protocol** | MAVLink v2 |
| **Library** | **MAVSDK-Python** (PX4 official, async/await native) |
| **Transport** | UART serial |
| **Key API** | `offboard.set_velocity_ned()` |
| **Why chosen** | Modern, async Python SDK. Cleaner than raw PyMAVLink. Built specifically for PX4 OFFBOARD mode. |
| **Changed from** | PyMAVLink (still works, but MAVSDK is more Pythonic for PX4) |

---

## Flight Controller
| | |
|---|---|
| **Autopilot** | **PX4** (BSD 3-Clause license) |
| **RTOS** | NuttX |
| **Hardware** | MicoAir H743 AIO 35A AM32 |
| **Mode** | OFFBOARD |
| **Ground Station** | QGroundControl |
| **Changed from** | ArduPilot (GPLv3 — requires open-sourcing modifications) |

---

## Companion Computer OS
| | |
|---|---|
| **OS** | Ubuntu 24.04 LTS (64-bit ARM) |
| **Hardware** | Raspberry Pi 5 (8GB RAM) |
| **Cooling** | Official RPi 5 Active Cooler |
| **Storage** | SanDisk Ultra 64GB microSDXC |
