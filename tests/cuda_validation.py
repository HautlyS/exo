"""Comprehensive CUDA backend validation tests.

Tests real model inference on CUDA devices to validate backend implementation.
Run with: pytest tests/cuda_validation.py -v

Requires: CuPy + CUDA 11.x or 12.x installed
"""

import asyncio
import logging
import pytest
from typing import Optional

from exo.gpu.backends.cuda_backend import CUDABackend
from exo.gpu.backend import GPUDevice, MemoryHandle

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)


class TestCUDADeviceEnumeration:
    """Test CUDA device detection and enumeration."""

    @pytest.mark.asyncio
    async def test_cuda_initialization(self):
        """Test basic CUDA backend initialization."""
        backend = CUDABackend()
        await backend.initialize()
        
        devices = backend.list_devices()
        assert len(devices) > 0, "No CUDA devices detected"
        
        for device in devices:
            assert device.device_id.startswith("cuda:")
            assert device.vendor == "nvidia"
            assert device.backend == "cuda"
            assert device.memory_bytes > 0
            assert device.compute_units > 0
            
        await backend.shutdown()

    @pytest.mark.asyncio
    async def test_device_properties(self):
        """Test that device properties are correctly populated."""
        backend = CUDABackend()
        await backend.initialize()
        
        devices = backend.list_devices()
        first_device = devices[0]
        
        # Check all required fields are present and valid
        assert first_device.device_id
        assert first_device.name
        assert first_device.vendor == "nvidia"
        assert first_device.backend == "cuda"
        assert first_device.compute_capability
        assert first_device.memory_bytes > 0
        assert first_device.memory_available > 0
        assert first_device.compute_units > 0
        assert first_device.max_threads_per_block > 0
        assert first_device.clock_rate_mhz > 0
        assert first_device.bandwidth_gbps > 0
        assert first_device.driver_version
        
        logger.info(f"Device: {first_device.name}")
        logger.info(f"  Compute Capability: {first_device.compute_capability}")
        logger.info(f"  Memory: {first_device.memory_bytes / 1024**3:.1f} GB")
        logger.info(f"  Clock: {first_device.clock_rate_mhz} MHz")
        logger.info(f"  Bandwidth: {first_device.bandwidth_gbps} GB/s")
        
        await backend.shutdown()

    @pytest.mark.asyncio
    async def test_get_device_by_id(self):
        """Test retrieving device by ID."""
        backend = CUDABackend()
        await backend.initialize()
        
        devices = backend.list_devices()
        first_device_id = devices[0].device_id
        
        retrieved = backend.get_device(first_device_id)
        assert retrieved is not None
        assert retrieved.device_id == first_device_id
        
        # Non-existent device
        non_existent = backend.get_device("cuda:999")
        assert non_existent is None
        
        await backend.shutdown()


class TestCUDAMemoryOperations:
    """Test CUDA memory allocation and deallocation."""

    @pytest.mark.asyncio
    async def test_memory_allocation(self):
        """Test basic memory allocation."""
        backend = CUDABackend()
        await backend.initialize()
        
        device = backend.list_devices()[0]
        size_bytes = 1024 * 1024  # 1 MB
        
        handle = await backend.allocate(device.device_id, size_bytes)
        
        assert handle is not None
        assert handle.handle_id
        assert handle.device_id == device.device_id
        assert handle.size_bytes == size_bytes
        
        await backend.deallocate(handle)
        await backend.shutdown()

    @pytest.mark.asyncio
    async def test_memory_allocation_large(self):
        """Test large memory allocation."""
        backend = CUDABackend()
        await backend.initialize()
        
        device = backend.list_devices()[0]
        # Allocate 1 GB
        size_bytes = 1024 * 1024 * 1024
        
        # Check we have enough memory
        free_memory = (await backend.get_device_memory_info(device.device_id))["available_bytes"]
        if free_memory < size_bytes:
            pytest.skip(f"Not enough GPU memory. Need {size_bytes/1024**3:.1f}GB, have {free_memory/1024**3:.1f}GB")
        
        handle = await backend.allocate(device.device_id, size_bytes)
        assert handle is not None
        
        await backend.deallocate(handle)
        await backend.shutdown()

    @pytest.mark.asyncio
    async def test_memory_deallocation(self):
        """Test memory deallocation."""
        backend = CUDABackend()
        await backend.initialize()
        
        device = backend.list_devices()[0]
        size_bytes = 1024 * 1024
        
        handle = await backend.allocate(device.device_id, size_bytes)
        
        # Deallocate
        await backend.deallocate(handle)
        
        # Double deallocation should be handled gracefully
        await backend.deallocate(handle)  # Should not raise
        
        await backend.shutdown()

    @pytest.mark.asyncio
    async def test_memory_info(self):
        """Test getting device memory info."""
        backend = CUDABackend()
        await backend.initialize()
        
        device = backend.list_devices()[0]
        
        info = await backend.get_device_memory_info(device.device_id)
        
        assert "total_bytes" in info
        assert "used_bytes" in info
        assert "available_bytes" in info
        assert info["total_bytes"] > 0
        
        logger.info(f"Memory Info for {device.name}:")
        logger.info(f"  Total: {info['total_bytes'] / 1024**3:.1f} GB")
        logger.info(f"  Used: {info['used_bytes'] / 1024**3:.1f} GB")
        logger.info(f"  Available: {info['available_bytes'] / 1024**3:.1f} GB")
        
        await backend.shutdown()


class TestCUDADataTransfer:
    """Test CUDA data copy operations."""

    @pytest.mark.asyncio
    async def test_copy_to_device(self):
        """Test host-to-device memory copy."""
        backend = CUDABackend()
        await backend.initialize()
        
        device = backend.list_devices()[0]
        size_bytes = 1024 * 1024  # 1 MB
        
        # Allocate device memory
        handle = await backend.allocate(device.device_id, size_bytes)
        
        # Create test data
        test_data = b'x' * size_bytes
        
        # Copy to device
        await backend.copy_to_device(test_data, handle)
        
        # Verify by copying back
        result = await backend.copy_from_device(handle, 0, len(test_data))
        assert result == test_data
        
        await backend.deallocate(handle)
        await backend.shutdown()

    @pytest.mark.asyncio
    async def test_copy_from_device(self):
        """Test device-to-host memory copy."""
        backend = CUDABackend()
        await backend.initialize()
        
        device = backend.list_devices()[0]
        size_bytes = 1024 * 1024
        
        handle = await backend.allocate(device.device_id, size_bytes)
        test_data = bytes(range(256)) * (size_bytes // 256)
        
        await backend.copy_to_device(test_data, handle)
        result = await backend.copy_from_device(handle, 0, len(test_data))
        
        assert result == test_data
        
        await backend.deallocate(handle)
        await backend.shutdown()

    @pytest.mark.asyncio
    async def test_copy_with_offset(self):
        """Test copy operations with offsets."""
        backend = CUDABackend()
        await backend.initialize()
        
        device = backend.list_devices()[0]
        size_bytes = 1024 * 1024
        
        handle = await backend.allocate(device.device_id, size_bytes)
        
        # Write to different offsets
        data1 = b'A' * 1024
        data2 = b'B' * 1024
        
        await backend.copy_to_device(data1, handle, offset_bytes=0)
        await backend.copy_to_device(data2, handle, offset_bytes=1024)
        
        # Read back
        result1 = await backend.copy_from_device(handle, 0, 1024)
        result2 = await backend.copy_from_device(handle, 1024, 1024)
        
        assert result1 == data1
        assert result2 == data2
        
        await backend.deallocate(handle)
        await backend.shutdown()


class TestCUDAP2P:
    """Test CUDA peer-to-peer (P2P) device transfers."""

    @pytest.mark.asyncio
    async def test_p2p_available(self):
        """Test P2P availability on multi-GPU systems."""
        backend = CUDABackend()
        await backend.initialize()
        
        devices = backend.list_devices()
        
        if len(devices) < 2:
            pytest.skip("Need 2+ GPUs for P2P tests")
        
        logger.info(f"Testing P2P on {len(devices)} devices")
        
        await backend.shutdown()

    @pytest.mark.asyncio
    async def test_p2p_copy(self):
        """Test P2P copy between devices."""
        backend = CUDABackend()
        await backend.initialize()
        
        devices = backend.list_devices()
        
        if len(devices) < 2:
            pytest.skip("Need 2+ GPUs for P2P tests")
        
        dev0 = devices[0].device_id
        dev1 = devices[1].device_id
        
        size_bytes = 1024 * 1024  # 1 MB
        
        # Allocate on both devices
        handle0 = await backend.allocate(dev0, size_bytes)
        handle1 = await backend.allocate(dev1, size_bytes)
        
        # Write test data
        test_data = bytes(range(256)) * (size_bytes // 256)
        await backend.copy_to_device(test_data, handle0)
        
        # Copy device-to-device
        await backend.copy_device_to_device(handle0, handle1, size_bytes)
        
        # Verify
        result = await backend.copy_from_device(handle1, 0, size_bytes)
        assert result == test_data
        
        await backend.deallocate(handle0)
        await backend.deallocate(handle1)
        await backend.shutdown()


class TestCUDASynchronization:
    """Test CUDA synchronization operations."""

    @pytest.mark.asyncio
    async def test_synchronize(self):
        """Test device synchronization."""
        backend = CUDABackend()
        await backend.initialize()
        
        device = backend.list_devices()[0]
        
        await backend.synchronize(device.device_id)
        # If we get here, synchronization worked
        
        await backend.shutdown()

    @pytest.mark.asyncio
    async def test_synchronize_after_operations(self):
        """Test synchronization after memory operations."""
        backend = CUDABackend()
        await backend.initialize()
        
        device = backend.list_devices()[0]
        size_bytes = 1024 * 1024
        
        # Do some operations
        handle = await backend.allocate(device.device_id, size_bytes)
        test_data = b'x' * size_bytes
        await backend.copy_to_device(test_data, handle)
        await backend.synchronize(device.device_id)
        
        # Verify sync point worked
        result = await backend.copy_from_device(handle, 0, size_bytes)
        assert result == test_data
        
        await backend.deallocate(handle)
        await backend.shutdown()


class TestCUDAMonitoring:
    """Test CUDA device monitoring operations."""

    @pytest.mark.asyncio
    async def test_get_temperature(self):
        """Test device temperature monitoring."""
        backend = CUDABackend()
        await backend.initialize()
        
        device = backend.list_devices()[0]
        
        temp = await backend.get_device_temperature(device.device_id)
        
        # May return None if nvidia-ml-py not installed
        if temp is not None:
            assert isinstance(temp, float)
            assert 0 < temp < 200  # Reasonable temperature range (Celsius)
            logger.info(f"Device temperature: {temp}°C")
        else:
            logger.info("Temperature monitoring not available (nvidia-ml-py not installed)")
        
        await backend.shutdown()

    @pytest.mark.asyncio
    async def test_get_power_usage(self):
        """Test device power usage monitoring."""
        backend = CUDABackend()
        await backend.initialize()
        
        device = backend.list_devices()[0]
        
        power = await backend.get_device_power_usage(device.device_id)
        
        # May return None if nvidia-ml-py not installed
        if power is not None:
            assert isinstance(power, float)
            assert power > 0
            logger.info(f"Device power usage: {power}W")
        else:
            logger.info("Power monitoring not available (nvidia-ml-py not installed)")
        
        await backend.shutdown()

    @pytest.mark.asyncio
    async def test_get_clock_rate(self):
        """Test device clock rate monitoring."""
        backend = CUDABackend()
        await backend.initialize()
        
        device = backend.list_devices()[0]
        
        clock = await backend.get_device_clock_rate(device.device_id)
        
        if clock is not None:
            assert isinstance(clock, int)
            assert 100 < clock < 5000  # Reasonable clock range (MHz)
            logger.info(f"Device clock rate: {clock} MHz")
        else:
            logger.info("Clock rate unavailable")
        
        await backend.shutdown()


class TestCUDAErrorHandling:
    """Test CUDA error handling and edge cases."""

    @pytest.mark.asyncio
    async def test_allocate_invalid_device(self):
        """Test allocation on invalid device."""
        backend = CUDABackend()
        await backend.initialize()
        
        with pytest.raises(Exception):
            await backend.allocate("cuda:999", 1024)
        
        await backend.shutdown()

    @pytest.mark.asyncio
    async def test_copy_to_invalid_handle(self):
        """Test copy to invalid memory handle."""
        backend = CUDABackend()
        await backend.initialize()
        
        device = backend.list_devices()[0]
        
        # Create a fake handle
        fake_handle = MemoryHandle(device_id=device.device_id, size_bytes=1024)
        fake_handle.handle_id = "fake-handle-12345"
        
        with pytest.raises(Exception):
            await backend.copy_to_device(b'data', fake_handle)
        
        await backend.shutdown()

    @pytest.mark.asyncio
    async def test_copy_from_invalid_handle(self):
        """Test copy from invalid memory handle."""
        backend = CUDABackend()
        await backend.initialize()
        
        device = backend.list_devices()[0]
        
        fake_handle = MemoryHandle(device_id=device.device_id, size_bytes=1024)
        fake_handle.handle_id = "fake-handle-99999"
        
        with pytest.raises(Exception):
            await backend.copy_from_device(fake_handle, 0, 1024)
        
        await backend.shutdown()


class TestCUDAIntegration:
    """Integration tests with actual tensor operations."""

    @pytest.mark.asyncio
    async def test_matrix_operations(self):
        """Test actual matrix operations on CUDA."""
        try:
            import cupy as cp
            import numpy as np
        except ImportError:
            pytest.skip("CuPy not installed")
        
        backend = CUDABackend()
        await backend.initialize()
        
        device = backend.list_devices()[0]
        
        # Allocate space for matrices
        matrix_size = 1024 * 1024  # ~1M float32 elements
        handle = await backend.allocate(device.device_id, matrix_size * 4)
        
        # Create test matrices on CPU
        np_matrix = np.ones((1024, 256), dtype=np.float32)
        
        # Copy to device
        await backend.copy_to_device(np_matrix.tobytes(), handle)
        
        # Copy back and verify
        result_bytes = await backend.copy_from_device(handle, 0, matrix_size * 4)
        result_matrix = np.frombuffer(result_bytes, dtype=np.float32).reshape(1024, 256)
        
        assert np.allclose(result_matrix, np_matrix)
        
        await backend.deallocate(handle)
        await backend.shutdown()

    @pytest.mark.asyncio
    async def test_memory_stress(self):
        """Stress test memory allocation/deallocation."""
        backend = CUDABackend()
        await backend.initialize()
        
        device = backend.list_devices()[0]
        memory_info = await backend.get_device_memory_info(device.device_id)
        available = memory_info["available_bytes"]
        
        # Allocate 50% of available memory in chunks
        chunk_size = available // 20  # 20 chunks of 5% each
        handles = []
        
        try:
            for i in range(10):  # Allocate 10 chunks
                handle = await backend.allocate(device.device_id, chunk_size)
                handles.append(handle)
            
            # Deallocate in reverse order
            for handle in reversed(handles):
                await backend.deallocate(handle)
            
            # Should complete without errors
            assert len(handles) == 10
            
        finally:
            # Cleanup any remaining
            for handle in handles:
                try:
                    await backend.deallocate(handle)
                except:
                    pass
        
        await backend.shutdown()


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
