.PHONY: run run-sim run-sitl sitl sitl-setup test download-models setup lint clean

# Run the DroneOS application (real hardware)
run:
	python -m garuda.main

# Run with simulation mode (stub telemetry — no hardware or SITL required)
run-sim:
	GARUDA_MODE=simulation python -m garuda.main

# Run connected to PX4 SITL (requires SITL running in WSL2)
# Use this after starting SITL with: make sitl
run-sitl:
	GARUDA_MODE=simulation python -m garuda.main

# Launch PX4 SITL + Gazebo inside WSL2 (run in separate terminal)
sitl:
	wsl bash scripts/launch_sitl.sh

# Launch PX4 SITL + Gazebo in 3D City Environment (Skyscrapers, Boulevards, Rooftop Helipads)
sitl-city:
	wsl bash scripts/launch_sitl.sh --world city

# Setup PX4 SITL environment in WSL2 (one-time installation)
sitl-setup:
	wsl bash scripts/setup_sitl.sh

# Run all tests
test:
	python -m pytest tests/ -v

# Download all AI model weights
download-models:
	python scripts/download_models.py

# Setup development environment
setup:
	pip install -r requirements.txt
	mkdir -p models

# Lint
lint:
	python -m py_compile garuda/main.py
	python -m py_compile garuda/core/orchestrator.py

# Clean artifacts
clean:
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -name "*.pyc" -delete 2>/dev/null || true
