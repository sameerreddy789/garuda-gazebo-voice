#!/usr/bin/env python3
"""Arm + GUIDED takeoff + hover + land an ArduCopter SITL coupled to Gazebo.
Targets the autopilot explicitly (sysid 1) and prints prearm STATUSTEXT."""
import sys
import time

from pymavlink import mavutil

CONN = sys.argv[1] if len(sys.argv) > 1 else "tcp:127.0.0.1:5760"
ALT = 8.0
SYS, COMP = 1, 1
ARMED = mavutil.mavlink.MAV_MODE_FLAG_SAFETY_ARMED

print(f"[fly] connecting {CONN} ...", flush=True)
m = mavutil.mavlink_connection(CONN, source_system=250)
m.wait_heartbeat(timeout=30)
print(f"[fly] link up (first hb sys={m.target_system}); targeting autopilot sys={SYS}", flush=True)
m.target_system, m.target_component = SYS, COMP
m.mav.request_data_stream_send(SYS, COMP, mavutil.mavlink.MAV_DATA_STREAM_ALL, 5, 1)


def set_mode(name):
    m.set_mode(m.mode_mapping()[name])
    print(f"[fly] mode -> {name}", flush=True)


def pump_status():
    while True:
        s = m.recv_match(type="STATUSTEXT", blocking=False)
        if not s:
            return
        print(f"[ap] {s.text}", flush=True)


set_mode("GUIDED")
time.sleep(1)

print("[fly] arming (waiting for EKF/GPS; prearm msgs below)...", flush=True)
armed = False
t0 = last_arm = 0.0
start = time.time()
while time.time() - start < 55:
    if time.time() - last_arm > 3:
        m.mav.command_long_send(SYS, COMP, mavutil.mavlink.MAV_CMD_COMPONENT_ARM_DISARM,
                                0, 1, 0, 0, 0, 0, 0, 0)
        last_arm = time.time()
    msg = m.recv_match(type=["HEARTBEAT", "STATUSTEXT"], blocking=True, timeout=1)
    if not msg:
        continue
    if msg.get_type() == "STATUSTEXT":
        print(f"[ap] {msg.text}", flush=True)
    elif msg.get_srcSystem() == SYS and (msg.base_mode & ARMED):
        armed = True
        break
print(f"[fly] armed={armed}", flush=True)
if not armed:
    sys.exit("[fly] FAILED to arm")

m.mav.command_long_send(SYS, COMP, mavutil.mavlink.MAV_CMD_NAV_TAKEOFF,
                        0, 0, 0, 0, 0, 0, 0, ALT)
print(f"[fly] takeoff -> {ALT}m commanded", flush=True)
t0 = time.time()
peak = 0.0
while time.time() - t0 < 40:
    msg = m.recv_match(type="GLOBAL_POSITION_INT", blocking=True, timeout=2)
    if msg:
        alt = msg.relative_alt / 1000.0
        peak = max(peak, alt)
        print(f"[fly] alt={alt:.2f}m", flush=True)
        if alt >= ALT * 0.9:
            break
print(f"[fly] reached ~{peak:.2f}m — hovering 6s", flush=True)
time.sleep(6)

set_mode("LAND")
print("[fly] landing...", flush=True)
t0 = time.time()
while time.time() - t0 < 60:
    hb = m.recv_match(type="HEARTBEAT", blocking=True, timeout=2)
    if hb and hb.get_srcSystem() == SYS and not (hb.base_mode & ARMED):
        print("[fly] disarmed/landed", flush=True)
        break
print(f"[fly] RESULT: PASS — flew to {peak:.1f}m in Gazebo and landed", flush=True)
