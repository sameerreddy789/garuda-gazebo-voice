# GarudaOne: Hardware Bill of Materials

## Prototype BOM (Current)

| # | Component | Qty | Unit Cost (₹) | Total (₹) | Purpose |
|---|---|---|---|---|---|
| 1 | MicoAir H743 AIO 35A AM32 | 1 | ₹6,299 | ₹6,299 | Flight Controller & ESC (PX4 Base) |
| 2 | Flywoo FlyLens 85 Lite Frame Kit | 1 | ₹2,214 | ₹2,214 | Sub-250g Experimental Frame |
| 3 | QPT 1404-4500KV Brushless Motors | 4 | ₹1,400 | ₹5,600 | Core Propulsion System |
| 4 | Zerodrag Nexus ELRS 2.4GHz Receiver | 1 | ₹1,549 | ₹1,549 | Low-Latency Telemetry/Radio Link |
| 5 | Foxeer M10Q GPS + Compass | 1 | ₹2,394 | ₹2,394 | GNSS Position Hold & Waypoint Nav |
| 6 | Radiomaster ELRS Pocket Radio | 1 | ₹6,000 | ₹6,000 | Ground Support Transmitter |
| 7 | Gemfan Hurricane 2023 Tri-Blade Props | 4 pr | ₹280 | ₹280 | Direct Thrust Generation |
| 8 | LAVA 3S 450mAh LiPo Battery | 2 | ₹3,342 | ₹3,342 | Flight Power Source |
| 9 | MicoAir Optical Flow Ranging Sensor | 1 | ₹4,420 | ₹4,420 | Indoor Altitude/Position Lock |
| 10 | Skydroid C10 Pro Three-Axis Gimbal Camera | 1 | ₹17,135 | ₹17,135 | Stabilized Imaging (reverse-engineered feed) |
| 11 | Heatshrink Tube Wire Insulation | 530pc | ₹322 | ₹322 | Electrical Isolation |
| 12 | RadioMaster 18650 3200mAh Battery | 1 | ₹1,899 | ₹1,899 | Ground Controller Power |
| 13 | HOTA T6 DC 300W Charger | 1 | ₹3,563 | ₹3,563 | LiPo Balance Charger |
| 14 | Raspberry Pi 5 (8GB RAM) | 1 | ₹9,618 | ₹9,618 | Companion Computer for AI |
| 15 | Official RPi 5 Active Cooler | 1 | ₹488 | ₹488 | Thermal Management |
| 16 | SanDisk Ultra 64GB microSDXC | 1 | ₹1,899 | ₹1,899 | OS & Model Storage |
| 17 | XT30 Pair Connectors | 1 pr | ₹59 | ₹59 | Power Routing |
| | **Base Hardware Cost** | | | **₹77,080** | |

### Financial Breakdown
| Item | Amount (₹) |
|---|---|
| Base Hardware Cost (Items 1–17) | ₹77,080 |
| Logistics / Taxes Buffer (5%) | ₹3,855 |
| Assembly & Tuning Charges | ₹5,000 |
| **FINAL BOM EXPENDITURE CAP** | **₹85,935** |

### Funding
- **Source:** SISFS (Startup India Seed Fund Scheme)
- **Amount:** ₹20,00,000
- **Structure:** Convertible Debenture (CCD)
- **Prototype spend:** ~₹90,000 (~4.5% of runway)

---

## Production BOM Estimate (10,000+ units)

| Component | Wholesale Cost |
|---|---|
| SoC (RK3588S or Ambarella CV52S, with integrated NPU) | ₹1,200–₹2,000 |
| Custom PCB (STM32 FC + SoC companion, single board) | ₹660–₹1,000 |
| True 4K Camera + Micro Gimbal (Sony IMX678) | ₹1,600–₹2,000 |
| 4× 1404 Motors (wholesale) | ₹1,000–₹1,600 |
| Frame (injection-molded plastic) + Battery | ₹660 |
| Sensors (GPS, Flow, TMF8828 ToF) | ₹400–₹800 |
| PCB assembly, QA, packaging | ₹1,000–₹1,500 |
| **Estimated Production BOM** | **₹8,300–₹10,000** |

### Target Retail Price: ₹49,999–₹54,999
### Gross Margin: ~80%
