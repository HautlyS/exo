"""Tests for GPU Discovery Service.

Tests verify:
1. Discovery service initializes correctly
2. Device discovery works
3. Device verification works
4. Registry persistence
5. Helper functions work
"""

import pytest
import tempfile
from pathlib import Path

from exo.gpu.discovery import (
    GPUDiscoveryService,
    discover_gpu_devices,
    get_total_gpu_memory,
    get_peak_flops,
)
from exo.gpu.backend import GPUDevice


class TestGPUDiscoveryService:
    """Tests for GPUDiscoveryService."""

    def test_discovery_service_initialization(self):
        """Test creating discovery service."""
        service = GPUDiscoveryService()
        assert service.registry_path is not None
        assert service._devices == []
        assert service._backend is None

    def test_discovery_service_custom_registry(self):
        """Test discovery service with custom registry path."""
        with tempfile.TemporaryDirectory() as tmpdir:
            registry_path = Path(tmpdir) / "custom_registry.json"
            service = GPUDiscoveryService(registry_path)

            assert service.registry_path == registry_path

    @pytest.mark.asyncio
    async def test_discover_devices(self):
        """Test discovering GPU devices."""
        service = GPUDiscoveryService()

        try:
            result = await service.discover_all_devices()

            assert "devices" in result
            assert "backend_name" in result
            assert "discovery_status" in result
            assert "timestamp" in result

            assert isinstance(result["devices"], list)
            assert result["discovery_status"] in ["success", "partial"]

            # Should have at least discovered CPU backend
            assert result["backend_name"] is not None

        finally:
            await service.shutdown()

    @pytest.mark.asyncio
    async def test_device_get_by_id(self):
        """Test getting device by ID."""
        service = GPUDiscoveryService()

        try:
            result = await service.discover_all_devices()
            devices = result["devices"]

            if devices:
                device = devices[0]
                found = service.get_device_by_id(device.device_id)
                assert found is not None
                assert found.device_id == device.device_id

            # Non-existent device
            not_found = service.get_device_by_id("nonexistent:999")
            assert not_found is None

        finally:
            await service.shutdown()

    @pytest.mark.asyncio
    async def test_registry_persistence(self):
        """Test saving and loading device registry."""
        with tempfile.TemporaryDirectory() as tmpdir:
            registry_path = Path(tmpdir) / "test_registry.json"
            service = GPUDiscoveryService(registry_path)

            try:
                result = await service.discover_all_devices()

                # Check registry was created
                assert registry_path.exists()

                # Load registry
                loaded = await service.load_registry()
                assert loaded is not None
                assert "devices" in loaded
                assert "timestamp" in loaded

            finally:
                await service.shutdown()

    @pytest.mark.asyncio
    async def test_load_missing_registry(self):
        """Test loading non-existent registry."""
        with tempfile.TemporaryDirectory() as tmpdir:
            registry_path = Path(tmpdir) / "nonexistent" / "registry.json"
            service = GPUDiscoveryService(registry_path)

            loaded = await service.load_registry()
            assert loaded is None


class TestDiscoverGPUDevices:
    """Tests for helper function."""

    @pytest.mark.asyncio
    async def test_discover_gpu_devices_helper(self):
        """Test discover_gpu_devices helper function."""
        with tempfile.TemporaryDirectory() as tmpdir:
            registry_path = Path(tmpdir) / "registry.json"
            result = await discover_gpu_devices(registry_path)

            assert "devices" in result
            assert "backend_name" in result


class TestHelperFunctions:
    """Tests for GPU memory/performance helper functions."""

    def test_get_total_gpu_memory(self):
        """Test calculating total GPU memory."""
        devices = [
            GPUDevice(
                device_id="cuda:0",
                name="GPU 0",
                vendor="nvidia",
                backend="cuda",
                compute_capability="8.0",
                memory_bytes=1000,
                memory_available=1000,
                compute_units=10,
                tensor_core_count=0,
                max_threads_per_block=1024,
                clock_rate_mhz=2000,
                bandwidth_gbps=100.0,
                support_level="full",
                driver_version="1.0",
                backend_name="cuda",
            ),
            GPUDevice(
                device_id="cuda:1",
                name="GPU 1",
                vendor="nvidia",
                backend="cuda",
                compute_capability="8.0",
                memory_bytes=2000,
                memory_available=2000,
                compute_units=10,
                tensor_core_count=0,
                max_threads_per_block=1024,
                clock_rate_mhz=2000,
                bandwidth_gbps=100.0,
                support_level="full",
                driver_version="1.0",
                backend_name="cuda",
            ),
        ]

        total = get_total_gpu_memory(devices)
        assert total == 3000

    def test_get_total_gpu_memory_empty(self):
        """Test total GPU memory with empty device list."""
        total = get_total_gpu_memory([])
        assert total == 0

    def test_get_peak_flops(self):
        """Test peak FLOPS estimation."""
        devices = [
            GPUDevice(
                device_id="cuda:0",
                name="RTX 4090",
                vendor="nvidia",
                backend="cuda",
                compute_capability="8.9",
                memory_bytes=24 * 1024 * 1024 * 1024,
                memory_available=24 * 1024 * 1024 * 1024,
                compute_units=128,
                tensor_core_count=5888,
                max_threads_per_block=1024,
                clock_rate_mhz=2500,
                bandwidth_gbps=960.0,
                support_level="full",
                driver_version="535.0",
                backend_name="cuda",
            )
        ]

        flops = get_peak_flops(devices)
        assert flops > 0

        # Rough sanity check: estimate should be positive
        # Formula: CUs * clock * threads_per_cu (64)
        # RTX 4090: 128 * 2.5GHz * 64 = 20.48 TFLOPS (conservative, 1 op/thread/cycle)
        tflops = flops / 1e12
        assert 10 < tflops < 30  # Conservative estimate based on formula


class TestDeviceMetadata:
    """Tests for GPU device metadata."""

    def test_device_metadata_complete(self):
        """Test GPU device has all required metadata."""
        device = GPUDevice(
            device_id="cuda:0",
            name="NVIDIA RTX 4090",
            vendor="nvidia",
            backend="cuda",
            compute_capability="8.9",
            memory_bytes=24 * 1024 * 1024 * 1024,
            memory_available=24 * 1024 * 1024 * 1024,
            compute_units=128,
            tensor_core_count=5888,
            max_threads_per_block=1024,
            clock_rate_mhz=2500,
            bandwidth_gbps=960.0,
            support_level="full",
            driver_version="535.104.05",
            backend_name="cuda",
        )

        # All fields present
        assert device.device_id == "cuda:0"
        assert device.name == "NVIDIA RTX 4090"
        assert device.vendor == "nvidia"
        assert device.compute_units == 128
        assert device.clock_rate_mhz == 2500
        assert device.bandwidth_gbps == 960.0
