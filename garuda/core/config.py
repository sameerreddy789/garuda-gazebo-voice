"""
GarudaOne DroneOS — Configuration Loader
=========================================
Loads and merges YAML configuration files from config/ directory.
Supports environment overrides (dev/sim/prod) via GARUDA_MODE env var.
"""

import os
from pathlib import Path
from typing import Any

import yaml

from garuda.utils.logger import get_logger

log = get_logger("config")


class Config:
    """
    Centralized configuration for all DroneOS modules.

    Loads three YAML files:
      - drone.yaml   → Hardware specs, PID data, sensor config
      - models.yaml  → AI model paths, inference parameters
      - mission.yaml → Flight parameters, safety limits, shot modes

    Access values using dot notation via get():
      config.get("flight.max_speed_ms")         → 10.0
      config.get("tracking.default_follow_distance_m")  → 5.0
    """

    def __init__(self, config_dir: str | None = None):
        if config_dir is None:
            # Default: config/ directory relative to project root
            config_dir = os.path.join(
                os.path.dirname(__file__), "..", "..", "config"
            )

        self._config_dir = Path(config_dir).resolve()
        self._data: dict[str, Any] = {}
        self._mode = os.environ.get("GARUDA_MODE", "hardware")

        log.info(f"Loading config from: {self._config_dir}")
        log.info(f"Mode: {self._mode}")

        self._load_all()

    def _load_all(self) -> None:
        """Load all configuration files."""
        config_files = ["drone.yaml", "models.yaml", "mission.yaml"]

        for filename in config_files:
            filepath = self._config_dir / filename
            if filepath.exists():
                with open(filepath, "r", encoding="utf-8") as f:
                    data = yaml.safe_load(f)
                    if data:
                        self._data.update(data)
                        log.info(f"  Loaded {filename} ({len(data)} top-level keys)")
            else:
                log.warning(f"  Config file not found: {filepath}")

    def get(self, key_path: str, default: Any = None) -> Any:
        """
        Get a config value using dot-notation path.

        Examples:
            config.get("flight.max_speed_ms")          → 10.0
            config.get("detector.input_width")          → 320
            config.get("safety.battery_warn_percent")   → 30
            config.get("nonexistent.key", "fallback")   → "fallback"
        """
        keys = key_path.split(".")
        current = self._data

        for key in keys:
            if isinstance(current, dict) and key in current:
                current = current[key]
            else:
                return default

        return current

    def get_required(self, key_path: str) -> Any:
        """Get a config value, raising an error if missing."""
        value = self.get(key_path)
        if value is None:
            raise KeyError(f"Required config key not found: {key_path}")
        return value

    @property
    def mode(self) -> str:
        """Current operating mode: 'hardware', 'simulation', or 'dev'."""
        return self._mode

    @property
    def is_simulation(self) -> bool:
        return self._mode == "simulation"

    @property
    def is_hardware(self) -> bool:
        return self._mode == "hardware"

    @property
    def models_dir(self) -> Path:
        """Absolute path to the models directory."""
        models_rel = self.get("models_dir", "models")
        return (self._config_dir.parent / models_rel).resolve()

    def dump(self) -> dict:
        """Return full config as dict (for debugging)."""
        return self._data.copy()
