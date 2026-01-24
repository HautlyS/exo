from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Any, cast

from pydantic import ConfigDict, Field, field_serializer, field_validator
from pydantic.alias_generators import to_camel

from exo.shared.topology import Topology, TopologySnapshot
from exo.shared.types.common import NodeId
from exo.shared.types.profiling import (
    MemoryUsage,
    NodeIdentity,
    NodeNetworkInfo,
    NodeThunderboltInfo,
    SystemPerformanceProfile,
    ThunderboltBridgeStatus,
)
from exo.shared.types.tasks import Task, TaskId
from exo.shared.types.worker.downloads import DownloadProgress
from exo.shared.types.worker.instances import Instance, InstanceId
from exo.shared.types.worker.runners import RunnerId, RunnerStatus
from exo.utils.pydantic_ext import CamelCaseModel


@dataclass(frozen=True)
class DeviceGPUState:
    """GPU device state tracking for heterogeneous clustering.
    
    Tracks per-device metrics needed for placement and monitoring:
    - Memory usage (current vs. total)
    - Compute utilization
    - Thermal status
    - Battery status (mobile devices)
    """

    device_id: str
    """Unique device identifier (e.g., 'cuda:0', 'metal:0')"""
    
    node_id: NodeId
    """Node owning this device"""
    
    memory_used_bytes: int
    """Current memory usage in bytes"""
    
    memory_total_bytes: int
    """Total device memory in bytes"""
    
    compute_utilization_percent: float
    """Current compute utilization (0-100)"""
    
    thermal_temperature_c: float
    """Current temperature in Celsius (or -1 if unavailable)"""
    
    thermal_throttle_threshold_c: float = 85.0
    """Hardware throttling threshold (default 85°C)"""
    
    is_thermal_throttling: bool = False
    """Whether device is currently thermal throttling"""
    
    battery_percent: float = 100.0
    """Battery charge (0-100, mobile devices only)"""
    
    is_plugged_in: bool = True
    """Whether device is plugged in (mobile devices)"""
    
    last_update: datetime = Field(default_factory=datetime.now)
    """When this state was last updated"""
    
    @property
    def memory_available_bytes(self) -> int:
        """Available memory in bytes."""
        return max(0, self.memory_total_bytes - self.memory_used_bytes)
    
    @property
    def memory_utilization_percent(self) -> float:
        """Memory utilization as percentage."""
        if self.memory_total_bytes == 0:
            return 0.0
        return 100.0 * self.memory_used_bytes / self.memory_total_bytes


class State(CamelCaseModel):
    """Global system state.

    The :class:`Topology` instance is encoded/decoded via an immutable
    :class:`~shared.topology.TopologySnapshot` to ensure compatibility with
    standard JSON serialisation.
    """

    model_config = ConfigDict(
        alias_generator=to_camel,
        validate_by_name=True,
        extra="forbid",
        # I want to reenable this ASAP, but it's causing an issue with TaskStatus
        strict=True,
        arbitrary_types_allowed=True,
    )
    instances: Mapping[InstanceId, Instance] = {}
    runners: Mapping[RunnerId, RunnerStatus] = {}
    downloads: Mapping[NodeId, Sequence[DownloadProgress]] = {}
    tasks: Mapping[TaskId, Task] = {}
    last_seen: Mapping[NodeId, datetime] = {}
    topology: Topology = Field(default_factory=Topology)
    last_event_applied_idx: int = Field(default=-1, ge=-1)

    # Granular node state mappings (update independently at different frequencies)
    node_identities: Mapping[NodeId, NodeIdentity] = {}
    node_memory: Mapping[NodeId, MemoryUsage] = {}
    node_system: Mapping[NodeId, SystemPerformanceProfile] = {}
    node_network: Mapping[NodeId, NodeNetworkInfo] = {}
    node_thunderbolt: Mapping[NodeId, NodeThunderboltInfo] = {}
    node_thunderbolt_bridge: Mapping[NodeId, ThunderboltBridgeStatus] = {}

    # GPU device state tracking for heterogeneous clustering
    # Key: "device_id" (e.g., "cuda:0"), Value: DeviceGPUState
    gpu_device_state: Mapping[str, DeviceGPUState] = {}

    # Detected cycles where all nodes have Thunderbolt bridge enabled (>2 nodes)
    thunderbolt_bridge_cycles: Sequence[Sequence[NodeId]] = []

    @field_serializer("topology", mode="plain")
    def _encode_topology(self, value: Topology) -> TopologySnapshot:
        return value.to_snapshot()

    @field_validator("topology", mode="before")
    @classmethod
    def _deserialize_topology(cls, value: object) -> Topology:  # noqa: D401 – Pydantic validator signature
        """Convert an incoming *value* into a :class:`Topology` instance.

        Accepts either an already constructed :class:`Topology` or a mapping
        representing :class:`~shared.topology.TopologySnapshot`.
        """

        if isinstance(value, Topology):
            return value

        if isinstance(value, Mapping):  # likely a snapshot-dict coming from JSON
            snapshot = TopologySnapshot(**cast(dict[str, Any], value))  # type: ignore[arg-type]
            return Topology.from_snapshot(snapshot)

        raise TypeError("Invalid representation for Topology field in State")
