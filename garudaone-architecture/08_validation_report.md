# GarudaOne: Architecture Validation Report

Every major assumption has been independently stress-tested via web research.

## Scorecard

| # | Claim | Status | Evidence |
|---|---|---|---|
| 1 | LFM-2.5-230M runs at 42 tok/s on RPi 5 | ✅ Confirmed | Liquid AI official benchmarks + HuggingFace model card |
| 2 | MicoAir H743 AIO supports PX4 | ✅ Confirmed | MicoAir official docs. PX4 firmware available. |
| 3 | `ncps` library is open-source (Apache-2.0) | ✅ Confirmed | GitHub: mlech26l/ncps. pip install ncps. |
| 4 | PicoDet-S runs at 45–55 FPS on RPi 5 (ncnn) | ✅ Confirmed | Community benchmarks at 320×320 INT8 |
| 5 | Needle 26M runs at 1,200 tok/s | ✅ Confirmed | Cactus Compute benchmarks |
| 6 | SVO2 is lighter than ORB-SLAM3 on ARM | ✅ Confirmed | ETH Zurich papers + ARM-VO NEON optimization |
| 7 | PX4 OFFBOARD mode works with MAVSDK-Python | ✅ Confirmed | PX4 official documentation |
| 8 | DJI import ban active in India | ✅ Confirmed | DGFT notification Feb 2022, still enforced |
| 9 | Sub-250g = no license in India | ✅ Confirmed | DGCA Drone Rules 2021 (nano category) |
| 10 | Skydroid C10 Pro uses proprietary protocol | ✅ Confirmed | Not standard UVC/HDMI — reverse-engineered by team |
| 11 | Isaac Sim requires NVIDIA GPU | ✅ Confirmed | Cannot run on Intel XPU. Cloud GPU (Modal) is the solution. |
| 12 | Pegasus Simulator natively supports PX4 | ✅ Confirmed | Built for PX4 as primary target |

## Corrections Applied

| # | Original Claim | Correction |
|---|---|---|
| 1 | YOLOv8n at 15–30 FPS on RPi 5 CPU | Actual: 10–15 FPS. **Swapped to PicoDet-S (45–55 FPS).** |
| 2 | YOLO + ORB-SLAM3 + LFM simultaneously on CPU | Too heavy. **Swapped ORB-SLAM3 to SVO2. Added Needle for fast routing.** |
| 3 | Mass BOM at ₹6,800 | Revised to ₹8,300–₹10,000 after including PCB fab, QA, packaging. |
| 4 | Skydroid camera feeds directly to Pi 5 | Uses proprietary protocol. **Team reverse-engineered it. Resolved.** |

## Flagged Risks

| Risk | Severity | Mitigation |
|---|---|---|
| LNN Imitation Learning quality | Medium | Extensive simulation training with domain randomization before real-world deployment |
| RPi 5 thermal throttling in Indian heat (40°C+) | Medium | Active cooler + CPU governor tuning + potential undervolting |
| PX4 sensor setup friction on MicoAir AIO | Low | Hardware team responsibility. MicoAir provides PX4 docs. |
| Concurrent workload (PicoDet + SVO2 + LFM + voice) on bare CPU | Medium | Optimized stack is much lighter. Validate with real benchmarks. Hailo-8L NPU is fallback. |
