"""
GarudaOne — Swarm Substrate + Aerial Detector Unit Tests
========================================================
Stack-independent tests that run natively on Windows with NO PX4 SITL and
NO model weights:

  - AerialDetector: stub fallback + the YOLOv8/v11 ONNX decode/NMS math
    (exercised with a synthetic output tensor, no real model needed).
  - SwarmManager:   sequential-port assignment + concurrent connect over a
    mocked MAVSDK System (no real UDP / SITL involved).

Run with:
    python -m pytest tests/test_swarm_logic.py -v
"""

import asyncio
from types import SimpleNamespace

import numpy as np
import pytest

from garuda.core.config import Config
from garuda.perception.detector import AerialDetector
from garuda.flight.swarm_manager import DroneAgent, SwarmManager
from garuda.utils.transforms import BoundingBox


@pytest.fixture
def config():
    return Config()


# ─────────────────────────────────────────────────────────────────────────
# Aerial detector
# ─────────────────────────────────────────────────────────────────────────

class TestAerialDetector:
    """YOLO/ONNX aerial detector — stub fallback and decode math."""

    def test_load_model_falls_back_to_stub(self, config):
        """With no ONNX weights present, it must load a stub, not crash."""
        detector = AerialDetector(config)
        assert detector.load_model() is True
        assert detector.backend == "stub"
        assert detector.is_loaded is True

    def test_detect_returns_list(self, config):
        """detect() returns a list[BoundingBox] in stub mode."""
        detector = AerialDetector(config)
        detector.load_model()
        frame = np.zeros((480, 640, 3), dtype=np.uint8)
        result = detector.detect(frame)
        assert isinstance(result, list)
        for det in result:
            assert isinstance(det, BoundingBox)

    def test_postprocess_decodes_person_and_applies_nms(self, config):
        """A synthetic YOLOv11 tensor should decode to one person box.

        Layout (VisDrone, 10 classes): channels = 4 box + 10 class = 14.
        Tensor shape (1, 14, N) with N candidate boxes. No objectness score.
        """
        detector = AerialDetector(config)
        # Pin thresholds so the test doesn't depend on YAML values.
        detector._conf_threshold = 0.4
        detector._nms_threshold = 0.45
        detector._person_class_ids = {0, 1}
        detector._persons_only = True

        num_classes = 10
        num_boxes = 4
        raw = np.zeros((1, 4 + num_classes, num_boxes), dtype=np.float32)

        # Box 0: strong "people" (class 1) at frame center, 64x128 px.
        raw[0, 0, 0], raw[0, 1, 0], raw[0, 2, 0], raw[0, 3, 0] = 320, 320, 64, 128
        raw[0, 4 + 1, 0] = 0.90
        # Box 1: near-duplicate of box 0 -> should be removed by NMS.
        raw[0, 0, 1], raw[0, 1, 1], raw[0, 2, 1], raw[0, 3, 1] = 322, 321, 64, 128
        raw[0, 4 + 1, 1] = 0.85
        # Box 2: strong "car" (class 3) -> dropped by persons_only.
        raw[0, 0, 2], raw[0, 1, 2], raw[0, 2, 2], raw[0, 3, 2] = 100, 100, 50, 50
        raw[0, 4 + 3, 2] = 0.95
        # Box 3: low-confidence pedestrian -> dropped by threshold.
        raw[0, 0, 3], raw[0, 1, 3], raw[0, 2, 3], raw[0, 3, 3] = 500, 400, 40, 40
        raw[0, 4 + 0, 3] = 0.10

        # gain=1, no padding, original frame == model input (640x640).
        detections = detector._postprocess(
            raw, gain=1.0, pad_w=0.0, pad_h=0.0, orig_w=640, orig_h=640
        )

        assert len(detections) == 1, "NMS + filters should leave one box"
        det = detections[0]
        # Person class (1) is re-mapped to 0 so the tracker locks onto it.
        assert det.class_id == 0
        assert det.confidence == pytest.approx(0.90, abs=1e-5)
        assert det.x_center == pytest.approx(0.5, abs=0.02)
        assert det.y_center == pytest.approx(0.5, abs=0.02)
        assert det.width == pytest.approx(0.10, abs=0.02)
        assert det.height == pytest.approx(0.20, abs=0.02)

    def test_postprocess_undoes_letterbox_padding(self, config):
        """Letterbox padding/scale must be removed before normalizing."""
        detector = AerialDetector(config)
        detector._conf_threshold = 0.4
        detector._nms_threshold = 0.45
        detector._person_class_ids = {0, 1}
        detector._persons_only = True

        # Simulate a 1280x720 frame letterboxed into 640x640:
        #   gain = 640/1280 = 0.5, scaled = 640x360, pad_h = (640-360)/2 = 140.
        gain, pad_w, pad_h = 0.5, 0.0, 140.0
        orig_w, orig_h = 1280, 720

        # A detection at the true center of the original frame maps to
        # letterbox pixel (640*0.5, 360*0.5 + 140) = (320, 320).
        raw = np.zeros((1, 14, 1), dtype=np.float32)
        raw[0, 0, 0], raw[0, 1, 0], raw[0, 2, 0], raw[0, 3, 0] = 320, 320, 100, 100
        raw[0, 4 + 0, 0] = 0.8  # pedestrian

        dets = detector._postprocess(raw, gain, pad_w, pad_h, orig_w, orig_h)
        assert len(dets) == 1
        assert dets[0].x_center == pytest.approx(0.5, abs=0.02)
        assert dets[0].y_center == pytest.approx(0.5, abs=0.02)

    def test_postprocess_empty_on_garbage_shape(self, config):
        """A malformed tensor must return [] rather than raising."""
        detector = AerialDetector(config)
        assert detector._postprocess(
            np.zeros((5,), dtype=np.float32), 1.0, 0.0, 0.0, 640, 640
        ) == []


# ─────────────────────────────────────────────────────────────────────────
# Mock MAVSDK System (no real network / SITL)
# ─────────────────────────────────────────────────────────────────────────

class _FakeCore:
    def __init__(self, connected: bool):
        self._connected = connected

    async def connection_state(self):
        if self._connected:
            yield SimpleNamespace(is_connected=True)
        else:
            # Never reports connected -> the agent's wait_for should time out.
            await asyncio.sleep(10.0)
            yield SimpleNamespace(is_connected=True)


class _FakeTelemetry:
    async def position(self):
        while True:
            yield SimpleNamespace(relative_altitude_m=5.0)
            await asyncio.sleep(0.02)


class FakeSystem:
    """Minimal stand-in for mavsdk.System covering the paths we use."""

    def __init__(self, connected: bool = True):
        self.core = _FakeCore(connected)
        self.telemetry = _FakeTelemetry()
        self.connected_address = None

    async def connect(self, system_address: str = ""):
        self.connected_address = system_address


# ─────────────────────────────────────────────────────────────────────────
# Swarm manager
# ─────────────────────────────────────────────────────────────────────────

class TestSwarmManager:
    """Multi-vehicle substrate — port math and concurrent connect."""

    def _swarm_config(self, count: int, timeout: float = 5.0) -> Config:
        cfg = Config()
        cfg._data["swarm"] = {
            "drone_count": count,
            "base_port": 14540,
            "connection_scheme": "udpout",
            "connection_host": "localhost",
            "connection_timeout_s": timeout,
        }
        return cfg

    def test_sequential_port_assignment(self):
        """Agent i must bind to base_port + i with a matching URL."""
        cfg = self._swarm_config(count=3)
        swarm = SwarmManager(cfg, system_factory=lambda p: FakeSystem(True))

        assert len(swarm.agents) == 3
        assert [a.udp_port for a in swarm.agents] == [14540, 14541, 14542]
        assert swarm.agents[0].connection_url == "udpout://localhost:14540"
        assert swarm.agents[2].connection_url == "udpout://localhost:14542"
        # Each drone must get its OWN gRPC server port (else mavsdk_server
        # instances collide and vehicles share one link).
        assert [a.grpc_port for a in swarm.agents] == [50051, 50052, 50053]

    @pytest.mark.asyncio
    async def test_connect_all_success(self):
        """All agents connect concurrently over the mocked System."""
        cfg = self._swarm_config(count=3)
        swarm = SwarmManager(cfg, system_factory=lambda p: FakeSystem(True))

        connected = await swarm.connect_all()
        assert connected == 3
        assert len(swarm.connected_agents) == 3

        # Telemetry monitor should populate the altitude cache.
        await asyncio.sleep(0.05)
        assert swarm.agents[0].latest_altitude_m == pytest.approx(5.0)

        await swarm.shutdown()
        assert len(swarm.connected_agents) == 0

    @pytest.mark.asyncio
    async def test_connect_all_times_out_cleanly(self):
        """A vehicle that never sends a heartbeat is skipped, not fatal."""
        cfg = self._swarm_config(count=2, timeout=0.2)
        swarm = SwarmManager(cfg, system_factory=lambda p: FakeSystem(False))

        connected = await swarm.connect_all()
        assert connected == 0
        assert swarm.connected_agents == []

        await swarm.shutdown()

    @pytest.mark.asyncio
    async def test_partial_connect(self):
        """Mixed fleet: some vehicles up, some down -> only live ones count."""
        cfg = self._swarm_config(count=2, timeout=0.3)
        # First agent connects, second never does.
        systems = iter([FakeSystem(True), FakeSystem(False)])
        swarm = SwarmManager(cfg, system_factory=lambda p: next(systems))

        connected = await swarm.connect_all()
        assert connected == 1
        assert len(swarm.connected_agents) == 1
        assert swarm.connected_agents[0].system_id == 0

        await swarm.shutdown()

    @pytest.mark.asyncio
    async def test_missing_mavsdk_returns_false(self):
        """If the System factory raises ImportError, connect() returns False."""
        def broken_factory(port):
            raise ImportError("mavsdk not installed")

        agent = DroneAgent(
            system_id=0,
            udp_port=14540,
            connection_url="udpout://localhost:14540",
            connection_timeout_s=1.0,
            system_factory=broken_factory,
        )
        assert await agent.connect() is False
        assert agent.is_connected is False
