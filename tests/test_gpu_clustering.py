"""GPU Clustering Tests - Phase 6."""

import pytest
import asyncio
from unittest.mock import Mock, AsyncMock, patch
from src.exo.gpu.clustering import GPUClusteringManager
from src.exo.gpu.backend import GPUDevice, MemoryHandle
from src.exo.gpu.telemetry_protocol import GPUMetrics, DeviceCapabilities, DeviceType


class TestGPUClusteringManagerInit:
    """Test clustering manager initialization"""

    @pytest.mark.asyncio
    async def test_initialization(self):
        """Test basic initialization"""
        manager = GPUClusteringManager()
        assert manager is not None
        assert len(manager._devices) == 0
        await manager.shutdown()

    @pytest.mark.asyncio
    async def test_register_device(self):
        """Test registering a device"""
        manager = GPUClusteringManager()
        
        device = GPUDevice(
            device_id="cuda:0",
            name="NVIDIA RTX 4090",
            vendor="nvidia",
            backend="cuda",
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
        
        manager.register_device(device)
        assert len(manager._devices) == 1
        assert manager.get_device("cuda:0") == device
        await manager.shutdown()

    @pytest.mark.asyncio
    async def test_register_multiple_devices(self):
        """Test registering multiple devices"""
        manager = GPUClusteringManager()
        
        devices = [
            self._create_device(f"cuda:{i}", f"RTX 409{i}") 
            for i in range(3)
        ]
        
        for device in devices:
            manager.register_device(device)
        
        assert len(manager._devices) == 3
        await manager.shutdown()

    @staticmethod
    def _create_device(device_id: str, name: str) -> GPUDevice:
        """Helper to create test device"""
        return GPUDevice(
            device_id=device_id,
            name=name,
            vendor="nvidia",
            backend="cuda",
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


class TestDeviceSelector:
    """Test device selector and scoring"""

    def test_select_best_device_by_memory(self):
        """Test selecting device with most available memory"""
        from src.exo.gpu.clustering import DeviceSelector
        
        devices_dict = {
            "cuda:0": (
                GPUMetrics(
                    device_id="cuda:0",
                    timestamp=1.0,
                    memory_used_bytes=8_000_000_000,
                    memory_total_bytes=24_000_000_000,
                    compute_utilization_percent=50.0,
                    power_watts=150.0,
                    temperature_celsius=65.0,
                    clock_rate_mhz=2500,
                ),
                DeviceCapabilities(
                    device_id="cuda:0",
                    device_type=DeviceType.CUDA,
                    device_name="RTX 4090",
                    vendor="nvidia",
                    compute_units=128,
                    memory_bandwidth_gbps=936.0,
                    max_memory_bytes=24_000_000_000,
                    driver_version="550.0",
                ),
            ),
            "cuda:1": (
                GPUMetrics(
                    device_id="cuda:1",
                    timestamp=1.0,
                    memory_used_bytes=20_000_000_000,
                    memory_total_bytes=24_000_000_000,
                    compute_utilization_percent=80.0,
                    power_watts=200.0,
                    temperature_celsius=75.0,
                    clock_rate_mhz=2500,
                ),
                DeviceCapabilities(
                    device_id="cuda:1",
                    device_type=DeviceType.CUDA,
                    device_name="RTX 4090",
                    vendor="nvidia",
                    compute_units=128,
                    memory_bandwidth_gbps=936.0,
                    max_memory_bytes=24_000_000_000,
                    driver_version="550.0",
                ),
            ),
        }
        
        selector = DeviceSelector(devices_dict)
        best = selector.select_best_device()
        
        assert best == "cuda:0"

    def test_rank_devices_by_score(self):
        """Test ranking devices by score"""
        from src.exo.gpu.clustering import DeviceSelector
        
        devices_dict = {
            "cuda:0": (
                GPUMetrics(
                    device_id="cuda:0",
                    timestamp=1.0,
                    memory_used_bytes=4_000_000_000,
                    memory_total_bytes=24_000_000_000,
                    compute_utilization_percent=20.0,
                    power_watts=100.0,
                    temperature_celsius=50.0,
                    clock_rate_mhz=2500,
                ),
                DeviceCapabilities(
                    device_id="cuda:0",
                    device_type=DeviceType.CUDA,
                    device_name="RTX 4090",
                    vendor="nvidia",
                    compute_units=128,
                    memory_bandwidth_gbps=936.0,
                    max_memory_bytes=24_000_000_000,
                    driver_version="550.0",
                ),
            ),
        }
        
        selector = DeviceSelector(devices_dict)
        ranked = selector.rank_devices()
        
        assert len(ranked) == 1
        assert ranked[0][0] == "cuda:0"
        assert 0.0 <= ranked[0][1] <= 1.0

    def test_select_device_by_memory_requirement(self):
        """Test selecting device with minimum memory requirement"""
        from src.exo.gpu.clustering import DeviceSelector
        
        devices_dict = {
            "cuda:0": (
                GPUMetrics(
                    device_id="cuda:0",
                    timestamp=1.0,
                    memory_used_bytes=20_000_000_000,
                    memory_total_bytes=24_000_000_000,
                    compute_utilization_percent=50.0,
                    power_watts=150.0,
                    temperature_celsius=65.0,
                    clock_rate_mhz=2500,
                ),
                DeviceCapabilities(
                    device_id="cuda:0",
                    device_type=DeviceType.CUDA,
                    device_name="RTX 4090",
                    vendor="nvidia",
                    compute_units=128,
                    memory_bandwidth_gbps=936.0,
                    max_memory_bytes=24_000_000_000,
                    driver_version="550.0",
                ),
            ),
        }
        
        selector = DeviceSelector(devices_dict)
        
        # Need 5GB - should succeed
        best = selector.select_best_device(min_memory_bytes=5_000_000_000)
        assert best == "cuda:0"
        
        # Need 10GB - should fail (only 4GB available)
        best = selector.select_best_device(min_memory_bytes=10_000_000_000)
        assert best is None


class TestTelemetryCollector:
    """Test telemetry collection and aggregation"""

    @pytest.mark.asyncio
    async def test_collect_metrics(self):
        """Test collecting metrics from a device"""
        from src.exo.gpu.clustering import TelemetryCollector
        
        collector = TelemetryCollector()
        
        metrics = GPUMetrics(
            device_id="cuda:0",
            timestamp=1707043200.0,
            memory_used_bytes=8_000_000_000,
            memory_total_bytes=24_000_000_000,
            compute_utilization_percent=50.0,
            power_watts=150.0,
            temperature_celsius=65.0,
            clock_rate_mhz=2500,
        )
        
        await collector.record_metrics(metrics)
        
        recorded = collector.get_metrics("cuda:0")
        assert recorded is not None
        assert recorded.device_id == "cuda:0"
        assert recorded.compute_utilization_percent == 50.0

    @pytest.mark.asyncio
    async def test_aggregate_metrics(self):
        """Test aggregating metrics across devices"""
        from src.exo.gpu.clustering import TelemetryCollector
        
        collector = TelemetryCollector()
        
        for i in range(3):
            metrics = GPUMetrics(
                device_id=f"cuda:{i}",
                timestamp=1707043200.0,
                memory_used_bytes=8_000_000_000,
                memory_total_bytes=24_000_000_000,
                compute_utilization_percent=30.0 + i * 10,
                power_watts=150.0,
                temperature_celsius=65.0,
                clock_rate_mhz=2500,
            )
            await collector.record_metrics(metrics)
        
        agg = collector.get_aggregated_metrics()
        assert agg is not None
        assert agg["device_count"] == 3
        assert "total_memory_bytes" in agg
        assert "average_utilization_percent" in agg

    @pytest.mark.asyncio
    async def test_metrics_history(self):
        """Test keeping metrics history"""
        from src.exo.gpu.clustering import TelemetryCollector
        
        collector = TelemetryCollector(max_history=10)
        
        for j in range(5):
            metrics = GPUMetrics(
                device_id="cuda:0",
                timestamp=1707043200.0 + j,
                memory_used_bytes=8_000_000_000 + j * 1_000_000,
                memory_total_bytes=24_000_000_000,
                compute_utilization_percent=50.0 + j,
                power_watts=150.0,
                temperature_celsius=65.0,
                clock_rate_mhz=2500,
            )
            await collector.record_metrics(metrics)
        
        history = collector.get_metrics_history("cuda:0")
        assert len(history) == 5


class TestWorkloadDistributor:
    """Test workload distribution across devices"""

    def test_distribute_uniform_workload(self):
        """Test uniform workload distribution"""
        from src.exo.gpu.clustering import WorkloadDistributor
        
        distributor = WorkloadDistributor()
        
        devices = ["cuda:0", "cuda:1", "cuda:2"]
        workload_items = list(range(9))
        
        distribution = distributor.distribute_uniform(
            devices=devices,
            workload_items=workload_items,
        )
        
        assert len(distribution) == 3
        assert len(distribution["cuda:0"]) == 3
        assert len(distribution["cuda:1"]) == 3
        assert len(distribution["cuda:2"]) == 3

    def test_distribute_by_capacity(self):
        """Test capacity-aware workload distribution"""
        from src.exo.gpu.clustering import WorkloadDistributor
        
        distributor = WorkloadDistributor()
        
        # Device capacities (relative)
        capacities = {"cuda:0": 1.0, "cuda:1": 2.0, "cuda:2": 1.0}
        workload_items = list(range(16))
        
        distribution = distributor.distribute_by_capacity(
            capacities=capacities,
            workload_items=workload_items,
        )
        
        # cuda:1 should get 2x the work
        assert len(distribution["cuda:1"]) == 8
        assert len(distribution["cuda:0"]) == 4
        assert len(distribution["cuda:2"]) == 4

    def test_distribute_respects_constraints(self):
        """Test distribution respects device constraints"""
        from src.exo.gpu.clustering import WorkloadDistributor
        
        distributor = WorkloadDistributor()
        
        devices = ["cuda:0"]
        max_items_per_device = 5
        workload_items = list(range(15))
        
        distribution = distributor.distribute_uniform(
            devices=devices,
            workload_items=workload_items,
            max_per_device=max_items_per_device,
        )
        
        # Should cap at max_per_device
        assert len(distribution["cuda:0"]) <= max_items_per_device


class TestGPUClusteringManagerIntegration:
    """Test clustering manager integration with all components"""

    @pytest.mark.asyncio
    async def test_manager_with_devices_and_metrics(self):
        """Test manager with registered devices and metrics"""
        manager = GPUClusteringManager()
        
        # Register devices
        for i in range(2):
            device = self._create_device(f"cuda:{i}", f"RTX 409{i}")
            manager.register_device(device)
        
        # Record metrics
        for i in range(2):
            metrics = GPUMetrics(
                device_id=f"cuda:{i}",
                timestamp=1707043200.0,
                memory_used_bytes=8_000_000_000,
                memory_total_bytes=24_000_000_000,
                compute_utilization_percent=30.0 + i * 10,
                power_watts=150.0,
                temperature_celsius=65.0,
                clock_rate_mhz=2500,
            )
            await manager.record_metrics(metrics)
        
        # Get best device
        best = manager.select_best_device()
        assert best in ["cuda:0", "cuda:1"]
        
        # Get aggregated metrics
        agg = manager.get_aggregated_metrics()
        assert agg["device_count"] == 2
        
        await manager.shutdown()

    @pytest.mark.asyncio
    async def test_manager_distributes_workload(self):
        """Test manager distributes workload across devices"""
        manager = GPUClusteringManager()
        
        # Register devices
        for i in range(2):
            device = self._create_device(f"cuda:{i}", f"RTX 409{i}")
            manager.register_device(device)
        
        # Distribute workload
        tasks = list(range(10))
        distribution = manager.distribute_workload(
            tasks=tasks,
            strategy="uniform",
        )
        
        assert len(distribution) == 2
        assert sum(len(v) for v in distribution.values()) == 10
        
        await manager.shutdown()

    @staticmethod
    def _create_device(device_id: str, name: str) -> GPUDevice:
        """Helper to create test device"""
        return GPUDevice(
            device_id=device_id,
            name=name,
            vendor="nvidia",
            backend="cuda",
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
