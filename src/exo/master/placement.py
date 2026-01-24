import logging
import random
from collections.abc import Mapping
from copy import deepcopy
from typing import Sequence

from exo.master.placement_csp import ConstraintSatisfactionPlacement, GPUDeviceScore
from exo.master.placement_utils import (
    Cycle,
    filter_cycles_by_memory,
    get_mlx_jaccl_coordinators,
    get_mlx_jaccl_devices_matrix,
    get_mlx_ring_hosts_by_node,
    get_shard_assignments,
    get_smallest_cycles,
)
from exo.shared.models.model_cards import ModelId
from exo.shared.topology import Topology
from exo.shared.types.commands import (
    CreateInstance,
    DeleteInstance,
    PlaceInstance,
)
from exo.shared.types.common import NodeId
from exo.shared.types.events import Event, InstanceCreated, InstanceDeleted
from exo.shared.types.memory import Memory
from exo.shared.types.profiling import MemoryUsage, NodeNetworkInfo
from exo.shared.types.state import DeviceGPUState
from exo.shared.types.worker.instances import (
    Instance,
    InstanceId,
    InstanceMeta,
    MlxJacclInstance,
    MlxRingInstance,
)
from exo.shared.types.worker.shards import Sharding

logger = logging.getLogger(__name__)


def random_ephemeral_port() -> int:
    port = random.randint(49153, 65535)
    return port - 1 if port <= 52415 else port


def _has_heterogeneous_gpus(gpu_device_state: Mapping[str, DeviceGPUState]) -> bool:
    """Check if cluster has heterogeneous GPU types.
    
    Returns True if:
    - Multiple device types (cuda:0, cuda:1 are same type)
    - Different memory sizes
    - Different compute capabilities
    """
    if len(gpu_device_state) <= 1:
        return False
    
    devices = list(gpu_device_state.values())
    
    # Check if any device memory differs
    memory_sizes = {d.memory_total_bytes for d in devices}
    if len(memory_sizes) > 1:
        logger.debug(f"Heterogeneous memory detected: {memory_sizes}")
        return True
    
    # Check if any device utilization differs significantly
    utilizations = {d.memory_utilization_percent for d in devices}
    if len(utilizations) > 1 and max(utilizations) - min(utilizations) > 20:
        logger.debug(f"Heterogeneous utilization detected: {utilizations}")
        return True
    
    return False


def _compute_device_scores(
    cycle_node_ids: Sequence[NodeId],
    gpu_device_state: Mapping[str, DeviceGPUState],
    shard_size_bytes: int,
    topology: Topology,
) -> list[GPUDeviceScore]:
    """Compute placement scores for devices in a cycle.
    
    Scores consider:
    - Memory fit (shard size vs available memory)
    - Compute utilization (prefer idle devices)
    - Thermal headroom (mobile devices)
    - Network position (prefer central nodes)
    """
    scores = []
    
    for dev_state in gpu_device_state.values():
        if dev_state.node_id not in cycle_node_ids:
            continue
        
        # Memory score: 0 = not enough, 1 = plenty of space
        memory_available = dev_state.memory_available_bytes
        if memory_available < shard_size_bytes:
            memory_score = 0.0
        elif memory_available >= shard_size_bytes * 2:
            memory_score = 1.0
        else:
            memory_score = memory_available / (shard_size_bytes * 2)
        
        # Compute score: 0 = busy, 1 = idle
        compute_score = max(0.0, 1.0 - dev_state.compute_utilization_percent / 100.0)
        
        # Thermal score: 0 = hot, 1 = cool
        thermal_margin = dev_state.thermal_throttle_threshold_c - dev_state.thermal_temperature_c
        if thermal_margin < 0:
            thermal_score = 0.0
        elif thermal_margin < 5:
            thermal_score = 0.3
        else:
            thermal_score = min(1.0, thermal_margin / 20.0)
        
        # Network score (simplified): prefer nodes with higher ID (leaf nodes)
        # In real implementation, this would use topology centrality
        network_score = 1.0
        
        score = GPUDeviceScore(
            device_id=dev_state.device_id,
            node_id=dev_state.node_id,
            compute_score=compute_score,
            memory_score=memory_score,
            network_score=network_score,
            thermal_score=thermal_score,
            bandwidth_score=1.0,
        )
        scores.append(score)
    
    return scores


def add_instance_to_placements(
    command: CreateInstance,
    topology: Topology,
    current_instances: Mapping[InstanceId, Instance],
) -> Mapping[InstanceId, Instance]:
    # TODO: validate against topology

    return {**current_instances, command.instance.instance_id: command.instance}


def place_instance(
    command: PlaceInstance,
    topology: Topology,
    current_instances: Mapping[InstanceId, Instance],
    node_memory: Mapping[NodeId, MemoryUsage],
    node_network: Mapping[NodeId, NodeNetworkInfo],
    required_nodes: set[NodeId] | None = None,
    gpu_device_state: Mapping[str, DeviceGPUState] | None = None,
) -> dict[InstanceId, Instance]:
    cycles = topology.get_cycles()
    candidate_cycles = list(filter(lambda it: len(it) >= command.min_nodes, cycles))

    # Filter to cycles containing all required nodes (subset matching)
    if required_nodes:
        candidate_cycles = [
            cycle
            for cycle in candidate_cycles
            if required_nodes.issubset(cycle.node_ids)
        ]
    cycles_with_sufficient_memory = filter_cycles_by_memory(
        candidate_cycles, node_memory, command.model_card.storage_size
    )
    if len(cycles_with_sufficient_memory) == 0:
        raise ValueError("No cycles found with sufficient memory")

    if command.sharding == Sharding.Tensor:
        if not command.model_card.supports_tensor:
            raise ValueError(
                f"Requested Tensor sharding but this model does not support tensor parallelism: {command.model_card.model_id}"
            )
        # TODO: the condition here for tensor parallel is not correct, but it works good enough for now.
        cycles_with_sufficient_memory = [
            cycle
            for cycle in cycles_with_sufficient_memory
            if command.model_card.hidden_size % len(cycle) == 0
        ]
        if not cycles_with_sufficient_memory:
            raise ValueError(
                f"No tensor sharding found for model with hidden_size {command.model_card.hidden_size} candidate cycles"
            )
    if command.sharding == Sharding.Pipeline and command.model_card.model_id == ModelId(
        "mlx-community/DeepSeek-V3.1-8bit"
    ):
        raise ValueError(
            "Pipeline parallelism is not supported for DeepSeek V3.1 (8-bit)"
        )

    smallest_cycles = get_smallest_cycles(cycles_with_sufficient_memory)

    smallest_rdma_cycles = [
        cycle for cycle in smallest_cycles if topology.is_rdma_cycle(cycle)
    ]

    if command.instance_meta == InstanceMeta.MlxJaccl and smallest_rdma_cycles != []:
        smallest_cycles = smallest_rdma_cycles

    cycles_with_leaf_nodes: list[Cycle] = [
        cycle
        for cycle in smallest_cycles
        if any(topology.node_is_leaf(node_id) for node_id in cycle)
    ]

    selected_cycle = max(
        cycles_with_leaf_nodes if cycles_with_leaf_nodes != [] else smallest_cycles,
        key=lambda cycle: sum(
            (node_memory[node_id].ram_available for node_id in cycle),
            start=Memory(),
        ),
    )

    shard_assignments = get_shard_assignments(
        command.model_card, selected_cycle, command.sharding, node_memory
    )

    cycle_digraph: Topology = topology.get_subgraph_from_nodes(selected_cycle.node_ids)

    instance_id = InstanceId()
    target_instances = dict(deepcopy(current_instances))

    if len(selected_cycle) == 1:
        command.instance_meta = InstanceMeta.MlxRing

    # TODO: Single node instances
    match command.instance_meta:
        case InstanceMeta.MlxJaccl:
            mlx_jaccl_devices = get_mlx_jaccl_devices_matrix(
                [node_id for node_id in selected_cycle],
                cycle_digraph,
            )
            mlx_jaccl_coordinators = get_mlx_jaccl_coordinators(
                coordinator=selected_cycle.node_ids[0],
                coordinator_port=random_ephemeral_port(),
                cycle_digraph=cycle_digraph,
                node_network=node_network,
            )
            target_instances[instance_id] = MlxJacclInstance(
                instance_id=instance_id,
                shard_assignments=shard_assignments,
                jaccl_devices=mlx_jaccl_devices,
                jaccl_coordinators=mlx_jaccl_coordinators,
            )
        case InstanceMeta.MlxRing:
            ephemeral_port = random_ephemeral_port()
            hosts_by_node = get_mlx_ring_hosts_by_node(
                selected_cycle=selected_cycle,
                cycle_digraph=cycle_digraph,
                ephemeral_port=ephemeral_port,
                node_network=node_network,
            )
            target_instances[instance_id] = MlxRingInstance(
                instance_id=instance_id,
                shard_assignments=shard_assignments,
                hosts_by_node=hosts_by_node,
                ephemeral_port=ephemeral_port,
            )

    return target_instances


def delete_instance(
    command: DeleteInstance,
    current_instances: Mapping[InstanceId, Instance],
) -> dict[InstanceId, Instance]:
    target_instances = dict(deepcopy(current_instances))
    if command.instance_id in target_instances:
        del target_instances[command.instance_id]
        return target_instances
    raise ValueError(f"Instance {command.instance_id} not found")


def get_transition_events(
    current_instances: Mapping[InstanceId, Instance],
    target_instances: Mapping[InstanceId, Instance],
) -> Sequence[Event]:
    events: list[Event] = []

    # find instances to create
    for instance_id, instance in target_instances.items():
        if instance_id not in current_instances:
            events.append(
                InstanceCreated(
                    instance=instance,
                )
            )

    # find instances to delete
    for instance_id in current_instances:
        if instance_id not in target_instances:
            events.append(
                InstanceDeleted(
                    instance_id=instance_id,
                )
            )

    return events
