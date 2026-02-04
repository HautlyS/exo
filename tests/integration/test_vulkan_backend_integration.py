"""Integration tests for Vulkan GPU backend (Phase 5).

Tests the full workflow:
1. Initialize backend
2. Enumerate devices
3. Allocate memory
4. Copy data host->device and device->host
5. Query device properties
6. Synchronize and deallocate
7. Shutdown
"""

import pytest
import asyncio
import json
from unittest.mock import patch, MagicMock
from exo.gpu.backends.vulkan_backend import VulkanGPUBackend, VulkanFFI


class TestVulkanBackendFullWorkflow:
    """Complete workflow integration tests"""
    
    @pytest.mark.asyncio
    async def test_full_workflow_single_device(self):
        """Test complete workflow: init, allocate, copy, synchronize, deallocate"""
        backend = VulkanGPUBackend()
        
        # Initialize
        await backend.initialize()
        devices = backend.list_devices()
        assert devices is not None
        
        if not devices:
            pytest.skip("No Vulkan devices available")
        
        device = devices[0]
        device_id = device.device_id
        
        # Verify device info
        assert device.device_id is not None
        assert device.device_name is not None
        assert device.memory_bytes > 0
        
        with patch.object(VulkanFFI, 'load_library') as mock_load:
            mock_lib = MagicMock()
            mock_load.return_value = mock_lib
            
            # Setup allocation mock
            handle_id = "test-handle-123"
            response_json = json.dumps({"handle_id": handle_id})
            mock_lib.allocate_device_memory.return_value = response_json.encode('utf-8')
            
            # Allocate
            handle = await backend.allocate(device_id, 1024 * 1024)
            assert handle.handle_id == handle_id
            assert handle.size_bytes == 1024 * 1024
            assert handle.device_id == device_id
            
            # Copy to device
            test_data = b"Hello from host"
            mock_lib.copy_data_to_device.return_value = True
            await backend.copy_to_device(test_data, handle)
            
            # Query memory info
            memory_info_json = json.dumps({
                "total_bytes": 8 * 1024 * 1024 * 1024,
                "available_bytes": 4 * 1024 * 1024 * 1024
            })
            mock_lib.get_device_memory_info.return_value = memory_info_json.encode('utf-8')
            total, available = await backend.get_device_memory_info(device_id)
            assert total > 0
            assert available <= total
            
            # Copy from device
            import base64
            retrieved_data = b"Data from GPU"
            encoded = base64.b64encode(retrieved_data).decode('utf-8')
            copy_response_json = json.dumps({"data": encoded})
            mock_lib.copy_data_from_device.return_value = copy_response_json.encode('utf-8')
            retrieved = await backend.copy_from_device(handle, 0, len(retrieved_data))
            assert retrieved == retrieved_data
            
            # Synchronize
            mock_lib.synchronize_device.return_value = True
            await backend.synchronize(device_id)
            
            # Deallocate
            mock_lib.free_device_memory.return_value = True
            await backend.deallocate(handle)
        
        await backend.shutdown()
    
    @pytest.mark.asyncio
    async def test_multiple_allocations_and_copies(self):
        """Test multiple allocations and data copies"""
        backend = VulkanGPUBackend()
        await backend.initialize()
        
        devices = backend.list_devices()
        if not devices:
            pytest.skip("No Vulkan devices available")
        
        device_id = devices[0].device_id
        
        with patch.object(VulkanFFI, 'load_library') as mock_load:
            mock_lib = MagicMock()
            mock_load.return_value = mock_lib
            
            # Setup mocks
            mock_lib.copy_data_to_device.return_value = True
            mock_lib.free_device_memory.return_value = True
            
            handles = []
            
            # Allocate multiple buffers
            for i in range(3):
                handle_id = f"test-handle-{i}"
                response_json = json.dumps({"handle_id": handle_id})
                mock_lib.allocate_device_memory.return_value = response_json.encode('utf-8')
                
                size = 1024 * (i + 1)
                handle = await backend.allocate(device_id, size)
                handles.append(handle)
                
                # Copy different data to each
                test_data = f"Buffer {i}".encode('utf-8')
                await backend.copy_to_device(test_data, handle)
            
            assert len(handles) == 3
            
            # Deallocate all
            for handle in handles:
                await backend.deallocate(handle)
        
        await backend.shutdown()
    
    @pytest.mark.asyncio
    async def test_device_properties_retrieval(self):
        """Test retrieving detailed device properties"""
        backend = VulkanGPUBackend()
        await backend.initialize()
        
        devices = backend.list_devices()
        if not devices:
            pytest.skip("No Vulkan devices available")
        
        device_id = devices[0].device_id
        
        props = await backend.get_device_properties(device_id)
        
        # Verify all required properties are present
        assert 'device_id' in props
        assert 'device_name' in props
        assert 'vendor' in props
        assert 'backend' in props
        assert 'memory_bytes' in props
        assert 'compute_units' in props
        
        # Verify values are reasonable
        assert props['device_id'] == device_id
        assert props['memory_bytes'] > 0
        assert props['compute_units'] > 0
        assert props['backend'] == 'vulkan'
        
        await backend.shutdown()
    
    @pytest.mark.asyncio
    async def test_large_allocation_and_transfer(self):
        """Test larger memory allocations and transfers"""
        backend = VulkanGPUBackend()
        await backend.initialize()
        
        devices = backend.list_devices()
        if not devices:
            pytest.skip("No Vulkan devices available")
        
        device_id = devices[0].device_id
        
        with patch.object(VulkanFFI, 'load_library') as mock_load:
            mock_lib = MagicMock()
            mock_load.return_value = mock_lib
            
            # Allocate 10MB
            allocation_size = 10 * 1024 * 1024
            handle_id = "large-allocation"
            response_json = json.dumps({"handle_id": handle_id})
            mock_lib.allocate_device_memory.return_value = response_json.encode('utf-8')
            
            handle = await backend.allocate(device_id, allocation_size)
            assert handle.size_bytes == allocation_size
            
            # Copy 5MB of data
            test_data = b'X' * (5 * 1024 * 1024)
            mock_lib.copy_data_to_device.return_value = True
            await backend.copy_to_device(test_data, handle)
            
            # Copy back
            import base64
            encoded = base64.b64encode(test_data).decode('utf-8')
            response_json = json.dumps({"data": encoded})
            mock_lib.copy_data_from_device.return_value = response_json.encode('utf-8')
            
            retrieved = await backend.copy_from_device(handle, 0, len(test_data))
            assert len(retrieved) == len(test_data)
            assert retrieved == test_data
            
            # Cleanup
            mock_lib.free_device_memory.return_value = True
            await backend.deallocate(handle)
        
        await backend.shutdown()


class TestVulkanBackendErrorHandling:
    """Test error cases and edge conditions"""
    
    @pytest.mark.asyncio
    async def test_allocate_on_invalid_device(self):
        """Allocate should fail on invalid device"""
        backend = VulkanGPUBackend()
        await backend.initialize()
        
        with pytest.raises(RuntimeError):
            await backend.allocate("invalid:device:id", 1024)
        
        await backend.shutdown()
    
    @pytest.mark.asyncio
    async def test_deallocate_nonexistent_handle(self):
        """Should handle deallocation of nonexistent handle"""
        backend = VulkanGPUBackend()
        await backend.initialize()
        
        devices = backend.list_devices()
        if not devices:
            pytest.skip("No Vulkan devices available")
        
        with patch.object(VulkanFFI, 'load_library') as mock_load:
            mock_lib = MagicMock()
            mock_load.return_value = mock_lib
            
            # Nonexistent handle should not raise (logged as warning)
            from exo.gpu.backend import MemoryHandle
            fake_handle = MemoryHandle(
                handle_id="nonexistent",
                device_id=devices[0].device_id,
                size_bytes=1024
            )
            
            mock_lib.free_device_memory.return_value = False
            
            # Should not raise, just log warning
            await backend.deallocate(fake_handle)
        
        await backend.shutdown()
    
    @pytest.mark.asyncio
    async def test_copy_exceeding_allocation_size(self):
        """Should raise ValueError if copy exceeds allocation"""
        backend = VulkanGPUBackend()
        await backend.initialize()
        
        devices = backend.list_devices()
        if not devices:
            pytest.skip("No Vulkan devices available")
        
        device_id = devices[0].device_id
        
        with patch.object(VulkanFFI, 'load_library') as mock_load:
            mock_lib = MagicMock()
            mock_load.return_value = mock_lib
            
            # Allocate small buffer
            handle_id = "small-buffer"
            response_json = json.dumps({"handle_id": handle_id})
            mock_lib.allocate_device_memory.return_value = response_json.encode('utf-8')
            
            handle = await backend.allocate(device_id, 100)
            
            # Try to copy more data than allocated
            large_data = b'X' * 1000
            
            with pytest.raises(ValueError):
                await backend.copy_to_device(large_data, handle)
            
            # Cleanup
            mock_lib.free_device_memory.return_value = True
            await backend.deallocate(handle)
        
        await backend.shutdown()
    
    @pytest.mark.asyncio
    async def test_copy_from_exceeds_allocation(self):
        """Should raise ValueError if copy_from exceeds allocation"""
        backend = VulkanGPUBackend()
        await backend.initialize()
        
        devices = backend.list_devices()
        if not devices:
            pytest.skip("No Vulkan devices available")
        
        device_id = devices[0].device_id
        
        with patch.object(VulkanFFI, 'load_library') as mock_load:
            mock_lib = MagicMock()
            mock_load.return_value = mock_lib
            
            # Allocate small buffer
            handle_id = "small-buffer"
            response_json = json.dumps({"handle_id": handle_id})
            mock_lib.allocate_device_memory.return_value = response_json.encode('utf-8')
            
            handle = await backend.allocate(device_id, 100)
            
            # Try to copy more than allocated
            with pytest.raises(ValueError):
                await backend.copy_from_device(handle, 0, 1000)
            
            # Cleanup
            mock_lib.free_device_memory.return_value = True
            await backend.deallocate(handle)
        
        await backend.shutdown()
    
    @pytest.mark.asyncio
    async def test_query_memory_invalid_device(self):
        """Should raise RuntimeError for invalid device"""
        backend = VulkanGPUBackend()
        await backend.initialize()
        
        with pytest.raises(RuntimeError):
            await backend.get_device_memory_info("invalid:device")
        
        await backend.shutdown()
    
    @pytest.mark.asyncio
    async def test_synchronize_invalid_device(self):
        """Should raise RuntimeError for invalid device"""
        backend = VulkanGPUBackend()
        await backend.initialize()
        
        with pytest.raises(RuntimeError):
            await backend.synchronize("invalid:device")
        
        await backend.shutdown()


class TestVulkanBackendMonitoring:
    """Test monitoring and telemetry methods"""
    
    @pytest.mark.asyncio
    async def test_temperature_not_available(self):
        """Temperature should not be available for Vulkan"""
        backend = VulkanGPUBackend()
        await backend.initialize()
        
        devices = backend.list_devices()
        if devices:
            device_id = devices[0].device_id
            temp = await backend.get_device_temperature(device_id)
            assert temp is None
        
        await backend.shutdown()
    
    @pytest.mark.asyncio
    async def test_power_usage_not_available(self):
        """Power usage should not be available for Vulkan"""
        backend = VulkanGPUBackend()
        await backend.initialize()
        
        devices = backend.list_devices()
        if devices:
            device_id = devices[0].device_id
            power = await backend.get_device_power_usage(device_id)
            assert power is None
        
        await backend.shutdown()
    
    @pytest.mark.asyncio
    async def test_clock_rate_not_available(self):
        """Clock rate should not be available for Vulkan"""
        backend = VulkanGPUBackend()
        await backend.initialize()
        
        devices = backend.list_devices()
        if devices:
            device_id = devices[0].device_id
            clock = await backend.get_device_clock_rate(device_id)
            assert clock is None
        
        await backend.shutdown()
    
    @pytest.mark.asyncio
    async def test_p2p_not_supported(self):
        """P2P transfers should raise NotImplementedError"""
        backend = VulkanGPUBackend()
        await backend.initialize()
        
        devices = backend.list_devices()
        if devices:
            device_id = devices[0].device_id
            
            with patch.object(VulkanFFI, 'load_library') as mock_load:
                mock_lib = MagicMock()
                mock_load.return_value = mock_lib
                
                # Allocate two buffers
                handle1_json = json.dumps({"handle_id": "handle-1"})
                handle2_json = json.dumps({"handle_id": "handle-2"})
                
                mock_lib.allocate_device_memory.side_effect = [
                    handle1_json.encode('utf-8'),
                    handle2_json.encode('utf-8')
                ]
                
                handle1 = await backend.allocate(device_id, 1024)
                handle2 = await backend.allocate(device_id, 1024)
                
                # P2P should raise NotImplementedError
                with pytest.raises(NotImplementedError):
                    await backend.copy_device_to_device(handle1, handle2, 512)
                
                # Cleanup
                mock_lib.free_device_memory.return_value = True
                await backend.deallocate(handle1)
                await backend.deallocate(handle2)
        
        await backend.shutdown()
