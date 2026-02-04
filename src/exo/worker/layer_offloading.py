"""Layer Offloading Manager - intelligent layer distribution across heterogeneous GPUs.

Manages:
- Layer-to-device mapping
- Dynamic layer migration
- Load balancing across devices
- Memory-aware placement
- Bandwidth-aware scheduling

Integrates with Worker's execution model and GPU topology.
"""

import asyncio
import logging
from dataclasses import dataclass, field
from typing import Optional, Dict, List, Set
from enum import Enum

from exo.gpu.backend import GPUDevice
from exo.shared.gpu_topology import GPUTopology

logger = logging.getLogger(__name__)


class LayerType(str, Enum):
    """Neural network layer types."""

    EMBEDDING = "embedding"
    ATTENTION = "attention"
    MLP = "mlp"
    NORMALIZATION = "normalization"
    OUTPUT = "output"


@dataclass
class LayerSpec:
    """Specification for a neural network layer."""

    layer_id: str
    """Unique layer identifier"""

    layer_type: LayerType
    """Type of layer"""

    memory_bytes: int
    """Memory required for layer weights and activations"""

    compute_flops: float
    """Estimated compute operations (FLOPS)"""

    input_size_bytes: int
    """Size of input tensor"""

    output_size_bytes: int
    """Size of output tensor"""

    dependencies: Set[str] = field(default_factory=set)
    """Layer IDs that must execute before this layer"""

    metadata: Dict = field(default_factory=dict)
    """Additional layer metadata"""


@dataclass
class LayerPlacement:
    """Placement decision for a layer."""

    layer_id: str
    device_id: str
    estimated_latency_ms: float
    memory_overhead_bytes: int
    transfer_cost_ms: float = 0.0
    """Cost of transferring data to/from this device"""


@dataclass
class OffloadingPlan:
    """Complete offloading plan for a model."""

    placements: List[LayerPlacement]
    """Layer placements"""

    total_memory_bytes: int
    """Total memory required across all devices"""

    estimated_latency_ms: float
    """Estimated end-to-end latency"""

    device_utilization: Dict[str, float]
    """Utilization per device (0.0 to 1.0)"""

    bottleneck_device: Optional[str] = None
    """Device that limits throughput"""


class LayerOffloadingManager:
    """Manager for layer offloading across heterogeneous GPUs."""

    def __init__(self, topology: GPUTopology):
        """Initialize layer offloading manager.

        Args:
            topology: GPU topology with device information
        """
        self.topology = topology
        self._current_plan: Optional[OffloadingPlan] = None
        self._layer_cache: Dict[str, str] = {}  # layer_id -> device_id
        self._lock = asyncio.Lock()

        logger.info("Layer offloading manager initialized")

    async def create_offloading_plan(
        self,
        layers: List[LayerSpec],
        devices: List[GPUDevice],
        optimization_goal: str = "latency",
    ) -> OffloadingPlan:
        """Create optimal offloading plan for layers across devices.

        Args:
            layers: List of layer specifications
            devices: Available GPU devices
            optimization_goal: "latency", "memory", or "balanced"

        Returns:
            OffloadingPlan: Optimal placement plan
        """
        async with self._lock:
            logger.info(
                f"Creating offloading plan for {len(layers)} layers "
                f"across {len(devices)} devices (goal: {optimization_goal})"
            )

            if optimization_goal == "latency":
                plan = await self._optimize_for_latency(layers, devices)
            elif optimization_goal == "memory":
                plan = await self._optimize_for_memory(layers, devices)
            else:  # balanced
                plan = await self._optimize_balanced(layers, devices)

            self._current_plan = plan

            logger.info(
                f"Created offloading plan: "
                f"{len(plan.placements)} placements, "
                f"estimated latency: {plan.estimated_latency_ms:.2f}ms"
            )

            return plan

    async def _optimize_for_latency(
        self,
        layers: List[LayerSpec],
        devices: List[GPUDevice],
    ) -> OffloadingPlan:
        """Optimize for minimum latency.

        Strategy:
        - Place compute-heavy layers on fastest devices
        - Minimize data transfers between devices
        - Pipeline execution where possible

        Args:
            layers: Layer specifications
            devices: Available devices

        Returns:
            OffloadingPlan: Latency-optimized plan
        """
        placements = []
        device_memory_used = {d.device_id: 0 for d in devices}

        # Sort devices by compute capability
        sorted_devices = sorted(
            devices,
            key=lambda d: d.compute_units * d.clock_rate_mhz,
            reverse=True,
        )

        # Sort layers by compute requirements
        sorted_layers = sorted(layers, key=lambda l: l.compute_flops, reverse=True)

        for layer in sorted_layers:
            # Find device with sufficient memory and best compute
            best_device = None
            best_latency = float("inf")

            for device in sorted_devices:
                available_memory = device.memory_available - device_memory_used[device.device_id]

                if available_memory < layer.memory_bytes:
                    continue

                # Estimate latency on this device
                compute_time = layer.compute_flops / (
                    device.compute_units * device.clock_rate_mhz * 1e6
                )

                # Add transfer cost if previous layer on different device
                transfer_cost = 0.0
                if placements:
                    prev_placement = placements[-1]
                    if prev_placement.device_id != device.device_id:
                        # Estimate transfer time
                        transfer_size = layer.input_size_bytes
                        transfer_cost = transfer_size / (device.bandwidth_gbps * 1e9)

                total_latency = compute_time + transfer_cost

                if total_latency < best_latency:
                    best_latency = total_latency
                    best_device = device

            if best_device is None:
                raise RuntimeError(
                    f"Cannot place layer {layer.layer_id}: insufficient memory"
                )

            # Create placement
            placement = LayerPlacement(
                layer_id=layer.layer_id,
                device_id=best_device.device_id,
                estimated_latency_ms=best_latency * 1000,
                memory_overhead_bytes=layer.memory_bytes,
                transfer_cost_ms=(best_latency - (layer.compute_flops / (
                    best_device.compute_units * best_device.clock_rate_mhz * 1e6
                ))) * 1000 if placements else 0.0,
            )

            placements.append(placement)
            device_memory_used[best_device.device_id] += layer.memory_bytes

        # Calculate plan metrics
        total_memory = sum(device_memory_used.values())
        total_latency = sum(p.estimated_latency_ms for p in placements)

        device_utilization = {
            device_id: used / next(d.memory_available for d in devices if d.device_id == device_id)
            for device_id, used in device_memory_used.items()
        }

        # Find bottleneck device (highest utilization)
        bottleneck = max(device_utilization.items(), key=lambda x: x[1])[0]

        return OffloadingPlan(
            placements=placements,
            total_memory_bytes=total_memory,
            estimated_latency_ms=total_latency,
            device_utilization=device_utilization,
            bottleneck_device=bottleneck,
        )

    async def _optimize_for_memory(
        self,
        layers: List[LayerSpec],
        devices: List[GPUDevice],
    ) -> OffloadingPlan:
        """Optimize for minimum memory usage.

        Strategy:
        - Distribute layers evenly across devices
        - Minimize peak memory usage per device
        - Allow higher latency for better memory efficiency

        Args:
            layers: Layer specifications
            devices: Available devices

        Returns:
            OffloadingPlan: Memory-optimized plan
        """
        placements = []
        device_memory_used = {d.device_id: 0 for d in devices}

        # Sort devices by available memory
        sorted_devices = sorted(
            devices,
            key=lambda d: d.memory_available,
            reverse=True,
        )

        for layer in layers:
            # Find device with most available memory
            best_device = None
            max_available = 0

            for device in sorted_devices:
                available = device.memory_available - device_memory_used[device.device_id]

                if available >= layer.memory_bytes and available > max_available:
                    max_available = available
                    best_device = device

            if best_device is None:
                raise RuntimeError(
                    f"Cannot place layer {layer.layer_id}: insufficient memory"
                )

            # Estimate latency
            compute_time = layer.compute_flops / (
                best_device.compute_units * best_device.clock_rate_mhz * 1e6
            )

            placement = LayerPlacement(
                layer_id=layer.layer_id,
                device_id=best_device.device_id,
                estimated_latency_ms=compute_time * 1000,
                memory_overhead_bytes=layer.memory_bytes,
            )

            placements.append(placement)
            device_memory_used[best_device.device_id] += layer.memory_bytes

        # Calculate metrics
        total_memory = sum(device_memory_used.values())
        total_latency = sum(p.estimated_latency_ms for p in placements)

        device_utilization = {
            device_id: used / next(d.memory_available for d in devices if d.device_id == device_id)
            for device_id, used in device_memory_used.items()
        }

        bottleneck = max(device_utilization.items(), key=lambda x: x[1])[0]

        return OffloadingPlan(
            placements=placements,
            total_memory_bytes=total_memory,
            estimated_latency_ms=total_latency,
            device_utilization=device_utilization,
            bottleneck_device=bottleneck,
        )

    async def _optimize_balanced(
        self,
        layers: List[LayerSpec],
        devices: List[GPUDevice],
    ) -> OffloadingPlan:
        """Optimize for balanced latency and memory.

        Strategy:
        - Balance compute load across devices
        - Keep memory usage reasonable
        - Minimize cross-device transfers

        Args:
            layers: Layer specifications
            devices: Available devices

        Returns:
            OffloadingPlan: Balanced plan
        """
        # Use weighted combination of latency and memory optimization
        latency_plan = await self._optimize_for_latency(layers, devices)
        memory_plan = await self._optimize_for_memory(layers, devices)

        # Choose plan with better overall score
        latency_score = 1.0 / (latency_plan.estimated_latency_ms + 1)
        memory_score = 1.0 / (latency_plan.total_memory_bytes / 1e9 + 1)

        latency_plan_score = 0.6 * latency_score + 0.4 * memory_score

        latency_score_mem = 1.0 / (memory_plan.estimated_latency_ms + 1)
        memory_score_mem = 1.0 / (memory_plan.total_memory_bytes / 1e9 + 1)

        memory_plan_score = 0.6 * latency_score_mem + 0.4 * memory_score_mem

        if latency_plan_score >= memory_plan_score:
            logger.info("Balanced plan: using latency-optimized approach")
            return latency_plan
        else:
            logger.info("Balanced plan: using memory-optimized approach")
            return memory_plan

    async def get_layer_device(self, layer_id: str) -> Optional[str]:
        """Get device assignment for a layer.

        Args:
            layer_id: Layer identifier

        Returns:
            str: Device ID or None if not assigned
        """
        async with self._lock:
            if self._current_plan is None:
                return None

            for placement in self._current_plan.placements:
                if placement.layer_id == layer_id:
                    return placement.device_id

            return None

    async def migrate_layer(
        self,
        layer_id: str,
        target_device_id: str,
    ) -> bool:
        """Migrate a layer to a different device.

        Args:
            layer_id: Layer to migrate
            target_device_id: Target device

        Returns:
            bool: True if migration successful
        """
        async with self._lock:
            if self._current_plan is None:
                logger.warning("No offloading plan exists")
                return False

            # Find layer placement
            placement = None
            for p in self._current_plan.placements:
                if p.layer_id == layer_id:
                    placement = p
                    break

            if placement is None:
                logger.warning(f"Layer {layer_id} not found in plan")
                return False

            # Update placement
            old_device = placement.device_id
            placement.device_id = target_device_id

            logger.info(
                f"Migrated layer {layer_id} from {old_device} to {target_device_id}"
            )

            return True

    def get_current_plan(self) -> Optional[OffloadingPlan]:
        """Get current offloading plan.

        Returns:
            OffloadingPlan or None if no plan exists
        """
        return self._current_plan

    async def clear_plan(self) -> None:
        """Clear current offloading plan."""
        async with self._lock:
            self._current_plan = None
            self._layer_cache.clear()
            logger.info("Cleared offloading plan")
