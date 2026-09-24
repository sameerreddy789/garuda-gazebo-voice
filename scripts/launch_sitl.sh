#!/bin/bash
# GarudaOne — PX4 SITL Launcher
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PX4_DIR="${PX4_DIR:-$HOME/PX4-Autopilot}"

MODEL="x500"
WORLD="${SITL_WORLD:-airfield_obstacles}"
while [[ $# -gt 0 ]]; do
    case "$1" in
        --model) MODEL="$2"; shift 2 ;;
        --world) WORLD="$2"; shift 2 ;;
        *) echo "Usage: $0 [--model x500] [--world airfield_obstacles]"; exit 1 ;;
    esac
done

export PX4_GZ_WORLD="$WORLD"
export PX4_HOME_LAT="${SITL_LAT:-12.9716}"
export PX4_HOME_LON="${SITL_LON:-77.5946}"
export PX4_HOME_ALT="${SITL_ALT:-920.0}"

cd "$PX4_DIR"
make px4_sitl gz_"$MODEL"
