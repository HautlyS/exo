"""Vulkan GPU backend for Linux/Android cross-device support.

Uses Vulkan API for platform-independent GPU acceleration.
"""

import logging
from typing import Optional

from exo.gpu.backend import GPUBackend, GPUDevice, MemoryHandle

logger = logging.getLogger(__name__)


class VulkanBackend(GPUBackend):
    """Vulkan GPU backend."""

    def __init__(self):
        raise NotImplementedError("Vulkan backend not yet implemented")
        self._initialized = False
        self._devices = []

    async def initialize(self) -> None:
        """Initialize Vulkan backend."""
        raise NotImplementedError("Vulkan backend - TODO: Future phases")

    async def shutdown(self) -> None:
        """Cleanup Vulkan resources."""
        raise NotImplementedError("Vulkan backend - TODO: Future phases")

    def list_devices(self):
        """Return list of Vulkan devices."""
        raise NotImplementedError("Vulkan backend - TODO: Future phases")

    def get_device(self, device_id: str) -> Optional[GPUDevice]:
        """Get Vulkan device by ID."""
        raise NotImplementedError("Vulkan backend - TODO: Future phases")

    async def allocate(self, device_id: str, size_bytes: int) -> MemoryHandle:
        """Allocate Vulkan device memory."""
        raise NotImplementedError("Vulkan backend - TODO: Future phases")

    async def deallocate(self, handle: MemoryHandle) -> None:
        """Free Vulkan device memory."""
        raise NotImplementedError("Vulkan backend - TODO: Future phases")

    async def copy_to_device(
        self,
        src: bytes,
        dst_handle: MemoryHandle,
        offset_bytes: int = 0,
    ) -> None:
        """Copy to Vulkan device."""
        raise NotImplementedError("Vulkan backend - TODO: Future phases")

    async def copy_from_device(
        self,
        src_handle: MemoryHandle,
        offset_bytes: int,
        size_bytes: int,
    ) -> bytes:
        """Copy from Vulkan device."""
        raise NotImplementedError("Vulkan backend - TODO: Future phases")

    async def copy_device_to_device(
        self,
        src_handle: MemoryHandle,
        dst_handle: MemoryHandle,
        size_bytes: int,
    ) -> None:
        """Copy between Vulkan devices."""
        raise NotImplementedError("Vulkan backend - TODO: Future phases")

    async def synchronize(self, device_id: str) -> None:
        """Synchronize Vulkan device."""
        raise NotImplementedError("Vulkan backend - TODO: Future phases")

    async def get_device_memory_info(self, device_id: str) -> dict:
        """Get memory info for Vulkan device."""
        raise NotImplementedError("Vulkan backend - TODO: Future phases")

    async def get_device_temperature(self, device_id: str) -> Optional[float]:
        """Get Vulkan device temperature."""
        raise NotImplementedError("Vulkan backend - TODO: Future phases")

    async def get_device_power_usage(self, device_id: str) -> Optional[float]:
        """Get Vulkan device power usage."""
        raise NotImplementedError("Vulkan backend - TODO: Future phases")

    async def get_device_clock_rate(self, device_id: str) -> Optional[int]:
        """Get Vulkan device clock rate."""
        raise NotImplementedError("Vulkan backend - TODO: Future phases")
