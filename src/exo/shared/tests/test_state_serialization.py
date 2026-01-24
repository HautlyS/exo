from datetime import datetime

from exo.shared.types.common import NodeId
from exo.shared.types.multiaddr import Multiaddr
from exo.shared.types.state import DeviceGPUState, State
from exo.shared.types.topology import Connection, SocketConnection


def test_state_serialization_roundtrip() -> None:
    """Verify that State → JSON → State round-trip preserves topology."""

    # --- build a simple state ------------------------------------------------
    node_a = NodeId("node-a")
    node_b = NodeId("node-b")

    connection = Connection(
        source=node_a,
        sink=node_b,
        edge=SocketConnection(
            sink_multiaddr=Multiaddr(address="/ip4/127.0.0.1/tcp/10001"),
        ),
    )

    state = State()
    state.topology.add_connection(connection)

    json_repr = state.model_dump_json()
    restored_state = State.model_validate_json(json_repr)

    assert (
        state.topology.to_snapshot().nodes
        == restored_state.topology.to_snapshot().nodes
    )
    assert set(state.topology.to_snapshot().connections) == set(
        restored_state.topology.to_snapshot().connections
    )
    assert restored_state.model_dump_json() == json_repr


def test_device_gpu_state_creation() -> None:
    """Test creating DeviceGPUState."""
    node_id = NodeId("node-1")
    state = DeviceGPUState(
        device_id="cuda:0",
        node_id=node_id,
        memory_used_bytes=4_000_000_000,
        memory_total_bytes=16_000_000_000,
        compute_utilization_percent=75.0,
        thermal_temperature_c=65.0,
    )

    assert state.device_id == "cuda:0"
    assert state.node_id == node_id
    assert state.memory_used_bytes == 4_000_000_000
    assert state.memory_total_bytes == 16_000_000_000
    assert state.compute_utilization_percent == 75.0
    assert state.thermal_temperature_c == 65.0


def test_device_gpu_state_memory_properties() -> None:
    """Test memory calculation properties."""
    state = DeviceGPUState(
        device_id="cuda:0",
        node_id=NodeId("node-1"),
        memory_used_bytes=8_000_000_000,
        memory_total_bytes=16_000_000_000,
        compute_utilization_percent=50.0,
        thermal_temperature_c=60.0,
    )

    assert state.memory_available_bytes == 8_000_000_000
    assert state.memory_utilization_percent == 50.0


def test_device_gpu_state_in_cluster_state() -> None:
    """Test adding DeviceGPUState to cluster State."""
    node_id = NodeId("node-1")
    device_state = DeviceGPUState(
        device_id="cuda:0",
        node_id=node_id,
        memory_used_bytes=4_000_000_000,
        memory_total_bytes=16_000_000_000,
        compute_utilization_percent=60.0,
        thermal_temperature_c=70.0,
    )

    state = State()
    state.gpu_device_state = {"cuda:0": device_state}

    assert "cuda:0" in state.gpu_device_state
    assert state.gpu_device_state["cuda:0"].device_id == "cuda:0"
    assert state.gpu_device_state["cuda:0"].memory_utilization_percent == 25.0


def test_device_gpu_state_thermal_throttling() -> None:
    """Test thermal throttling state."""
    state = DeviceGPUState(
        device_id="cuda:0",
        node_id=NodeId("node-1"),
        memory_used_bytes=1_000_000_000,
        memory_total_bytes=16_000_000_000,
        compute_utilization_percent=80.0,
        thermal_temperature_c=85.0,
        thermal_throttle_threshold_c=85.0,
        is_thermal_throttling=True,
    )

    assert state.is_thermal_throttling is True
    assert state.thermal_temperature_c == state.thermal_throttle_threshold_c


def test_device_gpu_state_mobile_battery() -> None:
    """Test mobile device battery status."""
    state = DeviceGPUState(
        device_id="metal:0",
        node_id=NodeId("iphone"),
        memory_used_bytes=2_000_000_000,
        memory_total_bytes=4_000_000_000,
        compute_utilization_percent=45.0,
        thermal_temperature_c=42.0,
        battery_percent=75.0,
        is_plugged_in=False,
    )

    assert state.battery_percent == 75.0
    assert state.is_plugged_in is False
    assert state.memory_utilization_percent == 50.0
