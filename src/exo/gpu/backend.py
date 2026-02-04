"""GPU backend abstraction layer - platform-agnostic async interface.

CRITICAL DESIGN: All GPU operations are non-blocking, async, and integrate with
Worker's task-based execution model (see src/exo/worker/runner/runner_supervisor.py).

This module defines the interface that all GPU backends (CUDA, ROCm, Metal, DirectML, etc.)
must implement. Operations are event-driven and integrate with exo's event-sourcing model.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field


# ===== Type Definitions =====

class MemoryHandle(BaseModel):
    """Opaque handle representing allocated device memory."""

    model_config = ConfigDict(frozen=True)

    handle_id: str = Field(default_factory=lambda: str(uuid4()))
    device_id: str
    size_bytes: int
    allocated_at: datetime = Field(default_factory=lambda: datetime.now(tz=timezone.utc))


@dataclass(frozen=True)
class GPUDevice:
    """Metadata about a GPU device."""

    device_id: str
    """Unique identifier (e.g., 'cuda:0', 'rocm:1', 'metal:0')"""

    name: str
    """Human-readable name (e.g., 'NVIDIA RTX 4090')"""

    vendor: str
    """GPU vendor ('nvidia', 'amd', 'intel', 'apple', 'qualcomm')"""

    backend: str
    """Backend name ('cuda', 'rocm', 'metal', 'directml', 'vulkan', 'nnapi')"""

    compute_capability: str
    """Compute capability version (e.g., '8.0' for NVIDIA, 'RDNA2' for AMD)"""

    memory_bytes: int
    """Total device memory in bytes"""

    memory_available: int
    """Available device memory in bytes (may differ from total due to reserved space)"""

    compute_units: int
    """Number of compute units (SMs for NVIDIA, CUs for AMD)"""

    tensor_core_count: int
    """Number of tensor cores (0 if not applicable)"""

    max_threads_per_block: int
    """Maximum threads per block/workgroup"""

    clock_rate_mhz: int
    """GPU clock rate in MHz"""

    bandwidth_gbps: float
    """Memory bandwidth in GB/s"""

    support_level: str
    """Support level: 'full', 'partial', or 'experimental'"""

    driver_version: str
    """GPU driver version string"""

    backend_name: str
    """Internal backend name (for backend-specific logic)"""


# ===== GPU Backend Abstract Interface =====

class GPUBackend(ABC):
    """Platform-agnostic GPU operations interface (async, non-blocking).

    All GPU operations are async to integrate with exo's async worker event loop.
    No synchronous kernel execution; instead, operations emit events and integrate
    with the Worker's RunnerSupervisor task model.

    Implementations should:
    1. Handle device initialization gracefully (fail if drivers missing)
    2. Manage device memory safely (no leaks)
    3. Support async memory operations (copy, allocate, deallocate)
    4. Implement proper error handling and recovery
    5. Integrate with exo's logging and observability
    """

    # ===== Device Management =====

    @abstractmethod
    async def initialize(self) -> None:
        """Initialize GPU backend, detect devices, setup resources.

        Must be called before any other operations. Should:
        - Detect available GPU devices
        - Verify driver compatibility
        - Setup device context/memory managers
        - Log initialization status

        Raises:
            RuntimeError: If GPU backend initialization fails (e.g., driver missing)
        """

    @abstractmethod
    async def shutdown(self) -> None:
        """Cleanup GPU resources, release memory, close handles.

        Must be called during Worker shutdown to prevent resource leaks.
        """

    @abstractmethod
    def list_devices(self) -> list[GPUDevice]:
        """Return list of available GPU devices with properties.

        Returns:
            list[GPUDevice]: List of detected GPU devices. Empty list if no GPUs found.
        """

    @abstractmethod
    def get_device(self, device_id: str) -> Optional[GPUDevice]:
        """Return specific device by ID.

        Args:
            device_id: Device identifier (e.g., 'cuda:0', 'rocm:1')

        Returns:
            GPUDevice or None if device not found
        """

    # ===== Memory Management =====

    @abstractmethod
    async def allocate(self, device_id: str, size_bytes: int) -> MemoryHandle:
        """Allocate device memory, return opaque handle.

        Args:
            device_id: Device identifier
            size_bytes: Number of bytes to allocate

        Returns:
            MemoryHandle: Handle to allocated memory

        Raises:
            RuntimeError: If allocation fails (e.g., out of memory, invalid device)
        """

    @abstractmethod
    async def deallocate(self, handle: MemoryHandle) -> None:
        """Free device memory.

        Args:
            handle: MemoryHandle from allocate()

        Raises:
            RuntimeError: If deallocation fails
        """

    @abstractmethod
    async def copy_to_device(
        self,
        src: bytes,
        dst_handle: MemoryHandle,
        offset_bytes: int = 0,
    ) -> None:
        """Copy host memory to device (async, non-blocking).

        Args:
            src: Host memory (bytes)
            dst_handle: Device memory handle from allocate()
            offset_bytes: Offset in device memory (default 0)

        Raises:
            RuntimeError: If copy fails
        """

    @abstractmethod
    async def copy_from_device(
        self,
        src_handle: MemoryHandle,
        offset_bytes: int,
        size_bytes: int,
    ) -> bytes:
        """Copy device memory to host (async, non-blocking).

        Args:
            src_handle: Device memory handle
            offset_bytes: Offset in device memory
            size_bytes: Number of bytes to copy

        Returns:
            bytes: Host memory buffer

        Raises:
            RuntimeError: If copy fails
        """

    @abstractmethod
    async def copy_device_to_device(
        self,
        src_handle: MemoryHandle,
        dst_handle: MemoryHandle,
        size_bytes: int,
    ) -> None:
        """Copy between devices for multi-GPU setups.

        Args:
            src_handle: Source device memory
            dst_handle: Destination device memory
            size_bytes: Number of bytes to copy

        Raises:
            RuntimeError: If copy fails (e.g., P2P not supported)
        """

    # ===== Synchronization =====

    @abstractmethod
    async def synchronize(self, device_id: str) -> None:
        """Wait for all pending GPU operations on device.

        Args:
            device_id: Device identifier

        Raises:
            RuntimeError: If synchronization fails
        """

    # ===== Monitoring (Optional) =====

    @abstractmethod
    async def get_device_memory_info(self, device_id: str) -> dict[str, int]:
        """Get current device memory usage info.

        Args:
            device_id: Device identifier

        Returns:
            dict with keys:
                - total_bytes: Total device memory
                - used_bytes: Currently allocated memory
                - available_bytes: Free memory
                - reserved_bytes: Reserved but unallocated memory

        Raises:
            RuntimeError: If query fails
        """

    @abstractmethod
    async def get_device_temperature(self, device_id: str) -> Optional[float]:
        """Get current device temperature in Celsius.

        Args:
            device_id: Device identifier

        Returns:
            float: Temperature in Celsius, or None if not available

        Raises:
            RuntimeError: If query fails
        """

    @abstractmethod
    async def get_device_power_usage(self, device_id: str) -> Optional[float]:
        """Get current device power usage in Watts.

        Args:
            device_id: Device identifier

        Returns:
            float: Power in Watts, or None if not available

        Raises:
            RuntimeError: If query fails
        """

    @abstractmethod
    async def get_device_clock_rate(self, device_id: str) -> Optional[int]:
        """Get current device clock rate in MHz.

        Args:
            device_id: Device identifier

        Returns:
            int: Clock rate in MHz, or None if not available

        Raises:
            RuntimeError: If query fails
        """
