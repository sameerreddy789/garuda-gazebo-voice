"""Generate GARUDA HackFusion 2026 pitch deck as .pptx"""

from pptx import Presentation
from pptx.util import Inches, Pt, Emu
from pptx.dml.color import RGBColor
from pptx.enum.text import PP_ALIGN, MSO_ANCHOR
from pptx.enum.shapes import MSO_SHAPE

# ── Colors ──
WHITE = RGBColor(0xFF, 0xFF, 0xFF)
BG = RGBColor(0xF7, 0xF8, 0xFA)
T1 = RGBColor(0x1A, 0x1A, 0x2E)
T2 = RGBColor(0x55, 0x57, 0x70)
T3 = RGBColor(0x8B, 0x8D, 0xA3)
BLUE = RGBColor(0x25, 0x63, 0xEB)
BLU_L = RGBColor(0xEF, 0xF4, 0xFF)
RED = RGBColor(0xDC, 0x26, 0x26)
RED_L = RGBColor(0xFE, 0xF2, 0xF2)
GRN = RGBColor(0x16, 0xA3, 0x4A)
GRN_L = RGBColor(0xF0, 0xFD, 0xF4)
AMB = RGBColor(0xD9, 0x77, 0x06)
AMB_L = RGBColor(0xFF, 0xFB, 0xEB)
ORG = RGBColor(0xEA, 0x58, 0x0C)
CYAN = RGBColor(0x08, 0x91, 0xB2)
PUR_L = RGBColor(0xFD, 0xF4, 0xFF)
BDR = RGBColor(0xE5, 0xE7, 0xEB)

prs = Presentation()
prs.slide_width = Inches(13.333)
prs.slide_height = Inches(7.5)

ML = Inches(0.9)  # left margin


def bg(slide):
    slide.background.fill.solid()
    slide.background.fill.fore_color.rgb = WHITE


def tb(slide, l, t, w, h):
    return slide.shapes.add_textbox(l, t, w, h)


def p(tf, text, sz=14, bold=False, c=T1, align=PP_ALIGN.LEFT, sa=Pt(4), fn="Calibri"):
    if len(tf.paragraphs) == 1 and tf.paragraphs[0].text == "":
        para = tf.paragraphs[0]
    else:
        para = tf.add_paragraph()
    para.text = text
    para.font.size = Pt(sz)
    para.font.bold = bold
    para.font.color.rgb = c
    para.font.name = fn
    para.alignment = align
    para.space_after = sa
    para.space_before = Pt(0)
    return para


def rect(slide, l, t, w, h, fill=BG, bdr=BDR):
    s = slide.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, l, t, w, h)
    s.fill.solid()
    s.fill.fore_color.rgb = fill
    s.line.color.rgb = bdr
    s.line.width = Pt(0.75)
    try:
        s.adjustments[0] = 0.04
    except Exception:
        pass
    return s


def label(slide, l, t, text):
    b = tb(slide, l, t, Inches(10), Inches(0.3))
    pr = p(b.text_frame, text, sz=10, bold=True, c=BLUE, sa=Pt(0))
    pr.font.letter_spacing = Pt(1.5)


def title(slide, l, t, text, sz=28):
    b = tb(slide, l, t, Inches(11), Inches(1))
    p(b.text_frame, text, sz=sz, bold=True, c=T1, sa=Pt(0))


def stat(slide, l, t, num, lab):
    b = tb(slide, l, t, Inches(1.5), Inches(0.9))
    p(b.text_frame, str(num), sz=32, bold=True, c=BLUE, sa=Pt(0))
    pr = p(b.text_frame, lab, sz=9, bold=True, c=T3, sa=Pt(0))
    pr.font.letter_spacing = Pt(1)


def tier(slide, l, t, w, lbl, ttl, desc, color):
    bw = Inches(0.75)
    bar = slide.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, l, t, bw, Inches(0.52))
    bar.fill.solid()
    bar.fill.fore_color.rgb = color
    bar.line.fill.background()
    try:
        bar.adjustments[0] = 0.08
    except Exception:
        pass
    tf = bar.text_frame
    tf.paragraphs[0].alignment = PP_ALIGN.CENTER
    r = tf.paragraphs[0].add_run()
    r.text = lbl
    r.font.size = Pt(8)
    r.font.bold = True
    r.font.color.rgb = WHITE
    r.font.name = "Calibri"
    tf.paragraphs[0].space_before = Pt(4)

    box = rect(slide, l + bw + Inches(0.08), t, w - bw - Inches(0.08), Inches(0.52))
    tf2 = box.text_frame
    tf2.word_wrap = True
    tf2.margin_left = Pt(8)
    tf2.margin_top = Pt(4)
    p(tf2, ttl, sz=11, bold=True, c=T1, sa=Pt(1))
    p(tf2, desc, sz=9, c=T2, sa=Pt(0))


def tbl_style(table, headers, rows, col_widths):
    for i, w in enumerate(col_widths):
        table.columns[i].width = Inches(w)
    for i, h in enumerate(headers):
        c = table.cell(0, i)
        c.text = h
        for pr in c.text_frame.paragraphs:
            pr.font.size = Pt(9)
            pr.font.bold = True
            pr.font.color.rgb = T3
            pr.font.name = "Calibri"
        c.fill.solid()
        c.fill.fore_color.rgb = BG
    for ri, row in enumerate(rows):
        for ci, txt in enumerate(row):
            c = table.cell(ri + 1, ci)
            c.text = txt
            for pr in c.text_frame.paragraphs:
                pr.font.size = Pt(11)
                pr.font.name = "Calibri"
                pr.font.color.rgb = T1 if ci == 0 else T2
                pr.font.bold = (ci == 0)
            c.fill.solid()
            c.fill.fore_color.rgb = WHITE


def quote(slide, l, t, w, h, text):
    qb = rect(slide, l, t, w, h, fill=BLU_L, bdr=BLUE)
    qb.line.width = Pt(0)
    lb = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, l, t, Pt(3), h)
    lb.fill.solid()
    lb.fill.fore_color.rgb = BLUE
    lb.line.fill.background()
    tf = qb.text_frame
    tf.word_wrap = True
    tf.margin_left = Pt(16)
    tf.margin_top = Pt(10)
    p(tf, text, sz=13, c=T1, sa=Pt(0))


# ═══════════ SLIDE 0: TITLE ═══════════
s = prs.slides.add_slide(prs.slide_layouts[6])
bg(s)
label(s, ML, Inches(1.8), "HACKFUSION 2026  ·  IEEE ROBOTICS & AUTOMATION SOCIETY  ·  THEME 3")
title(s, ML, Inches(2.2), "GARUDA", sz=48)
b = tb(s, ML, Inches(3.1), Inches(8), Inches(1))
b.text_frame.word_wrap = True
p(b.text_frame, "A physics-informed digital twin that monitors a drone's health\nin real-time, predicts failures before they happen, and makes\nautonomous safety decisions it can explain.", sz=16, c=T2, sa=Pt(0))
sx = ML
for n, l in [("7", "PHYSICS MODELS"), ("6", "DECISION TIERS"), ("7", "KALMAN FILTERS"), ("5", "FAILURE DEMOS")]:
    stat(s, sx, Inches(4.6), n, l)
    sx += Inches(2.2)
b = tb(s, ML, Inches(6.2), Inches(4), Inches(0.3))
p(b.text_frame, "Team GarudaOne", sz=11, c=T3, sa=Pt(0))


# ═══════════ SLIDE 1: PROBLEM ═══════════
s = prs.slides.add_slide(prs.slide_layouts[6])
bg(s)
label(s, ML, Inches(0.65), "THE PROBLEM")
title(s, ML, Inches(0.95), "Drones don't understand their own physics")
b = tb(s, ML, Inches(1.55), Inches(9), Inches(0.7))
b.text_frame.word_wrap = True
p(b.text_frame, "A drone in turbulent wind burns more power. A hot battery loses capacity. A worn motor creates asymmetric thrust. Today's drones don't track any of this — they find out when they crash.", sz=14, c=T2, sa=Pt(0))

bx = ML
for tt, bd in [
    ("No energy awareness", "Battery drains unpredictably under wind load. The drone doesn't know it can't make it home until it's already too late."),
    ("Blind to atmosphere", "Air density drops at altitude, turbulence varies with terrain, temperature affects everything. None of this is modeled."),
    ("No component health", "Motor bearings wear, batteries heat up, propellers degrade. No way to detect partial failure before it becomes total."),
]:
    box = rect(s, bx, Inches(2.6), Inches(3.7), Inches(1.5))
    tf = box.text_frame
    tf.word_wrap = True
    tf.margin_left = Pt(12)
    tf.margin_top = Pt(10)
    p(tf, tt, sz=13, bold=True, c=T1, sa=Pt(4))
    p(tf, bd, sz=11, c=T2, sa=Pt(0))
    bx += Inches(3.95)

quote(s, ML, Inches(4.5), Inches(11.5), Inches(1.0),
      "We need a system that continuously estimates the drone's physical state, predicts failures, quantifies how certain it is, and makes safety decisions it can justify.")


# ═══════════ SLIDE 2: WHAT WE BUILT ═══════════
s = prs.slides.add_slide(prs.slide_layouts[6])
bg(s)
label(s, ML, Inches(0.65), "OUR APPROACH")
title(s, ML, Inches(0.95), "Five physics modules running in a loop at 10 Hz")
b = tb(s, ML, Inches(1.55), Inches(10), Inches(0.4))
b.text_frame.word_wrap = True
p(b.text_frame, "Each module feeds into the next. The decision engine evaluates the complete picture every 100 ms.", sz=13, c=T2, sa=Pt(0))

t = s.shapes.add_table(6, 3, ML, Inches(2.2), Inches(11.5), Inches(4.5)).table
tbl_style(t, ["MODULE", "WHAT IT DOES", "PHYSICS BASIS"], [
    ("Environment Model", "Simulates wind, air density, temperature, pressure, turbulence as a function of altitude and time", "ICAO ISA + Dryden (O-U)"),
    ("Vehicle Health", "Tracks battery temperature, charge state, per-motor efficiency, payload mass, structural G-stress", "Thermal ODE + Coulomb"),
    ("Energy Forecasting", "Predicts power consumption, remaining flight time, mission feasibility", "Actuator Disk Theory"),
    ("State Estimator", "Fuses physics predictions with noisy sensors. 95% confidence intervals on every state", "7× Kalman filters"),
    ("Decision Engine", "Decides: continue, slow down, change altitude, return home, or abort", "6-tier hierarchical rules"),
], [2.3, 6.5, 2.7])


# ═══════════ SLIDE 3: ARCHITECTURE ═══════════
s = prs.slides.add_slide(prs.slide_layouts[6])
bg(s)
label(s, ML, Inches(0.65), "ARCHITECTURE")
title(s, ML, Inches(0.95), "How the pieces fit together")

arch = """┌──────────────────────────────────────────────────────────────────┐
│  DASHBOARD  (Rich TUI — 6 panels, 10 Hz refresh)                │
│  Telemetry · Environment · Health · Energy · Uncertainty · AI    │
└───────────────────────────────┬──────────────────────────────────┘
                                │  JSON telemetry snapshots
┌───────────────────────────────┴──────────────────────────────────┐
│  DIGITAL TWIN ENGINE  (Python, 10 Hz main loop)                  │
│                                                                   │
│  ┌───────────────┐ ┌────────────────┐ ┌────────────────────────┐ │
│  │ Environment    │ │ Vehicle Health │ │ Energy & Endurance     │ │
│  │ ISA + Dryden   │ │ Battery ODE    │ │ Actuator Disk Theory   │ │
│  └───────┬───────┘ └───────┬────────┘ └──────────┬─────────────┘ │
│          └─────────────────┼─────────────────────┘               │
│                     ┌──────┴──────┐                               │
│                     │ Kalman      │   7 state filters             │
│                     │ Filter UQ   │   95% confidence bounds       │
│                     └──────┬──────┘                               │
│                     ┌──────┴──────┐                               │
│                     │ DECISION    │   6-tier hierarchical engine  │
│                     │ ENGINE      │   + evidence trail logger     │
│                     └─────────────┘                               │
└───────────────────────────────────────────────────────────────────┘
                                │  autonomous commands
┌───────────────────────────────┴──────────────────────────────────┐
│  FLIGHT LAYER   PX4 via MAVSDK · Voice ("Hey Garuda") · LFM AI  │
└──────────────────────────────────────────────────────────────────┘"""

rect(s, ML, Inches(1.7), Inches(11.5), Inches(4.8), fill=BG)
b = tb(s, Inches(1.2), Inches(1.85), Inches(11), Inches(4.5))
p(b.text_frame, arch, sz=9, c=T1, fn="Consolas", sa=Pt(0))
b = tb(s, ML, Inches(6.65), Inches(11), Inches(0.4))
p(b.text_frame, "Fully async Python. Event-bus decoupled modules. 14 drone states with enforced transitions. Real hardware parameters from our 249g prototype.", sz=10, c=T3, sa=Pt(0))


# ═══════════ SLIDE 4: PHYSICS — ENVIRONMENT ═══════════
s = prs.slides.add_slide(prs.slide_layouts[6])
bg(s)
label(s, ML, Inches(0.65), "PHYSICS MODELS")
title(s, ML, Inches(0.95), "Environment: atmosphere + wind")

# Left: ISA
b = tb(s, ML, Inches(1.7), Inches(5.5), Inches(0.3))
p(b.text_frame, "ICAO Standard Atmosphere", sz=14, bold=True, sa=Pt(0))

eq1 = rect(s, ML, Inches(2.15), Inches(5), Inches(0.65), fill=BLU_L, bdr=RGBColor(0xDB, 0xEA, 0xFE))
b = tb(s, ML + Inches(0.15), Inches(2.2), Inches(4.7), Inches(0.55))
p(b.text_frame, "T(h) = 288.15 − 0.0065 · h", sz=12, c=T1, fn="Consolas", sa=Pt(2))
p(b.text_frame, "ρ(h) = 1.225 · (T / 288.15)^4.256", sz=12, c=T1, fn="Consolas", sa=Pt(0))

b = tb(s, ML, Inches(2.95), Inches(5.5), Inches(0.6))
b.text_frame.word_wrap = True
p(b.text_frame, "Air density drops with altitude — directly affects how much power the motors need to produce the same thrust. Recalculated every tick.", sz=11, c=T2, sa=Pt(0))

# Dryden
b = tb(s, ML, Inches(3.75), Inches(5.5), Inches(0.3))
p(b.text_frame, "Dryden Wind Turbulence (MIL-F-8785C)", sz=14, bold=True, sa=Pt(0))

eq2 = rect(s, ML, Inches(4.15), Inches(5.2), Inches(0.35), fill=BLU_L, bdr=RGBColor(0xDB, 0xEA, 0xFE))
b = tb(s, ML + Inches(0.15), Inches(4.18), Inches(5), Inches(0.3))
p(b.text_frame, "x(t+dt) = x(t)·exp(−dt/τ) + σ·√(1−exp(−2dt/τ))·N(0,1)", sz=11, c=T1, fn="Consolas", sa=Pt(0))

b = tb(s, ML, Inches(4.65), Inches(5.5), Inches(0.7))
b.text_frame.word_wrap = True
p(b.text_frame, "Wind is random but correlated in time (τ=4s). Standard aerospace model. Vertical axis has 60% lower turbulence than horizontal.", sz=11, c=T2, sa=Pt(0))

# Right: disturbances
rx = Inches(7)
b = tb(s, rx, Inches(1.7), Inches(5.3), Inches(0.3))
p(b.text_frame, "Disturbances we inject live", sz=14, bold=True, sa=Pt(0))

dy = Inches(2.15)
for lt, dt in [
    ("Crosswind gust:", "12 m/s sudden lateral wind"),
    ("Temperature spike:", "+20°C (flying over a heat island)"),
    ("Downdraft:", "5 m/s vertical shear (microburst)"),
    ("Wind shear layer:", "Altitude-dependent velocity gradient"),
]:
    box = rect(s, rx, dy, Inches(5.3), Inches(0.52))
    tf = box.text_frame
    tf.word_wrap = True
    tf.margin_left = Pt(10)
    tf.margin_top = Pt(6)
    tf.clear()
    para = tf.paragraphs[0]
    r1 = para.add_run()
    r1.text = lt + "  "
    r1.font.size = Pt(11)
    r1.font.bold = True
    r1.font.color.rgb = T1
    r1.font.name = "Calibri"
    r2 = para.add_run()
    r2.text = dt
    r2.font.size = Pt(11)
    r2.font.color.rgb = T2
    r2.font.name = "Calibri"
    dy += Inches(0.6)

b = tb(s, rx, dy + Inches(0.1), Inches(5.3), Inches(0.7))
b.text_frame.word_wrap = True
p(b.text_frame, "Each disturbance is a single function call. The decision engine reacts within the same tick.", sz=11, c=T2, sa=Pt(0))


# ═══════════ SLIDE 5: PHYSICS — VEHICLE + ENERGY ═══════════
s = prs.slides.add_slide(prs.slide_layouts[6])
bg(s)
label(s, ML, Inches(0.65), "PHYSICS MODELS")
title(s, ML, Inches(0.95), "Vehicle health + energy forecasting")

# Left: battery
b = tb(s, ML, Inches(1.7), Inches(5.5), Inches(0.3))
p(b.text_frame, "Battery: thermal ODE + Coulomb counting", sz=14, bold=True, sa=Pt(0))

eq = rect(s, ML, Inches(2.1), Inches(5.2), Inches(0.35), fill=BLU_L, bdr=RGBColor(0xDB, 0xEA, 0xFE))
b = tb(s, ML + Inches(0.15), Inches(2.13), Inches(5), Inches(0.3))
p(b.text_frame, "dT/dt = (I²R − h·A·ΔT) / (m·Cp)", sz=12, c=T1, fn="Consolas", sa=Pt(0))

b = tb(s, ML, Inches(2.55), Inches(5.5), Inches(1))
b.text_frame.word_wrap = True
p(b.text_frame, "Battery heats from internal resistance (I²R) and cools from airflow. LiPo capacity drops with temperature — a hot battery gives you less flight time than voltage suggests. Real 3S/450mAh pack params.", sz=11, c=T2, sa=Pt(0))

b = tb(s, ML, Inches(3.7), Inches(5.5), Inches(0.3))
p(b.text_frame, "Motor degradation", sz=14, bold=True, sa=Pt(0))
b = tb(s, ML, Inches(4.05), Inches(5.5), Inches(0.8))
b.text_frame.word_wrap = True
p(b.text_frame, "4 motors tracked independently. Bearing wear at 15%/1000h. Delta between best and worst motor (imbalance) is a key safety signal.", sz=11, c=T2, sa=Pt(0))

# Right: power
b = tb(s, rx, Inches(1.7), Inches(5.3), Inches(0.3))
p(b.text_frame, "Power: Actuator Disk Momentum Theory", sz=14, bold=True, sa=Pt(0))

eq = rect(s, rx, Inches(2.1), Inches(5.2), Inches(0.55), fill=BLU_L, bdr=RGBColor(0xDB, 0xEA, 0xFE))
b = tb(s, rx + Inches(0.15), Inches(2.13), Inches(5), Inches(0.5))
p(b.text_frame, "P_hover = √(T³ / 2ρA) · κ / η", sz=12, c=T1, fn="Consolas", sa=Pt(2))
p(b.text_frame, "P_fwd = P_hover·f(v) + ½ρCdAv³", sz=12, c=T1, fn="Consolas", sa=Pt(0))

b = tb(s, rx, Inches(2.8), Inches(5.3), Inches(0.8))
b.text_frame.word_wrap = True
p(b.text_frame, "Hover power depends on thrust, air density, disk area (4× 2-inch props), and rotor efficiency. Forward flight adds parasitic drag. All from real hardware config.", sz=11, c=T2, sa=Pt(0))

b = tb(s, rx, Inches(3.7), Inches(5.3), Inches(0.3))
p(b.text_frame, "Safe operating envelope (dynamic)", sz=14, bold=True, sa=Pt(0))
b = tb(s, rx, Inches(4.05), Inches(5.3), Inches(1.2))
b.text_frame.word_wrap = True
for item in ["Max altitude (density-limited)", "Max speed (rotor-efficiency-limited)", "Max range at cruise speed", "Can we reach target, return home, and keep 30s reserve?"]:
    p(b.text_frame, "•  " + item, sz=11, c=T2, sa=Pt(3))


# ═══════════ SLIDE 6: KALMAN FILTER ═══════════
s = prs.slides.add_slide(prs.slide_layouts[6])
bg(s)
label(s, ML, Inches(0.65), "UNCERTAINTY QUANTIFICATION")
title(s, ML, Inches(0.95), "Kalman filter: physics meets sensors")
b = tb(s, ML, Inches(1.55), Inches(9), Inches(0.5))
b.text_frame.word_wrap = True
p(b.text_frame, "Physics models predict what should happen. Sensors measure what actually happened. The Kalman filter finds the best estimate and tells you how confident it is.", sz=13, c=T2, sa=Pt(0))

code = """Predict (from physics model):
  x̂ = model_prediction(alt, speed, wind)
  P += Q · dt            ← uncertainty grows

Update (from noisy sensor):
  K = P / (P + R)        ← Kalman gain
  x̂ += K · (z − x̂)      ← fuse measurement
  P = (1 − K) · P        ← uncertainty shrinks

Output:
  estimate ± 2σ           ← 95% confidence band"""

rect(s, ML, Inches(2.2), Inches(5.5), Inches(2.8), fill=BG)
b = tb(s, ML + Inches(0.2), Inches(2.3), Inches(5.2), Inches(2.6))
p(b.text_frame, code, sz=10, c=T1, fn="Consolas", sa=Pt(0))

b = tb(s, rx, Inches(2.2), Inches(5.3), Inches(0.3))
p(b.text_frame, "7 independent filters tracking:", sz=14, bold=True, sa=Pt(0))

t = s.shapes.add_table(7, 2, rx, Inches(2.6), Inches(5.2), Inches(2.7)).table
tbl_style(t, ["STATE", "SENSOR NOISE (σ)"], [
    ("Position N, E", "GPS: 0.25 m"),
    ("Altitude", "Barometer: 0.25 m"),
    ("Airspeed", "Pitot: 0.20 m/s"),
    ("Wind speed", "Inferred: 0.40 m/s"),
    ("Battery SoC", "Current sensor: 0.30%"),
    ("Endurance", "Derived: ±25 s"),
], [2.8, 2.4])

b = tb(s, rx, Inches(5.5), Inches(5.3), Inches(0.5))
b.text_frame.word_wrap = True
p(b.text_frame, "The decision engine uses uncertainty to calibrate how aggressive its responses are.", sz=11, c=T2, sa=Pt(0))


# ═══════════ SLIDE 7: DECISION ENGINE ═══════════
s = prs.slides.add_slide(prs.slide_layouts[6])
bg(s)
label(s, ML, Inches(0.65), "AUTONOMOUS DECISIONS")
title(s, ML, Inches(0.95), "6-tier hierarchical safety engine")
b = tb(s, ML, Inches(1.55), Inches(10), Inches(0.4))
b.text_frame.word_wrap = True
p(b.text_frame, "Evaluates from most severe to least. Stops at the first tier that triggers. Every decision carries an evidence trail.", sz=13, c=T2, sa=Pt(0))

ty = Inches(2.2)
tw = Inches(11.5)
for lb, tt, dd, co in [
    ("ABORT", "Emergency landing — immediate", "Battery ≥ 60°C · rotor eff < 30% · structural stress exceeded · endurance < 45s", RED),
    ("RTB", "Return to base", "Not enough energy for RTH · SoC ≤ 18% · battery ≥ 50°C · motor degradation · wind ≥ 8.5 m/s", ORG),
    ("ALT", "Change altitude", "Air density too thin at current height · vertical downdraft ≥ 3 m/s", CYAN),
    ("SLOW", "Reduce speed", "Turbulence intensity ≥ 0.50 · crosswind ≥ 5.5 m/s · rotor imbalance ≥ 0.15", CYAN),
    ("ROUTE", "Modify trajectory", "Headwind ≥ 60% of airspeed — reroute to save energy", BLUE),
    ("GO", "Continue mission", "All parameters nominal. Confidence: 96%.", GRN),
]:
    tier(s, ML, ty, tw, lb, tt, dd, co)
    ty += Inches(0.62)

b = tb(s, ML, Inches(6.0), Inches(11), Inches(0.4))
b.text_frame.word_wrap = True
p(b.text_frame, "Every decision record includes: trigger parameter + value + threshold, confidence score, physics snapshot, and alternatives considered but rejected.", sz=10, c=T3, sa=Pt(0))


# ═══════════ SLIDE 8: SCENARIOS ═══════════
s = prs.slides.add_slide(prs.slide_layouts[6])
bg(s)
label(s, ML, Inches(0.65), "DEMONSTRATION")
title(s, ML, Inches(0.95), "5 failure scenarios, tested live")
b = tb(s, ML, Inches(1.55), Inches(10), Inches(0.4))
b.text_frame.word_wrap = True
p(b.text_frame, "We inject each disturbance during the simulation and show the decision engine reacting in real-time with evidence.", sz=13, c=T2, sa=Pt(0))

t = s.shapes.add_table(6, 3, ML, Inches(2.2), Inches(5.8), Inches(3.5)).table
tbl_style(t, ["#", "SCENARIO", "DECISION"], [
    ("1", "12 m/s crosswind gust", "REDUCE SPEED"),
    ("2", "Motor #3 bearing failure (35%)", "SLOW → RTB"),
    ("3", "Battery overheating (58°C)", "ABORT"),
    ("4", "Payload released mid-flight", "CONTINUE (re-calc)"),
    ("5", "Downdraft + thin air + low battery", "ALTER ALT → RTB"),
], [0.4, 3.2, 2.2])
# Color the decision column blue
for ri in range(1, 6):
    for pr in t.cell(ri, 2).text_frame.paragraphs:
        pr.font.color.rgb = BLUE
        pr.font.bold = True

# Evidence JSON
b = tb(s, rx, Inches(2.2), Inches(5.3), Inches(0.3))
p(b.text_frame, "Evidence trail (actual output)", sz=13, bold=True, sa=Pt(0))

json_t = """{
  "decision": "RETURN_TO_BASE",
  "confidence": 0.92,
  "triggers": [{
    "parameter": "battery_soc",
    "value": 16.2,
    "threshold": 18.0,
    "severity": "WARNING"
  }],
  "reason": "Energy reserve
    insufficient for safe RTH.",
  "physics_snapshot": {
    "wind_speed": 7.3,
    "hover_power": 28.4,
    "rotor_effs": [.89,.88,.58,.90]
  }
}"""
rect(s, rx, Inches(2.6), Inches(5.3), Inches(3.3), fill=BG)
b = tb(s, rx + Inches(0.15), Inches(2.7), Inches(5), Inches(3.1))
p(b.text_frame, json_t, sz=9, c=T1, fn="Consolas", sa=Pt(0))


# ═══════════ SLIDE 9: VOICE + AI ═══════════
s = prs.slides.add_slide(prs.slide_layouts[6])
bg(s)
label(s, ML, Inches(0.65), "INNOVATION BEYOND THE BRIEF")
title(s, ML, Inches(0.95), '"Hey Garuda" — voice-controlled digital twin')
b = tb(s, ML, Inches(1.55), Inches(9), Inches(0.4))
b.text_frame.word_wrap = True
p(b.text_frame, "Fully offline voice pipeline. No cloud, no internet — everything on-device. Think Siri, but for a drone.", sz=13, c=T2, sa=Pt(0))

b = tb(s, ML, Inches(2.2), Inches(5.5), Inches(0.3))
p(b.text_frame, "Voice pipeline", sz=14, bold=True, sa=Pt(0))

sy = Inches(2.6)
for num, desc in [
    ("1", 'Wake word — openWakeWord listens for "Garuda" (3-8% CPU)'),
    ("2", "Speech-to-text — Whisper Tiny (INT8, 39 MB)"),
    ("3", "Intent routing — keyword (<5ms), Needle 26M (<20ms), LFM (200ms)"),
    ("4", 'Voice feedback — Piper TTS: "Starting orbit mode"'),
]:
    circ = s.shapes.add_shape(MSO_SHAPE.OVAL, ML, sy + Inches(0.02), Inches(0.28), Inches(0.28))
    circ.fill.solid()
    circ.fill.fore_color.rgb = BLU_L
    circ.line.fill.background()
    ctf = circ.text_frame
    ctf.paragraphs[0].alignment = PP_ALIGN.CENTER
    r = ctf.paragraphs[0].add_run()
    r.text = num
    r.font.size = Pt(10)
    r.font.bold = True
    r.font.color.rgb = BLUE
    r.font.name = "Calibri"
    b = tb(s, ML + Inches(0.4), sy, Inches(5), Inches(0.3))
    b.text_frame.word_wrap = True
    p(b.text_frame, desc, sz=11, c=T2, sa=Pt(0))
    sy += Inches(0.42)

b = tb(s, ML, sy + Inches(0.1), Inches(5), Inches(0.3))
p(b.text_frame, "Most commands resolve in under 20 ms.", sz=10, c=T3, sa=Pt(0))

# AI models table
b = tb(s, rx, Inches(2.2), Inches(5.3), Inches(0.3))
p(b.text_frame, "AI models on a Raspberry Pi 5", sz=14, bold=True, sa=Pt(0))

t = s.shapes.add_table(6, 3, rx, Inches(2.6), Inches(5.3), Inches(2.7)).table
tbl_style(t, ["MODEL", "SIZE", "SPEED"], [
    ("LFM-2.5-230M (Liquid AI brain)", "180 MB", "42 tok/s"),
    ("Needle 26M (fast router)", "14 MB", "1,200 tok/s"),
    ("PicoDet-S (object detection)", "4 MB", "50 FPS"),
    ("Whisper Tiny (speech-to-text)", "39 MB", "Real-time"),
    ("Piper TTS (text-to-speech)", "20 MB", "Real-time"),
], [2.8, 1.0, 1.5])

b = tb(s, rx, Inches(5.5), Inches(5.3), Inches(0.4))
b.text_frame.word_wrap = True
p(b.text_frame, "All CPU-only on RPi 5 (8 GB). No GPU. Drone weighs 249g.", sz=10, c=T3, sa=Pt(0))


# ═══════════ SLIDE 10: DASHBOARD ═══════════
s = prs.slides.add_slide(prs.slide_layouts[6])
bg(s)
label(s, ML, Inches(0.65), "DASHBOARD")
title(s, ML, Inches(0.95), "6 panels, all updating at 10 Hz")
b = tb(s, ML, Inches(1.55), Inches(8), Inches(0.35))
b.text_frame.word_wrap = True
p(b.text_frame, "Built with Python's Rich library. Reads telemetry JSON from the twin runner.", sz=13, c=T2, sa=Pt(0))

panels = [
    ("Telemetry", "Altitude, airspeed, heading, GPS, distance to target/home", BLU_L),
    ("Environment", "ISA density, temperature, pressure, wind vector, turbulence", AMB_L),
    ("Vehicle Health", "Battery SoC + temp, 4× motor bars, structural stress", PUR_L),
    ("Energy", "Power draw, hover/cruise power, endurance countdown, envelope", GRN_L),
    ("Uncertainty", "Every Kalman estimate with ±2σ confidence bounds", BG),
    ("Decision", "Current action, confidence %, trigger reason, alternatives", RED_L),
]
bx = ML
by = Inches(2.15)
bw = Inches(3.7)
bh = Inches(1.1)
for i, (tt, dd, bgc) in enumerate(panels):
    col = i % 3
    row = i // 3
    x = bx + col * (bw + Inches(0.2))
    y = by + row * (bh + Inches(0.15))
    box = rect(s, x, y, bw, bh, fill=bgc)
    tf = box.text_frame
    tf.word_wrap = True
    tf.margin_left = Pt(12)
    tf.margin_top = Pt(10)
    p(tf, tt, sz=13, bold=True, c=T1, sa=Pt(3))
    p(tf, dd, sz=11, c=T2, sa=Pt(0))

quote(s, ML, Inches(4.7), Inches(11.5), Inches(0.85),
      "During the demo we inject failure scenarios live and watch all 6 panels react. The decision panel shows exactly why the engine made its choice.")


# ═══════════ SLIDE 11: JUDGING CRITERIA ═══════════
s = prs.slides.add_slide(prs.slide_layouts[6])
bg(s)
label(s, ML, Inches(0.65), "COVERAGE")
title(s, ML, Inches(0.95), "How we address each judging criterion")

t = s.shapes.add_table(8, 2, ML, Inches(1.6), Inches(11.5), Inches(5)).table
tbl_style(t, ["CRITERION", "OUR IMPLEMENTATION"], [
    ("Physical-state estimation accuracy", "7 Kalman filters fusing ISA physics with sensors. Each state has 95% CI bounds."),
    ("Environmental modeling quality", "ICAO atmosphere + Dryden wind turbulence (O-U process) + 4 injectable disturbances."),
    ("Energy/endurance prediction", "Actuator disk power with real hardware params. Mission feasibility: target + RTH + 30s reserve."),
    ("Safety decision effectiveness", "6-tier engine with confidence scores. Evidence trail for every decision. 5 failure scenarios."),
    ("Robustness under changing conditions", "Crosswind, motor failure, thermal runaway, payload change, combined — all real-time."),
    ("Physics/ML integration", "Kalman = physics+sensors. CfC LNN = learned control. LFM = NL understanding. Voice = ML chain."),
    ("Innovation", "Voice-controlled twin, Liquid AI, evidence audit trails, real sub-250g hardware parameters."),
], [3.3, 8.2])


# ═══════════ SLIDE 12: FUTURE ═══════════
s = prs.slides.add_slide(prs.slide_layouts[6])
bg(s)
label(s, ML, Inches(0.65), "WHAT'S NEXT")
title(s, ML, Inches(0.95), "Future development")
b = tb(s, ML, Inches(1.55), Inches(8), Inches(0.35))
b.text_frame.word_wrap = True
p(b.text_frame, "The modular architecture means each piece can be upgraded independently.", sz=13, c=T2, sa=Pt(0))

futures = [
    ("Voice biometrics", "Owner + 2 registered voices only. Speaker verification rejects unauthorized commands.", BLU_L),
    ("Satellite connectivity", "Iridium/Starlink backhaul for beyond-line-of-sight. Cloud twin mirroring.", AMB_L),
    ("Multi-drone swarm", "PX4 multi-SITL already configured. Coordinated formation flying.", GRN_L),
    ("Edge SLAM", "OpenVINS / ORB-SLAM3 via VisionPoseSource interface. Already defined.", BG),
    ("RL decision refinement", "Flight data tunes thresholds via RL. Physics constraints stay, RL tunes margins.", BG),
]
bx = ML
by = Inches(2.15)
bw = Inches(3.7)
bh = Inches(1.25)
for i, (tt, dd, bgc) in enumerate(futures):
    col = i % 3
    row = i // 3
    x = bx + col * (bw + Inches(0.2))
    y = by + row * (bh + Inches(0.15))
    box = rect(s, x, y, bw, bh, fill=bgc)
    tf = box.text_frame
    tf.word_wrap = True
    tf.margin_left = Pt(12)
    tf.margin_top = Pt(10)
    p(tf, tt, sz=13, bold=True, c=T1, sa=Pt(4))
    p(tf, dd, sz=11, c=T2, sa=Pt(0))


# ═══════════ SLIDE 13: CLOSING ═══════════
s = prs.slides.add_slide(prs.slide_layouts[6])
bg(s)

b = tb(s, Inches(1.5), Inches(1.4), Inches(10), Inches(0.3))
pr = p(b.text_frame, "GARUDA", sz=11, bold=True, c=BLUE, sa=Pt(0), align=PP_ALIGN.CENTER)
pr.font.letter_spacing = Pt(2)

b = tb(s, Inches(1.5), Inches(1.9), Inches(10), Inches(1.3))
p(b.text_frame, "It doesn't just simulate the drone.\nIt understands the physics.", sz=36, bold=True, c=T1, sa=Pt(12), align=PP_ALIGN.CENTER)
p(b.text_frame, "Real equations. Real hardware parameters.\nReal-time decisions with evidence you can audit.", sz=15, c=T2, sa=Pt(0), align=PP_ALIGN.CENTER)

sx = Inches(1.5)
for n, l in [("7", "PHYSICS MODELS"), ("6", "SAFETY TIERS"), ("7", "KALMAN FILTERS"), ("5", "LIVE SCENARIOS"), ("<20ms", "VOICE LATENCY")]:
    b = tb(s, sx, Inches(4.0), Inches(1.8), Inches(0.9))
    p(b.text_frame, str(n), sz=28, bold=True, c=BLUE, sa=Pt(0), align=PP_ALIGN.CENTER)
    pr = p(b.text_frame, l, sz=9, bold=True, c=T3, sa=Pt(0), align=PP_ALIGN.CENTER)
    pr.font.letter_spacing = Pt(1)
    sx += Inches(2.1)

b = tb(s, Inches(1.5), Inches(5.4), Inches(10), Inches(0.4))
p(b.text_frame, "Team GarudaOne  ·  HackFusion 2026  ·  IEEE RAS", sz=14, c=T2, sa=Pt(0), align=PP_ALIGN.CENTER)

b = tb(s, Inches(1.5), Inches(6.0), Inches(10), Inches(0.3))
p(b.text_frame, '"Hey Garuda, take off."', sz=12, c=T3, sa=Pt(0), align=PP_ALIGN.CENTER)


# ═══════════ SAVE ═══════════
out = r"d:\Hackathons\Projects\Web Dev\New\DroneOS\pitch\GARUDA_Pitch.pptx"
prs.save(out)
print(f"Saved: {out}")
print(f"Slides: {len(prs.slides)}")
