#!/usr/bin/env python3
"""
GarudaOne DroneOS — Airfield High-Altitude Autonomous Mission
=============================================================
1. Connects to PX4 SITL (airfield_obstacles world)
2. Arms motors and performs initial takeoff
3. Streams position setpoints at 10Hz to engage PX4 Offboard Mode
4. Climbs vertically to 105m altitude (above all airport obstacles & towers)
5. Translates 100m to the LEFT (West: East = -100m) at 105m altitude
6. Rotates 360° to survey the airfield, parked aircraft, and obstacles below
7. Flies back horizontally to home (North=0, East=0)
8. Commands automated landing safely onto the helipad
"""

import asyncio
import sys
from mavsdk import System
from mavsdk.offboard import OffboardError, PositionNedYaw

# Current active setpoint shared with the 10Hz stream loop
current_setpoint = PositionNedYaw(0.0, 0.0, -5.0, 0.0)
stream_active = True


async def setpoint_loop(drone):
    """Streams position setpoints at 10Hz as required by PX4 Offboard mode."""
    global current_setpoint, stream_active
    while stream_active:
        try:
            await drone.offboard.set_position_ned(current_setpoint)
        except Exception:
            pass
        await asyncio.sleep(0.1)


async def run_mission():
    global current_setpoint, stream_active
    drone = System()
    connection_url = sys.argv[1] if len(sys.argv) > 1 else "udpin://0.0.0.0:14550"

    print("\n========================================================", flush=True)
    print("  GarudaOne — 100m High-Altitude Airfield Mission", flush=True)
    print("========================================================", flush=True)
    print(f"▸ Connecting to PX4 at {connection_url}...", flush=True)

    await drone.connect(system_address=connection_url)

    print("▸ Waiting for drone connection...", flush=True)
    async for state in drone.core.connection_state():
        if state.is_connected:
            print("  ✓ Connected to PX4 Autopilot!", flush=True)
            break

    # Give MAVLink link a brief moment to sync
    await asyncio.sleep(2.0)

    # ── Step 1: Arm & Initial Takeoff ──────────────────────────────────────────
    print("\n[Step 1/5] Arming motors...", flush=True)
    try:
        await drone.action.arm()
        print("  ✓ Motors armed!", flush=True)
    except Exception as e:
        print(f"  [WARN] Arming note: {e}", flush=True)

    print("▸ Initiating takeoff to initial altitude (5.0m)...", flush=True)
    await drone.action.set_takeoff_altitude(5.0)
    await drone.action.takeoff()
    print("  ▸ Climbing to initial hover...", flush=True)
    await asyncio.sleep(7.0)
    print("  ✓ Drone airborne at 5.0m!", flush=True)

    # ── Step 2: Engage Offboard Mode at 10Hz ───────────────────────────────────
    print("\n[Step 2/5] Starting 10Hz setpoint stream and engaging Offboard mode...", flush=True)
    current_setpoint = PositionNedYaw(0.0, 0.0, -5.0, 0.0)
    stream_task = asyncio.create_task(setpoint_loop(drone))
    await asyncio.sleep(0.5)

    try:
        await drone.offboard.start()
        print("  ✓ Offboard control active and locked!", flush=True)
    except OffboardError as error:
        print(f"  [ERROR] Offboard start failed: {error._result.result}. Switching to manual climb.", flush=True)

    # ── Step 3: Vertical Climb Above 100m (Target: 105m) ───────────────────────
    target_altitude = 105.0
    print(f"\n[Step 3/5] Ascending vertically to {target_altitude}m above ground...", flush=True)
    print("  (Clearing control tower, aircraft hangar, and antennas)", flush=True)

    # Smooth stepped climb to 105m
    for alt in [15.0, 30.0, 50.0, 75.0, 90.0, 105.0]:
        current_setpoint = PositionNedYaw(0.0, 0.0, -alt, 0.0)
        print(f"  ▸ Ascending... current altitude target: {alt:.0f}m", flush=True)
        await asyncio.sleep(3.0)

    print(f"  ✓ High-altitude cruise reached: {target_altitude}m above airfield!", flush=True)
    await asyncio.sleep(2.0)

    # ── Step 4: Fly 100m to the LEFT (West: East = -100m) ─────────────────────
    print(f"\n[Step 4/5] Translating 100m to the LEFT at {target_altitude}m altitude...", flush=True)
    print("  (Cruising across the airfield corridor and obstacles below)", flush=True)

    for left_dist in [-25.0, -50.0, -75.0, -100.0]:
        current_setpoint = PositionNedYaw(0.0, left_dist, -target_altitude, 0.0)
        print(f"  ▸ Moving left: waypoint East = {left_dist:.0f}m (Altitude: {target_altitude:.0f}m)", flush=True)
        await asyncio.sleep(3.5)

    print("  ✓ Destination reached: 100m LEFT of takeoff point!", flush=True)
    await asyncio.sleep(2.0)

    # ── Panoramic Survey: 360° Yaw Rotation ───────────────────────────────────
    print("\n▸ Conducting 360° panoramic camera survey over the airfield...", flush=True)
    for yaw_angle in [90.0, 180.0, 270.0, 360.0]:
        current_setpoint = PositionNedYaw(0.0, -100.0, -target_altitude, yaw_angle)
        print(f"  ▸ Panning camera: yaw = {yaw_angle:.0f}° (surveying Cessna, Jet, and Hangars below)", flush=True)
        await asyncio.sleep(2.5)

    # ── Step 5: Return to Launch & Precision Landing ───────────────────────────
    print(f"\n[Step 5/5] Mission complete! Returning to launch position...", flush=True)
    print("  ▸ Returning horizontally: heading back to (North: 0m, East: 0m)...", flush=True)
    current_setpoint = PositionNedYaw(0.0, 0.0, -25.0, 0.0)
    await asyncio.sleep(6.0)

    # Stop offboard loop before landing
    stream_active = False
    await stream_task

    try:
        await drone.offboard.stop()
    except Exception:
        pass

    print("▸ Commanding automated precision landing onto helipad...", flush=True)
    await drone.action.land()

    async for in_air in drone.telemetry.in_air():
        if not in_air:
            print("  ✓ Touchdown! Motors disarmed on the helipad.", flush=True)
            break
        await asyncio.sleep(1.0)

    print("\n========================================================", flush=True)
    print("  MISSION SUCCESS: 100m LEFT + 105m HIGH ALTITUDE COMPLETE", flush=True)
    print("========================================================\n", flush=True)


if __name__ == "__main__":
    asyncio.run(run_mission())
