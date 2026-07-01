"""
GarudaOne DroneOS — Model Downloader
======================================
Downloads all AI model weights required for the drone.

Models downloaded:
  1. LFM-2.5-230M (GGUF, ~180MB) — Language model brain
  2. Needle 26M (GGUF, ~14MB) — Fast command router
  3. PicoDet-S (ncnn, ~4MB) — Object detector
  4. Whisper-tiny (faster-whisper, ~39MB) — Speech-to-text
  5. Piper TTS voice (~20MB) — Text-to-speech
  6. openWakeWord base (~3MB) — Wake word detection

Total download: ~260MB
"""

import hashlib
import os
import sys
import urllib.request
from pathlib import Path


# Project root
PROJECT_ROOT = Path(__file__).parent.parent
MODELS_DIR = PROJECT_ROOT / "models"


# Model definitions: (filename, url, expected_size_mb, description)
MODELS = [
    {
        "name": "LFM-2.5-230M (GGUF Q4_K_M)",
        "filename": "lfm-2.5-230m.Q4_K_M.gguf",
        "url": "https://huggingface.co/LiquidAI/LFM-2.5-230M-GGUF/resolve/main/lfm-2.5-230m.Q4_K_M.gguf",
        "size_mb": 180,
        "required": True,
    },
    {
        "name": "Needle 26M (GGUF Q4_0)",
        "filename": "needle-26m.Q4_0.gguf",
        "url": "https://huggingface.co/CactusCompute/Needle-26M-GGUF/resolve/main/needle-26m.Q4_0.gguf",
        "size_mb": 14,
        "required": False,
    },
    {
        "name": "Piper TTS Voice (en_US-lessac-medium)",
        "filename": "en_US-lessac-medium.onnx",
        "url": "https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_US/lessac/medium/en_US-lessac-medium.onnx",
        "size_mb": 20,
        "required": False,
    },
    {
        "name": "Piper TTS Voice Config",
        "filename": "en_US-lessac-medium.onnx.json",
        "url": "https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_US/lessac/medium/en_US-lessac-medium.onnx.json",
        "size_mb": 0.01,
        "required": False,
    },
    {
        "name": "openWakeWord Base Model",
        "filename": "melspectrogram.onnx",
        "url": "https://github.com/dscripka/openWakeWord/releases/download/v0.6.0/melspectrogram.onnx",
        "size_mb": 3,
        "required": False,
    },
]

# Note: PicoDet-S ncnn and Whisper-tiny are downloaded via their
# respective libraries (paddledet export / faster-whisper download).
# Only standalone model files are downloaded here.


def download_file(url: str, dest: Path, desc: str = "") -> bool:
    """
    Download a file with a simple progress indicator.

    Args:
        url: Download URL
        dest: Destination file path
        desc: Human-readable description

    Returns:
        True if download succeeded
    """
    if dest.exists():
        print(f"  ✓ Already downloaded: {dest.name}")
        return True

    print(f"  ↓ Downloading {desc or dest.name}...")
    print(f"    URL: {url}")

    try:
        def _report(block_count, block_size, total_size):
            downloaded = block_count * block_size
            if total_size > 0:
                percent = min(100, downloaded * 100 / total_size)
                mb_done = downloaded / (1024 * 1024)
                mb_total = total_size / (1024 * 1024)
                sys.stdout.write(
                    f"\r    Progress: {percent:.0f}% ({mb_done:.1f}/{mb_total:.1f} MB)"
                )
                sys.stdout.flush()

        urllib.request.urlretrieve(url, str(dest), reporthook=_report)
        print()  # Newline after progress
        print(f"  ✓ Downloaded: {dest.name} ({dest.stat().st_size / 1024 / 1024:.1f} MB)")
        return True

    except Exception as e:
        print(f"\n  ✗ Download failed: {e}")
        if dest.exists():
            dest.unlink()  # Clean up partial download
        return False


def main():
    """Download all models."""
    print("=" * 60)
    print("GarudaOne DroneOS — Model Downloader")
    print("=" * 60)
    print(f"\nModels directory: {MODELS_DIR}")

    # Create models directory
    MODELS_DIR.mkdir(parents=True, exist_ok=True)

    total = len(MODELS)
    succeeded = 0
    failed = 0

    total_size_mb = sum(m["size_mb"] for m in MODELS)
    print(f"Total models: {total}")
    print(f"Estimated download: ~{total_size_mb:.0f} MB\n")

    for i, model in enumerate(MODELS, 1):
        print(f"[{i}/{total}] {model['name']} (~{model['size_mb']} MB)")

        dest = MODELS_DIR / model["filename"]
        success = download_file(model["url"], dest, model["name"])

        if success:
            succeeded += 1
        else:
            failed += 1
            if model["required"]:
                print(f"  ⚠ WARNING: Required model failed to download!")

        print()

    # Summary
    print("=" * 60)
    print(f"Download complete: {succeeded}/{total} models downloaded")
    if failed > 0:
        print(f"  {failed} models failed — re-run to retry")
    print()

    # Additional models that need library-specific download
    print("Additional models (download via their libraries):")
    print("  • Whisper-tiny: Automatically downloaded by faster-whisper on first use")
    print("  • PicoDet-S: Export from PaddleDetection (see scripts/setup_rpi5.sh)")
    print("  • MiniLM: Automatically downloaded by sentence-transformers on first use")
    print()

    if failed == 0:
        print("✓ All models ready! Run 'make run' to start DroneOS.")
    else:
        print("Some models failed. DroneOS will use stub/fallback modes.")


if __name__ == "__main__":
    main()
