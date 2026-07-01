"""
GarudaOne DroneOS — Voice Pipeline
====================================
Complete offline voice pipeline:
  Wake Word → Speech-to-Text → Intent Classification → Tool Call → TTS Response

All processing happens on-device. No audio ever leaves the drone.

Pipeline flow:
  1. openWakeWord listens for "Garuda" (3-8% CPU, always on)
  2. Moonshine Tiny / Whisper-tiny transcribes the command (27MB model)
  3. Intent parser maps text to a drone command
  4. Piper TTS speaks the confirmation ("Starting orbit mode")
"""

import asyncio
import time
from typing import Optional

from garuda.core.config import Config
from garuda.core.events import Event, EventBus, EventType
from garuda.utils.logger import get_logger

log = get_logger("voice")


class VoicePipeline:
    """
    Complete voice interface for the drone.

    Manages the full pipeline from microphone input to drone command output.
    Each component (wake word, STT, TTS, intent) is a separate module
    that can be swapped independently.
    """

    def __init__(self, config: Config, event_bus: EventBus):
        self.config = config
        self.bus = event_bus

        self._enabled = config.get("voice.enabled", True)
        self._sample_rate = config.get("voice.audio_sample_rate", 16000)
        self._max_command_duration = config.get("voice.command_max_duration_s", 4.0)

        # Component state
        self._wake_word_model = None
        self._stt_model = None
        self._tts_engine = None
        self._intent_parser = None

        # Pipeline state
        self._is_listening = False
        self._is_recording_command = False
        self._running = False

        # Confirmation phrases
        self._confirmations = config.get("voice.confirmation_phrases", {})

        log.info(f"Voice pipeline initialized — enabled={self._enabled}")

    def initialize(self) -> bool:
        """Initialize all voice components."""
        if not self._enabled:
            log.info("Voice pipeline disabled in config")
            return True

        success = True

        # 1. Wake word detector
        success &= self._init_wake_word()

        # 2. Speech-to-text
        success &= self._init_stt()

        # 3. Text-to-speech
        success &= self._init_tts()

        # 4. Intent parser
        success &= self._init_intent()

        return success

    def _init_wake_word(self) -> bool:
        """Initialize openWakeWord for 'Garuda' detection."""
        try:
            from openwakeword.model import Model

            self._wake_word_model = Model(
                wakeword_models=["hey_garuda"],
                inference_framework="onnx",
            )
            log.info("✓ Wake word model loaded (openWakeWord)")
            return True
        except ImportError:
            log.warning("openwakeword not installed — wake word disabled")
            return True  # Non-fatal
        except Exception as e:
            log.warning(f"Wake word init failed: {e}")
            return True

    def _init_stt(self) -> bool:
        """Initialize speech-to-text (Whisper tiny or Moonshine)."""
        try:
            from faster_whisper import WhisperModel

            self._stt_model = WhisperModel(
                "tiny",
                device="cpu",
                compute_type="int8",
            )
            log.info("✓ STT model loaded (faster-whisper tiny INT8)")
            return True
        except ImportError:
            log.warning("faster-whisper not installed — STT disabled")
            return True
        except Exception as e:
            log.warning(f"STT init failed: {e}")
            return True

    def _init_tts(self) -> bool:
        """Initialize Piper TTS for drone voice responses.

        Looks for the Piper binary and voice model. If not found, TTS
        is disabled (text responses are still logged).
        """
        import shutil
        import os

        # Locate the piper binary (bundled, in PATH, or in models dir)
        self._piper_binary = shutil.which("piper")

        # Default voice model path
        models_dir = self.config.models_dir
        self._tts_voice_path = self.config.get(
            "voice.tts_model",
            str(models_dir / "en_US-lessac-medium.onnx"),
        )

        # Check if we have everything needed for real TTS
        if self._piper_binary and os.path.exists(self._tts_voice_path):
            self._tts_engine = "piper"
            log.info(f"✓ TTS engine ready (Piper: {self._piper_binary})")
            log.info(f"  Voice model: {self._tts_voice_path}")
        else:
            self._tts_engine = "stub"
            missing = []
            if not self._piper_binary:
                missing.append("piper binary")
            if not os.path.exists(self._tts_voice_path):
                missing.append("voice model")
            log.info(
                f"TTS running in stub mode (missing: {', '.join(missing)}). "
                f"Install Piper for voice output."
            )

        return True

    def _init_intent(self) -> bool:
        """Initialize intent parser."""
        self._intent_parser = IntentParser(self.config)
        log.info("✓ Intent parser ready")
        return True

    # ── Main Loop ─────────────────────────────────────────────────────────

    async def run(self) -> None:
        """
        Main voice pipeline loop.

        If openWakeWord + microphone are available: continuously listens
        for the wake word "Garuda", then records a command and processes it.
        If not available: runs in passive mode (commands can be injected
        via process_audio_command() for testing).
        """
        if not self._enabled:
            return

        self._running = True
        log.info("Voice pipeline listening...")

        # Try to initialize real microphone capture
        mic = self._init_microphone()
        if mic is None or self._wake_word_model is None:
            log.info(
                "Voice running in PASSIVE mode (no mic or wake word). "
                "Commands can be injected via process_audio_command()."
            )
            while self._running:
                await asyncio.sleep(0.5)
            return

        import numpy as np

        # Active listening loop
        chunk_duration = 0.1  # 100ms chunks for wake word detection
        chunk_samples = int(self._sample_rate * chunk_duration)

        # Buffer for command recording
        command_buffer: list[np.ndarray] = []
        silence_frames = 0
        max_silence_frames = int(1.5 / chunk_duration)  # 1.5s silence ends cmd

        log.info("Voice in ACTIVE mode — say 'Garuda' then your command")

        with mic:
            while self._running:
                try:
                    # Read audio chunk
                    audio_chunk = mic.read(chunk_samples)
                    if audio_chunk is None:
                        await asyncio.sleep(0.01)
                        continue

                    audio_np = np.frombuffer(audio_chunk, dtype=np.int16)

                    if not self._is_recording_command:
                        # ── Wake word detection phase ──────────────
                        prediction = self._wake_word_model.predict(audio_np)
                        # Check if any wake word score exceeds threshold
                        for model_name, score in prediction.items():
                            if score > 0.5:
                                log.info(f"🔊 Wake word detected: {model_name}")
                                self._is_recording_command = True
                                command_buffer = [audio_np]
                                silence_frames = 0
                                break
                    else:
                        # ── Command recording phase ────────────────
                        command_buffer.append(audio_np)

                        # Simple voice activity detection via energy
                        energy = np.abs(audio_np).mean()
                        if energy > 500:  # Threshold for speech
                            silence_frames = 0
                        else:
                            silence_frames += 1

                        # End command on silence or max duration
                        total_duration = (
                            len(command_buffer) * chunk_duration
                        )
                        if silence_frames >= max_silence_frames:
                            log.info(
                                f"Command recording complete "
                                f"({total_duration:.1f}s)"
                            )
                            self._is_recording_command = False
                            # Concatenate and process
                            full_audio = np.concatenate(command_buffer)
                            # Run in executor to avoid blocking
                            await asyncio.get_event_loop().run_in_executor(
                                None, self._process_command_thread, full_audio
                            )
                        elif total_duration >= self._max_command_duration:
                            log.info(
                                f"Max command duration reached "
                                f"({total_duration:.1f}s)"
                            )
                            self._is_recording_command = False
                            full_audio = np.concatenate(command_buffer)
                            await asyncio.get_event_loop().run_in_executor(
                                None, self._process_command_thread, full_audio
                            )

                except Exception as e:
                    log.error(f"Voice pipeline error: {e}")
                    self._is_recording_command = False
                    await asyncio.sleep(0.5)

    def _init_microphone(self):
        """Initialize microphone input via sounddevice.

        Returns a microphone stream or None if unavailable.
        """
        try:
            import sounddevice as sd

            stream = sd.RawInputStream(
                samplerate=self._sample_rate,
                channels=1,
                dtype="int16",
                blocksize=0,  # Variable block size
            )
            log.info(
                f"✓ Microphone initialized "
                f"({self._sample_rate}Hz, mono)"
            )
            return stream
        except ImportError:
            log.warning(
                "sounddevice not installed — microphone input disabled. "
                "Install: pip install sounddevice"
            )
            return None
        except Exception as e:
            log.warning(f"Microphone init failed: {e}")
            return None

    def _process_command_thread(self, audio_data) -> None:
        """Process a recorded command (runs in thread executor).

        This calls process_audio_command synchronously by creating a
        new event loop, since we're in a background thread.
        """
        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            loop.run_until_complete(self.process_audio_command(audio_data))
            loop.close()
        except Exception as e:
            log.error(f"Command processing failed: {e}")

    async def stop(self) -> None:
        """Stop the voice pipeline."""
        self._running = False
        log.info("Voice pipeline stopped")

    async def process_audio_command(self, audio_data) -> Optional[str]:
        """
        Process a captured audio command through the full pipeline.

        Args:
            audio_data: Raw audio bytes or numpy array (16kHz, mono)

        Returns:
            The parsed command string, or None if parsing failed
        """
        # Step 1: Transcribe audio → text
        text = await self._transcribe(audio_data)
        if not text:
            log.debug("STT returned empty transcription")
            return None

        log.info(f"Transcribed: \"{text}\"")

        # Step 2: Classify intent → command
        command = self._intent_parser.classify(text)
        if not command:
            log.info(f"Could not classify intent for: \"{text}\"")
            await self.speak("I didn't understand that command")
            return None

        log.info(f"Intent: \"{text}\" → {command}")

        # Step 3: Publish command event
        await self.bus.publish(Event(
            type=EventType.VOICE_COMMAND_PARSED,
            data={"text": text, "command": command},
            source="voice",
        ))

        # Step 4: Speak confirmation
        confirmation = self._confirmations.get(command, f"Executing {command}")
        await self.speak(confirmation)

        return command

    async def _transcribe(self, audio_data) -> Optional[str]:
        """Transcribe audio to text using STT model."""
        if self._stt_model is None:
            return None

        try:
            segments, _ = self._stt_model.transcribe(
                audio_data,
                language="en",
                beam_size=1,
                vad_filter=True,
            )
            text = " ".join(segment.text for segment in segments).strip()
            return text if text else None
        except Exception as e:
            log.error(f"Transcription failed: {e}")
            return None

    async def speak(self, text: str) -> None:
        """
        Speak a text response through the drone's speaker.

        Uses Piper TTS for natural-sounding voice output. If Piper is
        not available, the text is logged only (stub mode).
        """
        log.info(f"TTS: \"{text}\"")

        if self._tts_engine == "piper":
            # Run Piper in a thread to avoid blocking the event loop
            await asyncio.get_event_loop().run_in_executor(
                None, self._speak_piper, text
            )

    def _speak_piper(self, text: str) -> None:
        """Run Piper TTS via subprocess.

        Pipes text to piper, which outputs raw audio to stdout, then
        plays it via sounddevice (or aplay on Linux).
        """
        import subprocess
        import sys
        import tempfile
        import os

        try:
            # Generate audio to a temp WAV file via Piper
            with tempfile.NamedTemporaryFile(
                suffix=".wav", delete=False
            ) as tmp:
                output_path = tmp.name

            result = subprocess.run(
                [
                    self._piper_binary,
                    "--model", self._tts_voice_path,
                    "--output_file", output_path,
                ],
                input=text.encode("utf-8"),
                capture_output=True,
                timeout=5.0,
            )

            if result.returncode != 0:
                log.error(
                    f"Piper failed: {result.stderr.decode('utf-8', errors='replace')}"
                )
                return

            # Play the audio file
            try:
                import sounddevice as sd
                import soundfile as sf
                data, sr = sf.read(output_path)
                sd.play(data, sr)
                sd.wait()
            except ImportError:
                # Fallback: use system player
                if sys.platform == "win32":
                    os.startfile(output_path)  # type: ignore
                else:
                    subprocess.run(
                        ["aplay", output_path],
                        capture_output=True,
                    )

            # Clean up temp file
            try:
                os.unlink(output_path)
            except OSError:
                pass

        except subprocess.TimeoutExpired:
            log.error("Piper TTS timed out")
        except FileNotFoundError:
            log.error(
                f"Piper binary not found: {self._piper_binary}. "
                "Install from: https://github.com/rhasspy/piper"
            )
        except Exception as e:
            log.error(f"TTS playback failed: {e}")


class IntentParser:
    """
    Maps transcribed text to drone commands.

    Two-tier approach:
      1. Fast: Keyword matching (zero latency, handles 90% of commands)
      2. Fallback: Semantic similarity via MiniLM (for unusual phrasing)
    """

    # Keyword → command mapping
    COMMAND_KEYWORDS = {
        "takeoff": [
            "take off", "takeoff", "launch", "fly up", "go up",
            "start flying", "lift off",
        ],
        "land": [
            "land", "come down", "touch down", "put down",
            "bring it down",
        ],
        "rtl": [
            "come home", "return home", "go home", "come back",
            "return to launch", "return", "rtl",
        ],
        "hover": [
            "hover", "stay", "hold", "wait", "stay there",
            "hold position", "freeze",
        ],
        "stop": [
            "stop", "halt", "pause",
        ],
        "follow": [
            "follow me", "follow", "track me", "track",
            "come with me", "stay with me",
        ],
        "orbit": [
            "orbit", "circle", "go around", "circle around",
            "orbit me", "circle me",
        ],
        "chase": [
            "chase", "chase me", "follow behind",
            "stay behind", "behind me",
        ],
        "reveal": [
            "reveal", "reveal shot", "pull back", "rise up",
            "pull away", "dramatic",
        ],
        "recording_start": [
            "start recording", "record", "action",
            "start filming", "shoot", "rolling",
        ],
        "recording_stop": [
            "stop recording", "cut", "stop filming",
            "stop shooting", "done recording",
        ],
        "emergency_stop": [
            "emergency", "emergency stop", "kill",
            "abort", "mayday",
        ],
    }

    def __init__(self, config: Config):
        self._config = config
        self._semantic_model = None

        # Flatten keywords for quick search, sorted longest-first
        # so "stop recording" matches before "stop"
        self._keyword_pairs: list[tuple[str, str]] = []
        for command, keywords in self.COMMAND_KEYWORDS.items():
            for keyword in keywords:
                self._keyword_pairs.append((keyword.lower(), command))
        # Sort by keyword length descending — longer matches win
        self._keyword_pairs.sort(key=lambda x: len(x[0]), reverse=True)

    def classify(self, text: str) -> Optional[str]:
        """
        Classify transcribed text into a drone command.

        Args:
            text: Transcribed voice command

        Returns:
            Command string (e.g., "takeoff", "orbit") or None
        """
        text_lower = text.lower().strip()

        # Tier 1: Exact keyword match (longest first)
        for keyword, command in self._keyword_pairs:
            if keyword in text_lower:
                return command

        # Tier 2: Semantic similarity (if model loaded)
        if self._semantic_model:
            return self._semantic_classify(text_lower)

        return None

    def _semantic_classify(self, text: str) -> Optional[str]:
        """Semantic classification using sentence-transformers MiniLM."""
        # TODO: Load MiniLM and compute cosine similarity
        # against command descriptions
        return None
