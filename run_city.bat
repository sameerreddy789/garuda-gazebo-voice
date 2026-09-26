@echo off
echo =======================================================================
echo   GarudaOne DroneOS -- Launching 3D City Simulation (PX4 + Gazebo)
echo =======================================================================
echo.
echo Launching PX4 SITL with 3D City World in WSL2 Ubuntu...
echo The Gazebo 3D simulation window will appear on your desktop.
echo.
wsl -d Ubuntu bash -c "cd '/mnt/d/Hackathons/Projects/Web Dev/New/DroneOS' && bash scripts/launch_sitl.sh --world city"
pause
