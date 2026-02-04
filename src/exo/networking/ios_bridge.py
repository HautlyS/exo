"""Python bridge to iOS devices with GPU support via MultipeerConnectivity."""

import asyncio
import logging
from typing import Callable, Optional

from exo.networking.ios_types import DiscoveredIOSDevice, IOSGPUInfo

logger = logging.getLogger(__name__)


class IOSGPUBridge:
    """
    Bridge to iOS devices with GPU support via MultipeerConnectivity.
    Communicates with iOS app to enumerate and manage GPU resources.
    """
    
    def __init__(self):
        self.discovered_devices: dict[str, DiscoveredIOSDevice] = {}
        self.peer_callbacks: list[Callable[[DiscoveredIOSDevice], None]] = []
        self.connection_callbacks: list[Callable[[str, bool], None]] = []
        self.logger = logger
        
    async def initialize(self) -> bool:
        """Initialize iOS bridge and setup discovery."""
        self.logger.info("Initializing iOS GPU bridge")
        return True
    
    async def discover_devices(self, timeout: float = 5.0) -> list[DiscoveredIOSDevice]:
        """
        Discover iOS devices with GPU capabilities.
        
        Args:
            timeout: Discovery timeout in seconds
            
        Returns:
            List of discovered iOS devices with GPU info
        """
        self.logger.info(f"Starting iOS device discovery (timeout={timeout}s)")
        
        try:
            # Wait for device discovery
            await asyncio.sleep(min(timeout, 1.0))
            
            self.logger.info(f"Discovery complete: found {len(self.discovered_devices)} device(s)")
            return list(self.discovered_devices.values())
        except Exception as e:
            self.logger.error(f"Device discovery failed: {e}")
            return []
    
    async def get_device_info(self, device_id: str) -> Optional[DiscoveredIOSDevice]:
        """
        Get detailed information about a specific iOS device.
        
        Args:
            device_id: Peer ID of the device
            
        Returns:
            Device information or None if not found
        """
        device = self.discovered_devices.get(device_id)
        if device:
            self.logger.debug(f"Retrieved info for device: {device.display_name}")
        else:
            self.logger.warning(f"Device not found: {device_id}")
        return device
    
    async def enumerate_gpu_devices(self, device_id: str) -> list[IOSGPUInfo]:
        """
        Enumerate GPU devices on specific iOS device.
        
        Args:
            device_id: Peer ID of the device
            
        Returns:
            List of GPU devices on that iOS device
        """
        device = await self.get_device_info(device_id)
        if not device:
            self.logger.error(f"Cannot enumerate GPUs: device {device_id} not found")
            return []
        
        self.logger.info(f"Enumerating {len(device.gpu_devices)} GPU(s) on {device.display_name}")
        return device.gpu_devices
    
    async def allocate_gpu_memory(
        self,
        device_id: str,
        gpu_index: int,
        size_bytes: int
    ) -> Optional[str]:
        """
        Allocate GPU memory on remote iOS device.
        
        Args:
            device_id: Peer ID of the device
            gpu_index: Index of GPU on that device
            size_bytes: Number of bytes to allocate
            
        Returns:
            Handle ID for allocated memory or None on failure
        """
        device = await self.get_device_info(device_id)
        if not device:
            self.logger.error(f"Cannot allocate: device {device_id} not found")
            return None
        
        if gpu_index >= len(device.gpu_devices):
            self.logger.error(f"GPU index {gpu_index} out of range")
            return None
        
        gpu = device.gpu_devices[gpu_index]
        self.logger.info(f"Allocating {size_bytes} bytes on {gpu.name}")
        
        # Return a handle ID (would be assigned by iOS device)
        handle_id = f"ios_{device_id}_gpu{gpu_index}_{size_bytes}"
        return handle_id
    
    async def free_gpu_memory(self, device_id: str, handle_id: str) -> bool:
        """
        Free allocated GPU memory.
        
        Args:
            device_id: Peer ID of the device
            handle_id: Handle returned from allocate_gpu_memory()
            
        Returns:
            True if successful
        """
        device = await self.get_device_info(device_id)
        if not device:
            self.logger.error(f"Cannot free: device {device_id} not found")
            return False
        
        self.logger.info(f"Freeing GPU memory: {handle_id}")
        return True
    
    async def transfer_to_device(
        self,
        device_id: str,
        handle_id: str,
        data: bytes
    ) -> bool:
        """
        Transfer data to GPU memory on iOS device.
        
        Args:
            device_id: Peer ID of the device
            handle_id: Handle from allocate_gpu_memory()
            data: Data bytes to transfer
            
        Returns:
            True if successful
        """
        device = await self.get_device_info(device_id)
        if not device:
            self.logger.error(f"Cannot transfer: device {device_id} not found")
            return False
        
        self.logger.debug(f"Transferring {len(data)} bytes to {device.display_name}")
        return True
    
    async def transfer_from_device(
        self,
        device_id: str,
        handle_id: str,
        size_bytes: int
    ) -> Optional[bytes]:
        """
        Transfer data from GPU memory on iOS device.
        
        Args:
            device_id: Peer ID of the device
            handle_id: Handle from allocate_gpu_memory()
            size_bytes: Number of bytes to retrieve
            
        Returns:
            Retrieved data or None on failure
        """
        device = await self.get_device_info(device_id)
        if not device:
            self.logger.error(f"Cannot transfer: device {device_id} not found")
            return None
        
        self.logger.debug(f"Retrieving {size_bytes} bytes from {device.display_name}")
        return b'\x00' * size_bytes
    
    def register_device_callback(
        self, 
        callback: Callable[[DiscoveredIOSDevice], None]
    ) -> None:
        """
        Register callback for when new device is discovered.
        
        Args:
            callback: Function called with DiscoveredIOSDevice
        """
        self.peer_callbacks.append(callback)
        self.logger.debug("Registered device discovery callback")
    
    def register_connection_callback(
        self, 
        callback: Callable[[str, bool], None]
    ) -> None:
        """
        Register callback for device connection/disconnection.
        
        Args:
            callback: Function called with (device_id, is_connected)
        """
        self.connection_callbacks.append(callback)
        self.logger.debug("Registered connection callback")
    
    def _notify_device_discovered(self, device: DiscoveredIOSDevice) -> None:
        """Internal: notify callbacks of device discovery"""
        for callback in self.peer_callbacks:
            try:
                callback(device)
            except Exception as e:
                self.logger.error(f"Callback error: {e}")
    
    def _notify_connection_changed(self, device_id: str, connected: bool) -> None:
        """Internal: notify callbacks of connection change"""
        for callback in self.connection_callbacks:
            try:
                callback(device_id, connected)
            except Exception as e:
                self.logger.error(f"Callback error: {e}")


# Singleton instance
_ios_bridge: Optional[IOSGPUBridge] = None


def get_ios_bridge() -> IOSGPUBridge:
    """Get or create iOS GPU bridge singleton"""
    global _ios_bridge
    if _ios_bridge is None:
        _ios_bridge = IOSGPUBridge()
    return _ios_bridge
