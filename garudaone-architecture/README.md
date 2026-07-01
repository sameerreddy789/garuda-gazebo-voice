# GarudaOne Architecture Documentation

Technical architecture, validated decisions, and strategic positioning for the GarudaOne autonomous cinematography drone.

## Documents

| # | Document | Description |
|---|---|---|
| 00 | [Project Brief](00_project_brief.md) | What GarudaOne is, the problem, the solution, and every detail about the project |
| 01 | [Architecture Overview](01_architecture_overview.md) | 3-Layer Liquid AI architecture (LFM + LNN + PX4) |
| 02 | [Software Stack](02_software_stack.md) | All optimized software components with benchmarks |
| 03 | [Hardware BOM](03_hardware_bom.md) | Prototype costs + production estimates |
| 04 | [Obstacle Navigation](04_obstacle_navigation.md) | Cinematic "seamless flow" obstacle strategy |
| 05 | [Simulation Strategy](05_simulation_strategy.md) | Isaac Sim + Pegasus + PX4 SITL pipeline |
| 06 | [OS & Communications](06_os_and_comms.md) | Ubuntu + MAVSDK + PX4 OFFBOARD architecture |
| 07 | [Market Positioning](07_market_positioning.md) | Pricing, competition, and go-to-market |
| 08 | [Validation Report](08_validation_report.md) | Stress-tested assumptions and corrections |

## Key Decisions
- **Flight Controller:** PX4 (BSD license — proprietary modifications allowed)
- **Communication:** MAVSDK-Python (PX4's official async SDK)
- **AI Compute:** Raspberry Pi 5 (CPU-only, no GPU required)
- **Vision:** PicoDet-S @ 45–55 FPS (replaced YOLOv8n)
- **Brain:** LFM-2.5-230M @ 42 tok/s + Needle 26M @ 1,200 tok/s
- **Control:** CfC Liquid Neural Network (19–50 neurons, Imitation Learning)
- **Spatial:** SVO2 visual odometry (replaced ORB-SLAM3)
