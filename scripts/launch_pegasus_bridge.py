"""
GarudaOne DroneOS - Pegasus Simulator Bridge for Isaac Sim
==========================================================
Run this script INSIDE Isaac Sim's Python environment to:
1. Spawn the virtual drone (FlyLens 85 physics).
2. Connect it to PX4 SITL (running in headless mode).
3. Publish the simulated camera feed to GarudaOS.

Prerequisites:
  - NVIDIA Isaac Sim (installed via Omniverse Launcher)
  - Pegasus Simulator Extension enabled
"""


# Isaac Sim / Omniverse core imports
from omni.isaac.core import World
from omni.isaac.core.utils.extensions import enable_extension

# Enable Pegasus Simulator
enable_extension("PegasusSimulator")
from pegasus.simulator.params import ROBOTS, SIMULATION_ENVIRONMENTS
from pegasus.simulator.logic.vehicles.multirotor import Multirotor, MultirotorConfig
from pegasus.simulator.logic.interface.pegasus_interface import PegasusInterface
from pegasus.simulator.logic.backends.mavlink_backend import MavlinkBackend, MavlinkBackendConfig

def main():
    # 1. Initialize the Isaac Sim World
    world = World(stage_units_in_meters=1.0)
    
    # Initialize the Pegasus Interface
    pegasus_sim = PegasusInterface()
    pegasus_sim.load_environment(SIMULATION_ENVIRONMENTS["Warehouse"])

    # 2. Configure MAVLink Backend (Connects to PX4 SITL)
    mavlink_config = MavlinkBackendConfig({
        "vehicle_id": 0,
        "px4_autostart": 4001,
        "px4_dir": "",            # Assumes PX4 is running externally via launch_sitl_headless.sh
        "sim_port": 14560,
    })
    
    # 3. Create the Multirotor (Garuda Drone)
    config = MultirotorConfig()
    config.backends = [MavlinkBackend(mavlink_config)]
    
    # Add a front-facing camera for the perception AI
    from pegasus.simulator.logic.sensors.camera import Camera
    config.sensors = [
        Camera("front_cam", config={"resolution": [640, 480], "fov": 90.0, "update_rate": 30.0})
    ]

    # Spawn drone at coordinate 0,0,1
    Multirotor(
        "/World/quadcopter",
        ROBOTS["Iris"],  # We use Iris as the base template in simulation
        0,
        [0.0, 0.0, 1.0],
        Rotation=[0.0, 0.0, 0.0, 1.0],
        config=config,
    )

    # Reset and play
    world.reset()
    print("Pegasus Bridge Active: Isaac Sim is now rendering physics for PX4 SITL.")
    
    # 4. Simulation Loop
    while True:
        world.step(render=True)
        
        # Here we would capture drone.sensors["front_cam"].get_rgb() and stream it to GarudaOS
        # For this bridge, we rely on Isaac Sim's internal rendering or ROS2 bridge if configured.

if __name__ == "__main__":
    main()
