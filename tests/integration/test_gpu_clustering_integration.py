"""Integration tests for GPU clustering and scheduling."""

import pytest
import asyncio
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

from exo.gpu.clustering import (
    GPUClusteringManager,
    DeviceSelector,
    TelemetryCollector,
    WorkloadDistributor,
)
from exo.gpu.backend import GPUDevice
from exo.gpu.telemetry_protocol import GPUMetrics, DeviceType


class TestClusteringFullWorkflow:
    """Test complete clustering workflows"""

    @pytest.mark.asyncio
    async def test_full_clustering_workflow(self):
        """Test complete clustering workflow with multiple devices"""
        manager = GPUClusteringManager()

        # Setup 3 devices
        devices = [
            self._create_device("cuda:0", "RTX 4090"),
            self._create_device("cuda:1", "RTX 4080"),
            self._create_device("cuda:2", "RTX 3090"),
        ]

        for device in devices:
            manager.register_device(device)

        assert len(manager.list_devices()) == 3

        # Record metrics for each device
        for i, device_id in enumerate(["cuda:0", "cuda:1", "cuda:2"]):
            metrics = GPUMetrics(
                device_id=device_id,
                timestamp=1707043200.0,
                memory_used_bytes=8_000_000_000 + i * 1_000_000_000,
                memory_total_bytes=24_000_000_000,
                compute_utilization_percent=30.0 + i * 10,
                power_watts=150.0 + i * 10,
                temperature_celsius=65.0 + i * 2,
                clock_rate_mhz=2500,
            )
            await manager.record_metrics(metrics)

        # Get aggregated metrics
        agg = manager.get_aggregated_metrics()
        assert agg["device_count"] == 3
        assert agg["total_memory_bytes"] == 72_000_000_000

        # Select best device
        best = manager.select_best_device()
        assert best in ["cuda:0", "cuda:1", "cuda:2"]

        # Distribute workload
        tasks = list(range(30))
        distribution = manager.distribute_workload(
            tasks=tasks,
            strategy="uniform",
        )

        assert len(distribution) == 3
        assert sum(len(v) for v in distribution.values()) == 30

        await manager.shutdown()

    @pytest.mark.asyncio
    async def test_heterogeneous_device_clustering(self):
        """Test clustering with different device types"""
        manager = GPUClusteringManager()

        # Different device types
        devices = [
            self._create_device("cuda:0", "NVIDIA RTX 4090"),
            self._create_device("rocm:0", "AMD MI250X"),
        ]

        for device in devices:
            manager.register_device(device)

        assert len(manager.list_devices()) == 2

        # Record metrics
        for device_id in ["cuda:0", "rocm:0"]:
            metrics = GPUMetrics(
                device_id=device_id,
                timestamp=1707043200.0,
                memory_used_bytes=4_000_000_000,
                memory_total_bytes=32_000_000_000,
                compute_utilization_percent=50.0,
                power_watts=250.0,
                temperature_celsius=70.0,
                clock_rate_mhz=2500,
            )
            await manager.record_metrics(metrics)

        agg = manager.get_aggregated_metrics()
        assert agg["device_count"] == 2

        await manager.shutdown()

    @pytest.mark.asyncio
    async def test_workload_distribution_strategies(self):
        """Test different workload distribution strategies"""
        manager = GPUClusteringManager()

        # Setup devices with different capacities
        for i in range(3):
            device = self._create_device(f"cuda:{i}", f"Device {i}")
            manager.register_device(device)

        tasks = list(range(12))

        # Uniform distribution
        uniform_dist = manager.distribute_workload(
            tasks=tasks,
            strategy="uniform",
        )

        assert len(uniform_dist["cuda:0"]) == 4
        assert len(uniform_dist["cuda:1"]) == 4
        assert len(uniform_dist["cuda:2"]) == 4

        # Capacity-aware distribution
        capacities = {"cuda:0": 1.0, "cuda:1": 2.0, "cuda:2": 1.0}
        capacity_dist = manager.distribute_workload(
            tasks=tasks,
            strategy="capacity",
            capacities=capacities,
        )

        assert len(capacity_dist["cuda:1"]) > len(capacity_dist["cuda:0"])

        await manager.shutdown()

    @pytest.mark.asyncio
    async def test_device_selection_with_constraints(self):
        """Test device selection respects memory constraints"""
        manager = GPUClusteringManager()

        # Setup devices
        for i in range(2):
            device = self._create_device(f"cuda:{i}", f"Device {i}")
            manager.register_device(device)

        # Record metrics with low memory on cuda:1
        metrics_0 = GPUMetrics(
            device_id="cuda:0",
            timestamp=1707043200.0,
            memory_used_bytes=4_000_000_000,
            memory_total_bytes=24_000_000_000,
            compute_utilization_percent=30.0,
            power_watts=150.0,
            temperature_celsius=65.0,
            clock_rate_mhz=2500,
        )
        await manager.record_metrics(metrics_0)

        metrics_1 = GPUMetrics(
            device_id="cuda:1",
            timestamp=1707043200.0,
            memory_used_bytes=22_000_000_000,  # Almost full
            memory_total_bytes=24_000_000_000,
            compute_utilization_percent=80.0,
            power_watts=200.0,
            temperature_celsius=85.0,
            clock_rate_mhz=2500,
        )
        await manager.record_metrics(metrics_1)

        # Select device needing 5GB
        best = manager.select_best_device(min_memory_bytes=5_000_000_000)
        assert best == "cuda:0"

        await manager.shutdown()

    @staticmethod
    def _create_device(device_id: str, name: str) -> GPUDevice:
        """Helper to create test device"""
        return GPUDevice(
            device_id=device_id,
            name=name,
            vendor="nvidia" if "cuda" in device_id else "amd",
            backend="cuda" if "cuda" in device_id else "rocm",
            compute_capability="8.9",
            memory_bytes=24_000_000_000,
            memory_available=24_000_000_000,
            compute_units=128,
            tensor_core_count=512,
            max_threads_per_block=1024,
            clock_rate_mhz=2500,
            bandwidth_gbps=936.0,
            support_level="full",
            driver_version="550.90.07",
            backend_name="CUDABackend",
        )
