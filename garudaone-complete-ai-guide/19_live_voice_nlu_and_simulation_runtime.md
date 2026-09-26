# Part 19: Live Voice NLU, Acoustic Feedback & Simulation Runtime

**Status:** Operational  
**Revision Date:** September 2026  
**Integration Scope:** Voice recognition, parameter extraction, Smallest.ai TTS, Windows SAPI fallback, offboard flight synchronization.

---

## 1. Multi-Tiered Speech Recognition Pipeline

GarudaOne implements a low-latency, dual-engine voice interface:

```
[ Ambient Microphone Audio Stream ]
                 │
                 ▼
[ Background Noise Floor Calibration (1.2s ambient sample, >550 energy threshold) ]
                 │
                 ▼
      [ SpeechRecognition Recognizer (Google STT / Offline Whisper) ]
                 │
                 ▼
       [ Fast-Path Regex Matcher & Parameter Extractor ]
       ├─ Wake word recognition ("Garuda", "Drone", etc.)
       ├─ Direct keyword matching (<1ms latency)
       └─ Metric parameter parser (e.g., "50 meters", "10 mins")
                 │
                 ├─ If direct match found: DISPATCH COMMAND IMMEDIATELY
                 │
                 └─ If unmatched (natural phrasing):
                          │
                          ▼
            [ Cloud LLM NLU: OpenAI GPT-5-nano ]
            - Semantic intent classification
            - JSON parameter payload extraction:
              {"action": "...", "distance_m": 5.0, "duration_mins": 10.0, "reply": "..."}
```

---

## 2. Parameter Extraction Engine

Voice commands dynamically dictate flight envelopes:
- **Default Translation:** Unspecified translation commands default to **5.0 meters**.
- **Default Takeoff Hover:** Takeoff defaults to a **10-minute** hover endurance window.
- **Parametric Directives:** Phrasing such as *"move right for 50 metres"* automatically scales speed ($5.0\text{ m/s}$) and time duration ($10.0\text{s}$) to precisely translate 50 meters.

---

## 3. High-Fidelity Audio Synthesis & Local Fallback

GarudaOne guarantees zero voice silence across all operational environments:
1. **Primary Cloud Engine:** Smallest.ai Waves Lightning TTS API (`lightning_v3.1_pro`, 24kHz sample rate).
2. **Local Zero-Latency Fallback:** Native Windows SAPI COM automation engine (`SpVoice`). Instantaneous, 100% offline, zero API latency.
3. **Acoustic Feedback:** Synthesized quadcopter rotor harmonics (`assets/drone_fan.wav`) and safety interlock warning sirens (`900Hz` / `600Hz`).
