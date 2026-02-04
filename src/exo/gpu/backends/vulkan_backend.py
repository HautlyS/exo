"""Vulkan GPU backend for Android and cross-platform GPU compute.

This module provides a Vulkan-based GPU backend implementation for non-Apple platforms,
particularly Android. It wraps the Rust Vulkan FFI bindings and implements the GPUBackend interface.
"""

import asyncio
import logging
from typing import Optional
from dataclasses import dataclass, field
from datetime import datetime, timezone

from exo.gpu.backend import GPUBackend, GPUDevice, MemoryHandle

logger = logging.getLogger(__name__)


@dataclass
class VulkanDevice(GPUDevice):
    """Vulkan-specific GPU device information."""
    backend_name: str = "vulkan"
    support_level: str = "experimental"  # Vulkan support is experimental
    max_threads_per_block: int = 256
    tensor_core_count: int = 0  # Vulkan doesn't expose tensor cores


class VulkanGPUBackend(GPUBackend):
    """Vulkan-based GPU backend for Android and other non-Apple platforms.
    
    Provides GPU acceleration via Vulkan compute shaders on Android devices
    (Qualcomm Adreno, ARM Mali, etc.) and other platforms with Vulkan support.
    """

    def __init__(self) -> None:
        """Initialize Vulkan backend."""
        self._devices: dict[str, VulkanDevice] = {}
        self._memory_allocations: dict[str, tuple[str, int]] = {}  # handle_id -> (device_id, size)
        self._initialized = False
        self._context: Optional[object] = None

    async def initialize(self) -> None:
        """Initialize Vulkan context and enumerate devices.
        
        This method:
        1. Initializes the Vulkan context
        2. Enumerates available GPU devices
        3. Creates GPUDevice objects for each device
        4. Stores devices for later use
        
        Raises:
            RuntimeError: If Vulkan initialization fails
        """
        if self._initialized:
            logger.warning("Vulkan backend already initialized, skipping re-initialization")
            return

        try:
            # Import Vulkan FFI bindings built by cargo
            try:
                # TODO: This should be imported from exo_pyo3_bindings once integrated
                # from exo_pyo3_bindings import VulkanContext, enumerate_vulkan_devices
                # For now, we'll stub it out for testing
                devices_info = await asyncio.to_thread(self._stub_enumerate_vulkan_devices)
            except ImportError:
                logger.warning("Vulkan FFI not available, using stub device")
                devices_info = await asyncio.to_thread(self._stub_enumerate_vulkan_devices)

            # Create GPUDevice objects for each discovered device
            for i, dev_info in enumerate(devices_info):
                device_id = f"vulkan:{i}"
                device = VulkanDevice(
                    device_id=device_id,
                    device_name=dev_info.get("name", f"Vulkan Device {i}"),
                    vendor=dev_info.get("vendor", "unknown"),
                    backend="vulkan",
                    compute_capability=dev_info.get("compute_capability", "1.1"),
                    memory_bytes=dev_info.get("total_memory_bytes", 1024 * 1024 * 1024),
                    memory_available=dev_info.get("available_memory_bytes", 1024 * 1024 * 1024),
                    compute_units=dev_info.get("compute_units", 16),
                    tensor_core_count=0,
                    max_threads_per_block=256,
                    clock_rate_mhz=dev_info.get("clock_rate_mhz", 0),
                    bandwidth_gbps=dev_info.get("bandwidth_gbps", 32.0),
                    support_level="experimental",
                    driver_version=dev_info.get("driver_version", "unknown"),
                    backend_name="vulkan",
                )
                self._devices[device_id] = device
                logger.info(f"Detected Vulkan device: {device.device_name} ({device_id})")

            self._initialized = True
            logger.info(f"Vulkan backend initialized with {len(self._devices)} device(s)")

        except Exception as e:
            logger.error(f"Failed to initialize Vulkan: {e}")
            raise RuntimeError(f"Vulkan initialization failed: {e}") from e

    async def shutdown(self) -> None:
        """Cleanup Vulkan resources."""
        self._devices.clear()
        self._memory_allocations.clear()
        self._initialized = False
        self._context = None
        logger.info("Vulkan backend shutdown complete")

    def list_devices(self) -> list[GPUDevice]:
        """Return list of available Vulkan devices."""
        return list(self._devices.values())

    def get_device(self, device_id: str) -> Optional[GPUDevice]:
        """Get device by ID."""
        return self._devices.get(device_id)

    async def allocate(self, device_id: str, size_bytes: int) -> MemoryHandle:
        """Allocate device memory on the specified device.
        
        Args:
            device_id: Device to allocate on
            size_bytes: Number of bytes to allocate
            
        Returns:
            MemoryHandle: Handle to allocated memory
            
        Raises:
            RuntimeError: If backend not initialized or device not found
        """
        if not self._initialized:
            raise RuntimeError("Vulkan backend not initialized")

        device = self.get_device(device_id)
        if device is None:
            raise RuntimeError(f"Device {device_id} not found")

        # TODO: Call actual Vulkan allocation via FFI
        handle_id = f"vulkan-mem-{len(self._memory_allocations)}"
        self._memory_allocations[handle_id] = (device_id, size_bytes)

        return MemoryHandle(
            handle_id=handle_id,
            size_bytes=size_bytes,
            device_id=device_id,
            allocated_at=datetime.now(timezone.utc).timestamp(),
        )

    async def deallocate(self, handle: MemoryHandle) -> None:
        """Free device memory.
        
        Args:
            handle: Memory handle to free
        """
        # TODO: Call actual Vulkan deallocation via FFI
        if handle.handle_id in self._memory_allocations:
            del self._memory_allocations[handle.handle_id]
            logger.debug(f"Deallocated Vulkan memory: {handle.handle_id}")

    async def copy_to_device(
        self, device_id: str, host_data: bytes, device_handle: MemoryHandle
    ) -> None:
        """Copy data from host to device.
        
        Args:
            device_id: Target device ID
            host_data: Data to copy
            device_handle: Destination memory handle
            
        Raises:
            ValueError: If data exceeds device memory size
            RuntimeError: If copy fails
        """
        if len(host_data) > device_handle.size_bytes:
            raise ValueError(
                f"Data size {len(host_data)} exceeds device memory {device_handle.size_bytes}"
            )

        # TODO: Call actual Vulkan copy via FFI
        logger.debug(
            f"Copy to device {device_id}: {len(host_data)} bytes to {device_handle.handle_id}"
        )

    async def copy_from_device(self, device_id: str, device_handle: MemoryHandle) -> bytes:
        """Copy data from device to host.
        
        Args:
            device_id: Source device ID
            device_handle: Source memory handle
            
        Returns:
            Copied data as bytes
        """
        # TODO: Call actual Vulkan copy via FFI
        logger.debug(
            f"Copy from device {device_id}: {device_handle.size_bytes} bytes from {device_handle.handle_id}"
        )
        
        # Stub: return empty bytes for now
        return b"\x00" * device_handle.size_bytes

    async def get_device_memory_info(self, device_id: str) -> tuple[int, int]:
        """Get device memory info.
        
        Args:
            device_id: Device to query
            
        Returns:
            Tuple of (total_memory_bytes, available_memory_bytes)
            
        Raises:
            RuntimeError: If device not found
        """
        device = self.get_device(device_id)
        if device is None:
            raise RuntimeError(f"Device {device_id} not found")

        # TODO: Query actual device memory via FFI
        return (device.memory_bytes, device.memory_available)

    async def synchronize(self, device_id: str) -> None:
        """Synchronize with device (wait for outstanding operations).
        
        Args:
            device_id: Device to synchronize with
        """
        # TODO: Call actual Vulkan synchronization via FFI
        logger.debug(f"Synchronize with device {device_id}")

    async def get_device_properties(self, device_id: str) -> dict:
        """Get detailed device properties.
        
        Args:
            device_id: Device to query
            
        Returns:
            Dictionary of device properties
        """
        device = self.get_device(device_id)
        if device is None:
            raise RuntimeError(f"Device {device_id} not found")

        return {
            "device_id": device.device_id,
            "device_name": device.device_name,
            "vendor": device.vendor,
            "backend": device.backend,
            "compute_capability": device.compute_capability,
            "memory_bytes": device.memory_bytes,
            "compute_units": device.compute_units,
            "bandwidth_gbps": device.bandwidth_gbps,
            "driver_version": device.driver_version,
        }

    # ========== Stub methods for testing ==========

    @staticmethod
    def _stub_enumerate_vulkan_devices() -> list[dict]:
        """Stub Vulkan device enumeration for testing.
        
        Returns mock device information.
        """
        return [
            {
                "device_id": "vulkan:0",
                "name": "Stub Vulkan Device",
                "vendor": "unknown",
                "driver_version": "1.0.0",
                "compute_units": 16,
                "total_memory_bytes": 2 * 1024 * 1024 * 1024,  # 2GB
                "available_memory_bytes": 2 * 1024 * 1024 * 1024,
                "bandwidth_gbps": 32.0,
                "compute_capability": "1.1",
            }
        ]
