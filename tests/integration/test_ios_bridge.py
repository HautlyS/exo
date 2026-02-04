"""Integration tests for iOS GPU bridge."""

import asyncio
import pytest

from exo.networking.ios_bridge import IOSGPUBridge, get_ios_bridge
from exo.networking.ios_types import IOSGPUInfo, DiscoveredIOSDevice


class TestIOSGPUBridge:
    """Test iOS GPU bridge functionality"""
    
    @pytest.fixture
    def bridge(self):
        """Create fresh bridge instance for each test"""
        return IOSGPUBridge()
    
    @pytest.mark.asyncio
    async def test_initialize(self, bridge):
        """Test bridge initialization"""
        result = await bridge.initialize()
        assert result is True
    
    @pytest.mark.asyncio
    async def test_discover_devices(self, bridge):
        """Test device discovery"""
        devices = await bridge.discover_devices(timeout=1.0)
        assert isinstance(devices, list)
    
    @pytest.mark.asyncio
    async def test_get_device_info_not_found(self, bridge):
        """Test getting non-existent device"""
        device = await bridge.get_device_info("nonexistent")
        assert device is None
    
    @pytest.mark.asyncio
    async def test_enumerate_gpu_no_device(self, bridge):
        """Test GPU enumeration with no device"""
        gpus = await bridge.enumerate_gpu_devices("invalid")
        assert gpus == []
    
    @pytest.mark.asyncio
    async def test_allocate_gpu_memory_no_device(self, bridge):
        """Test memory allocation on non-existent device"""
        handle = await bridge.allocate_gpu_memory("invalid", 0, 1024)
        assert handle is None
    
    @pytest.mark.asyncio
    async def test_allocate_gpu_memory_invalid_index(self, bridge):
        """Test memory allocation with invalid GPU index"""
        handle = await bridge.allocate_gpu_memory("invalid", 999, 1024)
        assert handle is None
    
    @pytest.mark.asyncio
    async def test_free_gpu_memory_no_device(self, bridge):
        """Test freeing memory on non-existent device"""
        result = await bridge.free_gpu_memory("invalid", "handle")
        assert result is False
    
    @pytest.mark.asyncio
    async def test_transfer_to_device_no_device(self, bridge):
        """Test data transfer to non-existent device"""
        result = await bridge.transfer_to_device("invalid", "handle", b"data")
        assert result is False
    
    @pytest.mark.asyncio
    async def test_transfer_from_device_no_device(self, bridge):
        """Test data transfer from non-existent device"""
        result = await bridge.transfer_from_device("invalid", "handle", 1024)
        assert result is None
    
    def test_register_device_callback(self, bridge):
        """Test device callback registration"""
        called = []
        
        def device_callback(device):
            called.append(device)
        
        bridge.register_device_callback(device_callback)
        
        assert len(bridge.peer_callbacks) == 1
    
    def test_register_connection_callback(self, bridge):
        """Test connection callback registration"""
        called = []
        
        def connection_callback(device_id, connected):
            called.append((device_id, connected))
        
        bridge.register_connection_callback(connection_callback)
        
        assert len(bridge.connection_callbacks) == 1
    
    def test_register_multiple_callbacks(self, bridge):
        """Test registering multiple callbacks"""
        def device_cb(d): pass
        def conn_cb(d, c): pass
        
        bridge.register_device_callback(device_cb)
        bridge.register_device_callback(device_cb)
        bridge.register_connection_callback(conn_cb)
        
        assert len(bridge.peer_callbacks) == 2
        assert len(bridge.connection_callbacks) == 1
    
    def test_singleton_bridge(self):
        """Test iOS bridge singleton"""
        bridge1 = get_ios_bridge()
        bridge2 = get_ios_bridge()
        assert bridge1 is bridge2


class TestIOSGPUInfo:
    """Test iOS GPU info data structures"""
    
    def test_gpu_info_creation(self):
        """Test creating GPU info"""
        gpu = IOSGPUInfo(
            device_id="gpu-0",
            name="A17 Pro",
            vendor="Apple",
            max_memory=8 * 1024 * 1024 * 1024,
            compute_units=6,
            supports_family="Apple8",
            is_low_power=False
        )
        
        assert gpu.device_id == "gpu-0"
        assert gpu.name == "A17 Pro"
        assert gpu.vendor == "Apple"
        assert gpu.memory_gb == 8.0
        assert gpu.compute_units == 6
    
    def test_gpu_info_string_representation(self):
        """Test GPU info string representation"""
        gpu = IOSGPUInfo(
            device_id="gpu-0",
            name="A17 Pro",
            vendor="Apple",
            max_memory=8 * 1024 * 1024 * 1024,
            compute_units=6,
            supports_family="Apple8",
            is_low_power=False
        )
        
        str_repr = str(gpu)
        assert "A17 Pro" in str_repr
        assert "Apple" in str_repr
        assert "8.0GB" in str_repr
    
    def test_gpu_info_memory_calculation(self):
        """Test GPU info memory conversions"""
        gpu = IOSGPUInfo(
            device_id="gpu-0",
            name="Test GPU",
            vendor="Apple",
            max_memory=4 * 1024 * 1024 * 1024,  # 4GB
            compute_units=4,
            supports_family="Apple7",
            is_low_power=False
        )
        
        assert gpu.memory_gb == pytest.approx(4.0)


class TestDiscoveredIOSDevice:
    """Test discovered iOS device data structures"""
    
    def test_device_creation(self):
        """Test creating discovered device"""
        gpu = IOSGPUInfo(
            device_id="gpu-0",
            name="A17 Pro",
            vendor="Apple",
            max_memory=8 * 1024 * 1024 * 1024,
            compute_units=6,
            supports_family="Apple8",
            is_low_power=False
        )
        
        device = DiscoveredIOSDevice(
            peer_id="peer-1",
            display_name="iPhone 15 Pro",
            address="192.168.1.100",
            port=5000,
            gpu_devices=[gpu]
        )
        
        assert device.peer_id == "peer-1"
        assert device.display_name == "iPhone 15 Pro"
        assert device.address == "192.168.1.100"
        assert device.port == 5000
        assert device.has_gpu() is True
        assert device.total_gpu_memory() == 8 * 1024 * 1024 * 1024
        assert device.total_gpu_memory_gb == pytest.approx(8.0)
    
    def test_device_without_gpu(self):
        """Test device without GPU"""
        device = DiscoveredIOSDevice(
            peer_id="peer-1",
            display_name="iPhone 15",
            address="192.168.1.100",
            port=5000,
            gpu_devices=[]
        )
        
        assert device.has_gpu() is False
        assert device.total_gpu_memory() == 0
        assert device.total_gpu_memory_gb == 0.0
    
    def test_device_multiple_gpus(self):
        """Test device with multiple GPUs"""
        gpu1 = IOSGPUInfo(
            device_id="gpu-0",
            name="GPU 1",
            vendor="Apple",
            max_memory=4 * 1024 * 1024 * 1024,
            compute_units=4,
            supports_family="Apple8",
            is_low_power=False
        )
        
        gpu2 = IOSGPUInfo(
            device_id="gpu-1",
            name="GPU 2",
            vendor="Apple",
            max_memory=4 * 1024 * 1024 * 1024,
            compute_units=4,
            supports_family="Apple8",
            is_low_power=False
        )
        
        device = DiscoveredIOSDevice(
            peer_id="peer-1",
            display_name="iPhone 15 Pro Max",
            address="192.168.1.100",
            port=5000,
            gpu_devices=[gpu1, gpu2]
        )
        
        assert device.has_gpu() is True
        assert len(device.gpu_devices) == 2
        assert device.total_gpu_memory() == 8 * 1024 * 1024 * 1024
        assert device.total_gpu_memory_gb == pytest.approx(8.0)
    
    def test_device_string_representation(self):
        """Test device string representation"""
        gpu = IOSGPUInfo(
            device_id="gpu-0",
            name="A17 Pro",
            vendor="Apple",
            max_memory=8 * 1024 * 1024 * 1024,
            compute_units=6,
            supports_family="Apple8",
            is_low_power=False
        )
        
        device = DiscoveredIOSDevice(
            peer_id="peer-1",
            display_name="iPhone 15 Pro",
            address="192.168.1.100",
            port=5000,
            gpu_devices=[gpu]
        )
        
        str_repr = str(device)
        assert "iPhone 15 Pro" in str_repr
        assert "192.168.1.100:5000" in str_repr
        assert "1 GPU" in str_repr
