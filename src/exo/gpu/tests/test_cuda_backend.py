"""Tests for CUDA backend implementation.

Tests verify:
1. CUDA backend initialization
2. Device detection
3. Memory allocation/deallocation
4. Memory copy operations
5. P2P copy
6. Synchronization
7. Monitoring
"""

import pytest
from unittest.mock import Mock, MagicMock, patch

from exo.gpu.backends.cuda_backend import CUDABackend
from exo.gpu.backend import MemoryHandle


# Check if CuPy is available
try:
    import cupy as cp
    CUPY_AVAILABLE = True
except ImportError:
    CUPY_AVAILABLE = False


@pytest.mark.skipif(not CUPY_AVAILABLE, reason="CuPy not installed")
class TestCUDABackendInitialization:
    """Tests for CUDA backend initialization."""

    @pytest.mark.asyncio
    async def test_cuda_backend_creation(self):
        """Test creating CUDA backend instance."""
        try:
            backend = CUDABackend()
            assert backend is not None
            assert not backend._initialized
            await backend.shutdown()
        except ImportError:
            pytest.skip("CuPy not installed")

    @pytest.mark.asyncio
    async def test_cuda_backend_initialization(self):
        """Test CUDA backend initialization."""
        try:
            backend = CUDABackend()
            await backend.initialize()

            assert backend._initialized
            assert backend._device_count >= 0
            devices = backend.list_devices()
            assert isinstance(devices, list)

            await backend.shutdown()
        except ImportError:
            pytest.skip("CuPy not installed")


@pytest.mark.skipif(not CUPY_AVAILABLE, reason="CuPy not installed")
class TestCUDADeviceDetection:
    """Tests for CUDA device detection."""

    @pytest.mark.asyncio
    async def test_list_devices(self):
        """Test listing CUDA devices."""
        try:
            backend = CUDABackend()
            await backend.initialize()

            devices = backend.list_devices()
            assert isinstance(devices, list)

            # Each device should have required fields
            for device in devices:
                assert device.device_id is not None
                assert device.name is not None
                assert device.vendor == "nvidia"
                assert device.backend == "cuda"
                assert device.memory_bytes > 0

            await backend.shutdown()
        except ImportError:
            pytest.skip("CuPy not installed")

    @pytest.mark.asyncio
    async def test_get_device(self):
        """Test getting specific device by ID."""
        try:
            backend = CUDABackend()
            await backend.initialize()

            devices = backend.list_devices()
            if devices:
                device_id = devices[0].device_id
                device = backend.get_device(device_id)
                assert device is not None
                assert device.device_id == device_id

            # Non-existent device
            not_found = backend.get_device("cuda:999")
            assert not_found is None

            await backend.shutdown()
        except ImportError:
            pytest.skip("CuPy not installed")


@pytest.mark.skipif(not CUPY_AVAILABLE, reason="CuPy not installed")
class TestCUDAMemoryOperations:
    """Tests for CUDA memory operations."""

    @pytest.mark.asyncio
    async def test_memory_allocation(self):
        """Test CUDA memory allocation."""
        try:
            backend = CUDABackend()
            await backend.initialize()

            devices = backend.list_devices()
            if not devices:
                pytest.skip("No CUDA devices found")

            device_id = devices[0].device_id
            size = 1024 * 1024  # 1MB

            handle = await backend.allocate(device_id, size)
            assert handle is not None
            assert handle.device_id == device_id
            assert handle.size_bytes == size
            assert handle.handle_id in backend._memory_handles

            await backend.deallocate(handle)
            assert handle.handle_id not in backend._memory_handles

            await backend.shutdown()
        except ImportError:
            pytest.skip("CuPy not installed")

    @pytest.mark.asyncio
    async def test_memory_deallocation(self):
        """Test CUDA memory deallocation."""
        try:
            backend = CUDABackend()
            await backend.initialize()

            devices = backend.list_devices()
            if not devices:
                pytest.skip("No CUDA devices found")

            device_id = devices[0].device_id
            handle = await backend.allocate(device_id, 1024)

            # Should not raise
            await backend.deallocate(handle)

            # Deallocating same handle twice should not raise
            await backend.deallocate(handle)

            await backend.shutdown()
        except ImportError:
            pytest.skip("CuPy not installed")

    @pytest.mark.asyncio
    async def test_copy_to_device(self):
        """Test copying data to CUDA device."""
        try:
            backend = CUDABackend()
            await backend.initialize()

            devices = backend.list_devices()
            if not devices:
                pytest.skip("No CUDA devices found")

            device_id = devices[0].device_id
            size = 1024
            test_data = b"x" * size

            handle = await backend.allocate(device_id, size)
            await backend.copy_to_device(test_data, handle)
            await backend.deallocate(handle)

            await backend.shutdown()
        except ImportError:
            pytest.skip("CuPy not installed")

    @pytest.mark.asyncio
    async def test_copy_from_device(self):
        """Test copying data from CUDA device."""
        try:
            backend = CUDABackend()
            await backend.initialize()

            devices = backend.list_devices()
            if not devices:
                pytest.skip("No CUDA devices found")

            device_id = devices[0].device_id
            size = 1024
            test_data = b"test_data_content"

            handle = await backend.allocate(device_id, size)
            await backend.copy_to_device(test_data, handle)

            # Copy back from device
            result = await backend.copy_from_device(handle, 0, len(test_data))
            assert isinstance(result, bytes)
            assert len(result) == len(test_data)

            await backend.deallocate(handle)
            await backend.shutdown()
        except ImportError:
            pytest.skip("CuPy not installed")

    @pytest.mark.asyncio
    async def test_memory_offset(self):
        """Test memory operations with offset."""
        try:
            backend = CUDABackend()
            await backend.initialize()

            devices = backend.list_devices()
            if not devices:
                pytest.skip("No CUDA devices found")

            device_id = devices[0].device_id
            size = 1024
            offset = 256
            test_data = b"offset_test"

            handle = await backend.allocate(device_id, size)
            await backend.copy_to_device(test_data, handle, offset_bytes=offset)

            # Copy back from offset
            result = await backend.copy_from_device(handle, offset_bytes=offset, size_bytes=len(test_data))
            assert isinstance(result, bytes)

            await backend.deallocate(handle)
            await backend.shutdown()
        except ImportError:
            pytest.skip("CuPy not installed")


@pytest.mark.skipif(not CUPY_AVAILABLE, reason="CuPy not installed")
class TestCUDAP2PCopy:
    """Tests for P2P copy between CUDA devices."""

    @pytest.mark.asyncio
    async def test_p2p_copy_single_gpu(self):
        """Test P2P copy on single GPU (same device)."""
        try:
            backend = CUDABackend()
            await backend.initialize()

            devices = backend.list_devices()
            if len(devices) < 1:
                pytest.skip("Need at least 1 CUDA device")

            device_id = devices[0].device_id
            size = 1024

            src_handle = await backend.allocate(device_id, size)
            dst_handle = await backend.allocate(device_id, size)

            test_data = b"p2p_test_data"
            await backend.copy_to_device(test_data, src_handle)

            # P2P copy (same device)
            await backend.copy_device_to_device(src_handle, dst_handle, len(test_data))

            result = await backend.copy_from_device(dst_handle, 0, len(test_data))
            assert isinstance(result, bytes)

            await backend.deallocate(src_handle)
            await backend.deallocate(dst_handle)
            await backend.shutdown()
        except ImportError:
            pytest.skip("CuPy not installed")


@pytest.mark.skipif(not CUPY_AVAILABLE, reason="CuPy not installed")
class TestCUDASynchronization:
    """Tests for CUDA synchronization."""

    @pytest.mark.asyncio
    async def test_synchronize(self):
        """Test device synchronization."""
        try:
            backend = CUDABackend()
            await backend.initialize()

            devices = backend.list_devices()
            if not devices:
                pytest.skip("No CUDA devices found")

            device_id = devices[0].device_id

            # Should not raise
            await backend.synchronize(device_id)

            await backend.shutdown()
        except ImportError:
            pytest.skip("CuPy not installed")


@pytest.mark.skipif(not CUPY_AVAILABLE, reason="CuPy not installed")
class TestCUDAMonitoring:
    """Tests for CUDA device monitoring."""

    @pytest.mark.asyncio
    async def test_get_memory_info(self):
        """Test getting device memory info."""
        try:
            backend = CUDABackend()
            await backend.initialize()

            devices = backend.list_devices()
            if not devices:
                pytest.skip("No CUDA devices found")

            device_id = devices[0].device_id
            info = await backend.get_device_memory_info(device_id)

            assert "total_bytes" in info
            assert "used_bytes" in info
            assert "available_bytes" in info
            assert info["total_bytes"] > 0

            await backend.shutdown()
        except ImportError:
            pytest.skip("CuPy not installed")

    @pytest.mark.asyncio
    async def test_get_device_temperature(self):
        """Test getting device temperature (optional)."""
        try:
            backend = CUDABackend()
            await backend.initialize()

            devices = backend.list_devices()
            if not devices:
                pytest.skip("No CUDA devices found")

            device_id = devices[0].device_id
            temp = await backend.get_device_temperature(device_id)

            # May return None if nvidia-ml-py not installed
            if temp is not None:
                assert isinstance(temp, float)
                assert temp > -100  # Reasonable temperature range

            await backend.shutdown()
        except ImportError:
            pytest.skip("CuPy not installed")

    @pytest.mark.asyncio
    async def test_get_device_power_usage(self):
        """Test getting device power usage (optional)."""
        try:
            backend = CUDABackend()
            await backend.initialize()

            devices = backend.list_devices()
            if not devices:
                pytest.skip("No CUDA devices found")

            device_id = devices[0].device_id
            power = await backend.get_device_power_usage(device_id)

            # May return None if nvidia-ml-py not installed
            if power is not None:
                assert isinstance(power, float)
                assert power >= 0

            await backend.shutdown()
        except ImportError:
            pytest.skip("CuPy not installed")

    @pytest.mark.asyncio
    async def test_get_device_clock_rate(self):
        """Test getting device clock rate."""
        try:
            backend = CUDABackend()
            await backend.initialize()

            devices = backend.list_devices()
            if not devices:
                pytest.skip("No CUDA devices found")

            device_id = devices[0].device_id
            clock = await backend.get_device_clock_rate(device_id)

            if clock is not None:
                assert isinstance(clock, int)
                assert clock > 0

            await backend.shutdown()
        except ImportError:
            pytest.skip("CuPy not installed")


class TestCUDABandwidthEstimate:
    """Tests for GPU bandwidth estimation."""

    def test_bandwidth_estimate_ampere(self):
        """Test bandwidth estimation for Ampere GPUs."""
        backend = CUDABackend.__new__(CUDABackend)
        bw = backend._estimate_bandwidth(8, 0)
        assert bw == 936.0  # Ampere A100

    def test_bandwidth_estimate_ada(self):
        """Test bandwidth estimation for Ada GPUs."""
        backend = CUDABackend.__new__(CUDABackend)
        bw = backend._estimate_bandwidth(8, 9)
        assert bw == 960.0  # Ada RTX 4090

    def test_bandwidth_estimate_unknown(self):
        """Test bandwidth estimation for unknown GPU."""
        backend = CUDABackend.__new__(CUDABackend)
        bw = backend._estimate_bandwidth(99, 99)
        assert bw == 500.0  # Default fallback
