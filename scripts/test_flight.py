import asyncio
from mavsdk import System

async def run():
    drone = System()
    # Connect to the secondary simulator port so we don't interfere with DroneOS
    await drone.connect(system_address="udpin://0.0.0.0:14550")
    
    print("Searching for simulator...")
    async for state in drone.core.connection_state():
        if state.is_connected:
            print("✓ Connected to PX4 Simulator!")
            break
            
    print("Arming motors...")
    await drone.action.arm()
    
    print("Taking off!")
    await drone.action.takeoff()
    
    print("Hovering for 10 seconds...")
    await asyncio.sleep(10)
    
    print("Landing...")
    await drone.action.land()

if __name__ == "__main__":
    asyncio.run(run())
