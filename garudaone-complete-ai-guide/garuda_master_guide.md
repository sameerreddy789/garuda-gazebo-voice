# GarudaOne & GarudaPin: Complete AI/ML Models Guide & Implementation Roadmap

> **Document Purpose:** This is the full technical blueprint for the AI/ML stack powering GarudaOne and GarudaPin — every model, every hardware chip, every training recipe, and every implementation step. Ground truth sourced from peer-reviewed research (ECCV, CVPR, AAAI, ICML, NeurIPS), verified HuggingFace model repos, and real embedded hardware benchmarks.

---

## PART 1 — WEIGHT BUDGET & HARDWARE ARCHITECTURE

### Sub-250g Weight Budget (Reference: HoverAir X1 = 159g production drone)

| Component | Estimated Weight | Notes |
|---|---|---|
| Carbon fiber foldable frame | ~25g | Proprietary chassis design |
| 4× brushless motors + ESC | ~30g | BLDC, 4000–5000 KV class |
| Propellers (folding) + guards | ~15g | 3-inch props with guard |
| Battery (2S LiPo, ~1100mAh) | ~55g | Flight time vs weight tradeoff |
| Flight Controller (FC) | ~5g | F7/H7 MCU, ~3–5g |
| **AI Compute Module** | **~15–20g** | See compute options below |
| 4K Camera + EIS | ~8g | Sensor-only (no gimbal) |
| Stereo/ToF sensor pair | ~5g | OAK-D variant or custom |
| GPS + Compass | ~4g | Dual-band miniaturized |
| Communication (UWB anchor + radio) | ~6g | DW3000 + OcuSync/similar |
| Wi-Fi / Connectivity | ~3g | M.2 or SoC-integrated |
| **Total (target)** | **~171–176g** | Sub-250g with ~75g margin |

---

### Compute Architecture — Dual-Layer Design

GarudaOne must split processing into two isolated planes:

```
┌─────────────────────────────────────────────────────────┐
│  PLANE A: Flight Control (Real-Time, Deterministic)     │
│  Chip:    STM32H7 (Cortex-M7, 480MHz) or ICF5          │
│  Roles:   Motor PWM, IMU fusion, PID loop, RC link      │
│  RTOS:    PX4 or ArduPilot on FreeRTOS / NuttX          │
│  Latency: <1ms motor control loop                        │
│  Weight:  ~4–5g (Matek H743 class FC)                   │
└─────────────────────────────────────────────────────────┘
         │ MAVLink / UART command interface
┌─────────────────────────────────────────────────────────┐
│  PLANE B: AI Vision + NLP (High-Throughput, Async)      │
│  Chip:    Jetson Orin Nano 8GB (10W max, ~8g module)    │
│  Roles:   Tracking, SLAM, voice, gesture, path planning  │
│  OS:      JetPack 6.x (Ubuntu 22.04 + CUDA 12.x)       │
│  Sends:   Velocity setpoints + waypoints to Plane A     │
│  Weight:  ~8g (module only) + ~5g carrier = ~13g        │
└─────────────────────────────────────────────────────────┘
```

#### Compute Options (Ranked by Feasibility)

| Option | TOPS | TDP | Weight | VRAM | Verdict |
|---|---|---|---|---|---|
| **Jetson Orin Nano 8GB** (recommended) | 40 TOPS | 7–10W | ~8g module | 8GB LPDDR5 | Best balance |
| Qualcomm QRB5165 (RB3 Gen 2) | ~15 TOPS AI | 5–8W | ~10g module | 8GB LPDDR5 | Alt, Snapdragon SDK |
| Rockchip RK3588 | 6 TOPS NPU | 5–10W | ~8g SoM | 8GB | Limited ML SW ecosystem |
| Ambarella CV52S | 12 TOPS | ~3W | ~5g SoC | 2GB | Drone-native, very low power |
| Raspberry Pi CM5 + Coral TPU M.2 | ~4 TOPS (TPU) | 5W + 2W | 7g + 8g | 8GB RAM | EdgeTPU only TFLite |
| Jetson Orin NX 16GB | 70 TOPS | 10–25W | ~10g module | 16GB | Too hot/heavy for sub-250g |

> **Recommended:** **Ambarella CV52S** as primary flight AI chip (drone-native, 3W, ~5g), augmented with **Jetson Orin Nano 8GB** carrier-board-integrated for heavy lifting (SLAM, NLP). Dual-chip total ~13g, ~10–13W peak.

---

### Camera System

| Spec | Recommendation | Notes |
|---|---|---|
| Primary sensor | Sony IMX678 (1/2.0") | 4K/60fps, low-light leader |
| Lens | 3.6mm f/2.0 fixed (95° HFOV) | Match HoverAir X1 profile |
| Stabilization | **EIS (primary) + 1-axis soft-mount** | No gimbal to save 15–20g |
| Horizon Lock | Software: 3-axis EIS with gravity vector from IMU | Real-time warp during encode |
| Low-light | IMX678 + AI denoise (TensorRT) | No manual ISO needed |
| Encode | H.265 10-bit, hardware encode (Ambarella/Orin) | SD card or USB3 SSD |

---

### Obstacle Sensing Array

| Sensor | Weight | Range | Role |
|---|---|---|---|
| **OAK-D S2 (stereo 120° FOV)** | ~20g | 0.3–15m | Forward obstacle + depth |
| **Garmin LIDAR-Lite v4 (ToF)** | ~7g | 1–35m | Downward + forward alt-hold |
| Optical flow (PMW3901) | ~1g | 0–5m | Position hold near ground |
| IMU (ICM-42688-P 6-DOF) | <1g | — | VIO fusion |

> For sub-250g strict budget: replace OAK-D S2 with **2× Arducam IMX219 stereo pair** (~3g each) + custom stereo processing on Orin Nano — saves ~16g.

---

## PART 2 — SUBJECT TRACKING STACK

### Primary Tracking Pipeline

```
Camera feed (30fps) → YOLOv11s Detector → BoT-SORT + GarudaPin fusion → Drone velocity commands
```

#### 2.1 Object Detector

| Model | Params | Size | Source | Benchmark |
|---|---|---|---|---|
| **YOLO11s** (recommended) | 9.4M | 18.4MB | `Ultralytics/YOLO11` | mAP 47.0 COCO |
| YOLO11n (min-power) | 2.6M | 5.4MB | `Ultralytics/YOLO11` | mAP 39.5 COCO |
| RT-DETRv2-S (alt) | ~20M | ~80MB | `PekingU/rtdetr_r18vd` | Best aerial (FlyPose) |

**Mandatory fine-tuning:** Fine-tune YOLO11s on **VisDrone2019-DET** dataset. Vanilla COCO-trained models lose ~7+ mAP on aerial views. This is non-negotiable.

```python
from ultralytics import YOLO
model = YOLO("yolo11s.pt")
# Fine-tune on VisDrone2019
model.train(
    data="VisDrone.yaml",
    epochs=100,
    imgsz=640,
    batch=16,
    lr0=0.01,
    device="cuda"
)
```

#### 2.2 Multi-Object Tracker

**Primary: BoT-SORT with Camera Motion Compensation (CMC)**
BoT-SORT is specifically designed for moving-camera scenarios. The CMC module uses ECC (Enhanced Correlation Coefficient) to compensate for drone ego-motion before computing IoU overlaps — critical because the drone itself is always moving.

```python
from ultralytics import YOLO
model = YOLO("yolo11s.pt")  # or fine-tuned weights

# Built-in BoT-SORT with CMC — one-liner
results = model.track(
    source=camera_stream,
    tracker="botsort.yaml",   # CMC enabled by default
    persist=True,
    conf=0.3,
    iou=0.5,
    classes=[0],              # person class only
    stream=True
)

# Or via BoxMOT for full control
# pip install boxmot
from boxmot import BotSort
tracker = BotSort(
    reid_weights="osnet_x0_25_msmt17.pt",
    device="cuda",
    half=True,
    with_reid=False  # disable ReID in normal tracking, enable on re-acquisition
)
```

**Benchmark Context:**
- BoT-SORT: MOT17 → MOTA=80.5, IDF1=80.2, HOTA=65.0
- UCMCTrack+: MOT17 → HOTA=66.8, IDF1=81.8 (best motion-only)
- HopTrack (embedded): MOT16 @ Jetson AGX Xavier → 28.54 FPS @ 7.16W

**For CPU-only fallback:** OC-SORT runs at **700+ FPS on CPU alone** (no GPU), and is the strongest tracker for non-linear motion (crowd scenes, running subjects).

#### 2.3 Person Re-Identification (Re-Acquisition Module)

Used only when the visual track is lost (>30 frames absent). Not run every frame.

```python
import torchreid

# Lightweight edge version
model = torchreid.models.build_model(
    name='osnet_x0_25',       # 0.2M params — EDGE version
    num_classes=751,          # Market1501 pre-trained
    pretrained=True
)
# Full accuracy version: osnet_x1_0 (2.2M params, 2MB)
# Market1501 Rank-1: 94.8%, MSMT17 Rank-1: 79.1%
```

**Critical gap — aerial re-ID:** OSNet/FastReID are trained on frontal street-level camera data. For aerial top-down view, **fine-tune on P-DESTRE dataset** (arxiv:2004.02782 — the only annotated aerial person re-ID dataset).

#### 2.4 GarudaPin Sensor Fusion Integration

GarudaPin transforms the tracking problem from **find and track** to **verify and re-acquire**:

```python
class GarudaPinFusedTracker:
    """
    Fuses UWB/BLE beacon position with visual BoT-SORT tracker.
    UWB provides absolute position; visual provides bbox.
    """
    def __init__(self):
        self.visual_tracker = BotSort(...)
        self.kalman = UnscentedKalmanFilter(dim_x=9, dim_z=1)
        
    def update(self, frame, uwb_range, uwb_angle, imu_accel):
        # 1. Visual tracking update
        visual_tracks = self.visual_tracker.update(detections, frame)
        
        # 2. UWB beacon → 3D position (range + PDoA angle from DW3000)
        beacon_x, beacon_y, beacon_z = self.uwb_to_xyz(uwb_range, uwb_angle)
        
        # 3. Kalman filter fusion: UWB measurement corrects IMU dead-reckoning
        self.kalman.predict(u=imu_accel)           # IMU @ 200Hz
        self.kalman.update(z=[uwb_range])           # UWB @ 100Hz
        
        # 4. Cross-validate: if visual bbox centroid vs UWB position IoU < 0.3
        #    → re-ID event, search for GarudaPin wearer in candidates
        if self.iou(visual_centroid, beacon_pos) < 0.3:
            self.trigger_reid(frame, beacon_pos)
        
        # 5. Activity-aware follow behavior from BLE payload
        activity = self.parse_ble_payload(ble_adv_data)  # WALKING/RUNNING/CYCLING
        follow_distance = self.activity_to_follow_distance(activity)
        
        return SubjectState(position=beacon_pos, velocity=self.kalman.x[3:6],
                           bbox=visual_tracks, follow_distance=follow_distance)
```

---

## PART 3 — SPATIAL INTELLIGENCE & SLAM

### 3.1 Visual-Inertial Odometry (VIO)

**Primary: AirSLAM (Jetson AGX Orin verified)**
- **40 FPS** on Jetson AGX Orin, **989 MB GPU VRAM**
- Joint point+line detection in single forward pass
- Handles illumination changes (day→dusk→night), important for golden hour shoots
- GitHub: https://github.com/sair-lab/AirSLAM

**Fallback / CPU-only: OpenVINS**
- ~80–150 MB RAM, 30 Hz on ARM Cortex
- EKF-based, fully configurable, active community
- https://docs.openvins.com

**Selection matrix:**

| Compute Config | SLAM Choice | RAM | Frequency |
|---|---|---|---|
| Jetson Orin Nano 8GB (TRT FP16) | AirSLAM (reduced keypoints) | ~600 MB | ~25–30 Hz |
| CPU-only / ultra-low power | OpenVINS | ~120 MB | 30 Hz |
| Full Jetson AGX Orin (future) | AirSLAM full | 989 MB | 40 Hz |

```bash
# AirSLAM TensorRT deployment
git clone https://github.com/sair-lab/AirSLAM
# Tune for Orin Nano: reduce keypoints 350→200 in config
# min_num_kpts: 200, max_num_kpts: 200
# alpha1: 0.5, alpha2: 0.2  (keyframe sparsity)
```

### 3.2 Depth Estimation (Obstacle Detection)

**Primary: Depth Anything V2 Small**
- **24.8M params, ~100MB model**
- HuggingFace: `depth-anything/Depth-Anything-V2-Small`
- **~20–25 FPS** on Jetson Orin NX (TensorRT FP16)
- Used by Fly360 paper as frozen depth backbone → proved sim-to-real transfer

```python
from transformers import AutoImageProcessor, AutoModelForDepthEstimation
import torch

processor = AutoImageProcessor.from_pretrained("depth-anything/Depth-Anything-V2-Small-hf")
model = AutoModelForDepthEstimation.from_pretrained("depth-anything/Depth-Anything-V2-Small-hf")
model = model.to("cuda").half()  # FP16 for Jetson

# For obstacle detection (real-time inference path):
inputs = processor(images=frame_rgb, return_tensors="pt").to("cuda")
with torch.no_grad():
    depth_map = model(**inputs).predicted_depth  # [1, H, W]

# ONNX export for TensorRT:
torch.onnx.export(model, dummy_input, "depth_v2_small.onnx", opset_version=17)
# Then: trtexec --onnx=depth_v2_small.onnx --fp16 --saveEngine=depth_v2_small.engine
```

**Ultra-lightweight fallback: FastDepth**
- ~4M params, ~16MB, **27 FPS on Jetson TX2 CPU** (no GPU)
- Use when Orin is CPU-constrained during complex shots
- GitHub: https://github.com/dwofk/fast-depth

### 3.3 Omnidirectional Obstacle Avoidance — Fly360 Architecture

Based on arxiv:2603.06573 (Mar 2025) — **10/10 flight success in complex environments**. Forward-view-only drones achieved 0–1/10.

```
Architecture:
  Fixed frozen backbone: Depth-Anything-V2-Small (panoramic input)
  Trainable policy: Small Conv + LSTM → velocity commands
  Training: Single RTX 3090, AdamW, lr=1e-3, cosine decay
  Key: Panoramic depth as intermediate = zero sim-to-real gap

For 360° pre-flight scanning:
  Equirectangular panoramic depth map
  → Voxel grid occupancy (0.1m resolution)
  → Connected component analysis → safe corridors
  → Candidate path seeds for planner
```

### 3.4 Path Planning — Cinematic + Safe

```
[Global Path Planning]  A* / RRT* on voxel occupancy map from AirSLAM
[Local Re-planning]     EGO-Planner v2 (< 5ms on CPU, gradient-based ESDF)
[Cinematic Smoothing]   Minimum-jerk trajectory (quintic spline, analytical)
[Quality Ranking]       CLIP-IQA scoring of simulated viewpoints
```

**EGO-Planner v2 Integration:**
```bash
# GitHub: HKUST-Aerial-Robotics/ego-planner-swarm
# ROS2 compatible wrapper available
# Key params for cinematic smoothing:
# max_vel: 5.0 m/s (chase shot), 2.0 m/s (reveal)
# max_acc: 3.0 m/s² 
# swarm_clearance: 0.5m from obstacles
```

---

## PART 4 — VOICE INTERFACE (OFFLINE, ALL INDIAN LANGUAGES)

### Architecture Overview

```
Microphone (16kHz mono)
    │
    ▼
[openWakeWord < 1MB ONNX — always-on, <10ms/chunk]
    │ "Hey Garuda" detected
    ▼
[Silero VAD ONNX ~1MB — endpoint detection]
    │ 2–4s command audio
    ▼
[Language Router: facebook/mms-lid-126 ~2MB TFLite]
    │
    ├── Indian language → [IndicConformer-120M CTC ONNX ~120MB INT8]
    └── English         → [Whisper-tiny INT8 ~39MB — faster-whisper]
    │
    ▼
[Intent: keyword regex OR MiniLM-L12 ONNX ~118MB]
    │
    ▼
[Drone Command: RECORD / LAND / SWITCH_SHOT / TRACK / RTH]
```

**Total model footprint:** ~300–350MB (1 lang active + wake word + English fallback + NLU)

### 4.1 Wake Word Detection

```python
# pip install openwakeword
from openwakeword.model import Model

oww = Model(
    wakeword_models=["hey_garuda.onnx"],  # custom trained
    inference_framework="onnx"
)

# Always-on loop (80ms audio chunks at 16kHz = 1280 samples)
while True:
    audio_chunk = mic.read(1280)
    prediction = oww.predict(audio_chunk)
    if prediction["hey_garuda"] > 0.5:
        start_command_capture()
```

**Training "Hey Garuda" wake word:**
1. Generate 1000+ "Hey Garuda" TTS samples using `ai4bharat/indic-parler-tts` (10+ Indian accents + English)
2. Use openWakeWord automated training notebook (ships with repo)
3. Output: `hey_garuda.onnx` — ~500KB, <10ms/chunk inference

### 4.2 Speech Recognition — Indian Languages

**Primary: IndicConformer-120M (CTC-ONNX)**
- HuggingFace: `trysem/indicconformer-120m-onnx` (per-language ONNX)
- Source: `ai4bharat/indicconformer_stt_{lang}_hybrid_ctc_rnnt_large`
- Languages: hi / ta / te / kn / ml / bn / mr / gu / pa / ur
- **INT8 quantization: 470MB → ~120MB per language**
- Benchmark: Tier I on Voice of India benchmark (arxiv:2604.19151)

```python
import json, numpy as np, librosa, onnxruntime as ort
from huggingface_hub import hf_hub_download
from onnxruntime.quantization import quantize_dynamic, QuantType

# Step 1: Quantize (one-time, do offline)
quantize_dynamic("hi/model.onnx", "hi/model_int8.onnx",
                 weight_type=QuantType.QInt8)

# Step 2: Load quantized model
session = ort.InferenceSession("hi/model_int8.onnx",
    providers=["CPUExecutionProvider"])  # or TensorrtExecutionProvider

# Step 3: NeMo-compatible mel preprocessing
def nemo_mel(audio, sr=16000, n_mels=80):
    audio = np.concatenate([audio[:1], audio[1:] - 0.97 * audio[:-1]])
    mel = librosa.feature.melspectrogram(y=audio, sr=sr, n_fft=512,
          hop_length=160, win_length=400, n_mels=n_mels,
          fmin=0, fmax=8000, norm="slaney", power=2.0)
    log_mel = np.log(mel + 2**-24).astype(np.float32)
    mean = log_mel.mean(axis=1, keepdims=True)
    std  = log_mel.std(axis=1, ddof=1, keepdims=True) + 1e-5
    return ((log_mel - mean) / std)[np.newaxis]  # [1, 80, T]

mel = nemo_mel(audio_array)
logits = session.run(None, {
    "audio_signal": mel,
    "length": np.array([mel.shape[2]], dtype=np.int64)
})[0]
# CTC greedy decode → transcript string
```

**English fallback:**
```python
from faster_whisper import WhisperModel
model_en = WhisperModel("tiny", device="cpu", compute_type="int8")
# Model size: ~39MB, latency: ~100ms for 3s audio on Cortex-A78
segments, _ = model_en.transcribe("command.wav", language="en",
                                   beam_size=1, vad_filter=True)
```

**Qualcomm NPU path:** `qualcomm/Whisper-Small-Quantized` (w8a16 QNN format) — encoder 157–391ms on Snapdragon NPU.

### 4.3 Command Classification

For GarudaOne's 5–8 primary commands, use keyword matching first:

```python
COMMAND_KEYWORDS = {
    "en": {
        "RECORD_START": ["start recording", "record", "shoot", "action"],
        "RECORD_STOP":  ["stop recording", "cut", "stop"],
        "LAND":         ["land", "come down", "return"],
        "RTH":          ["come home", "return home", "go home"],
        "SWITCH_ORBIT": ["orbit", "circle around", "go around"],
        "SWITCH_CHASE": ["follow me", "chase", "track me"],
        "SWITCH_REVEAL": ["reveal shot", "pull back", "rise up"],
    },
    "hi": {
        "RECORD_START": ["रिकॉर्डिंग शुरू", "रिकॉर्ड करो", "शूट करो"],
        "LAND":         ["उतरो", "नीचे आओ", "लैंड करो"],
        # ... 10 languages × 8 commands
    }
}
```

**Semantic fallback:** `sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2` (118MB, ONNX)

---

## PART 5 — GESTURE RECOGNITION

### 5.1 Pipeline

```
Camera frame (30fps) → MediaPipe Hands Lite → 21 keypoints → Graph Transformer → Command
```

```python
import mediapipe as mp
import numpy as np

mp_hands = mp.solutions.hands
hands = mp_hands.Hands(
    static_image_mode=False,
    max_num_hands=2,
    min_detection_confidence=0.7,
    min_tracking_confidence=0.5,
    model_complexity=0      # Lite model: ~7ms CPU, 3ms GPU
)

# Keypoint buffer for temporal gesture recognition
keypoint_buffer = []  # 30 frames of 21×3 landmarks

def classify_gesture(landmarks_sequence):
    # Input shape: [T=30, 21, 3] → Graph Transformer → class
    # Pre-trained on HaGRIDv2 (1M images, 33 gesture classes)
    # Custom GarudaOne gestures registered via 1-demo MAML (arxiv:2402.08420)
    pass
```

### 5.2 GarudaOne Gesture Vocabulary

| Gesture | Command | MAML Training |
|---|---|---|
| ✋ Open palm (static) | HOVER / STOP | 1 demo |
| ✊ Fist (static) | EMERGENCY LAND | 1 demo |
| 👋 Wave left-right | FOLLOW ME (chase mode) | 1 demo |
| 🔄 Circular finger trace | ORBIT mode | 1 demo |
| 👆→ Point + pull back | REVEAL shot | 1 demo |
| 🤏 Pinch + expand | ZOOM / change distance | 1 demo |
| 🛑 Two palms facing out | HARD STOP (emergency) | 1 demo |
| 📸 Finger-gun pose | START/STOP RECORDING | 1 demo |

**Training dataset:** `ai-forever/HaGRIDv2` (1M+ images, 33 classes) for pre-training, then MAML fine-tune on above gestures with 1 demo each.

---

## PART 6 — PRE-FLIGHT SCENE INTELLIGENCE (HITLoop)

### 6.1 360° Environment Scanning — Fly360 Architecture

```python
class PreFlightScanner:
    def __init__(self):
        self.depth_model = load_depth_v2_small_trt()  # TensorRT engine
        self.voxel_grid = VoxelGrid(resolution=0.15, extent=50)  # 50m × 50m
    
    def scan(self, drone):
        # Tier 1: Ascend to scout altitude
        drone.ascend_to(altitude=8.0)  # meters
        
        # Tier 2: 360° yaw sweep (6 × 60° positions, panoramic depth)
        for yaw_angle in range(0, 360, 60):
            drone.set_yaw(yaw_angle)
            frame = drone.capture()
            depth = self.depth_model.infer(frame)   # Depth-Anything-V2-Small
            self.voxel_grid.update(depth, drone.pose)
        
        # Tier 3: Identify safe corridors, lighting zones, subject position
        corridors = self.find_safe_corridors(self.voxel_grid)
        light_quality = self.assess_lighting(frames)  # CLIP-IQA
        
        return SceneMap(corridors=corridors, light_quality=light_quality,
                       voxel_grid=self.voxel_grid)
```

### 6.2 Shot Generation — DVGFormer

**Model:** `yunzhong-hou/DVGFormer`
**Dataset:** `yunzhong-hou/DroneMotion-99k` (99K real drone trajectories)

```python
import torch
from src.models import DVGFormerModel

model = DVGFormerModel.from_pretrained('yunzhong-hou/DVGFormer')
model = model.to('cuda').to(torch.bfloat16)

# Generate N shot candidates from scene depth + text description
shot_types = ["cinematic orbit", "low chase reveal", "high pull-back", "coastal flythrough"]
candidates = []

for shot_type in shot_types:
    trajectory = model.generate(
        depth_frame=scene_depth_frame,
        text_prompt=shot_type,
        num_steps=50,
        temperature=0.8
    )
    candidates.append(trajectory)
```

### 6.3 Shot Quality Ranking — CLIP-IQA (Edge) / Q-Align (Pre-flight)

```python
# FAST: CLIP-IQA for on-drone real-time scoring (~10ms/frame on GPU)
from torchmetrics.functional.multimodal import clip_iqa
scores = clip_iqa(rendered_frames, prompts=["cinematic quality"])

# THOROUGH: OneAlign for pre-flight ranking (run on phone/cloud, ~400ms)
from transformers import AutoModelForCausalLM
model = AutoModelForCausalLM.from_pretrained(
    "q-future/one-align", trust_remote_code=True,
    torch_dtype=torch.float16, device_map="auto"
)
for candidate_path in shot_candidates:
    rendered = render_path_frames(candidate_path, scene_splat)
    score = model.score(rendered, task_="aesthetics", input_="video")
    candidate_path.aesthetic_score = score

# Return top-3 sorted by aesthetic score
top_shots = sorted(shot_candidates, key=lambda x: x.aesthetic_score, reverse=True)[:3]
```

### 6.4 Director's Preview — 3D Gaussian Splatting

```python
# Build 3DGS from 5-min aerial survey at start of session
# Then render real-time preview of any planned trajectory

# Step 1: Run 3DGS on captured survey frames
# github.com/graphdeco-inria/gaussian-splatting
# python train.py -s ./survey_images --model_path ./scene_splat

# Step 2: SplaTraj — optimize trajectory through scene
# arxiv:2410.06014 — cost terms:
#   visibility(subject) + clearance(obstacles) + smooth_vel + aesthetic_angle
# Output: B-spline trajectory that avoids obstacles and maximizes subject visibility

# Step 3: Real-time render for phone preview (via WebRTC to companion app)
# 3DGS real-time renderer: 30fps at 1080p on phone GPU (iPhone 15 / Android flagship)
```

**"Change the light" preview:**
```python
# Simulate different lighting using DiffusionLight (arxiv:2312.09168)
# Estimates HDR environment map from single frame
# Re-render 3DGS with different sun angle → shows how shot looks in 30min
from diffusionlight import LightEstimator
estimator = LightEstimator()
current_envmap = estimator.estimate(scene_frame)
future_envmap = rotate_sun_by_degrees(current_envmap, degrees=15)  # 30min = ~7.5° sun movement
preview_future = render_splat_with_envmap(scene_splat, trajectory, future_envmap)
```

---

## PART 7 — SHOT MEMORY & CREATOR STYLE LEARNING

### 7.1 Session Data Logging

Every flight logs:
```json
{
  "session_id": "uuid",
  "creator_id": "user_hash",
  "shots": [
    {
      "trajectory": [[x,y,z,qw,qx,qy,qz], ...],  // 10Hz pose stream
      "shot_type": "orbit",                          // CameraBench classifier output
      "aesthetic_score": 4.2,                        // Q-Align rating
      "creator_rating": 5,                           // explicit thumbs up/down
      "subject_distance_avg": 4.5,                   // meters
      "flight_speed_avg": 2.1,                       // m/s
      "altitude": 6.0,                               // meters
      "environment": "coastal_beach",
      "duration_seconds": 12
    }
  ]
}
```

### 7.2 Creator Fingerprint Model

Based on PAMELA (arxiv:2604.07427):

```python
class CreatorFingerprint:
    """
    Builds a personalized style model from the creator's shot history.
    Uses SigLIP2 embeddings + lightweight MLP preference predictor.
    """
    def __init__(self, creator_id):
        self.creator_id = creator_id
        self.embedding_model = SigLIP2()  # Frozen, 400M params
        self.preference_head = MLP(in=1152, hidden=256, out=1)  # Tiny, trainable
        self.shot_history = load_history(creator_id)
    
    def update_fingerprint(self, new_shots):
        # After each session, update preference head with new shots
        # Training: MSE on creator_rating score, 10 gradient steps
        self.preference_head.update(new_shots, lr=1e-4)
    
    def score_candidate_path(self, trajectory_render):
        # Predict how much THIS creator will like this specific shot
        embedding = self.embedding_model(trajectory_render)
        return self.preference_head(embedding)  # [1.0, 5.0]
    
    def get_style_summary(self):
        # ViPer-style LLM extraction of natural language preferences
        return llm.extract_preferences(self.shot_history)
        # → "Prefers low-altitude (3-5m), slow orbits (1.5m/s), golden hour light,
        #    wide subjects (4-6m distance), 12-15s duration shots"
```

### 7.3 "Do It Again" — Exact Shot Replay

```python
class ShotReplay:
    def __init__(self, shot_id):
        self.trajectory = load_trajectory(shot_id)    # B-spline from logged session
        self.splat_map = load_splat_map(shot_id)      # 3DGS from that session
        self.localizer = MonoGS()                     # Visual relocalization
    
    def replay(self, drone):
        # Step 1: Visual relocalization against stored 3DGS map
        current_pose = self.localizer.localize(drone.frame, self.splat_map)
        
        # Step 2: Compute alignment transform (new location → original frame)
        T_align = compute_transform(current_pose, self.trajectory[0])
        
        # Step 3: Execute trajectory with live MPC correction
        for waypoint in self.trajectory:
            adjusted_wp = T_align @ waypoint
            drone.fly_to(adjusted_wp, feed_controller=True)
            # MPC corrects for wind/environment deviations continuously
        
        # Expected accuracy: ±0.3–0.5m position, GPS+RTK fallback for <0.1m
```

---

## PART 8 — GARUDAPIN HARDWARE & FIRMWARE

### Hardware Specification

```
MCU:          Nordic nRF5340 (dual-core: app + net)
UWB:          Qorvo DW3000 via SPI (TWR responder + PDoA angle reporting)
IMU:          ICM-42688-P 6-DOF @ 200Hz (accelerometer + gyroscope)
BLE radio:    nRF5340 integrated (CTE beacon @ 10Hz, connectionless)
Button:       GPIO → emergency stop → BLE advertisement flag bit
Battery:      50mAh LiPo → ~1h continuous / ~8h duty-cycled
Weight target: < 8g total (PCB + battery + clip housing)
Form factor:  Clip-on, 30×20×8mm
```

### UWB Performance (DW3000)

| Metric | LOS | NLOS |
|---|---|---|
| Ranging accuracy (DS-TWR) | **±10 cm** | ±30–50 cm |
| After Transformer CIR correction | — | **±40 cm** |
| Update rate | 100 Hz | 100 Hz |
| Range | 300m+ outdoor | 60m indoor |
| Active current | 35 mA @ 3.3V | — |
| Crowd disambiguation | Unique 64-bit IEEE 802.15.4a ID | Zero collision |

### BLE 5.1 AoA (Backup Layer)

```
Angle accuracy: ±2–5° 
Position accuracy: 30–50 cm (LOS), ~80 cm (NLOS)
Update rate: 10–20 Hz
Pairing: Connectionless CTE — ZERO pairing time
Drone antenna array: 4 antennas, λ/2 ≈ 2.5cm spacing at 6.5GHz
Algorithm: MUSIC/ESPRIT in Nordic SDK
```

### UWB + IMU Fusion (Unscented Kalman Filter)

```python
from filterpy.kalman import UnscentedKalmanFilter as UKF
import numpy as np

# 9-state UKF: position (3) + velocity (3) + acceleration (3)
kf = UKF(dim_x=9, dim_z=1, dt=0.005, fx=motion_model, hx=uwb_range_model)
kf.x = np.array([x0, y0, z0, 0, 0, 0, 0, 0, 0])
kf.Q = Q_discrete_white_noise(dim=3, dt=0.005, var=0.1, block_size=3)
kf.R = np.diag([0.01])    # UWB range variance = (10cm)²

# Fusion loop:
# IMU predict @ 200Hz → fast position propagation
# UWB range correct @ 100Hz → absolute position anchor
# BLE AoA correct @ 10Hz → angle/bearing refinement

def uwb_imu_loop():
    while True:
        accel = imu.read()                        # 200Hz
        kf.predict(u=accel)
        
        if uwb.new_measurement():                 # 100Hz
            kf.update(z=[uwb.range])
        
        if ble.new_aoa():                         # 10Hz
            kf.update_bearing(ble.angle)          # custom bearing update
        
        # Output to drone flight controller
        send_to_drone(position=kf.x[:3], velocity=kf.x[3:6])
```

### Activity Recognition on GarudaPin MCU

```c
// nRF5340 Application Core (Cortex-M33, 64MHz)
// Model: 1D-ResNet18 (SSL pre-trained on 700K person-days, OxWearables)
// Quantized to INT8: ~2MB, fits in nRF5340 flash (1MB) → store in external QSPI

// Change-detection gate (arxiv:2605.00870): ~16kFLOPs
// Reduces HAR invocations by 67% → battery life 3× improvement

typedef enum {
    ACTIVITY_STATIONARY = 0,
    ACTIVITY_WALKING,
    ACTIVITY_RUNNING,
    ACTIVITY_CYCLING,
    ACTIVITY_UNKNOWN
} activity_state_t;

// BLE advertisement payload (7 bytes)
// [UWB_ID(2B) | activity_state(1B) | velocity_est(2B) | battery(1B) | flags(1B)]
// flags: bit 0 = emergency_stop, bit 1 = pin_removed, bit 2 = button_pressed
```

### Emergency Stop Protocol

```
Hardware path (< 5ms):
  Button press → GPIO interrupt → nRF5340 net core
  → BLE CTE packet with flags.emergency_stop = 1
  → Drone BLE receiver → interrupt → FC UART emergency stop command
  → Motor throttle → 0%

Software path (< 25ms):
  BLE advertisement interval 20ms → drone receives within 20ms
  → Python watchdog → MAVLink EMERGENCY_STOP
  → FC motor kill
```

---

## PART 9 — ENVIRONMENTAL INTELLIGENCE

### 9.1 Golden Hour Detection

```python
from astral import LocationInfo
from astral.sun import sun, elevation
from torchmetrics.functional.multimodal import clip_iqa
import datetime

class GoldenHourMonitor:
    def __init__(self, lat, lon, user_threshold=4.0):
        self.location = LocationInfo(latitude=lat, longitude=lon)
        self.user_threshold = user_threshold  # Q-Align score threshold
        
    def check_now(self, current_frame=None):
        # Tier 1: Astronomical calculation (deterministic, 0ms)
        sun_el = elevation(self.location.observer, datetime.datetime.now())
        is_golden_window = 0 <= sun_el <= 6     # golden hour
        is_blue_window   = -6 <= sun_el < 0     # blue hour
        
        if not (is_golden_window or is_blue_window):
            return None  # Not in interesting window
        
        # Tier 2: Actual image quality check
        if current_frame:
            score = clip_iqa(current_frame, prompts=["golden light quality"])
            if score > self.user_threshold:
                return Alert(
                    type="GOLDEN_HOUR",
                    message=f"Light quality {score:.1f}/5 — shoot NOW",
                    urgency="HIGH"
                )
    
    def predict_next_window(self):
        # Return next golden hour windows for today
        s = sun(self.location.observer, date=datetime.date.today())
        return {
            "dawn_golden_start": s['dawn'],
            "sunrise": s['sunrise'],
            "sunset": s['sunset'],
            "dusk_golden_end": s['dusk']
        }
```

### 9.2 Weather Window Prediction

```python
import requests

class WeatherWindowPredictor:
    def get_optimal_windows(self, lat, lon, shot_type):
        # OpenWeatherMap hourly forecast (free tier)
        forecast = self.fetch_owm_hourly(lat, lon)
        
        windows = []
        for hour in forecast:
            score = self.score_conditions(hour, shot_type)
            if score > 0.7:
                windows.append({
                    "time": hour['dt'],
                    "wind_speed": hour['wind_speed'],  # m/s
                    "cloud_cover": hour['clouds'],       # 0-100%
                    "score": score
                })
        
        return sorted(windows, key=lambda x: x['score'], reverse=True)[:3]
    
    def score_conditions(self, conditions, shot_type):
        # Sub-250g drone limits: wind < 8 m/s operational, < 5 m/s ideal
        wind_ok = conditions['wind_speed'] < 5.0
        # Clear sky for aerial = better; overcast for portrait = better
        cloud_ok = conditions['clouds'] < 40 if shot_type in ['landscape', 'reveal'] \
                   else conditions['clouds'] < 80
        return (wind_ok * 0.6) + (cloud_ok * 0.4)
```

---

## PART 10 — CROWD-SOURCED ENVIRONMENT MAP SHARING

### Architecture

```python
class EnvironmentMapNetwork:
    """
    Peer-to-peer spatial map sharing between GarudaOne units.
    Privacy: Only obstacle voxel grids shared, never footage or identity.
    Protocol: Wi-Fi Direct (P2P) or Bluetooth mesh for local sharing.
    """
    
    def share_map(self, voxel_grid, session_id):
        # Serialize: 50m×50m×20m at 0.15m resolution = ~740KB compressed
        map_payload = {
            "schema_version": "1.0",
            "location": self.gps.get_coarse_location(),   # ±50m precision
            "timestamp": time.time(),
            "voxel_grid": voxel_grid.compress_lz4(),       # obstacle data only
            "safe_corridors": voxel_grid.get_corridors(),
            "no_fly_zones": self.geofence.export(),
            # NO footage, NO person positions, NO faces, NO re-ID data
        }
        # Broadcast via Wi-Fi Direct to nearby GarudaOne units
        self.wifi_direct.broadcast(map_payload)
    
    def receive_map(self, map_payload):
        # Validate: map is recent (< 2h) and within 500m
        if self.validate_map(map_payload):
            self.cached_maps[map_payload['location']] = map_payload
            return True  # Skip pre-flight scan if map available
```

---

## PART 11 — SHOT CLASSIFICATION MODEL

### Camera Motion Taxonomy (CameraBench)

Fine-tune `chancharikm/qwen2.5-vl-7b-cam-motion` on GarudaOne-specific shots:

```python
from transformers import Qwen2VLForConditionalGeneration, AutoProcessor

model = Qwen2VLForConditionalGeneration.from_pretrained(
    "chancharikm/qwen2.5-vl-7b-cam-motion",
    torch_dtype=torch.bfloat16,
    device_map="auto"
)

# GarudaOne shot type mapping from CameraBench taxonomy:
GARUDA_SHOT_MAP = {
    "orbit": ["arc-CW", "arc-CCW"],
    "reveal": ["dolly-backward", "pedestal-up", "combined-reveal"],
    "flythrough": ["dolly-forward", "fast-forward"],
    "chase": ["tail-tracking", "dynamic-follow"],
    "pull_back": ["dolly-backward-fast"],
    "orbit_rise": ["arc-CW+pedestal-up"],
    "low_chase": ["tail-tracking+low-altitude"],
}
```

---

## PART 12 — MODEL TRAINING REQUIREMENTS

### Fine-Tuning Jobs Required (Priority Order)

| # | Model | Task | Dataset | Hardware | Estimated Time |
|---|---|---|---|---|---|
| 1 | YOLO11s | Aerial person detection | VisDrone2019-DET | a10g-large | ~4h |
| 2 | OSNet x0.25 | Aerial person re-ID | P-DESTRE + Market1501 | a10g-large | ~6h |
| 3 | IndicConformer-120M | INT8 quantization | None (post-training) | CPU | ~30min |
| 4 | openWakeWord custom | "Hey Garuda" detection | TTS-generated | CPU | ~2h |
| 5 | DVGFormer (optional) | Drone-specific shot types | DroneMotion-99K subset | a100-large | ~12h |
| 6 | CameraBench VLM | GarudaOne shot taxonomy | 200 labeled drone clips | a10g-large | ~3h |
| 7 | HaGRIDv2 gesture | Custom drone gestures | HaGRIDv2 + 8 custom | a10g-large | ~4h |
| 8 | 1D-ResNet18 HAR | GarudaPin activity states | WISDM + PAMAP2 | a10g-small | ~2h |

### Key Training Datasets

| Dataset | Task | Link / ID |
|---|---|---|
| VisDrone2019-DET | Aerial object detection | `github.com/VisDrone/VisDrone-Dataset` |
| VisDrone2019-MOT | Aerial multi-object tracking | Same repo |
| P-DESTRE | Aerial person re-ID | `arxiv:2004.02782` |
| DroneMotion-99K | Drone trajectory generation | `yunzhong-hou/DroneMotion-99k` |
| CameraBench | Shot type classification | `syCen/CameraBench` |
| HaGRIDv2 | Hand gesture recognition | `ai-forever/HaGRIDv2` |
| Vistaar | Indian language ASR | AI4Bharat GitHub |
| WISDM | Activity recognition (HAR) | UCI ML Repository |
| PAMAP2 | Activity recognition (HAR) | UCI ML Repository |

---

## PART 13 — IMPLEMENTATION ROADMAP

### Phase 1 — Core Autonomy (Months 1–4)

| Week | Milestone | Key Model/System |
|---|---|---|
| 1–2 | Flight controller integration (PX4 + MAVLink) | STM32H7 / Pixhawk 6C Mini |
| 3–4 | Basic VIO + position hold | OpenVINS (CPU) |
| 5–6 | Person detection on drone | YOLO11n → YOLO11s (VisDrone fine-tuned) |
| 7–8 | ByteTrack tracking (no ReID) | boxmot library |
| 9–10 | BoT-SORT + CMC for moving camera | AirSLAM integration |
| 11–12 | Basic obstacle avoidance (depth) | Depth-Anything-V2-Small TensorRT |
| 13–14 | GarudaPin UWB integration (DW3000) | Qorvo QMatter SDK |
| 15–16 | End-to-end subject tracking test | Full tracking stack validation |

### Phase 2 — Shot Intelligence (Months 5–8)

| Week | Milestone | Key Model/System |
|---|---|---|
| 17–18 | Basic shot modes (orbit, chase, reveal, pull-back) | Trajectory templates + EGO-Planner |
| 19–20 | Voice commands (English) | faster-whisper tiny INT8 + openWakeWord |
| 21–22 | Voice commands (Hindi + 3 South Indian languages) | IndicConformer-120M ONNX INT8 |
| 23–24 | Pre-flight 360° scan + voxel map | Fly360 architecture + AirSLAM |
| 25–26 | DVGFormer shot generation | `yunzhong-hou/DVGFormer` |
| 27–28 | Shot quality ranking (CLIP-IQA) | torchmetrics CLIP-IQA |
| 29–30 | Gesture recognition (8 commands) | MediaPipe + Graph Transformer |
| 31–32 | Director's preview (3DGS) | gaussian-splatting + SplaTraj |

### Phase 3 — Creator Intelligence (Months 9–12)

| Week | Milestone | Key Model/System |
|---|---|---|
| 33–34 | Shot classification + session logging | CameraBench VLM fine-tuned |
| 35–36 | Creator fingerprint (ViPer phase) | LLM preference extraction |
| 37–38 | PAMELA-style preference model | SigLIP2 + MLP per user |
| 39–40 | "Do it again" replay (B-spline + MonoGS) | MonoGS visual relocalization |
| 41–42 | Golden hour alerts + weather window | astral + OpenWeatherMap + CLIP-IQA |
| 43–44 | Environment map sharing (Wi-Fi Direct) | Custom P2P protocol |
| 45–46 | Multi-subject tracking + group mode | Multi-target UWB + OC-SORT |
| 47–48 | Full system integration test | End-to-end creator workflow |

---

## PART 14 — COMPLETE MODELS REFERENCE TABLE

| Feature | Model | HF Hub / Source | Params | Size | Edge Latency |
|---|---|---|---|---|---|
| **Person detection** | YOLO11s (VisDrone FT) | `Ultralytics/YOLO11` | 9.4M | 18.4MB | ~15ms Orin Nano |
| **Multi-object tracking** | BoT-SORT (CMC mode) | `github.com/mikel-brostrom/boxmot` | — | 1MB | ~5ms overhead |
| **Person re-ID** | OSNet x0.25 | `KaiyangZhou/deep-person-reid` | 0.2M | ~1MB | ~3ms Orin |
| **Monocular depth** | Depth-Anything-V2-Small | `depth-anything/Depth-Anything-V2-Small-hf` | 24.8M | ~100MB | ~25ms Orin (TRT) |
| **Visual SLAM** | AirSLAM | `github.com/sair-lab/AirSLAM` | CNN+GNN | ~989MB VRAM | 40Hz Orin |
| **SLAM (CPU fallback)** | OpenVINS | `docs.openvins.com` | EKF | ~120MB RAM | 30Hz ARM |
| **Path planning** | EGO-Planner v2 | `github.com/HKUST-Aerial-Robotics/ego-planner-swarm` | — | <5MB | <5ms CPU |
| **Shot generation** | DVGFormer | `yunzhong-hou/DVGFormer` | ~100M | ~400MB | ~300ms (pre-flight) |
| **Shot quality** | CLIP-IQA (edge) | `pip install torchmetrics[multimodal]` | ~150M | ~600MB | ~10ms GPU |
| **Shot quality** | OneAlign (pre-flight) | `q-future/one-align` | ~7B | ~14GB | ~400ms/frame |
| **3D scene preview** | 3DGS + SplaTraj | `github.com/graphdeco-inria/gaussian-splatting` | — | Scene-dependent | 30fps render |
| **Shot classifier** | Qwen2.5-VL-7B-CamMotion | `chancharikm/qwen2.5-vl-7b-cam-motion` | 7B | 14GB | Pre-flight only |
| **Wake word** | openWakeWord custom | `davidscripka/openwakeword` | <1M | <1MB | <10ms/chunk |
| **ASR Indian langs** | IndicConformer-120M INT8 | `trysem/indicconformer-120m-onnx` | 120M | ~120MB/lang | <150ms |
| **ASR English** | Whisper-tiny INT8 | `mukowaty/faster-whisper-int8` | 39M | ~39MB | ~100ms |
| **Language ID** | MMS-LID-126 | `facebook/mms-lid-126` | — | ~2MB | <10ms |
| **NLU intent** | MiniLM-L12 multilingual | `sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2` | 118M | 118MB | ~20–50ms |
| **Gesture detection** | MediaPipe Hands Lite | `mediapipe` | ~3.3M | ~7MB | ~7ms CPU |
| **Gesture classification** | Graph Transformer (MAML) | `arxiv:2402.08420` | ~5M | ~20MB | ~5ms |
| **Obstacle avoidance** | Fly360 policy (conv+LSTM) | `arxiv:2603.06573` | <5M | <20MB | ~5ms |
| **Shot replay** | MonoGS | `github.com/muskie82/monogs` | — | ~500MB VRAM | ~30Hz |
| **Creator style** | PAMELA (SigLIP2+MLP) | `arxiv:2604.07427` | SigLIP2+tiny | ~1.5GB | Pre-flight |
| **HAR on GarudaPin** | 1D-ResNet18 SSL | `github.com/OxWearables/ssl-wearables` | 11M | ~44MB | <5ms (MCU) |
| **Golden hour** | astral library (deterministic) | `pip install astral` | N/A | <1MB | <1ms |

---

## PART 15 — TECHNOLOGY RISK MATRIX

| Risk | Severity | Mitigation |
|---|---|---|
| Sub-250g weight budget overrun | HIGH | Ambarella CV52S (3W, ~5g) instead of full Orin; no gimbal |
| Orin Nano too hot (10W) in flight | MEDIUM | Thermal throttling mode; reduce compute during stable hover |
| IndicConformer INT8 WER degradation | MEDIUM | Validate on held-out Vistaar test set; keep FP16 fallback |
| VisDrone fine-tuning insufficient for specific shoot env | LOW | Collect 200–500 shots in real locations, do domain fine-tune |
| DW3000 NLOS accuracy in crowd | MEDIUM | Transformer CIR correction (arxiv:2507.03523) → 40cm |
| 3DGS build time too long for field use | MEDIUM | Instantsplat (3DGS in <30s from sparse views, 2024) |
| OSNet aerial re-ID degradation (top-down view) | HIGH | Fine-tune mandatory on P-DESTRE; no workaround |
| Gesture recognition confusion in bright sunlight | LOW | IR-cut filter + exposure normalization before MediaPipe |
| DVGFormer trajectory quality for India-specific scenes | MEDIUM | Fine-tune on DataDoP + collected India footage |
| Battery life < 15min with full AI stack active | HIGH | Dynamic compute gating: reduce depth model FPS during stable tracking |

---

## SUMMARY: THE FULL STACK

```
GarudaOne + GarudaPin — Complete AI Stack

┌─ GarudaPin (wearable) ──────────────────────────────────────┐
│  nRF5340 + DW3000 (UWB ±10cm @ 100Hz) + ICM-42688-P (IMU)  │
│  Activity: 1D-ResNet18 HAR (SSL-pretrained OxWearables)      │
│  BLE CTE: angle @ 10Hz (connectionless, 0s pairing)         │
│  Emergency: GPIO → BLE flag → drone motor kill < 25ms        │
└─────────────────────────────────────────────────────────────┘
           │ UWB range + BLE angle + activity state
┌─ GarudaOne Drone ───────────────────────────────────────────┐
│                                                               │
│  ┌─ Plane A: Flight Control ─────────────────────────────┐  │
│  │  STM32H7 / PX4 → Motor PWM → PID → MAVLink            │  │
│  │  Sensors: IMU, barometer, GPS, optical flow            │  │
│  └────────────────────────────────────────────────────────┘  │
│                   ↑ Velocity setpoints / waypoints            │
│  ┌─ Plane B: AI Vision Stack (Jetson Orin Nano 8GB) ─────┐  │
│  │                                                         │  │
│  │  TRACKING:   YOLO11s → BoT-SORT+CMC → OSNet re-ID     │  │
│  │              UKF fusion with GarudaPin UWB/BLE         │  │
│  │                                                         │  │
│  │  PERCEPTION: Depth-Anything-V2-Small (TRT FP16)        │  │
│  │              AirSLAM (40Hz VIO, 3D map)                │  │
│  │              Fly360 omnidirectional avoidance policy    │  │
│  │                                                         │  │
│  │  PLANNING:   DVGFormer shot generation                  │  │
│  │              EGO-Planner v2 local trajectory (<5ms)     │  │
│  │              CLIP-IQA real-time quality scoring         │  │
│  │                                                         │  │
│  │  VOICE:      openWakeWord → IndicConformer-120M INT8    │  │
│  │              + Whisper-tiny INT8 (English path)         │  │
│  │              Regex intent → MAVLink command             │  │
│  │                                                         │  │
│  │  GESTURE:    MediaPipe Hands Lite → Graph Transformer   │  │
│  │                                                         │  │
│  │  STYLE:      CreatorFingerprint (PAMELA / ViPer)        │  │
│  │              Shot logger → B-spline memory              │  │
│  └─────────────────────────────────────────────────────────┘  │
│                                                               │
│  ┌─ Pre-flight (Phone companion app) ────────────────────┐  │
│  │  3DGS scene build → SplaTraj path optimization         │  │
│  │  DVGFormer shot candidates → OneAlign ranking          │  │
│  │  DiffusionLight "future light" preview                 │  │
│  │  Weather window prediction (OpenWeatherMap + astral)   │  │
│  └─────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────┘
```

---

---

## PART 16 — VLA & WORLD ACTION MODELS FOR DRONE CINEMATOGRAPHY

> This section maps the VLA/WAM research frontier (indoor manipulation dominated) to aerial cinematography use-cases. The core insight: **drones are embodied agents navigating 3D space with camera-as-effector** — the same world-modeling and action-generation principles apply, but the action space is SE(3) camera pose instead of joint angles.

### 16.1 EgoDex / EgoScale — Learning Shots from Human Egocentric Video

**Paper:** *EgoScale: Scaling Dexterous Manipulation with Diverse Egocentric Human Data* (arxiv:2505.11709 / 2602.16710) / *EgoDex* (Apple, arxiv:2505.11709)
**Relevance:** ⭐⭐⭐⭐⭐ HIGHEST for GarudaOne

**Why it matters:** EgoDex/EgoScale learns from **egocentric human video** — the exact perspective a creator has when walking, running, cycling. For GarudaOne, this means:
- **Zero-shot shot imitation:** Train a world model on millions of hours of human egocentric footage (walking through a forest, running on a beach, cycling downhill). The drone learns *what a good follow-shot feels like* from human perspective without any drone flight data.
- **Activity-conditioned trajectories:** EgoScale's activity labels map directly to GarudaPin's HAR output (WALKING → slow follow, RUNNING → lead distance, CYCLING → wide chase).

**Implementation path for GarudaOne:**
```python
# Pre-train a video world model on EgoDex / Ego4D / HumanNet
# Input: past 2s of drone footage + text prompt ("cinematic follow")
# Output: next camera SE(3) pose (x,y,z,quat) + velocity
# Fine-tune on 1K labeled drone shots (vs 100K required from scratch)
```

**Dataset links:** `Ego4D` (3,000h egocentric), `HumanNet` (1M hours human-centric video), `EgoDex` (dexterous + locomotion egocentric)

---

### 16.2 VoxPoser — Language → 3D Value Map → Trajectory

**Paper:** *VoxPoser: Composable 3D Value Maps for Robotic Manipulation with Language Models* (arxiv:2307.05973)
**Relevance:** ⭐⭐⭐⭐⭐ HIGHEST for GarudaOne

**Why it matters:** VoxPoser generates **3D value maps from natural language** — "orbit the tower clockwise at 8m altitude while keeping the subject centered." The LLM decomposes this into:
1. Obstacle avoidance value (negative inside voxel obstacles)
2. Subject visibility value (positive along line-of-sight to subject)
3. Cinematic quality value (positive for smooth arc trajectories)
4. Altitude constraint value (positive at 6–10m range)

**Drone adaptation:**
```python
# GPT-4 / Qwen2.5-VL parses: "orbit the tower clockwise at 8m"
# → Generates Python reward functions (as in Code-as-Policies)
# → Composes 3D voxel value map V(x,y,z) from AirSLAM occupancy
# → Gradient ascent on V(x,y,z) → trajectory via EGO-Planner v2
# This replaces hand-coded shot templates with LLM-composed rewards
```

**Code-as-Policies** (arxiv:2209.07753) is the enabler: the LLM writes the reward-composition code at runtime, not just selects a pre-defined shot.

---

### 16.3 Diffusion Policy / Diffusers — Trajectory Planning as Diffusion

**Paper:** *Diffusion Policy: Visuomotor Policy Learning via Action Diffusion* (arxiv:2303.04137) / *Planning with Diffusion for Flexible Behavior Synthesis* (arxiv:2205.09991)
**Relevance:** ⭐⭐⭐⭐⭐

**Why it matters for drone cinematography:**
Diffusion models generate **smooth, multi-modal trajectories** conditioned on scene context. For GarudaOne:
- **Shot trajectory diffusion:** Train a diffusion model on 99K drone trajectories (DroneMotion-99K). Condition on: current depth map + text prompt ("coastal reveal") + subject position.
- **Multimodal output:** The diffusion model captures *all plausible cinematic paths* through a scene, not just one. Sample 16 trajectories → rank with CLIP-IQA → present top-3 to creator.
- **Constraint satisfaction:** Hard constraints (obstacles, geofence) can be injected as classifier-free guidance during sampling.

```python
# DroneTrajectoryDiffusion — inspired by Diffusion Policy
from diffusers import DDPMScheduler, UNet2DModel

# Condition: depth_map (H×W) + text_embedding (768D) + subject_pos (3D)
# Action: sequence of SE(3) waypoints (T×7) as denoising target
# Training: 99K trajectories from DroneMotion-99K + EgoDex locomotion data

scheduler = DDPMScheduler(num_train_timesteps=100)
model = UNet1DConditionModel(...)  # 1D temporal UNet over trajectory waypoints

# Inference: denoise from random noise → smooth, scene-aware trajectory
trajectory = denoise(condition={depth, text, subject_pos}, num_samples=16)
top3 = rank_by_aesthetic(trajectory, scene_splat)  # CLIP-IQA scoring
```

---

### 16.4 Cosmos / Cosmos Policy — NVIDIA World Foundation Model for Physical AI

**Paper:** *Cosmos World Foundation Model Platform for Physical AI* (arxiv:2501.03575) / *Cosmos Policy: Fine-Tuning Video Models for Visuomotor Control and Planning* (arxiv:2601.16163)
**Relevance:** ⭐⭐⭐⭐

**Why it matters:** Cosmos is a **7B-parameter video world model** pre-trained on 9,000+ hours of physical-world video (driving, drone, indoor, outdoor). It predicts future video frames given current frame + action.

**GarudaOne application:**
```python
# Use Cosmos as a "flight simulator" for shot planning:
# 1. Current drone camera frame → Cosmos predicts next 3s of video
#    for any candidate trajectory
# 2. Use predicted video for pre-flight preview (no 3DGS needed)
# 3. Fine-tune Cosmos-Policy on drone trajectory data for control

# Pre-flight "what-if":
# "What if I fly through this corridor at 3m/s?"
# → Cosmos generates predicted 3s video → Q-Align scores it → approve/reject
```

**Size challenge:** Cosmos-7B requires ~14GB VRAM. For sub-250g, run inference on phone companion app (offload), or use **Cosmos-1B-Test** variant. Jetson Orin Nano 8GB can run 1B model at ~5fps.

---

### 16.5 DreamZero / World-VLA-Loop — Zero-Shot World Action Models

**Paper:** *DreamZero: World Action Models are Zero-shot Policies* (arxiv:2602.15922) / *World-VLA-Loop: Closed-Loop Learning of Video World Model and VLA Policy* (arxiv:2602.06508)
**Relevance:** ⭐⭐⭐⭐

**DreamZero insight:** A world model trained *only on video prediction* (no action labels) can be used as a zero-shot policy via "inverse dynamics" — given current state + goal state (next frame), infer the action that caused the transition.

**GarudaOne application:**
```python
# DreamZero for zero-shot shot styles:
# 1. Show the world model a reference video clip: "I want this smooth orbit style"
# 2. World model extracts latent action pattern from reference video
# 3. During flight, current frame + target next frame → inferred velocity command
# Zero training data needed for new shot styles — just show example video
```

**World-VLA-Loop:** Alternates between (a) improving world model from real flight video and (b) improving VLA policy using the updated world model. This is the **online learning loop** for GarudaOne's shot memory — each real flight improves both the world model and the policy.

---

### 16.6 3D-VLA / SpatialVLA — 3D-Aware Vision-Language-Action

**Paper:** *3D-VLA: A 3D Vision-Language-Action Generative World Model* (arxiv:2403.09631) / *SpatialVLA: Exploring Spatial Representations for Visual-Language-Action Model* (arxiv:2501.15830)
**Relevance:** ⭐⭐⭐⭐

**Why it matters:** 3D-VLA generates **3D-aware next frames** with voxel-aligned text grounding. For GarudaOne:
- Text prompt: "fly behind the tree, then reveal the lake" → 3D-VLA predicts the sequence of 3D-consistent frames + the camera trajectory that produces them.
- SpatialVLA's spatial representations (depth-aligned attention) improve generalization across different locations.
- Combined with 3DGS scene representation: 3D-VLA provides the " imagination engine" for HITLoop Tier 1 (pre-flight shot imagination).

---

### 16.7 DreamerV3 / DayDreamer — Model-Based RL for Physical Robots

**Paper:** *DreamerV3: Mastering Diverse Domains through World Models* (arxiv:2301.04104) / *DayDreamer: World Models for Physical Robot Learning* (arxiv:2206.14176)
**Relevance:** ⭐⭐⭐

**Why it matters:** DreamerV3 learns a **recurrent state-space world model** from pixels, then plans actions entirely inside the learned latent space. DayDreamer deployed this on a real quadruped robot (in 2022!).

**GarudaOne adaptation:**
- Learn world model from drone flight video (not just human video)
- Plan trajectories by imagined rollouts in latent space (much faster than 3DGS rendering)
- Use for **exploration**: when arriving at a new location, DreamerV3 explores to reduce model uncertainty, then switches to exploitation (shot execution)
- **Computational cost:** Recurrent world model is lightweight (~50M params) — feasible on Jetson Orin Nano.

---

### 16.8 TinyVLA / SmolVLA / PokeVLA — Efficient Edge VLA

**Papers:**
- *TinyVLA: Towards Fast, Data-Efficient Vision-Language-Action Models* (arxiv:2409.12514)
- *SmolVLA: A Vision-Language-Action Model for Affordable and Efficient Robotics* (arxiv:2506.01844) — HuggingFace LeRobot
- *PokeVLA: Empowering Pocket-Sized Vision-Language-Action Model* (arxiv:2604.20834)
**Relevance:** ⭐⭐⭐⭐⭐ for Edge Deployment

**Why it matters:** These are specifically designed for **resource-constrained deployment**:
- TinyVLA: ~100M params, runs at 10Hz on consumer GPU, data-efficient (1K demos)
- SmolVLA: built on SmolVLM (2B → 450M), open-source via LeRobot, fine-tuned on Open X-Embodiment
- PokeVLA: "Pocket-sized" — mobile-phone deployable with comprehensive world knowledge guidance

**GarudaOne path:** Fine-tune **SmolVLA** (open-source, 450M params, LeRobot ecosystem) on:
- EgoDex egocentric locomotion video (pre-training world understanding)
- DroneMotion-99K trajectory data (drone-specific action space)
- 500 creator-annotated shot examples (personalization)

Deployment target: **Jetson Orin Nano 8GB** — 450M param VLA should run at ~3–5Hz with TensorRT FP16.

---

### 16.9 OpenVLA-OFT — Fine-Tuning Recipes

**Paper:** *OpenVLA-OFT: Fine-Tuning Vision-Language-Action Models — Optimizing Speed and Success* (arxiv:2502.19645)
**Relevance:** ⭐⭐⭐⭐

**Key recipe for GarudaOne:** The paper shows that **full fine-tuning > LoRA** for VLA fine-tuning on new embodiments. Critical finding: when adapting a VLA trained on robot arms to a drone (completely different action space), LoRA underfits. Full fine-tuning of the action head + vision encoder is required.

**Implementation:**
```python
# Base model: OpenVLA (7B) or TinyVLA (100M) or SmolVLA (450M)
# Fine-tune strategy:
#   - Freeze LLM backbone (language understanding)
#   - Full fine-tune vision encoder (aerial imagery ≠ indoor robotics)
#   - Full fine-tune action head (SE(3) waypoints ≠ joint angles)
#   - Use DroneMotion-99K + EgoDex + 500 labeled creator shots
# Expected: 1K training steps sufficient for new embodiment
```

---

### 16.10 Unified Video Action Models (UVAM / UniVLA / GR-1)

**Papers:**
- *UVAM: Unified Video Action Model* (arxiv:2503.00200) ⭐
- *UniVLA: Learning to Act Anywhere with Task-centric Latent Actions* (arxiv:2505.06111)
- *GR-1: Unleashing Large-Scale Video Generative Pre-training for Visual Robot Manipulation* (arxiv:2312.13139)
**Relevance:** ⭐⭐⭐⭐

**Why it matters:** These models unify **video understanding** and **action generation** in one model. For GarudaOne:
- UVAM: A single transformer handles "understand the scene" (video encoder) and "plan the shot" (action decoder). No separate perception → planning pipeline.
- GR-1: Pre-trains on massive video generation (not just robot data), then fine-tunes for control. The video generation capability = Director's Preview engine.

**Implementation:** Use GR-1/UVAM architecture but with:
- Input: drone video stream + text prompt ("orbit the subject")
- Output: next camera SE(3) pose + predicted next-frame preview
- Pre-training data: Ego4D (egocentric) + AirSim/FlightGear synthetic drone footage

---

## PART 17 — UPDATED MODELS REFERENCE (VLA/WAM INCLUSIONS)

| Feature | Model | Source | Params | Size | Latency | GarudaOne Role |
|---|---|---|---|---|---|---|
| **Egocentric pre-training** | EgoDex / EgoScale | arxiv:2505.11709 | — | Dataset | N/A | Zero-shot shot style transfer from human video |
| **Language→3D trajectory** | VoxPoser | arxiv:2307.05973 | LLM-dependent | — | ~500ms | Natural language shot composition |
| **LLM action coding** | Code-as-Policies | arxiv:2209.07753 | GPT-4 / Qwen | — | ~1s | Runtime reward function generation |
| **Trajectory diffusion** | Diffusion Policy | arxiv:2303.04137 | ~100M | ~400MB | ~50ms | Multimodal cinematic trajectory sampling |
| **Video world model** | Cosmos-1B | arxiv:2501.03575 | 1B | ~2GB | ~200ms | Pre-flight "what-if" video prediction |
| **Video world model** | Cosmos-7B | arxiv:2501.03575 | 7B | ~14GB | ~1s | Phone-app preview generation |
| **Zero-shot policy** | DreamZero | arxiv:2602.15922 | — | World model | ~100ms | Imitate reference video style zero-shot |
| **Online learning loop** | World-VLA-Loop | arxiv:2602.06508 | VLM+WM | — | — | Continuous improvement from each flight |
| **3D-aware VLA** | 3D-VLA | arxiv:2403.09631 | ~3B | ~6GB | ~500ms | 3D-consistent shot imagination |
| **Spatial VLA** | SpatialVLA | arxiv:2501.15830 | ~1B | ~2GB | ~200ms | Cross-location generalization |
| **Model-based RL** | DreamerV3 | arxiv:2301.04104 | ~50M | ~200MB | ~20ms | Latent-space trajectory planning |
| **Edge VLA** | TinyVLA | arxiv:2409.12514 | ~100M | ~400MB | ~100ms | Resource-constrained VLA |
| **Edge VLA (HF)** | SmolVLA | arxiv:2506.01844 | ~450M | ~900MB | ~200ms | LeRobot ecosystem, open-source |
| **Pocket VLA** | PokeVLA | arxiv:2604.20834 | ~1B | ~2GB | ~300ms | Mobile-phone deployable |
| **VLA fine-tuning** | OpenVLA-OFT | arxiv:2502.19645 | Recipe | — | — | Full fine-tune > LoRA for new embodiment |
| **Unified video+action** | UVAM | arxiv:2503.00200 | ~1B | ~2GB | ~200ms | Single model for perception + control |
| **Video gen + control** | GR-1 | arxiv:2312.13139 | ~1B | ~2GB | ~200ms | Director's Preview + action decoder |

---

## PART 18 — RECOMMENDED VLA STACK FOR GARUDAONE

Based on the VLA/WAM research frontier, here is the updated recommended architecture integrating these advances:

```
Tier 0 — Foundation Pre-Training (Offline, once)
  Data: Ego4D (3,000h) + EgoDex + AirSim synthetic drone footage
  Model: UVAM / GR-1 architecture, 1B params
  Task: Video prediction + SE(3) action prediction pre-training

Tier 1 — Drone Embodiment Fine-Tuning (Offline, one-time)
  Data: DroneMotion-99K + 500 creator-annotated shots
  Model: Full fine-tune vision encoder + action head (OpenVLA-OFT recipe)
  Task: Adapt from human/robot embodiment to drone camera-as-effector

Tier 2 — Creator Personalization (Per-user, online)
  Data: Creator's flight logs + ratings
  Model: PAMELA-style preference head (frozen VLA + tiny MLP)
  Task: Personal shot ranking and style adaptation

Tier 3 — Pre-Flight Shot Generation (Per-session)
  Input: 3DGS scene + text prompt ("coastal reveal") + reference video (optional)
  Pipeline:
    a. VoxPoser → composes 3D reward value map from language
    b. Diffusion Policy → samples 16 candidate SE(3) trajectories
    c. Cosmos-1B / 3D-VLA → generates predicted video for each candidate
    d. CLIP-IQA + creator preference head → ranks candidates
    e. Top-3 presented to creator in Director's Preview

Tier 4 — Real-Time Execution (Per-frame, 10–30Hz)
  Input: Current frame + target trajectory + GarudaPin UWB position
  Model: SmolVLA / TinyVLA (edge-optimized, 450M params)
  Output: Next SE(3) camera pose → EGO-Planner v2 → motor commands
  Fallback: DreamerV3 latent-space planner if VLA confidence < threshold

Tier 5 — Continuous Improvement (Post-flight)
  Data: Recorded flight video + creator rating
  Loop: World-VLA-Loop → update world model → update VLA policy
  Frequency: Every 10 flights → one gradient update step
```
---

## PART 9 — RECENT IMPLEMENTATION FIXES & STABILITY PATCHES

During recent testing, several core bugs were resolved across the system:

### 1. Unicode Encoding Hardening
The original logger, main boot banner, and profiler crashed on Windows (`cp1252` encoding) due to Unicode box-drawing characters and emojis (`✓`, `═`, `🛩️`).
- **Fix:** Substituted with ASCII equivalents (`-`, `[OK]`, `===`).
- **Fix:** Wrapped the logger `sys.stdout` handler in a UTF-8 `TextIOWrapper` with `errors='replace'` to guarantee stability across environments without crashing the main loop.

### 2. Simulation Mode & Telemetry Stub (Hardware Constraint Fallback)
The previous simulation configuration hung indefinitely if a PX4 SITL (Software In The Loop) simulator wasn't actively responding.
- **Fix:** Updated the default SITL connection URL from the deprecated `udp://` to `udpin://:14540`.
- **Fix:** Implemented a **10-second timeout** for the MAVSDK connection.
- **Fix:** Added a **Simulated Telemetry Fallback** stub. If no PX4 instance is detected, the drone automatically boots into a pure software stub, feeding realistic fake GPS, battery drain, and attitude data to the `EventBus`. This bypasses hardware requirements (e.g., Isaac Sim requiring an RTX 4080) and allows high-level testing (State Machine, Brain, Perception) completely offline.
- **Fix:** Patched `SafetyWatchdog` to ignore `HEARTBEAT_LOST` errors when running in stub telemetry mode, preventing log spam and false emergency RTL states.

### 3. Inter-Layer Communication & Wiring
Several key modules were instantiated but not properly wired together, resulting in broken features:
- **Path Smoother:** `PathSmoother` (B-spline velocity smoothing) was instantiated in `main.py` but never passed down to the Orchestrator. Raw PID/CfC outputs were going straight to flight. 
  - *Fix:* Passed `smoother` reference to the `PerceptionInterface`, allowing `Orchestrator._update_tracking` to smooth velocities before sending MAVLink setpoints, fixing jerky cinematic footage.
- **Gimbal Controller:** The `set_gimbal()` method in `FlightController` was a no-op `pass`.
  - *Fix:* Wired `GimbalController` directly into `FlightController` via `set_gimbal_controller()`. The drone now properly targets the subject using pitch/yaw gimbal corrections during tracking, orbit, and reveal modes.
- **Windows Shutdown Support:** Replaced the unsupported `loop.add_signal_handler(signal.SIGTERM)` with standard `signal.signal(signal.SIGINT)` logic for clean cross-platform shutdown.

---

*Research sources: ECCV 2022 (ByteTrack), CVPR 2022 (OC-SORT), AAAI 2024 (UCMCTrack), ICML 2024 (Q-Align/OneAlign), NeurIPS 2023 (3DGS), arxiv 2024-2025 (AirSLAM, DroneMOT, HopTrack, Fly360, Mono-Hydra++, VoI benchmark). VLA/WAM sources: RT-2 (arxiv:2307.15818), OpenVLA (arxiv:2406.09246), π0 (arxiv:2410.24164), Cosmos (arxiv:2501.03575), DreamZero (arxiv:2602.15922), World-VLA-Loop (arxiv:2602.06508), 3D-VLA (arxiv:2403.09631), VoxPoser (arxiv:2307.05973), Diffusion Policy (arxiv:2303.04137), DreamerV3 (arxiv:2301.04104), EgoDex (arxiv:2505.11709), SmolVLA (arxiv:2506.01844), TinyVLA (arxiv:2409.12514), OpenVLA-OFT (arxiv:2502.19645), UVAM (arxiv:2503.00200). All model IDs verified against HuggingFace Hub. Hardware specs from manufacturer datasheets (Qorvo DW3000, Nordic nRF5340, Sony IMX678, NVIDIA Jetson).*

