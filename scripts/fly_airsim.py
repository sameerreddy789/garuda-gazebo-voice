#!/usr/bin/env python3
"""
GarudaOne DroneOS — Live Unreal Engine / AirSim Flight Controller
================================================================
Connects directly to the drone inside Unreal Engine 5.
Supports automated takeoff, hover, waypoint navigation, and live telemetry.
"""

import sys
import time
import math
import logging

try:
    import projectairsim as pas
except ImportError:
    print("[Error] projectairsim not found in Python environment. Run: pip install projectairsim")
    sys.exit(1)

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("AirSimPilot")


class LiveAirSimPilot:
    def __init__(self, address="127.0.0.1", port_topics=8989, port_services=8990, drone_name="Drone1"):
        self.address = address
        self.port_topics = port_topics
        self.port_services = port_services
        self.drone_name = drone_name
        
        self.client = None
        self.world = None
        self.drone = None
        self.is_connected = False
        self.altitude = 0.0

    def connect(self, timeout=15):
        log.info(f"Connecting to Unreal Engine simulation at {self.address} (topics={self.port_topics}, services={self.port_services})...")
        t0 = time.time()
        while time.time() - t0 < timeout:
            try:
                self.client = pas.ProjectAirSimClient(
                    address=self.address,
                    port_topics=self.port_topics,
                    port_services=self.port_services
                )
                self.client.connect()
                log.info("Connection to Unreal Engine simulation established!")
                break
            except Exception as e:
                time.sleep(1.0)
        else:
            log.warning("Could not auto-connect to ProjectAirSim client. Checking standard AirSim fallback...")
            return False

        try:
            self.drone = pas.Drone(self.client, self.drone_name)
            log.info(f"Drone [{self.drone_name}] acquired in simulation!")
            self.is_connected = True
            return True
        except Exception as e:
            log.error(f"Failed to bind drone: {e}")
            return False

    def takeoff(self, altitude=5.0):
        if not self.drone:
            log.error("Drone not initialized!")
            return False

        log.info(f"Enabling API control and arming motors for {self.drone_name}...")
        try:
            self.drone.enable_api_control()
            self.drone.arm()
            log.info(f"Motors armed! Initiating automated takeoff to {altitude:.1f} meters...")
            self.drone.takeoff(altitude=altitude)
            log.info(f"Hover established at {altitude:.1f}m!")
            return True
        except Exception as e:
            log.error(f"Takeoff error: {e}")
            return False

    def move(self, vx=0.0, vy=0.0, vz=0.0, duration=2.0):
        if not self.drone:
            return
        log.info(f"Velocity command: vx={vx}m/s, vy={vy}m/s, vz={vz}m/s for {duration}s")
        try:
            self.drone.move_by_velocity_async(vx, vy, vz, duration)
        except Exception as e:
            log.error(f"Move error: {e}")

    def land(self):
        if not self.drone:
            return
        log.info("Initiating automated landing sequence...")
        try:
            self.drone.land()
            log.info("Landed safely. Disarming motors.")
            self.drone.disarm()
            self.drone.disable_api_control()
        except Exception as e:
            log.error(f"Landing error: {e}")

    def get_telemetry(self):
        if not self.drone:
            return {}
        try:
            pose = self.drone.get_ground_truth_pose("NED")
            if pose:
                pos = pose.get("position", {})
                self.altitude = -pos.get("z", 0.0)
                return {
                    "x": pos.get("x", 0.0),
                    "y": pos.get("y", 0.0),
                    "z": pos.get("z", 0.0),
                    "alt_m": self.altitude
                }
        except Exception:
            pass
        return {}


def main():
    pilot = LiveAirSimPilot()
    print("==================================================")
    print("  GarudaOne DroneOS — Unreal Engine Live Flight   ")
    print("==================================================")
    connected = pilot.connect(timeout=5)
    if not connected:
        print("\n[Notice] Unreal Engine is not yet streaming on port 8989/8990.")
        print("Make sure your Unreal project is running and you have clicked Play in the editor.")
        print("To test standby mode or PX4 SITL, you can run: python scripts/voice_pilot.py\n")
        return

    print("\n[Ready] Press Enter to execute automated Takeoff to 5 meters...")
    input()
    pilot.takeoff(altitude=5.0)

    print("\n[Flight Mode] Commands: (w) forward, (s) back, (a) left, (d) right, (l) land, (q) quit")
    while True:
        cmd = input("DroneOS >> ").strip().lower()
        if cmd == "w":
            pilot.move(vx=2.0, duration=1.5)
        elif cmd == "s":
            pilot.move(vx=-2.0, duration=1.5)
        elif cmd == "a":
            pilot.move(vy=-2.0, duration=1.5)
        elif cmd == "d":
            pilot.move(vy=2.0, duration=1.5)
        elif cmd == "l":
            pilot.land()
            break
        elif cmd == "q":
            pilot.land()
            break


if __name__ == "__main__":
    main()
