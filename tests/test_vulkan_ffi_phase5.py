"""Phase 5 FFI tests for Vulkan backend.

Comprehensive tests for:
- Memory allocation and deallocation via FFI
- Host-to-device and device-to-host copies
- Device memory queries
- Device synchronization
- Error handling and edge cases
"""

import pytest
import json
from unittest.mock import Mock, patch, MagicMock
from exo.gpu.backends.vulkan_backend import VulkanFFI, VulkanGPUBackend


class TestVulkanFFIAllocate:
    """Test memory allocation via FFI"""
    
    def test_allocate_memory_returns_handle(self):
        """allocate_memory should return a non-empty handle string"""
        # Mock the library
        with patch.object(VulkanFFI, 'load_library') as mock_load:
            mock_lib = MagicMock()
            mock_load.return_value = mock_lib
            
            # Setup mock response
            handle_id = "test-handle-123"
            response_json = json.dumps({"handle_id": handle_id})
            mock_lib.allocate_device_memory.return_value = response_json.encode('utf-8')
            
            result = VulkanFFI.allocate_memory(0, 1024 * 1024)
            assert result == handle_id
            
    def test_allocate_memory_error_handling(self):
        """allocate_memory should return None on error"""
        with patch.object(VulkanFFI, 'load_library') as mock_load:
            mock_lib = MagicMock()
            mock_load.return_value = mock_lib
            
            # Setup mock to return None
            mock_lib.allocate_device_memory.return_value = None
            
            result = VulkanFFI.allocate_memory(0, 1024)
            assert result is None


class TestVulkanFFIDeallocate:
    """Test memory deallocation via FFI"""
    
    def test_deallocate_memory_success(self):
        """deallocate_memory should return True on success"""
        with patch.object(VulkanFFI, 'load_library') as mock_load:
            mock_lib = MagicMock()
            mock_load.return_value = mock_lib
            
            mock_lib.free_device_memory.return_value = True
            
            result = VulkanFFI.deallocate_memory("test-handle")
            assert result is True
            
    def test_deallocate_memory_invalid_handle(self):
        """deallocate_memory should handle empty handle"""
        result = VulkanFFI.deallocate_memory("")
        assert result is False


class TestVulkanFFICopyToDevice:
    """Test host-to-device copy via FFI"""
    
    def test_copy_to_device_success(self):
        """copy_to_device should return True on success"""
        with patch.object(VulkanFFI, 'load_library') as mock_load:
            mock_lib = MagicMock()
            mock_load.return_value = mock_lib
            
            mock_lib.copy_data_to_device.return_value = True
            
            test_data = b"Hello, GPU!"
            result = VulkanFFI.copy_to_device("test-handle", test_data)
            assert result is True
            
    def test_copy_to_device_empty_data(self):
        """copy_to_device should handle empty data"""
        result = VulkanFFI.copy_to_device("test-handle", b"")
        assert result is False
        
    def test_copy_to_device_invalid_handle(self):
        """copy_to_device should handle invalid handle"""
        result = VulkanFFI.copy_to_device("", b"data")
        assert result is False


class TestVulkanFFICopyFromDevice:
    """Test device-to-host copy via FFI"""
    
    def test_copy_from_device_success(self):
        """copy_from_device should return bytes"""
        with patch.object(VulkanFFI, 'load_library') as mock_load:
            import base64
            mock_lib = MagicMock()
            mock_load.return_value = mock_lib
            
            # Create response with base64-encoded data
            test_data = b"GPU data"
            encoded = base64.b64encode(test_data).decode('utf-8')
            response_json = json.dumps({"data": encoded})
            mock_lib.copy_data_from_device.return_value = response_json.encode('utf-8')
            
            result = VulkanFFI.copy_from_device("test-handle", len(test_data))
            assert result == test_data
            
    def test_copy_from_device_zero_bytes(self):
        """copy_from_device should handle zero-byte copy"""
        with patch.object(VulkanFFI, 'load_library') as mock_load:
            mock_lib = MagicMock()
            mock_load.return_value = mock_lib
            
            response_json = json.dumps({"data": ""})
            mock_lib.copy_data_from_device.return_value = response_json.encode('utf-8')
            
            result = VulkanFFI.copy_from_device("test-handle", 0)
            assert result == b''


class TestVulkanFFIMemoryInfo:
    """Test device memory info queries"""
    
    def test_get_device_memory_info_success(self):
        """get_device_memory_info should return (total, available) tuple"""
        with patch.object(VulkanFFI, 'load_library') as mock_load:
            mock_lib = MagicMock()
            mock_load.return_value = mock_lib
            
            response_json = json.dumps({
                "total_bytes": 8 * 1024 * 1024 * 1024,  # 8GB
                "available_bytes": 4 * 1024 * 1024 * 1024  # 4GB
            })
            mock_lib.get_device_memory_info.return_value = response_json.encode('utf-8')
            
            total, available = VulkanFFI.get_device_memory_info(0)
            assert total == 8 * 1024 * 1024 * 1024
            assert available == 4 * 1024 * 1024 * 1024
            
    def test_get_device_memory_info_error(self):
        """get_device_memory_info should return (0, 0) on error"""
        with patch.object(VulkanFFI, 'load_library') as mock_load:
            mock_lib = MagicMock()
            mock_load.return_value = mock_lib
            
            mock_lib.get_device_memory_info.return_value = None
            
            total, available = VulkanFFI.get_device_memory_info(0)
            assert total == 0
            assert available == 0


class TestVulkanFFISynchronize:
    """Test device synchronization"""
    
    def test_synchronize_device_success(self):
        """synchronize_device should return True"""
        with patch.object(VulkanFFI, 'load_library') as mock_load:
            mock_lib = MagicMock()
            mock_load.return_value = mock_lib
            
            mock_lib.synchronize_device.return_value = True
            
            result = VulkanFFI.synchronize_device(0)
            assert result is True
            
    def test_synchronize_device_error(self):
        """synchronize_device should return False on error"""
        with patch.object(VulkanFFI, 'load_library') as mock_load:
            mock_lib = MagicMock()
            mock_load.return_value = mock_lib
            
            mock_lib.synchronize_device.side_effect = Exception("Test error")
            
            result = VulkanFFI.synchronize_device(0)
            assert result is False


class TestVulkanBackendIntegration:
    """Integration tests for backend methods"""
    
    @pytest.mark.asyncio
    async def test_backend_initialization(self):
        """Backend should initialize successfully"""
        backend = VulkanGPUBackend()
        await backend.initialize()
        
        # Should have at least stub device or real devices
        devices = backend.list_devices()
        assert devices is not None
        
        await backend.shutdown()
        
    @pytest.mark.asyncio
    async def test_allocate_and_deallocate(self):
        """Should allocate and deallocate memory"""
        backend = VulkanGPUBackend()
        await backend.initialize()
        
        devices = backend.list_devices()
        if devices:
            device_id = devices[0].device_id
            
            # Allocate
            with patch.object(VulkanFFI, 'load_library') as mock_load:
                mock_lib = MagicMock()
                mock_load.return_value = mock_lib
                
                # Setup mocks
                handle_id = "test-123"
                response_json = json.dumps({"handle_id": handle_id})
                mock_lib.allocate_device_memory.return_value = response_json.encode('utf-8')
                
                handle = await backend.allocate(device_id, 1024)
                assert handle.size_bytes == 1024
                
                # Deallocate
                mock_lib.free_device_memory.return_value = True
                await backend.deallocate(handle)
        
        await backend.shutdown()
        
    @pytest.mark.asyncio
    async def test_memory_info_query(self):
        """Should query device memory info"""
        backend = VulkanGPUBackend()
        await backend.initialize()
        
        devices = backend.list_devices()
        if devices:
            device_id = devices[0].device_id
            
            with patch.object(VulkanFFI, 'load_library') as mock_load:
                mock_lib = MagicMock()
                mock_load.return_value = mock_lib
                
                response_json = json.dumps({
                    "total_bytes": 8 * 1024 * 1024 * 1024,
                    "available_bytes": 4 * 1024 * 1024 * 1024
                })
                mock_lib.get_device_memory_info.return_value = response_json.encode('utf-8')
                
                total, available = await backend.get_device_memory_info(device_id)
                assert total > 0
                assert available <= total
        
        await backend.shutdown()
        
    @pytest.mark.asyncio
    async def test_synchronize(self):
        """Should synchronize with device"""
        backend = VulkanGPUBackend()
        await backend.initialize()
        
        devices = backend.list_devices()
        if devices:
            device_id = devices[0].device_id
            
            with patch.object(VulkanFFI, 'load_library') as mock_load:
                mock_lib = MagicMock()
                mock_load.return_value = mock_lib
                
                mock_lib.synchronize_device.return_value = True
                
                # Should not raise
                await backend.synchronize(device_id)
        
        await backend.shutdown()
        
    @pytest.mark.asyncio
    async def test_copy_to_device(self):
        """Should copy data to device"""
        backend = VulkanGPUBackend()
        await backend.initialize()
        
        devices = backend.list_devices()
        if devices:
            device_id = devices[0].device_id
            
            with patch.object(VulkanFFI, 'load_library') as mock_load:
                mock_lib = MagicMock()
                mock_load.return_value = mock_lib
                
                # Setup mocks
                handle_id = "test-123"
                response_json = json.dumps({"handle_id": handle_id})
                mock_lib.allocate_device_memory.return_value = response_json.encode('utf-8')
                mock_lib.copy_data_to_device.return_value = True
                
                handle = await backend.allocate(device_id, 1024)
                test_data = b"Test data"
                
                # Should not raise
                await backend.copy_to_device(test_data, handle)
                
                # Cleanup
                mock_lib.free_device_memory.return_value = True
                await backend.deallocate(handle)
        
        await backend.shutdown()
        
    @pytest.mark.asyncio
    async def test_copy_from_device(self):
        """Should copy data from device"""
        backend = VulkanGPUBackend()
        await backend.initialize()
        
        devices = backend.list_devices()
        if devices:
            device_id = devices[0].device_id
            
            with patch.object(VulkanFFI, 'load_library') as mock_load:
                import base64
                mock_lib = MagicMock()
                mock_load.return_value = mock_lib
                
                # Setup mocks
                handle_id = "test-123"
                response_json = json.dumps({"handle_id": handle_id})
                mock_lib.allocate_device_memory.return_value = response_json.encode('utf-8')
                
                test_data = b"GPU data"
                encoded = base64.b64encode(test_data).decode('utf-8')
                response_json = json.dumps({"data": encoded})
                mock_lib.copy_data_from_device.return_value = response_json.encode('utf-8')
                
                handle = await backend.allocate(device_id, 1024)
                result = await backend.copy_from_device(handle, 0, len(test_data))
                assert result == test_data
                
                # Cleanup
                mock_lib.free_device_memory.return_value = True
                await backend.deallocate(handle)
        
        await backend.shutdown()
        
    @pytest.mark.asyncio
    async def test_copy_exceeds_allocation(self):
        """Should raise ValueError if copy exceeds allocation"""
        backend = VulkanGPUBackend()
        await backend.initialize()
        
        devices = backend.list_devices()
        if devices:
            device_id = devices[0].device_id
            
            with patch.object(VulkanFFI, 'load_library') as mock_load:
                mock_lib = MagicMock()
                mock_load.return_value = mock_lib
                
                # Setup mocks
                handle_id = "test-123"
                response_json = json.dumps({"handle_id": handle_id})
                mock_lib.allocate_device_memory.return_value = response_json.encode('utf-8')
                
                handle = await backend.allocate(device_id, 100)
                
                # Try to copy more than allocated
                large_data = b'X' * 1000
                with pytest.raises(ValueError):
                    await backend.copy_to_device(large_data, handle)
                
                # Cleanup
                mock_lib.free_device_memory.return_value = True
                await backend.deallocate(handle)
        
        await backend.shutdown()
        
    @pytest.mark.asyncio
    async def test_missing_methods_implemented(self):
        """Should have all abstract methods implemented"""
        backend = VulkanGPUBackend()
        await backend.initialize()
        
        devices = backend.list_devices()
        if devices:
            device_id = devices[0].device_id
            
            # Test P2P raises NotImplementedError
            with pytest.raises(NotImplementedError):
                handle1 = await backend.allocate(device_id, 1024)
                handle2 = await backend.allocate(device_id, 1024)
                await backend.copy_device_to_device(handle1, handle2, 512)
                
        # Test monitoring methods return None (not available for Vulkan)
        devices = backend.list_devices()
        if devices:
            device_id = devices[0].device_id
            
            temp = await backend.get_device_temperature(device_id)
            assert temp is None
            
            power = await backend.get_device_power_usage(device_id)
            assert power is None
            
            clock = await backend.get_device_clock_rate(device_id)
            assert clock is None
        
        await backend.shutdown()
