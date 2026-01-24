"""CPU-only backend for GPU interface - serves as fallback when no GPU available.

This backend uses host memory and simulates GPU operations. Used when:
1. No GPU drivers are installed
2. Explicit CPU backend is requested
3. As fallback when all GPU backends fail
"""

import logging
from typing import Optional

from exo.gpu.backend import GPUBackend, GPUDevice, MemoryHandle

logger = logging.getLogger(__name__)


class CPUBackend(GPUBackend):
    """CPU-only backend using host memory."""

    def __init__(self):
        self._initialized = False
        self._devices = []
        self._allocated_memory = {}

    async def initialize(self) -> None:
        """Initialize CPU backend (always succeeds)."""
        logger.info("Initializing CPU backend (no GPU acceleration)")

        # Create a virtual "CPU device"
        cpu_device = GPUDevice(
            device_id="cpu:0",
            name="CPU Host Memory",
            vendor="system",
            backend="cpu",
            compute_capability="N/A",
            memory_bytes=0,  # Unlimited (use system memory)
            memory_available=0,
            compute_units=1,
            tensor_core_count=0,
            max_threads_per_block=1,
            clock_rate_mhz=0,
            bandwidth_gbps=0.0,
            support_level="full",
            driver_version="N/A",
            backend_name="cpu",
        )

        self._devices = [cpu_device]
        self._initialized = True

    async def shutdown(self) -> None:
        """Cleanup CPU backend."""
        self._allocated_memory.clear()
        self._initialized = False

    def list_devices(self):
        """Return list of CPU devices."""
        return self._devices

    def get_device(self, device_id: str) -> Optional[GPUDevice]:
        """Get CPU device by ID."""
        for device in self._devices:
            if device.device_id == device_id:
                return device
        return None

    async def allocate(self, device_id: str, size_bytes: int) -> MemoryHandle:
        """Allocate host memory."""
        handle = MemoryHandle(device_id=device_id, size_bytes=size_bytes)
        # Store allocated memory buffer
        self._allocated_memory[handle.handle_id] = bytearray(size_bytes)
        logger.debug(f"Allocated {size_bytes} bytes on {device_id}")
        return handle

    async def deallocate(self, handle: MemoryHandle) -> None:
        """Free host memory."""
        if handle.handle_id in self._allocated_memory:
            del self._allocated_memory[handle.handle_id]
            logger.debug(f"Deallocated {handle.size_bytes} bytes")

    async def copy_to_device(
        self,
        src: bytes,
        dst_handle: MemoryHandle,
        offset_bytes: int = 0,
    ) -> None:
        """Copy to host memory."""
        if dst_handle.handle_id not in self._allocated_memory:
            raise RuntimeError(f"Invalid memory handle: {dst_handle.handle_id}")

        buffer = self._allocated_memory[dst_handle.handle_id]
        if offset_bytes + len(src) > len(buffer):
            raise RuntimeError(
                f"Copy would exceed buffer bounds: "
                f"offset={offset_bytes}, src_len={len(src)}, buffer_size={len(buffer)}"
            )

        buffer[offset_bytes : offset_bytes + len(src)] = src

    async def copy_from_device(
        self,
        src_handle: MemoryHandle,
        offset_bytes: int,
        size_bytes: int,
    ) -> bytes:
        """Copy from host memory."""
        if src_handle.handle_id not in self._allocated_memory:
            raise RuntimeError(f"Invalid memory handle: {src_handle.handle_id}")

        buffer = self._allocated_memory[src_handle.handle_id]
        if offset_bytes + size_bytes > len(buffer):
            raise RuntimeError(
                f"Copy would exceed buffer bounds: "
                f"offset={offset_bytes}, size={size_bytes}, buffer_size={len(buffer)}"
            )

        return bytes(buffer[offset_bytes : offset_bytes + size_bytes])

    async def copy_device_to_device(
        self,
        src_handle: MemoryHandle,
        dst_handle: MemoryHandle,
        size_bytes: int,
    ) -> None:
        """Copy between host memory buffers."""
        src_data = await self.copy_from_device(src_handle, 0, size_bytes)
        await self.copy_to_device(src_data, dst_handle)

    async def synchronize(self, device_id: str) -> None:
        """Synchronize CPU device (no-op)."""
        pass

    async def get_device_memory_info(self, device_id: str) -> dict:
        """Get memory info for CPU."""
        import os

        try:
            # Try to get total system memory
            with open("/proc/meminfo", "r") as f:
                meminfo = f.read()
                mem_total = None
                mem_available = None
                for line in meminfo.split("\n"):
                    if line.startswith("MemTotal:"):
                        mem_total = int(line.split()[1]) * 1024
                    elif line.startswith("MemAvailable:"):
                        mem_available = int(line.split()[1]) * 1024

                if mem_total and mem_available:
                    used = mem_total - mem_available
                    return {
                        "total_bytes": mem_total,
                        "used_bytes": used,
                        "available_bytes": mem_available,
                        "reserved_bytes": 0,
                    }
        except (FileNotFoundError, Exception):
            pass

        # Fallback: return 0 (unlimited)
        return {
            "total_bytes": 0,
            "used_bytes": sum(len(b) for b in self._allocated_memory.values()),
            "available_bytes": 0,
            "reserved_bytes": 0,
        }

    async def get_device_temperature(self, device_id: str) -> Optional[float]:
        """CPU has no temperature sensor (return None)."""
        return None

    async def get_device_power_usage(self, device_id: str) -> Optional[float]:
        """CPU has no power sensor (return None)."""
        return None

    async def get_device_clock_rate(self, device_id: str) -> Optional[int]:
        """CPU clock rate not available (return None)."""
        return None
