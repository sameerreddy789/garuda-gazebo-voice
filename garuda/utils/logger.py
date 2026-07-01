"""
GarudaOne DroneOS — Structured Logging
======================================
Async-friendly structured logger with per-module tags,
flight session recording, and performance timestamps.
"""

import io
import logging
import os
import sys
from datetime import datetime
from logging.handlers import RotatingFileHandler


class GarudaLogger:
    """
    Centralized logger for all DroneOS modules.

    Each module gets a tagged child logger so you can instantly see
    which part of the system generated each log line:
        [2026-07-01 16:30:00.123] [INFO] [flight] Armed successfully
        [2026-07-01 16:30:00.456] [INFO] [perception] Subject detected: conf=0.92
    """

    _instance = None
    _initialized = False

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        if GarudaLogger._initialized:
            return
        GarudaLogger._initialized = True

        self._root_logger = logging.getLogger("garuda")
        self._root_logger.setLevel(logging.DEBUG)

        # Console handler — human readable
        # Wrap stdout in UTF-8 to avoid UnicodeEncodeError on Windows cp1252
        try:
            utf8_stdout = io.TextIOWrapper(
                sys.stdout.buffer, encoding="utf-8", errors="replace",
                line_buffering=True,
            )
        except AttributeError:
            # Fallback if stdout has no buffer (e.g., some IDE consoles)
            utf8_stdout = sys.stdout

        console = logging.StreamHandler(utf8_stdout)
        console.setLevel(logging.INFO)
        console_fmt = logging.Formatter(
            "[%(asctime)s.%(msecs)03d] [%(levelname)-5s] [%(name)s] %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
        console.setFormatter(console_fmt)
        self._root_logger.addHandler(console)

        # File handler — detailed, rotating
        log_dir = os.path.join(os.path.dirname(__file__), "..", "..", "logs")
        os.makedirs(log_dir, exist_ok=True)

        log_file = os.path.join(
            log_dir,
            f"garuda_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log",
        )
        file_handler = RotatingFileHandler(
            log_file, maxBytes=50 * 1024 * 1024, backupCount=5
        )
        file_handler.setLevel(logging.DEBUG)
        file_fmt = logging.Formatter(
            "%(asctime)s.%(msecs)03d | %(levelname)-8s | %(name)-20s | %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
        file_handler.setFormatter(file_fmt)
        self._root_logger.addHandler(file_handler)

    def get_logger(self, module_name: str) -> logging.Logger:
        """
        Get a child logger for a specific module.

        Args:
            module_name: Short name like 'flight', 'perception', 'brain', 'voice'

        Returns:
            A logging.Logger tagged with the module name
        """
        return self._root_logger.getChild(module_name)


def get_logger(module_name: str) -> logging.Logger:
    """Convenience function — call from any module to get a tagged logger."""
    return GarudaLogger().get_logger(module_name)
