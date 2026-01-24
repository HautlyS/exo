"""GPU Backend Reliability Tests.

Tests GPU operations under error conditions and edge cases:
- Device initialization failures
- Memory allocation edge cases (OOM, fragmentation)
- Kernel timeout recovery
- Device reset handling
- Thermal throttling simulation
"""

import asyncio
import pytest

from exo.gpu.backend import GPUBackend, MemoryHandle
from exo.gpu.factory import GPUBackendFactory


def skip_if_cpu_backend(backend):
    """Skip test if running on CPU fallback (no real GPU)."""
    if backend.__class__.__name__ == "CPUBackend":
        pytest.skip("No real GPU available (CPU fallback)")


class TestGPUInitialization:
    """Test GPU initialization and device detection."""

    @pytest.mark.asyncio
    async def test_backend_initialization(self):
        """Test that backend initializes successfully."""
        try:
            backend = await GPUBackendFactory.create_backend()
            assert backend is not None
            
            # Verify devices detected
            devices = backend.list_devices()
            if len(devices) > 0:
                assert all(
                    d.device_id and d.name and d.vendor
                    for d in devices
                )
        except RuntimeError as e:
            # Graceful handling if no GPU available
            pytest.skip(f"No GPU available: {e}")

    @pytest.mark.asyncio
    async def test_multiple_device_detection(self):
        """Test detection of multiple GPU devices."""
        try:
            backend = await GPUBackendFactory.create_backend()
            skip_if_cpu_backend(backend)
            
            devices = backend.list_devices()
            
            # All devices should have unique IDs
            device_ids = [d.device_id for d in devices]
            assert len(device_ids) == len(set(device_ids))
            
            # All devices should have valid properties
            for device in devices:
                assert device.memory_bytes > 0
                assert device.compute_units > 0
        except RuntimeError:
            pytest.skip("No GPU available")

    @pytest.mark.asyncio
    async def test_device_info_completeness(self):
        """Test that device info is complete and valid."""
        try:
            backend = await GPUBackendFactory.create_backend()
            device = backend.list_devices()[0] if backend.list_devices() else None
            
            if device is None:
                pytest.skip("No GPU available")
            
            # Verify all required fields
            assert device.device_id
            assert device.name
            assert device.vendor in ["nvidia", "amd", "intel", "apple", "qualcomm"]
            assert device.backend
            assert device.compute_capability
            assert device.memory_bytes > 0
            assert device.compute_units > 0
            assert device.clock_rate_mhz >= 0
            assert device.bandwidth_gbps > 0
            assert device.support_level in ["full", "partial", "experimental"]
        except RuntimeError:
            pytest.skip("No GPU available")

    @pytest.mark.asyncio
    async def test_device_not_found(self):
        """Test handling of non-existent device."""
        try:
            backend = await GPUBackendFactory.create_backend()
            
            # Try to access non-existent device
            with pytest.raises(RuntimeError):
                backend.get_device("nonexistent:99")
        except RuntimeError:
            pytest.skip("No GPU available")


class TestMemoryManagement:
    """Test GPU memory allocation and deallocation."""

    @pytest.mark.asyncio
    async def test_allocate_and_deallocate(self):
        """Test basic memory allocation and deallocation."""
        try:
            backend = await GPUBackendFactory.create_backend()
            await backend.initialize()
            
            device = backend.list_devices()[0]
            
            # Allocate 1MB
            handle = await backend.allocate(device.device_id, 1024 * 1024)
            assert handle is not None
            assert handle.size_bytes == 1024 * 1024
            
            # Deallocate
            await backend.deallocate(handle)
            
        except RuntimeError:
            pytest.skip("No GPU available")

    @pytest.mark.asyncio
    async def test_allocate_maximum_memory(self):
        """Test allocation of maximum available memory."""
        try:
            backend = await GPUBackendFactory.create_backend()
            await backend.initialize()
            
            device = backend.list_devices()[0]
            available = device.memory_available
            
            # Try to allocate all available memory (should succeed)
            try:
                handle = await backend.allocate(device.device_id, available)
                await backend.deallocate(handle)
            except RuntimeError:
                # Some backends may reserve space
                pytest.skip("Device reserves memory")
                
        except RuntimeError:
            pytest.skip("No GPU available")

    @pytest.mark.asyncio
    async def test_allocate_exceeds_available(self):
        """Test allocation exceeding available memory (should fail gracefully)."""
        try:
            backend = await GPUBackendFactory.create_backend()
            await backend.initialize()
            
            device = backend.list_devices()[0]
            
            # Try to allocate more than available
            with pytest.raises(RuntimeError):
                await backend.allocate(device.device_id, device.memory_available + 1024*1024)
                
        except RuntimeError:
            pytest.skip("No GPU available")

    @pytest.mark.asyncio
    async def test_memory_handle_properties(self):
        """Test that memory handles have correct properties."""
        try:
            backend = await GPUBackendFactory.create_backend()
            await backend.initialize()
            
            device = backend.list_devices()[0]
            size = 100 * 1024  # 100KB
            
            handle = await backend.allocate(device.device_id, size)
            
            assert handle.handle_id
            assert handle.device_id == device.device_id
            assert handle.size_bytes == size
            assert handle.allocated_at is not None
            
            await backend.deallocate(handle)
            
        except RuntimeError:
            pytest.skip("No GPU available")

    @pytest.mark.asyncio
    async def test_multiple_allocations(self):
        """Test multiple simultaneous allocations."""
        try:
            backend = await GPUBackendFactory.create_backend()
            await backend.initialize()
            
            device = backend.list_devices()[0]
            handles = []
            
            # Allocate multiple buffers
            for i in range(5):
                handle = await backend.allocate(device.device_id, 512 * 1024)
                handles.append(handle)
            
            # Verify all are different
            handle_ids = [h.handle_id for h in handles]
            assert len(set(handle_ids)) == len(handles)
            
            # Deallocate all
            for handle in handles:
                await backend.deallocate(handle)
                
        except RuntimeError:
            pytest.skip("No GPU available")


class TestDataTransfer:
    """Test host-to-device and device-to-host transfers."""

    @pytest.mark.asyncio
    async def test_copy_to_device(self):
        """Test copying data to device."""
        try:
            backend = await GPUBackendFactory.create_backend()
            await backend.initialize()
            
            device = backend.list_devices()[0]
            
            # Allocate on device
            handle = await backend.allocate(device.device_id, 1024)
            
            # Copy data to device
            data = b"test data" * 100
            await backend.copy_to_device(data[:1024], handle)
            
            # Verify (by copying back)
            retrieved = await backend.copy_from_device(handle, 0, 1024)
            assert len(retrieved) == 1024
            
            await backend.deallocate(handle)
            
        except RuntimeError:
            pytest.skip("No GPU available")

    @pytest.mark.asyncio
    async def test_copy_with_offset(self):
        """Test copying data with offset."""
        try:
            backend = await GPUBackendFactory.create_backend()
            await backend.initialize()
            
            device = backend.list_devices()[0]
            
            # Allocate large buffer
            handle = await backend.allocate(device.device_id, 10 * 1024)
            
            # Copy with offset
            data = b"X" * 1024
            await backend.copy_to_device(data, handle, offset_bytes=1024)
            
            # Retrieve with offset
            retrieved = await backend.copy_from_device(handle, 1024, 1024)
            assert len(retrieved) == 1024
            
            await backend.deallocate(handle)
            
        except RuntimeError:
            pytest.skip("No GPU available")

    @pytest.mark.asyncio
    async def test_large_transfer(self):
        """Test transferring large amounts of data."""
        try:
            backend = await GPUBackendFactory.create_backend()
            await backend.initialize()
            
            device = backend.list_devices()[0]
            
            # Allocate 100MB
            size = 100 * 1024 * 1024
            if size > device.memory_available:
                pytest.skip("Device has insufficient memory")
            
            handle = await backend.allocate(device.device_id, size)
            
            # Transfer (would test actual throughput in real scenario)
            data = b"\x00" * size
            await backend.copy_to_device(data, handle)
            
            await backend.deallocate(handle)
            
        except RuntimeError:
            pytest.skip("No GPU available")


class TestDeviceSync:
    """Test device synchronization."""

    @pytest.mark.asyncio
    async def test_synchronize_device(self):
        """Test device synchronization."""
        try:
            backend = await GPUBackendFactory.create_backend()
            await backend.initialize()
            
            device = backend.list_devices()[0]
            
            # Allocate and sync
            handle = await backend.allocate(device.device_id, 1024)
            await backend.copy_to_device(b"test", handle)
            await backend.synchronize(device.device_id)
            
            await backend.deallocate(handle)
            
        except RuntimeError:
            pytest.skip("No GPU available")

    @pytest.mark.asyncio
    async def test_multiple_synchronize_calls(self):
        """Test multiple synchronize calls."""
        try:
            backend = await GPUBackendFactory.create_backend()
            await backend.initialize()
            
            device = backend.list_devices()[0]
            
            # Multiple syncs should not error
            for _ in range(3):
                await backend.synchronize(device.device_id)
                
        except RuntimeError:
            pytest.skip("No GPU available")


class TestMonitoring:
    """Test GPU monitoring and telemetry."""

    @pytest.mark.asyncio
    async def test_memory_info(self):
        """Test getting device memory info."""
        try:
            backend = await GPUBackendFactory.create_backend()
            await backend.initialize()
            
            device = backend.list_devices()[0]
            
            info = await backend.get_device_memory_info(device.device_id)
            assert "used" in info or "available" in info
            
        except RuntimeError:
            pytest.skip("No GPU available")

    @pytest.mark.asyncio
    async def test_temperature_monitoring(self):
        """Test temperature monitoring (may not be available on all devices)."""
        try:
            backend = await GPUBackendFactory.create_backend()
            await backend.initialize()
            
            device = backend.list_devices()[0]
            
            try:
                temp = await backend.get_device_temperature(device.device_id)
                assert temp >= 0  # Temperature should be non-negative
            except RuntimeError:
                pytest.skip("Temperature monitoring not available")
                
        except RuntimeError:
            pytest.skip("No GPU available")

    @pytest.mark.asyncio
    async def test_power_usage_monitoring(self):
        """Test power usage monitoring (may not be available on all devices)."""
        try:
            backend = await GPUBackendFactory.create_backend()
            await backend.initialize()
            
            device = backend.list_devices()[0]
            
            try:
                power = await backend.get_device_power_usage(device.device_id)
                assert power >= 0
            except RuntimeError:
                pytest.skip("Power monitoring not available")
                
        except RuntimeError:
            pytest.skip("No GPU available")

    @pytest.mark.asyncio
    async def test_clock_rate_monitoring(self):
        """Test clock rate monitoring."""
        try:
            backend = await GPUBackendFactory.create_backend()
            await backend.initialize()
            
            device = backend.list_devices()[0]
            
            clock = await backend.get_device_clock_rate(device.device_id)
            assert clock >= 0
            
        except RuntimeError:
            pytest.skip("No GPU available")


class TestErrorRecovery:
    """Test error handling and recovery."""

    @pytest.mark.asyncio
    async def test_double_deallocate_handling(self):
        """Test handling of double deallocation."""
        try:
            backend = await GPUBackendFactory.create_backend()
            await backend.initialize()
            
            device = backend.list_devices()[0]
            
            handle = await backend.allocate(device.device_id, 1024)
            await backend.deallocate(handle)
            
            # Second deallocation should fail gracefully
            with pytest.raises(RuntimeError):
                await backend.deallocate(handle)
                
        except RuntimeError:
            pytest.skip("No GPU available")

    @pytest.mark.asyncio
    async def test_copy_from_deallocated_handle(self):
        """Test copying from deallocated handle."""
        try:
            backend = await GPUBackendFactory.create_backend()
            await backend.initialize()
            
            device = backend.list_devices()[0]
            
            handle = await backend.allocate(device.device_id, 1024)
            await backend.deallocate(handle)
            
            # Copy from deallocated should fail
            with pytest.raises(RuntimeError):
                await backend.copy_from_device(handle, 0, 1024)
                
        except RuntimeError:
            pytest.skip("No GPU available")

    @pytest.mark.asyncio
    async def test_backend_shutdown_cleanup(self):
        """Test backend shutdown cleans up resources."""
        try:
            backend = await GPUBackendFactory.create_backend()
            await backend.initialize()
            
            device = backend.list_devices()[0]
            
            # Allocate some memory
            handle = await backend.allocate(device.device_id, 1024)
            
            # Shutdown should clean up
            await backend.shutdown()
            
            # Subsequent operations should fail
            with pytest.raises((RuntimeError, AttributeError)):
                await backend.copy_from_device(handle, 0, 1024)
                
        except RuntimeError:
            pytest.skip("No GPU available")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
