.PHONY: run test download-models setup lint clean

# Run the DroneOS application
run:
	python -m garuda.main

# Run with simulation mode (no hardware required)
run-sim:
	GARUDA_MODE=simulation python -m garuda.main

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
