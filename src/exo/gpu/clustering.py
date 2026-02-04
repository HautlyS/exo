"""GPU clustering and multi-device coordination.

Provides:
- Device registration and enumeration
- Device scoring and selection
- Multi-device workload distribution
- Telemetry aggregation
"""

import asyncio
import logging
from typing import Optional, Dict, List
from datetime import datetime, timezone

from exo.gpu.backend import GPUDevice, MemoryHandle, GPUBackend
from exo.gpu.telemetry_protocol import (
    GPUMetrics, DeviceCapabilities, DeviceType, DeviceScorer
)

logger = logging.getLogger(__name__)


class GPUClusteringManager:
    """Manage multi-GPU clustering and workload distribution."""

    def __init__(self):
        """Initialize clustering manager."""
        self._devices: Dict[str, GPUDevice] = {}
        self._telemetry = None
        self._workload_distributor = None
        self._backend: Optional[GPUBackend] = None
        self._telemetry_task: Optional[asyncio.Task] = None
        self._initialized = False
        
        # Lazy initialize components
        self._init_components()

    def _init_components(self) -> None:
        """Initialize clustering components."""
        if self._telemetry is None:
            self._telemetry = TelemetryCollector()
        if self._workload_distributor is None:
            self._workload_distributor = WorkloadDistributor()

    def register_device(self, device: GPUDevice) -> None:
        """Register a GPU device with the cluster.

        Args:
            device: GPU device to register
        """
        self._devices[device.device_id] = device
        logger.info(f"Registered device: {device.device_id} ({device.name})")

    def get_device(self, device_id: str) -> Optional[GPUDevice]:
        """Get device by ID.

        Args:
            device_id: Device identifier

        Returns:
            GPUDevice or None if not found
        """
        return self._devices.get(device_id)

    def list_devices(self) -> List[GPUDevice]:
        """Get all registered devices.

        Returns:
            List of GPUDevice objects
        """
        return list(self._devices.values())

    async def record_metrics(self, metrics: GPUMetrics) -> None:
        """Record metrics for a device.

        Args:
            metrics: GPU metrics to record
        """
        await self._telemetry.record_metrics(metrics)

    def get_aggregated_metrics(self) -> Dict:
        """Get aggregated metrics across all devices.

        Returns:
            Dict with aggregated metrics
        """
        return self._telemetry.get_aggregated_metrics()

    def select_best_device(
        self, min_memory_bytes: int = 0
    ) -> Optional[str]:
        """Select best device for a workload.

        Args:
            min_memory_bytes: Minimum required device memory

        Returns:
            Best device_id or None if no suitable device
        """
        devices_dict = {}
        for device_id in self._devices.keys():
            metrics = self._telemetry.get_metrics(device_id)
            if metrics:
                # Create basic capabilities from device info
                device = self._devices[device_id]
                caps = DeviceCapabilities(
                    device_id=device_id,
                    device_type=DeviceType.CUDA,
                    device_name=device.name,
                    vendor=device.vendor,
                    compute_units=device.compute_units,
                    memory_bandwidth_gbps=device.bandwidth_gbps,
                    max_memory_bytes=device.memory_bytes,
                    driver_version=device.driver_version,
                )
                devices_dict[device_id] = (metrics, caps)

        if not devices_dict:
            return None

        selector = DeviceSelector(devices_dict)
        return selector.select_best_device(min_memory_bytes)

    def distribute_workload(
        self,
        tasks: List,
        strategy: str = "uniform",
        capacities: Optional[Dict[str, float]] = None,
    ) -> Dict[str, List]:
        """Distribute workload across devices.

        Args:
            tasks: List of tasks to distribute
            strategy: Distribution strategy ('uniform' or 'capacity')
            capacities: Optional capacity weights for 'capacity' strategy

        Returns:
            Dict of device_id -> assigned tasks
        """
        device_ids = list(self._devices.keys())

        if strategy == "uniform":
            return self._workload_distributor.distribute_uniform(
                devices=device_ids,
                workload_items=tasks,
            )
        elif strategy == "capacity":
            if not capacities:
                # Use compute units as capacity
                capacities = {
                    did: float(self._devices[did].compute_units)
                    for did in device_ids
                }
            return self._workload_distributor.distribute_by_capacity(
                capacities=capacities,
                workload_items=tasks,
            )
        else:
            raise ValueError(f"Unknown distribution strategy: {strategy}")

    async def shutdown(self) -> None:
        """Shutdown clustering manager and cleanup resources."""
        if self._telemetry_task and not self._telemetry_task.done():
            self._telemetry_task.cancel()
            try:
                await self._telemetry_task
            except asyncio.CancelledError:
                pass

        if self._backend:
            await self._backend.shutdown()
            self._backend = None

        self._devices.clear()
        logger.info("GPU clustering manager shutdown")


class DeviceSelector:
    """Select best device(s) for workload based on metrics and capabilities."""

    def __init__(
        self,
        devices: Dict[str, tuple[GPUMetrics, DeviceCapabilities]],
    ):
        """Initialize device selector.

        Args:
            devices: Dict of device_id -> (metrics, capabilities)
        """
        self._devices = devices

    def select_best_device(
        self, min_memory_bytes: int = 0
    ) -> Optional[str]:
        """Select best device for a workload.

        Args:
            min_memory_bytes: Minimum required device memory

        Returns:
            Best device_id or None if no suitable device
        """
        ranked = self.rank_devices()

        for device_id, score in ranked:
            if score > 0.0:
                metrics, caps = self._devices[device_id]
                available_bytes = metrics.memory_total_bytes - metrics.memory_used_bytes
                if available_bytes >= min_memory_bytes:
                    return device_id

        return None

    def rank_devices(self) -> List[tuple[str, float]]:
        """Rank devices by suitability.

        Returns:
            List of (device_id, score) tuples sorted by score (highest first)
        """
        scores = []
        for device_id, (metrics, caps) in self._devices.items():
            score = DeviceScorer.score_device(metrics, caps)
            scores.append((device_id, score))

        return sorted(scores, key=lambda x: x[1], reverse=True)


class TelemetryCollector:
    """Collect and aggregate telemetry from GPU devices."""

    def __init__(self, max_history: int = 100):
        """Initialize telemetry collector.

        Args:
            max_history: Maximum history entries per device
        """
        self._max_history = max_history
        self._current_metrics: Dict[str, GPUMetrics] = {}
        self._metrics_history: Dict[str, List[GPUMetrics]] = {}

    async def record_metrics(self, metrics: GPUMetrics) -> None:
        """Record metrics from a device.

        Args:
            metrics: GPU metrics to record
        """
        device_id = metrics.device_id

        # Update current
        self._current_metrics[device_id] = metrics

        # Add to history
        if device_id not in self._metrics_history:
            self._metrics_history[device_id] = []

        self._metrics_history[device_id].append(metrics)

        # Keep history size limited
        if len(self._metrics_history[device_id]) > self._max_history:
            self._metrics_history[device_id] = self._metrics_history[device_id][
                -self._max_history :
            ]

        logger.debug(f"Recorded metrics for {device_id}")

    def get_metrics(self, device_id: str) -> Optional[GPUMetrics]:
        """Get current metrics for a device.

        Args:
            device_id: Device identifier

        Returns:
            GPUMetrics or None if no metrics recorded
        """
        return self._current_metrics.get(device_id)

    def get_metrics_history(self, device_id: str) -> List[GPUMetrics]:
        """Get metrics history for a device.

        Args:
            device_id: Device identifier

        Returns:
            List of GPUMetrics (empty if no history)
        """
        return self._metrics_history.get(device_id, [])

    def get_aggregated_metrics(self) -> Dict:
        """Get aggregated metrics across all devices.

        Returns:
            Dict with aggregated metrics
        """
        if not self._current_metrics:
            return {}

        devices = list(self._current_metrics.values())

        total_memory = sum(m.memory_total_bytes for m in devices)
        used_memory = sum(m.memory_used_bytes for m in devices)
        avg_utilization = (
            sum(m.compute_utilization_percent for m in devices)
            / len(devices)
        )
        avg_temp = sum(m.temperature_celsius for m in devices) / len(devices)
        total_power = sum(m.power_watts for m in devices)

        return {
            "device_count": len(devices),
            "total_memory_bytes": total_memory,
            "used_memory_bytes": used_memory,
            "available_memory_bytes": total_memory - used_memory,
            "average_utilization_percent": avg_utilization,
            "average_temperature_celsius": avg_temp,
            "total_power_watts": total_power,
            "timestamp": datetime.now(tz=timezone.utc).isoformat(),
        }


class WorkloadDistributor:
    """Distribute workload across devices based on capacity and constraints."""

    def distribute_uniform(
        self,
        devices: List[str],
        workload_items: List,
        max_per_device: Optional[int] = None,
    ) -> Dict[str, List]:
        """Distribute workload uniformly across devices.

        Args:
            devices: List of device IDs
            workload_items: Items to distribute
            max_per_device: Maximum items per device (optional)

        Returns:
            Dict of device_id -> list of assigned items
        """
        distribution = {d: [] for d in devices}

        if not devices or not workload_items:
            return distribution

        items_per_device = len(workload_items) // len(devices)
        remainder = len(workload_items) % len(devices)

        item_idx = 0
        for i, device_id in enumerate(devices):
            # Distribute remainder items to first devices
            count = items_per_device + (1 if i < remainder else 0)

            if max_per_device is not None:
                count = min(count, max_per_device)

            distribution[device_id] = workload_items[item_idx : item_idx + count]
            item_idx += count

        return distribution

    def distribute_by_capacity(
        self,
        capacities: Dict[str, float],
        workload_items: List,
    ) -> Dict[str, List]:
        """Distribute workload based on device capacity.

        Args:
            capacities: Dict of device_id -> capacity_weight (relative)
            workload_items: Items to distribute

        Returns:
            Dict of device_id -> list of assigned items
        """
        distribution = {d: [] for d in capacities.keys()}

        if not capacities or not workload_items:
            return distribution

        total_capacity = sum(capacities.values())
        item_idx = 0

        for device_id in sorted(capacities.keys()):
            capacity = capacities[device_id]
            proportion = capacity / total_capacity
            count = max(1, int(len(workload_items) * proportion))

            distribution[device_id] = workload_items[item_idx : item_idx + count]
            item_idx += count

        # Assign remaining items to largest capacity device
        if item_idx < len(workload_items):
            largest_device = max(capacities.keys(), key=lambda d: capacities[d])
            distribution[largest_device].extend(workload_items[item_idx:])

        return distribution
