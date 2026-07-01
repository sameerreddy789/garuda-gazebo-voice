#!/bin/bash
# =============================================================================
# GarudaOne DroneOS — PX4 SITL Setup Script (WSL2 Ubuntu)
# =============================================================================
#
# This script sets up a complete PX4 SITL (Software-In-The-Loop) environment
# inside WSL2 Ubuntu on Windows. After running this, you can:
#
#   1. Launch PX4 SITL + Gazebo inside WSL2 (run: ./scripts/launch_sitl.sh)
#   2. Connect QGroundControl on Windows (udp://localhost:14550)
#   3. Run GarudaOne DroneOS on Windows (GARUDA_MODE=simulation make run-sitl)
#
# PX4 SITL runs the EXACT same PX4 firmware that flies on the MicoAir H743.
# The only difference: motor outputs go to Gazebo instead of real ESCs.
#
# Prerequisites:
#   - WSL2 with Ubuntu 22.04 or 24.04 installed
#   - At least 20GB free disk space
#   - At least 4GB RAM
#   - Internet connection (first run downloads ~2GB)
#
# Usage:
#   chmod +x scripts/setup_sitl.sh
#   ./scripts/setup_sitl.sh
#
# =============================================================================

set -e

echo ""
echo "════════════════════════════════════════════════════════════════════════"
echo "  GarudaOne DroneOS — PX4 SITL Environment Setup (WSL2)"
echo "════════════════════════════════════════════════════════════════════════"
echo ""

# ── Step 1: System Dependencies ────────────────────────────────────────────
echo "▸ Step 1/6: Installing system dependencies..."
echo "  (This may take 5-10 minutes on first run)"

sudo apt update
sudo apt install -y \
    git \
    cmake \
    ninja-build \
    python3 \
    python3-pip \
    python3-dev \
    python3-venv \
    protobuf-compiler \
    protobuf-c-compiler \
    geographiclib-tools \
    libgeographic-dev \
    libeigen3-dev \
    libjsoncpp-dev \
    libfmt-dev \
    libxml2-dev \
    libgstreamer1.0-dev \
    libgstreamer-plugins-base1.0-dev \
    gstreamer1.0-plugins-good \
    gstreamer1.0-plugins-bad \
    gstreamer1.0-plugins-ugly \
    gstreamer1.0-tools \
    gstreamer1.0-alsa \
    libgazebo-dev \
    gazebo11 \
    libopencv-dev \
    libpygame-sdl2-dev \
    pyqt5-dev \
    wget \
    curl \
    unzip \
    ccache \
    clang \
    lld \
    build-essential \
    2>&1 | tail -5

echo "  ✓ System dependencies installed"

# ── Step 2: GeographicLib Datasets (for GPS on the actual Earth) ──────────
echo ""
echo "▸ Step 2/6: Installing GeographicLib datasets..."
echo "  (Required for accurate GPS simulation)"

# Install geoid model and gravity model
if ! geographiclib-get-geoids egm96-5 2>/dev/null; then
    sudo geographiclib-get-geoids egm96-5
fi
if ! geographiclib-get-gravity egm96 2>/dev/null; then
    sudo geographiclib-get-gravity egm96
fi
if ! geographiclib-get-magnetic emm2015 2>/dev/null; then
    sudo geographiclib-get-magnetic emm2015
fi

echo "  ✓ GeographicLib datasets installed"

# ── Step 3: Clone PX4 Autopilot ──────────────────────────────────────────
echo ""
echo "▸ Step 3/6: Cloning PX4 Autopilot..."

PX4_DIR="$HOME/PX4-Autopilot"

if [ -d "$PX4_DIR" ]; then
    echo "  ✓ PX4 Autopilot already exists at $PX4_DIR"
    echo "    Updating to latest..."
    cd "$PX4_DIR"
    git fetch --all
    git pull --ff-only || echo "  ⚠ Could not update (local changes?). Using existing clone."
else
    echo "  Cloning PX4 Autopilot (~1.5GB, first time only)..."
    cd "$HOME"
    git clone --recursive https://github.com/PX4/PX4-Autopilot.git
    echo "  ✓ PX4 Autopilot cloned to $PX4_DIR"
fi

# ── Step 4: Build PX4 SITL ────────────────────────────────────────────────
echo ""
echo "▸ Step 4/6: Building PX4 SITL target..."
echo "  (This takes ~10-20 minutes on first build)"

cd "$PX4_DIR"

# Use ccache to speed up rebuilds
export CCACHE_MAXSIZE=5G
export CCACHE_DIR="$HOME/.ccache/px4"

# Check if already built
if [ -f "build/px4_sitl_rtps/px4" ]; then
    echo "  ✓ PX4 SITL already built. Skipping."
    echo "    To rebuild: cd $PX4_DIR && make px4_sitl_rtps clean && make px4_sitl_rtps"
else
    # Build only the SITL target (no board hardware needed)
    make px4_sitl_rtps default 2>&1 | tail -20
    echo "  ✓ PX4 SITL build complete"
fi

# ── Step 5: Install MAVProxy / MAVLink Tools ──────────────────────────────
echo ""
echo "▸ Step 5/6: Installing MAVLink tools..."

python3 -m pip install --user --upgrade pip
python3 -m pip install --user \
    MAVProxy \
    mavlink \
    pyserial \
    numpy \
    2>&1 | tail -5

echo "  ✓ MAVProxy and MAVLink tools installed"

# ── Step 6: Create Launch Script ─────────────────────────────────────────
echo ""
echo "▸ Step 6/6: Creating launch scripts..."

# Create the PX4 SITL launch script
cat > "$HOME/px4_sitl_launch.sh" << 'LAUNCH_EOF'
#!/bin/bash
# =============================================================================
# GarudaOne — PX4 SITL + Gazebo Launcher
# =============================================================================
#
# Launches PX4 SITL with Gazebo simulation.
# After launching, connect from Windows:
#   - QGroundControl: automatically discovers on UDP 14550
#   - GarudaOne DroneOS: GARUDA_MODE=simulation make run-sitl
#
# Press Ctrl+C to stop.
# =============================================================================

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Default settings (override via environment variables)
PX4_DIR="${PX4_DIR:-$HOME/PX4-Autopilot}"
MODEL="${SITL_MODEL:-x500}"
HOME_LAT="${SITL_LAT:-12.9716}"
HOME_LON="${SITL_LON:-77.5946}"
HOME_ALT="${SITL_ALT:-920.0}"

echo ""
echo "════════════════════════════════════════════════════════════════════════"
echo "  GarudaOne — PX4 SITL + Gazebo"
echo "════════════════════════════════════════════════════════════════════════"
echo ""
echo "  Model:    $MODEL"
echo "  Location: $HOME_LAT, $HOME_LON (alt: ${HOME_ALT}m)"
echo "  PX4 Dir:  $PX4_DIR"
echo "  MAVLink:  UDP :14540 (MAVSDK) / UDP :14550 (QGC)"
echo ""
echo "  Press Ctrl+C to stop"
echo ""
echo "────────────────────────────────────────────────────────────────────────"

# Set PX4 home location via environment
export PX4_HOME_LAT="$HOME_LAT"
export PX4_HOME_LON="$HOME_LON"
export PX4_HOME_ALT="$HOME_ALT"

cd "$PX4_DIR"

# Launch PX4 SITL with Gazebo
# The drone model determines the Gazebo model loaded.
# Available: x500, typhoon_h480, iris, plane, standard_vtol
#
# UDP ports:
#   14540 — MAVSDK (Python) connects here
#   14550 — QGroundControl connects here
#
make px4_sitl_rtps gazebo_"$MODEL"
LAUNCH_EOF

chmod +x "$HOME/px4_sitl_launch.sh"

# Also create the script inside the DroneOS project for convenience
cat > "$HOME/DroneOS/scripts/launch_sitl.sh" << 'LAUNCH_EOF'
#!/bin/bash
# =============================================================================
# GarudaOne — PX4 SITL Launcher (from Windows)
# =============================================================================
#
# Run this INSIDE WSL2 to launch PX4 SITL + Gazebo.
#
# Usage:
#   wsl bash scripts/launch_sitl.sh
#   wsl bash scripts/launch_sitl.sh --model x500
#   wsl bash scripts/launch_sitl.sh --model typhoon_h480
# =============================================================================

set -e

# Parse arguments
MODEL="x500"
while [[ $# -gt 0 ]]; do
    case "$1" in
        --model)
            MODEL="$2"
            shift 2
            ;;
        *)
            echo "Unknown argument: $1"
            echo "Usage: $0 [--model x500|typhoon_h480|iris]"
            exit 1
            ;;
    esac
done

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Default settings (Bangalore, India)
PX4_DIR="${PX4_DIR:-$HOME/PX4-Autopilot}"
HOME_LAT="${SITL_LAT:-12.9716}"
HOME_LON="${SITL_LON:-77.5946}"
HOME_ALT="${SITL_ALT:-920.0}"

echo ""
echo "════════════════════════════════════════════════════════════════════════"
echo "  GarudaOne — PX4 SITL + Gazebo"
echo "════════════════════════════════════════════════════════════════════════"
echo ""
echo "  Model:    $MODEL"
echo "  Location: $HOME_LAT, $HOME_LON (alt: ${HOME_ALT}m)"
echo "  PX4 Dir:  $PX4_DIR"
echo "  MAVLink:  UDP :14540 (MAVSDK) / UDP :14550 (QGC)"
echo ""
echo "  Press Ctrl+C to stop"
echo ""
echo "────────────────────────────────────────────────────────────────────────"

# Set PX4 home location
export PX4_HOME_LAT="$HOME_LAT"
export PX4_HOME_LON="$HOME_LON"
export PX4_HOME_ALT="$HOME_ALT"

cd "$PX4_DIR"

# Launch PX4 SITL with Gazebo
make px4_sitl_rtps gazebo_"$MODEL"
LAUNCH_EOF

chmod +x "$HOME/DroneOS/scripts/launch_sitl.sh"

echo "  ✓ Launch scripts created"
echo "    - $HOME/px4_sitl_launch.sh (global)"
echo "    - $HOME/DroneOS/scripts/launch_sitl.sh (project)"

# ── Summary ─────────────────────────────────────────────────────────────────
echo ""
echo "════════════════════════════════════════════════════════════════════════"
echo "  Setup Complete!"
echo "════════════════════════════════════════════════════════════════════════"
echo ""
echo "  Next steps:"
echo ""
echo "  1. Launch PX4 SITL (inside WSL2):"
echo "     cd ~/PX4-Autopilot"
echo "     ./make px4_sitl_rtps gazebo_x500"
echo ""
echo "     Or from anywhere:"
echo "     ~/px4_sitl_launch.sh"
echo ""
echo "  2. Open QGroundControl on Windows:"
echo "     Download from: https://qgroundcontrol.com/downloads/"
echo "     It will auto-discover PX4 on UDP :14550"
echo ""
echo "  3. Run GarudaOne DroneOS on Windows:"
echo "     cd D:\\Aatonovaz\\DroneOS"
echo "     GARUDA_MODE=simulation python -m garuda.main"
echo ""
echo "  Or from PowerShell:"
echo "     $env:GARUDA_MODE='simulation'; python -m garuda.main"
echo ""
echo "  Available SITL models:"
echo "     x500            — Quadcopter (default, similar to FlyLens 85)"
echo "     typhoon_h480    — Hex with 3-axis gimbal (closest to GarudaOne)"
echo "     iris            — Standard PX4 quadcopter"
echo "     standard_vtol   — VTOL aircraft"
echo ""
echo "  Troubleshooting:"
echo "     - If Gazebo won't start: 'export DISPLAY=:0' or use 'headless' mode"
echo "     - If MAVSDK can't connect: check Windows Firewall allows UDP 14540"
echo "     - If build fails: 'cd ~/PX4-Autopilot && make distclean && make px4_sitl_rtps'"
echo ""
