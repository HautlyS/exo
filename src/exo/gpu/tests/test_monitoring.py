"""Tests for GPU monitoring and telemetry."""

import asyncio
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from exo.gpu.backend import GPUDevice
from exo.gpu.monitoring import GPUMetricsCollector, GPUMetricsSnapshot, GPUMonitoringService


class MockGPUBackend:
    """Mock GPU backend for testing."""

    def __init__(self, device_id: str = "cuda:0"):
        self.device_id = device_id
        self.memory_used_bytes = 4_000_000_000
        self.memory_total_bytes = 16_000_000_000
        self.temperature_c = 50.0
        self.power_w = 100.0

    def list_devices(self):
        return [
            GPUDevice(
                device_id=self.device_id,
                name="Mock GPU",
                vendor="nvidia",
                backend="cuda",
                compute_capability="8.0",
                memory_bytes=self.memory_total_bytes,
                memory_available=self.memory_total_bytes - self.memory_used_bytes,
                compute_units=100,
                tensor_core_count=0,
                max_threads_per_block=1024,
                clock_rate_mhz=2000,
                bandwidth_gbps=500.0,
                support_level="full",
                driver_version="535.0",
                backend_name="cuda",
            )
        ]

    async def get_device_memory_info(self, device_id: str):
        """Return memory info as dict (matching backend interface)."""
        return {
            "used_bytes": self.memory_used_bytes,
            "total_bytes": self.memory_total_bytes,
            "available_bytes": self.memory_total_bytes - self.memory_used_bytes,
        }

    async def get_device_temperature(self, device_id: str) -> float:
        return self.temperature_c

    async def get_device_power_usage(self, device_id: str) -> float:
        return self.power_w


class TestGPUMetricsCollector:
    """Test GPU metrics collection."""

    def test_collector_initialization(self):
        """Test creating metrics collector."""
        device = MockGPUBackend().list_devices()[0]
        backend = MockGPUBackend()
        collector = GPUMetricsCollector(device, backend)

        assert collector.device.device_id == "cuda:0"
        assert collector.window_size_seconds == 60.0
        assert len(collector.snapshots) == 0

    @pytest.mark.asyncio
    async def test_collect_snapshot(self):
        """Test collecting a metrics snapshot."""
        device = MockGPUBackend().list_devices()[0]
        backend = MockGPUBackend()
        collector = GPUMetricsCollector(device, backend)

        snapshot = await collector.collect_snapshot()

        assert snapshot.device_id == "cuda:0"
        assert snapshot.memory_used_bytes == 4_000_000_000
        assert snapshot.memory_total_bytes == 16_000_000_000
        assert snapshot.temperature_c == 50.0
        assert snapshot.power_usage_w == 100.0
        assert len(collector.snapshots) == 1

    @pytest.mark.asyncio
    async def test_collect_multiple_snapshots(self):
        """Test collecting multiple snapshots."""
        device = MockGPUBackend().list_devices()[0]
        backend = MockGPUBackend()
        collector = GPUMetricsCollector(device, backend)

        for _ in range(5):
            await collector.collect_snapshot()
            await asyncio.sleep(0.01)

        assert len(collector.snapshots) == 5

    @pytest.mark.asyncio
    async def test_get_summary(self):
        """Test getting metrics summary."""
        device = MockGPUBackend().list_devices()[0]
        backend = MockGPUBackend()
        backend.memory_used_bytes = 4_000_000_000
        backend.temperature_c = 50.0
        backend.power_w = 100.0
        collector = GPUMetricsCollector(device, backend)

        # Collect multiple snapshots
        for _ in range(3):
            await collector.collect_snapshot()

        summary = collector.get_summary()

        assert summary is not None
        assert summary.device_id == "cuda:0"
        assert summary.memory_current_used_bytes == 4_000_000_000
        assert summary.temperature_current_c == 50.0
        assert summary.power_current_w == 100.0

    @pytest.mark.asyncio
    async def test_get_device_gpu_state(self):
        """Test converting metrics to DeviceGPUState."""
        device = MockGPUBackend().list_devices()[0]
        backend = MockGPUBackend()
        collector = GPUMetricsCollector(device, backend)

        await collector.collect_snapshot()
        state = collector.get_device_gpu_state()

        assert state is not None
        assert state.device_id == "cuda:0"
        assert state.memory_used_bytes == 4_000_000_000
        assert state.memory_total_bytes == 16_000_000_000


class TestGPUMonitoringService:
    """Test GPU monitoring service."""

    @pytest.mark.asyncio
    async def test_service_initialization(self):
        """Test initializing monitoring service."""
        backend = MockGPUBackend()
        service = GPUMonitoringService(backend)

        assert len(service.collectors) == 0

    @pytest.mark.asyncio
    async def test_start_monitoring(self):
        """Test starting GPU monitoring."""
        backend = MockGPUBackend()
        service = GPUMonitoringService(backend)

        await service.start(collection_interval_seconds=0.1)

        # Wait for first collection
        await asyncio.sleep(0.15)

        assert len(service.collectors) == 1
        assert "cuda:0" in service.collectors

        await service.stop()

    @pytest.mark.asyncio
    async def test_get_device_states(self):
        """Test getting device states from service."""
        backend = MockGPUBackend()
        service = GPUMonitoringService(backend)

        await service.start(collection_interval_seconds=0.1)
        await asyncio.sleep(0.15)

        states = service.get_device_states()

        assert len(states) == 1
        assert "cuda:0" in states
        assert states["cuda:0"].memory_used_bytes == 4_000_000_000

        await service.stop()

    @pytest.mark.asyncio
    async def test_get_summaries(self):
        """Test getting metric summaries from service."""
        backend = MockGPUBackend()
        service = GPUMonitoringService(backend)

        await service.start(collection_interval_seconds=0.1)
        await asyncio.sleep(0.15)

        summaries = service.get_summaries()

        assert len(summaries) == 1
        assert "cuda:0" in summaries
        assert summaries["cuda:0"].temperature_current_c == 50.0

        await service.stop()

    @pytest.mark.asyncio
    async def test_prometheus_metrics(self):
        """Test Prometheus format metrics output."""
        backend = MockGPUBackend()
        service = GPUMonitoringService(backend)

        await service.start(collection_interval_seconds=0.1)
        await asyncio.sleep(0.15)

        metrics = service.get_prometheus_metrics()

        assert "gpu_memory_used_bytes" in metrics
        assert "gpu_temperature_celsius" in metrics
        assert "gpu_power_watts" in metrics
        assert 'device_id="cuda:0"' in metrics

        await service.stop()

    @pytest.mark.asyncio
    async def test_alert_callback(self):
        """Test alert callback functionality."""
        backend = MockGPUBackend()
        backend.memory_used_bytes = int(0.95 * 16_000_000_000)  # High memory
        service = GPUMonitoringService(backend)

        alerts = []

        async def alert_handler(alert):
            alerts.append(alert)

        service.set_alert_callback(alert_handler)

        await service.start(collection_interval_seconds=0.1)
        await asyncio.sleep(0.25)  # Wait for monitoring

        assert len(alerts) > 0
        assert any(alert["type"] == "high_memory" for alert in alerts)

        await service.stop()
