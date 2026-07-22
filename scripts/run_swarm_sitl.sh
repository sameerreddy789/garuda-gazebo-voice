#!/bin/bash
# =============================================================================
# GarudaOne — Headless multi-vehicle PX4 SITL launcher (Gazebo gz / x500)
# =============================================================================
# Launches N headless PX4 SITL instances. Instance i binds MAVSDK UDP port
# 14540 + i (PX4's sequential offset). The first instance starts the gz
# server; subsequent instances spawn into the same world at offset poses.
#
# Usage (inside WSL):
#   bash run_swarm_sitl.sh [N]        # default N=2
# Logs: /tmp/px4_<i>.log
# =============================================================================
set -u

PX4_DIR=/mnt/d/Aatonovaz/PX4-Autopilot
N=${1:-2}

cd "$PX4_DIR" || { echo "[sitl] PX4_DIR not found: $PX4_DIR"; exit 1; }

echo "[sitl] cleaning any prior px4/gz processes"
pkill -f 'build/px4_sitl_default/bin/px4' 2>/dev/null || true
pkill -f 'gz sim' 2>/dev/null || true
pkill -f 'gz-sim' 2>/dev/null || true
sleep 3

for i in $(seq 0 $((N - 1))); do
  pose="0,$((i * 3))"
  echo "[sitl] launching instance $i at pose ($pose) -> /tmp/px4_$i.log"
  PX4_SYS_AUTOSTART=4001 \
  PX4_SIM_MODEL=gz_x500 \
  PX4_GZ_MODEL_POSE="$pose" \
  HEADLESS=1 \
    setsid nohup ./build/px4_sitl_default/bin/px4 -i "$i" -d \
      </dev/null >"/tmp/px4_$i.log" 2>&1 &
  if [ "$i" -eq 0 ]; then
    echo "[sitl] waiting ~25s for gz server + instance 0 to initialize..."
    sleep 25
  else
    sleep 8
  fi
done

echo "[sitl] LAUNCH_DONE (N=$N)"
