"""
GarudaOne DroneOS — Multi-Vehicle Swarm Manager (PX4 SITL via MAVSDK)
=====================================================================
Spins up N independent MAVSDK connections, one per PX4 vehicle, over
sequentially allocated UDP ports.

Why this works without ROS 2:
  PX4 multi-vehicle SITL assigns each instance its own MAVSDK remote UDP
  port starting at 14540 (instance 0 -> 14540, instance 1 -> 14541, ...).
  Each ``mavsdk.System`` therefore talks to exactly one vehicle, so the
  telemetry and command streams stay strictly isolated with no ROS 2
  middleware, namespacing, or DDS layer required. This keeps the swarm on
  the same lightweight async foundation as the single-drone stack.

Two isolation requirements (both learned the hard way):
  1. Connection scheme: PX4 SITL SENDS its onboard MAVLink stream TO the API
     port (local 14580 -> remote 14540), so the companion must LISTEN.
     -> use ``udpin`` (bind), not ``udpout`` (which silently never connects).
  2. gRPC server port: each ``System`` auto-starts its own ``mavsdk_server``.
     If they all use the default gRPC port (50051) the servers collide and
     the vehicles end up SHARING one link (telemetry + commands cross-talk).
     -> give every drone a UNIQUE gRPC port (base_grpc_port + instance).

Named ``SwarmManager`` (not "orchestrator") to avoid confusion with the
single-vehicle mission state machine in ``garuda.core.orchestrator``.
"""

import asyncio
from typing import Any, Callable, Optional

from garuda.core.config import Config
from garuda.utils.logger import get_logger

log = get_logger("swarm")

# PX4 SITL allocates MAVSDK remote UDP ports sequentially from here.
DEFAULT_BASE_PORT = 14540
# Each System's mavsdk_server needs its own gRPC port; allocate from here.
DEFAULT_BASE_GRPC_PORT = 50051


def _default_system_factory(grpc_port: int) -> Any:
    """Create a real MAVSDK ``System`` bound to a UNIQUE gRPC server port.

    Each ``System`` auto-starts its own ``mavsdk_server``. Left at the default
    port (50051) the servers collide and multiple vehicles silently share one
    link. A distinct port per drone guarantees isolation — this is the
    standard MAVSDK-Python multi-vehicle pattern.

    Imported lazily so this module stays importable (and testable) on
    machines without ``mavsdk`` installed. Raises ImportError if mavsdk is
    genuinely missing, which the caller handles gracefully.
    """
    from mavsdk import System  # type: ignore

    return System(port=grpc_port)


class DroneAgent:
    """One autonomous vehicle in the swarm, backed by a single MAVSDK link.

    Each agent owns its own ``System`` instance (on its own gRPC port) and a
    private telemetry task, so nothing is shared between vehicles.
    """

    def __init__(
        self,
        system_id: int,
        udp_port: int,
        connection_url: str,
        grpc_port: int = DEFAULT_BASE_GRPC_PORT,
        connection_timeout_s: float = 10.0,
        system_factory: Optional[Callable[[int], Any]] = None,
    ):
        self.system_id = system_id
        self.udp_port = udp_port
        self.connection_url = connection_url
        self.grpc_port = grpc_port
        self.connection_timeout_s = connection_timeout_s
        self._system_factory = system_factory or _default_system_factory

        self.drone: Optional[Any] = None
        self.is_connected = False

        # Latest telemetry cache (updated by the monitor task).
        self.latest_altitude_m: float = 0.0
        self.latest_position: Optional[Any] = None

        self._tasks: list[asyncio.Task] = []

    async def connect(self) -> bool:
        """Establish an isolated MAVSDK connection with a hard timeout.

        Returns True only if a heartbeat is received within the timeout.
        Never raises for the common failure cases (no vehicle, no mavsdk);
        it logs and returns False so one bad agent can't sink the swarm.
        """
        log.info(
            f"[Drone {self.system_id}] Connecting on {self.connection_url} "
            f"(gRPC server port {self.grpc_port}) ..."
        )

        try:
            self.drone = self._system_factory(self.grpc_port)
        except ImportError:
            log.warning(
                f"[Drone {self.system_id}] mavsdk not installed — cannot connect. "
                "Install with: pip install mavsdk"
            )
            return False
        except Exception as e:  # noqa: BLE001 - defensive: factory must not sink swarm
            log.error(f"[Drone {self.system_id}] failed to create System: {e}")
            return False

        try:
            await self.drone.connect(system_address=self.connection_url)
        except Exception as e:  # noqa: BLE001
            log.error(f"[Drone {self.system_id}] connect() failed: {e}")
            return False

        try:
            await asyncio.wait_for(
                self._await_heartbeat(), timeout=self.connection_timeout_s
            )
        except asyncio.TimeoutError:
            log.warning(
                f"[Drone {self.system_id}] No heartbeat within "
                f"{self.connection_timeout_s}s — is SITL instance "
                f"{self.system_id} running on port {self.udp_port}?"
            )
            self.is_connected = False
            return False

        log.info(
            f"[Drone {self.system_id}] Heartbeat established on port "
            f"{self.udp_port}."
        )
        return True

    async def _await_heartbeat(self) -> None:
        """Block until MAVSDK reports the vehicle as connected."""
        async for state in self.drone.core.connection_state():
            if state.is_connected:
                self.is_connected = True
                return

    async def _monitor_telemetry(self) -> None:
        """Continuously cache position telemetry without blocking the loop."""
        try:
            async for position in self.drone.telemetry.position():
                self.latest_position = position
                self.latest_altitude_m = getattr(
                    position, "relative_altitude_m", 0.0
                )
                log.debug(
                    f"[Drone {self.system_id}] Alt: "
                    f"{self.latest_altitude_m:.2f}m"
                )
        except asyncio.CancelledError:
            log.info(f"[Drone {self.system_id}] Telemetry monitoring stopped.")
            raise
        except Exception as e:  # noqa: BLE001
            log.debug(f"[Drone {self.system_id}] telemetry stream ended: {e}")

    def start_monitoring(self) -> None:
        """Spawn the background telemetry task (only if connected)."""
        if self.is_connected and self.drone is not None:
            self._tasks.append(
                asyncio.create_task(
                    self._monitor_telemetry(),
                    name=f"drone{self.system_id}-telemetry",
                )
            )

    async def stop(self) -> None:
        """Cancel background tasks and release the vehicle reference."""
        for task in self._tasks:
            task.cancel()
        for task in self._tasks:
            try:
                await task
            except asyncio.CancelledError:
                pass
        self._tasks.clear()
        self.is_connected = False
        self.drone = None


class SwarmManager:
    """Spawns and coordinates multiple :class:`DroneAgent` instances.

    Reads swarm sizing and connection settings from config (``swarm.*``)
    and builds one agent per sequential UDP port, each on its own gRPC port.
    """

    def __init__(
        self,
        config: Config,
        system_factory: Optional[Callable[[int], Any]] = None,
    ):
        self.config = config

        self.base_port = int(config.get("swarm.base_port", DEFAULT_BASE_PORT))
        self.base_grpc_port = int(
            config.get("swarm.base_grpc_port", DEFAULT_BASE_GRPC_PORT)
        )
        self.drone_count = max(1, int(config.get("swarm.drone_count", 2)))
        self.scheme = config.get("swarm.connection_scheme", "udpin")
        self.host = config.get("swarm.connection_host", "localhost")
        self.timeout_s = float(config.get("swarm.connection_timeout_s", 10.0))

        self.agents: list[DroneAgent] = [
            DroneAgent(
                system_id=i,
                udp_port=self.base_port + i,
                connection_url=self._build_url(self.base_port + i),
                grpc_port=self.base_grpc_port + i,
                connection_timeout_s=self.timeout_s,
                system_factory=system_factory,
            )
            for i in range(self.drone_count)
        ]

        last_port = self.base_port + self.drone_count - 1
        log.info(
            f"SwarmManager initialized — {self.drone_count} agents on "
            f"{self.scheme}://{self.host}:{self.base_port}..{last_port} "
            f"(gRPC {self.base_grpc_port}..{self.base_grpc_port + self.drone_count - 1})"
        )

    def _build_url(self, port: int) -> str:
        """Build the MAVSDK connection URL for a given instance port.

        Scheme is configurable because the correct form depends on how PX4
        SITL is launched:
          - ``udpin://host:port``  — MAVSDK listens on 14540+i. This is the
            DEFAULT and the verified-correct form for PX4 SITL, which sends
            its onboard MAVLink stream *to* the API port (e.g. local 14580 ->
            remote 14540), so the companion must be the listener.
          - ``udpout://host:port`` — MAVSDK dials out. Use only if a given
            setup has PX4 binding/listening on the API port instead.
        """
        if self.scheme in ("udpin", "udpout"):
            return f"{self.scheme}://{self.host}:{port}"
        # Legacy/simple form.
        return f"udp://{self.host}:{port}"

    async def connect_all(self) -> int:
        """Connect every agent concurrently. Returns the number connected.

        Failures are isolated: an agent that times out or errors is skipped,
        and the rest of the swarm still comes online.
        """
        results = await asyncio.gather(
            *(agent.connect() for agent in self.agents),
            return_exceptions=True,
        )

        connected = 0
        for agent, result in zip(self.agents, results):
            if result is True:
                agent.start_monitoring()
                connected += 1
            elif isinstance(result, Exception):
                log.error(
                    f"[Drone {agent.system_id}] connection raised: {result}"
                )

        log.info(
            f"Swarm substrate online — {connected}/{self.drone_count} "
            "drones connected"
        )
        return connected

    @property
    def connected_agents(self) -> list[DroneAgent]:
        """The subset of agents that currently have a live link."""
        return [agent for agent in self.agents if agent.is_connected]

    async def shutdown(self) -> None:
        """Tear down every agent's tasks and connections."""
        await asyncio.gather(
            *(agent.stop() for agent in self.agents),
            return_exceptions=True,
        )
        log.info("Swarm substrate shut down")
