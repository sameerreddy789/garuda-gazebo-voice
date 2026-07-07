#!/bin/bash
# =============================================================================
# GarudaOne DroneOS — PX4 SITL Setup Script (WSL2 Ubuntu 22.04 / 24.04)
# =============================================================================
#
# This script sets up a complete PX4 SITL (Software-In-The-Loop) environment
# inside WSL2 Ubuntu on Windows. 
#
# Usage:
#   wsl bash scripts/setup_sitl.sh
#
# =============================================================================

set -e

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BASE_DIR="$(dirname "$PROJECT_DIR")"
PX4_DIR="$BASE_DIR/PX4-Autopilot"

echo ""
echo "════════════════════════════════════════════════════════════════════════"
echo "  GarudaOne DroneOS — PX4 SITL Environment Setup (WSL2)"
echo "════════════════════════════════════════════════════════════════════════"
echo ""

# Ask for sudo upfront
echo "Please enter your WSL password for sudo access:"
sudo -v

# Keep sudo alive
while true; do sudo -n true; sleep 60; kill -0 "$$" || exit; done 2>/dev/null &

# ── Step 1: Clone PX4 Autopilot ──────────────────────────────────────────
echo "▸ Step 1/4: Cloning PX4 Autopilot..."

if [ -d "$PX4_DIR" ]; then
    echo "  ✓ PX4 Autopilot already exists at $PX4_DIR"
    echo "    Updating to latest..."
    cd "$PX4_DIR"
    git fetch --all
    git pull --ff-only || echo "  ⚠ Could not update (local changes?). Using existing clone."
else
    echo "  Cloning PX4 Autopilot (~1.5GB, first time only)..."
    cd "$BASE_DIR"
    git clone --recursive https://github.com/PX4/PX4-Autopilot.git
    echo "  ✓ PX4 Autopilot cloned to $PX4_DIR"
fi

# ── Step 2: Install Dependencies via PX4's Official Script ─────────────────
echo ""
echo "▸ Step 2/4: Installing system dependencies via PX4 official script..."
echo "  (This installs the correct version of Gazebo based on your Ubuntu version)"

cd "$PX4_DIR"
bash ./Tools/setup/ubuntu.sh
echo "  ✓ Dependencies installed"

# ── Step 3: Build PX4 SITL ────────────────────────────────────────────────
echo ""
echo "▸ Step 3/4: Building PX4 SITL target..."
echo "  (This takes ~10-20 minutes on first build)"

export CCACHE_MAXSIZE=5G
export CCACHE_DIR="$BASE_DIR/.ccache/px4"

cd "$PX4_DIR"
# Check if already built
if [ -f "build/px4_sitl_default/bin/px4" ]; then
    echo "  ✓ PX4 SITL already built."
else
    # Build only the SITL target 
    make px4_sitl default
    echo "  ✓ PX4 SITL build complete"
fi

# ── Step 4: Create Launch Scripts ─────────────────────────────────────────
echo ""
echo "▸ Step 4/4: Creating launch scripts..."

cat > "$BASE_DIR/px4_sitl_launch.sh" << 'LAUNCH_EOF'
#!/bin/bash
# GarudaOne — PX4 SITL + Gazebo Launcher
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PX4_DIR="${PX4_DIR:-$SCRIPT_DIR/PX4-Autopilot}"
MODEL="${SITL_MODEL:-x500}"
HOME_LAT="${SITL_LAT:-12.9716}"
HOME_LON="${SITL_LON:-77.5946}"
HOME_ALT="${SITL_ALT:-920.0}"

echo "Launching PX4 SITL (Model: gz_$MODEL) at $HOME_LAT, $HOME_LON..."
export PX4_HOME_LAT="$HOME_LAT"
export PX4_HOME_LON="$HOME_LON"
export PX4_HOME_ALT="$HOME_ALT"

cd "$PX4_DIR"
make px4_sitl gz_"$MODEL"
LAUNCH_EOF

chmod +x "$BASE_DIR/px4_sitl_launch.sh"

# Create project-local launcher
cat > "$PROJECT_DIR/scripts/launch_sitl.sh" << 'LAUNCH_EOF'
#!/bin/bash
# GarudaOne — PX4 SITL Launcher
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PX4_DIR="${PX4_DIR:-$SCRIPT_DIR/../../PX4-Autopilot}"

MODEL="x500"
while [[ $# -gt 0 ]]; do
    case "$1" in
        --model) MODEL="$2"; shift 2 ;;
        *) echo "Usage: $0 [--model x500]"; exit 1 ;;
    esac
done

export PX4_HOME_LAT="${SITL_LAT:-12.9716}"
export PX4_HOME_LON="${SITL_LON:-77.5946}"
export PX4_HOME_ALT="${SITL_ALT:-920.0}"

cd "$PX4_DIR"
make px4_sitl gz_"$MODEL"
LAUNCH_EOF

chmod +x "$PROJECT_DIR/scripts/launch_sitl.sh"

echo "  ✓ Launch scripts created"
echo "    - $BASE_DIR/px4_sitl_launch.sh"
echo "    - $PROJECT_DIR/scripts/launch_sitl.sh"

echo ""
echo "════════════════════════════════════════════════════════════════════════"
echo "  Setup Complete!"
echo "════════════════════════════════════════════════════════════════════════"
echo "  IMPORTANT: Please RESTART your WSL terminal or run 'source ~/.bashrc'"
echo "  before launching the simulator so the new PATH variables take effect."
echo ""
echo "  To launch: $PROJECT_DIR/scripts/launch_sitl.sh"
echo ""
