"""
GarudaOne DroneOS — Autonomous AI-Powered Cinematography Drone
==============================================================

3-Layer Liquid AI Architecture:
  Layer 1 (Brain):      LFM-2.5-230M + Needle 26M — voice understanding + tool calling
  Layer 2 (Perception): PicoDet-S + SVO2 + CfC LNN — vision + spatial + control
  Layer 3 (Flight):     PX4 via MAVSDK-Python — 400Hz PID motor control

Target: Raspberry Pi 5 (8GB), CPU-only, sub-250g drone
"""

__version__ = "0.1.0"
__author__ = "GarudaOne Team"
