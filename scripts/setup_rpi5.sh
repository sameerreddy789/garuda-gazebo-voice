#!/bin/bash
# =============================================================================
# GarudaOne DroneOS — Raspberry Pi 5 Setup Script
# Target: Ubuntu 24.04 LTS ARM64 on RPi5 (8GB)
# =============================================================================

set -e

echo "════════════════════════════════════════════════════════════"
echo " GarudaOne DroneOS — RPi5 Environment Setup"
echo "════════════════════════════════════════════════════════════"

# ── System Dependencies ───────────────────────────────────────────────────────
echo ""
echo "▸ Step 1/6: Installing system dependencies..."
sudo apt update
sudo apt install -y \
    python3.11 python3.11-venv python3.11-dev \
    python3-pip \
    cmake build-essential git \
    libopencv-dev python3-opencv \
    libasound2-dev portaudio19-dev \
    libusb-1.0-0-dev \
    ffmpeg \
    screen

# ── Python Virtual Environment ────────────────────────────────────────────────
echo ""
echo "▸ Step 2/6: Creating Python virtual environment..."
VENV_DIR="$HOME/.venvs/garuda"
python3.11 -m venv "$VENV_DIR"
source "$VENV_DIR/bin/activate"

pip install --upgrade pip wheel setuptools

# ── Python Dependencies ──────────────────────────────────────────────────────
echo ""
echo "▸ Step 3/6: Installing Python dependencies..."
pip install -r requirements.txt

# ARM-specific packages
pip install ncps                    # CfC Liquid Neural Networks
pip install openwakeword            # Wake word detection
pip install faster-whisper          # Whisper STT
pip install sounddevice             # Audio input

echo ""
echo "▸ Step 4/6: Building llama.cpp (for LFM-2.5-230M)..."
# Build llama.cpp from source for ARM NEON acceleration
if [ ! -d "$HOME/llama.cpp" ]; then
    cd "$HOME"
    git clone https://github.com/ggerganov/llama.cpp.git
    cd llama.cpp
    mkdir -p build && cd build
    cmake .. -DGGML_CPU_ARM_ARCH=armv8.2-a+dotprod+fp16+sve
    cmake --build . --config Release -j4
    echo "✓ llama.cpp built with ARM NEON/SVE support"
else
    echo "✓ llama.cpp already installed"
fi

# ── ncnn (for PicoDet-S) ─────────────────────────────────────────────────────
echo ""
echo "▸ Step 5/6: Building ncnn (for PicoDet-S detector)..."
if ! python3 -c "import ncnn" 2>/dev/null; then
    cd "$HOME"
    git clone https://github.com/Tencent/ncnn.git
    cd ncnn
    mkdir -p build && cd build
    cmake -DNCNN_BUILD_TOOLS=ON \
          -DNCNN_BUILD_EXAMPLES=OFF \
          -DNCNN_BUILD_BENCHMARK=OFF \
          -DNCNN_PYTHON=ON \
          ..
    make -j4
    cd ../python
    pip install .
    echo "✓ ncnn built with ARM NEON support"
else
    echo "✓ ncnn already installed"
fi

# ── UART Setup ────────────────────────────────────────────────────────────────
echo ""
echo "▸ Step 6/6: Configuring UART for PX4 communication..."

# Enable UART on RPi5 GPIO (disable Bluetooth on UART0)
if ! grep -q "dtoverlay=disable-bt" /boot/firmware/config.txt; then
    echo "" | sudo tee -a /boot/firmware/config.txt
    echo "# GarudaOne: Free UART0 for PX4 companion link" | sudo tee -a /boot/firmware/config.txt
    echo "dtoverlay=disable-bt" | sudo tee -a /boot/firmware/config.txt
    echo "enable_uart=1" | sudo tee -a /boot/firmware/config.txt
    sudo systemctl disable hciuart
    echo "⚠ UART configured — REBOOT REQUIRED"
else
    echo "✓ UART already configured"
fi

# Add user to dialout group (for serial access without sudo)
sudo usermod -a -G dialout "$USER"

# ── Download Models ──────────────────────────────────────────────────────────
echo ""
echo "════════════════════════════════════════════════════════════"
echo " Setup complete!"
echo "════════════════════════════════════════════════════════════"
echo ""
echo "Next steps:"
echo "  1. Reboot if UART was configured: sudo reboot"
echo "  2. Activate venv: source $VENV_DIR/bin/activate"
echo "  3. Download models: python scripts/download_models.py"
echo "  4. Test: make test"
echo "  5. Run: make run"
echo ""
echo "UART device: /dev/ttyAMA0 (connect to MicoAir H743 TX/RX)"
echo "Baud rate: 921600"
echo ""
