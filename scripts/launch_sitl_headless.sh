#!/bin/bash
# =============================================================================
# GarudaOne DroneOS — PX4 SITL Headless Launcher (for Isaac Sim)
# =============================================================================
#
# This script launches PX4 SITL in a headless mode (without Gazebo) inside WSL2.
# It configures PX4 to listen for an external physics simulator, specifically
# the Pegasus Simulator bridge running inside NVIDIA Isaac Sim on Windows.
#
# Usage:
#   wsl bash scripts/launch_sitl_headless.sh
#
# =============================================================================

set -e

echo ""
echo "════════════════════════════════════════════════════════════════════════"
echo "  GarudaOne DroneOS — PX4 SITL Headless Launcher (Isaac Sim Mode)"
echo "════════════════════════════════════════════════════════════════════════"
echo ""

# Check if PX4 is installed
PX4_DIR="$HOME/PX4-Autopilot"

if [ ! -d "$PX4_DIR" ]; then
    echo "ERROR: PX4-Autopilot directory not found at $PX4_DIR"
    echo "Please run scripts/setup_sitl.sh first to clone and build PX4."
    exit 1
fi

echo "▸ Starting PX4 SITL without Gazebo..."
echo "▸ Waiting for Isaac Sim (Pegasus Simulator) to connect on UDP 14560..."
echo "▸ Once Isaac Sim is running, start GarudaOS with GARUDA_MODE=simulation"
echo ""

# Navigate to PX4 directory
cd "$PX4_DIR"

# 'none_iris' builds and runs PX4 with the iris airframe but skips launching Gazebo
# It opens UDP ports for MAVLink waiting for the simulator
make px4_sitl none_iris
