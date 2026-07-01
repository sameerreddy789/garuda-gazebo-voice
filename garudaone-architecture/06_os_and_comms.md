# GarudaOne: OS & Communication Architecture

## Flight Controller (Layer 3)
| | |
|---|---|
| **OS** | NuttX (Real-Time Operating System) |
| **Autopilot** | PX4 |
| **License** | BSD 3-Clause (proprietary modifications allowed) |
| **Loop Rate** | 400Hz+ |
| **Why NuttX** | Hard real-time guarantees. Motor response within 2ms. |

## Companion Computer (Layers 1 & 2)
| | |
|---|---|
| **OS** | Ubuntu 24.04 LTS (64-bit ARM) |
| **Hardware** | Raspberry Pi 5 (8GB RAM) |
| **Why Ubuntu** | Required for Python, AI model runtimes (llama.cpp, ncnn), OpenCV, MAVSDK |
| **Why NOT RTOS** | Cannot run heavy AI models on an RTOS |
| **Why NOT ROS 2** | Overkill for a single-purpose consumer product. Adds boot time, CPU overhead, and complexity. DJI and Skydio don't run ROS 2 internally on production consumer drones. |

## Communication Bridge
| | |
|---|---|
| **Protocol** | MAVLink v2 |
| **Library** | **MAVSDK-Python** |
| **Why MAVSDK** | PX4's official SDK. Async/await native. Cleaner API than raw PyMAVLink. Built specifically for PX4 OFFBOARD mode. |
| **Transport** | UART serial (RPi 5 GPIO TX/RX → MicoAir TELEM port) |
| **Baud Rate** | 921600 (standard for PX4 companion links) |
| **Key Commands** | `offboard.set_velocity_ned()`, `telemetry.position()`, `action.arm()` |

## Why Not PyMAVLink?
PyMAVLink still works perfectly with PX4. However, MAVSDK-Python provides:
- Higher-level abstractions (no manual message packing)
- Built-in connection management and heartbeating
- Native async/await for non-blocking I/O
- Official PX4 support and documentation

PyMAVLink remains available as a fallback for any low-level MAVLink message manipulation if needed.
