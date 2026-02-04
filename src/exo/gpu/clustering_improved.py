"""GPU clustering and multi-device coordination - IMPROVED VERSION.

This module contains production-hardened versions of clustering components
with fixes for:
- Memory management (Issue #1: deque for bounded history)
- Error handling (Issue #2: Init validation, #3: Input validation)
- Async safety (Issue #5: Race condition guards)
- Resource cleanup (Issue #6: Comprehensive shutdown)

Use this as reference for improvements to clustering.py
"""

import asyncio
import logging
from collections import deque
from typing import Optional, Dict, List, Any, Union
from datetime import datetime, timezone
from enum import Enum

from exo.gpu.backend import GPUDevice, MemoryHandle, GPUBackend
from exo.gpu.telemetry_protocol import (
    GPUMetrics, DeviceCapabilities, DeviceType, DeviceScorer
)

logger = logging.getLogger(__name__)


class DistributionStrategy(Enum):
    """Type-safe distribution strategies (replaces string matching)."""
    UNIFORM = "uniform"
    CAPACITY = "capacity"


class GPUClusteringManagerImproved:
    """Production-hardened GPU clustering manager.
    
    Improvements:
    - Initialization error handling (Issue #2)
    - Shutdown race condition guard (Issue #5)
    - Input validation (Issue #3)
    - Comprehensive cleanup (Issue #6)
    """

    def __init__(self) -> None:
        """Initialize clustering manager with error handling."""
        self._devices: Dict[str, GPUDevice] = {}
        self._telemetry: Optional[TelemetryCollectorImproved] = None
        self._workload_distributor: Optional[WorkloadDistributorImproved] = None
        self._backend: Optional[GPUBackend] = None
        self._telemetry_task: Optional[asyncio.Task] = None
        self._initialized = False
        self._shutdown_event = asyncio.Event()
        self._metrics_lock = asyncio.Lock()
        
        # Initialize components with error handling
        self._init_components()

    def _init_components(self) -> None:
        """Initialize clustering components with error handling.
        
        Raises:
            RuntimeError: If initialization fails
        """
        try:
            if self._telemetry is None:
                self._telemetry = TelemetryCollectorImproved()
            if self._workload_distributor is None:
                self._workload_distributor = WorkloadDistributorImproved()
            self._initialized = True
            logger.info("GPU clustering components initialized")
        except Exception as e:
            logger.error(f"Failed to initialize clustering components: {e}")
            self._initialized = False
            raise RuntimeError(
                f"Clustering component initialization failed: {e}"
            ) from e

    def _check_initialized(self) -> None:
        """Verify manager is initialized before operations.
        
        Raises:
            RuntimeError: If not initialized
        """
        if not self._initialized:
            raise RuntimeError("GPUClusteringManager not properly initialized")
        
        if self._shutdown_event.is_set():
            raise RuntimeError("GPUClusteringManager is shutting down")

    def register_device(self, device: GPUDevice) -> None:
        """Register a GPU device with the cluster.

        Args:
            device: GPU device to register
            
        Raises:
            ValueError: If device is invalid
        """
        self._check_initialized()
        
        if not device.device_id:
            raise ValueError("Device must have valid device_id")
        
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
        """Record metrics for a device with validation and thread safety.

        Args:
            metrics: GPU metrics to record
            
        Raises:
            KeyError: If device not registered
            ValueError: If metrics are invalid
            RuntimeError: If shutting down
        """
        self._check_initialized()
        
        # Check for shutdown
        if self._shutdown_event.is_set():
            raise RuntimeError("Cannot record metrics: manager shutting down")
        
        # Validate device is registered
        if metrics.device_id not in self._devices:
            raise KeyError(f"Device {metrics.device_id} not registered")
        
        # Validate metric ranges
        if not 0 <= metrics.compute_utilization_percent <= 100:
            raise ValueError(
                f"Utilization out of range [0, 100]: "
                f"{metrics.compute_utilization_percent}%"
            )
        
        if metrics.memory_used_bytes < 0:
            raise ValueError(
                f"Memory used cannot be negative: {metrics.memory_used_bytes}"
            )
        
        if metrics.memory_total_bytes <= 0:
            raise ValueError(
                f"Total memory must be positive: {metrics.memory_total_bytes}"
            )
        
        if metrics.memory_used_bytes > metrics.memory_total_bytes:
            raise ValueError(
                f"Used memory ({metrics.memory_used_bytes}) exceeds total "
                f"({metrics.memory_total_bytes})"
            )
        
        if metrics.temperature_celsius < -273.15:  # Absolute zero
            raise ValueError(
                f"Temperature below absolute zero: {metrics.temperature_celsius}°C"
            )
        
        # Record with lock to prevent race conditions
        async with self._metrics_lock:
            await self._telemetry.record_metrics(metrics)

    def get_aggregated_metrics(self) -> Dict[str, Any]:
        """Get aggregated metrics across all devices.

        Returns:
            Dict with aggregated metrics, or empty dict if no devices
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
            
        Raises:
            ValueError: If min_memory_bytes is negative
        """
        if min_memory_bytes < 0:
            raise ValueError("min_memory_bytes cannot be negative")
        
        devices_dict = {}
        for device_id in self._devices.keys():
            metrics = self._telemetry.get_metrics(device_id)
            if metrics:
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

        selector = DeviceSelectorImproved(devices_dict)
        return selector.select_best_device(min_memory_bytes)

    def distribute_workload(
        self,
        tasks: List[Any],
        strategy: Union[DistributionStrategy, str] = DistributionStrategy.UNIFORM,
        capacities: Optional[Dict[str, float]] = None,
    ) -> Dict[str, List[Any]]:
        """Distribute workload across devices.

        Args:
            tasks: List of tasks to distribute
            strategy: Distribution strategy (Enum or string for compatibility)
            capacities: Optional capacity weights for 'capacity' strategy

        Returns:
            Dict of device_id -> assigned tasks
            
        Raises:
            ValueError: If strategy is invalid or capacities invalid
        """
        if not tasks:
            return {d: [] for d in self._devices.keys()}
        
        device_ids = list(self._devices.keys())
        
        # Handle both enum and string for backwards compatibility
        if isinstance(strategy, str):
            try:
                strategy = DistributionStrategy(strategy)
            except ValueError:
                raise ValueError(
                    f"Unknown distribution strategy: {strategy}. "
                    f"Valid: {[s.value for s in DistributionStrategy]}"
                )

        if strategy == DistributionStrategy.UNIFORM:
            return self._workload_distributor.distribute_uniform(
                devices=device_ids,
                workload_items=tasks,
            )
        elif strategy == DistributionStrategy.CAPACITY:
            if not capacities:
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
        """Shutdown clustering manager and cleanup all resources.
        
        This is async-safe and handles concurrent operations gracefully.
        """
        try:
            # Signal shutdown to prevent new operations
            self._shutdown_event.set()
            logger.info("GPU clustering manager shutting down...")
            
            # Wait for in-flight operations (grace period)
            await asyncio.sleep(0.1)
            
            # Cancel any running telemetry tasks
            if self._telemetry_task and not self._telemetry_task.done():
                self._telemetry_task.cancel()
                try:
                    await self._telemetry_task
                except asyncio.CancelledError:
                    logger.debug("Telemetry task cancelled")

            # Shutdown backend
            if self._backend:
                try:
                    await self._backend.shutdown()
                except Exception as e:
                    logger.error(f"Error shutting down backend: {e}")
                finally:
                    self._backend = None

            # Clear telemetry data
            if self._telemetry:
                try:
                    self._telemetry._current_metrics.clear()
                    self._telemetry._metrics_history.clear()
                except Exception as e:
                    logger.error(f"Error clearing telemetry: {e}")
                finally:
                    self._telemetry = None

            # Clear workload distributor
            self._workload_distributor = None

            # Clear devices
            self._devices.clear()
            
            self._initialized = False
            logger.info("GPU clustering manager shutdown complete")
            
        except Exception as e:
            logger.error(f"Error during clustering manager shutdown: {e}")
            raise


class DeviceSelectorImproved:
    """Type-safe device selector with better error handling."""

    def __init__(
        self,
        devices: Dict[str, tuple[GPUMetrics, DeviceCapabilities]],
    ) -> None:
        """Initialize device selector.

        Args:
            devices: Dict of device_id -> (metrics, capabilities)
            
        Raises:
            ValueError: If devices dict is invalid
        """
        if not devices:
            raise ValueError("Device dict cannot be empty")
        
        self._devices = devices

    def select_best_device(
        self, min_memory_bytes: int = 0
    ) -> Optional[str]:
        """Select best device for a workload.

        Args:
            min_memory_bytes: Minimum required device memory

        Returns:
            Best device_id or None if no suitable device
            
        Raises:
            ValueError: If min_memory_bytes is negative
        """
        if min_memory_bytes < 0:
            raise ValueError("min_memory_bytes cannot be negative")
        
        ranked = self.rank_devices()

        for device_id, score in ranked:
            if score > 0.0:
                metrics, _caps = self._devices[device_id]
                available_bytes = (
                    metrics.memory_total_bytes - metrics.memory_used_bytes
                )
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
            try:
                score = DeviceScorer.score_device(metrics, caps)
                scores.append((device_id, score))
            except Exception as e:
                logger.error(f"Error scoring device {device_id}: {e}")
                scores.append((device_id, 0.0))

        return sorted(scores, key=lambda x: x[1], reverse=True)


class TelemetryCollectorImproved:
    """Memory-efficient telemetry collector using deque.
    
    Fixes Issue #1: Uses collections.deque with maxlen for O(1)
    automatic eviction instead of creating new list on every append.
    """

    def __init__(self, max_history: int = 100) -> None:
        """Initialize telemetry collector.

        Args:
            max_history: Maximum history entries per device
            
        Raises:
            ValueError: If max_history is invalid
        """
        if max_history <= 0:
            raise ValueError("max_history must be positive")
        
        self._max_history = max_history
        self._current_metrics: Dict[str, GPUMetrics] = {}
        # Use deque for O(1) bounded memory eviction
        self._metrics_history: Dict[str, deque] = {}

    async def record_metrics(self, metrics: GPUMetrics) -> None:
        """Record metrics from a device.

        Args:
            metrics: GPU metrics to record
        """
        device_id = metrics.device_id

        # Update current
        self._current_metrics[device_id] = metrics

        # Add to history with automatic eviction
        if device_id not in self._metrics_history:
            # deque with maxlen automatically evicts oldest when full
            self._metrics_history[device_id] = deque(maxlen=self._max_history)

        self._metrics_history[device_id].append(metrics)
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
        history = self._metrics_history.get(device_id)
        return list(history) if history else []

    def get_aggregated_metrics(self) -> Dict[str, Any]:
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
            sum(m.compute_utilization_percent for m in devices) / len(devices)
        )
        avg_temp = (
            sum(m.temperature_celsius for m in devices) / len(devices)
        )
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


class WorkloadDistributorImproved:
    """Production-hardened workload distributor with validation.
    
    Fixes Issue #4: Validates capacity dict to prevent division by zero.
    """

    def distribute_uniform(
        self,
        devices: List[str],
        workload_items: List[Any],
        max_per_device: Optional[int] = None,
    ) -> Dict[str, List[Any]]:
        """Distribute workload uniformly across devices.

        Args:
            devices: List of device IDs
            workload_items: Items to distribute
            max_per_device: Maximum items per device (optional)

        Returns:
            Dict of device_id -> list of assigned items
            
        Raises:
            ValueError: If inputs are invalid
        """
        if not devices:
            return {}
        
        if max_per_device is not None and max_per_device <= 0:
            raise ValueError("max_per_device must be positive")
        
        distribution = {d: [] for d in devices}

        if not workload_items:
            return distribution

        items_per_device = len(workload_items) // len(devices)
        remainder = len(workload_items) % len(devices)

        item_idx = 0
        for i, device_id in enumerate(devices):
            count = items_per_device + (1 if i < remainder else 0)

            if max_per_device is not None:
                count = min(count, max_per_device)

            distribution[device_id] = workload_items[item_idx : item_idx + count]
            item_idx += count

        return distribution

    def distribute_by_capacity(
        self,
        capacities: Dict[str, float],
        workload_items: List[Any],
    ) -> Dict[str, List[Any]]:
        """Distribute workload based on device capacity with validation.

        Args:
            capacities: Dict of device_id -> capacity_weight (relative)
            workload_items: Items to distribute

        Returns:
            Dict of device_id -> list of assigned items
            
        Raises:
            ValueError: If capacities are invalid
        """
        distribution = {d: [] for d in capacities.keys()}

        if not capacities or not workload_items:
            return distribution

        # Validate all capacities are positive
        if any(cap < 0 for cap in capacities.values()):
            raise ValueError("All capacity values must be non-negative")
        
        total_capacity = sum(capacities.values())
        
        # Validate total capacity
        if total_capacity <= 0:
            raise ValueError(
                f"Total capacity must be positive, got {total_capacity}"
            )

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
