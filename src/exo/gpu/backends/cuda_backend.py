"""CUDA backend implementation via CuPy.

Uses CuPy (mature, production-tested library) instead of raw CUDA FFI.
Benefits:
- Built-in async support
- Memory management proven
- NumPy-compatible API
- Error handling for driver variations

Implementation time: 3-4 days vs. 12+ for raw FFI.
"""

import logging
from typing import Optional

try:
    import cupy as cp
except ImportError:
    cp = None

from exo.gpu.backend import GPUBackend, GPUDevice, MemoryHandle

logger = logging.getLogger(__name__)


class CUDABackend(GPUBackend):
    """NVIDIA CUDA backend using CuPy."""

    def __init__(self):
        if cp is None:
            raise ImportError(
                "CuPy not installed. Install with: pip install cupy-cuda11x or cupy-cuda12x"
            )
        self._initialized = False
        self._devices: list[GPUDevice] = []
        self._device_count = 0
        self._memory_handles: dict[str, tuple[int, int]] = {}

    async def initialize(self) -> None:
        """Initialize CUDA backend via CuPy."""
        try:
            # Detect CUDA devices
            self._device_count = cp.cuda.runtime.getDeviceCount()
            logger.info(f"Detected {self._device_count} CUDA devices")

            if self._device_count == 0:
                raise RuntimeError("No CUDA devices detected")

            for i in range(self._device_count):
                try:
                    device = self._create_device_info(i)
                    self._devices.append(device)
                    logger.info(f"Registered device {device.device_id}: {device.name}")
                except Exception as e:
                    logger.warning(f"Failed to register CUDA device {i}: {e}")

            if not self._devices:
                raise RuntimeError("No CUDA devices could be registered")

            self._initialized = True

        except Exception as e:
            logger.error(f"CUDA initialization failed: {e}")
            raise RuntimeError(f"CUDA initialization failed: {e}") from e

    def _create_device_info(self, device_index: int) -> GPUDevice:
        """Create GPUDevice metadata for a CUDA device."""
        with cp.cuda.Device(device_index):
            device = cp.cuda.Device(device_index)
            props = device.attributes

            # Extract properties
            try:
                name = str(props.get("deviceName", f"CUDA Device {device_index}"))
            except (AttributeError, KeyError):
                name = f"CUDA Device {device_index}"

            compute_major = int(props.get("computeCapabilityMajor", 7))
            compute_minor = int(props.get("computeCapabilityMinor", 0))
            compute_capability = f"{compute_major}.{compute_minor}"

            memory_bytes = int(props.get("totalGlobalMem", 4 * 1024 * 1024 * 1024))
            compute_units = int(props.get("multiProcessorCount", 1))
            max_threads = int(props.get("maxThreadsPerBlock", 1024))
            clock_rate_khz = int(props.get("clockRate", 1000000))
            clock_rate_mhz = clock_rate_khz // 1000

            try:
                driver_version = str(cp.cuda.runtime.getDriverVersion())
            except Exception:
                driver_version = "unknown"

            # Estimate bandwidth based on compute capability
            bandwidth_gbps = self._estimate_bandwidth(compute_major, compute_minor)

            return GPUDevice(
                device_id=f"cuda:{device_index}",
                name=name,
                vendor="nvidia",
                backend="cuda",
                compute_capability=compute_capability,
                memory_bytes=memory_bytes,
                memory_available=memory_bytes,
                compute_units=compute_units,
                tensor_core_count=0,
                max_threads_per_block=max_threads,
                clock_rate_mhz=clock_rate_mhz,
                bandwidth_gbps=bandwidth_gbps,
                support_level="full",
                driver_version=driver_version,
                backend_name="cuda",
            )

    @staticmethod
    def _estimate_bandwidth(compute_major: int, compute_minor: int) -> float:
        """Estimate GPU memory bandwidth based on compute capability."""
        bandwidth_map = {
            (3, 0): 288.0,  # Kepler
            (3, 5): 288.0,
            (5, 0): 320.0,  # Maxwell
            (5, 2): 320.0,
            (6, 0): 432.0,  # Pascal
            (6, 1): 432.0,
            (7, 0): 432.0,  # Volta
            (7, 5): 576.0,  # Turing
            (8, 0): 936.0,  # Ampere
            (8, 6): 936.0,
            (8, 7): 576.0,
            (8, 9): 960.0,  # Ada
            (9, 0): 960.0,  # Hopper
        }
        return bandwidth_map.get((compute_major, compute_minor), 500.0)

    async def shutdown(self) -> None:
        """Cleanup CUDA resources."""
        # CuPy handles cleanup automatically
        self._devices.clear()
        self._initialized = False
        logger.info("CUDA backend shutdown")

    def list_devices(self):
        """Return list of CUDA devices."""
        return self._devices

    def get_device(self, device_id: str) -> Optional[GPUDevice]:
        """Get CUDA device by ID."""
        for device in self._devices:
            if device.device_id == device_id:
                return device
        return None

    async def allocate(self, device_id: str, size_bytes: int) -> MemoryHandle:
        """Allocate CUDA device memory."""
        try:
            device_idx = int(device_id.split(":")[1])
            with cp.cuda.Device(device_idx):
                ptr = cp.cuda.memory.alloc(size_bytes)
                handle = MemoryHandle(device_id=device_id, size_bytes=size_bytes)
                # Store ptr reference for deallocation
                self._memory_handles[handle.handle_id] = (ptr, device_idx)
                logger.debug(f"Allocated {size_bytes} bytes on {device_id}")
                return handle
        except Exception as e:
            logger.error(f"CUDA allocation failed: {e}")
            raise RuntimeError(f"CUDA allocation failed: {e}") from e

    async def deallocate(self, handle: MemoryHandle) -> None:
        """Free CUDA device memory."""
        try:
            if handle.handle_id not in self._memory_handles:
                logger.warning(f"Handle {handle.handle_id} not found in memory registry")
                return

            ptr, device_idx = self._memory_handles[handle.handle_id]
            with cp.cuda.Device(device_idx):
                ptr.free()
            del self._memory_handles[handle.handle_id]
            logger.debug(f"Deallocated {handle.size_bytes} bytes on {handle.device_id}")
        except Exception as e:
            logger.error(f"CUDA deallocation failed: {e}")
            raise RuntimeError(f"CUDA deallocation failed: {e}") from e

    async def copy_to_device(
        self,
        src: bytes,
        dst_handle: MemoryHandle,
        offset_bytes: int = 0,
    ) -> None:
        """Copy host memory to CUDA device."""
        try:
            if dst_handle.handle_id not in self._memory_handles:
                raise RuntimeError(f"Invalid memory handle: {dst_handle.handle_id}")

            ptr, device_idx = self._memory_handles[dst_handle.handle_id]
            with cp.cuda.Device(device_idx):
                # Create CuPy array from source data
                src_array = cp.asarray(src, dtype=cp.uint8)
                # Copy to device memory
                dst_ptr = ptr.as_raw_data()[0]
                cp.cuda.memory.memcpy_dtod(
                    dst_ptr + offset_bytes,
                    src_array.data.ptr,
                    len(src)
                )
            logger.debug(f"Copied {len(src)} bytes to {dst_handle.device_id} (offset {offset_bytes})")
        except Exception as e:
            logger.error(f"CUDA copy_to_device failed: {e}")
            raise RuntimeError(f"CUDA copy_to_device failed: {e}") from e

    async def copy_from_device(
        self,
        src_handle: MemoryHandle,
        offset_bytes: int,
        size_bytes: int,
    ) -> bytes:
        """Copy CUDA device memory to host."""
        try:
            if src_handle.handle_id not in self._memory_handles:
                raise RuntimeError(f"Invalid memory handle: {src_handle.handle_id}")

            ptr, device_idx = self._memory_handles[src_handle.handle_id]
            with cp.cuda.Device(device_idx):
                # Create destination buffer on host
                dst_array = cp.asnumpy(cp.cuda.asarray(
                    cp.cuda.memory.MemoryPointer(ptr, offset_bytes),
                    dtype=cp.uint8
                ))[:size_bytes]
            logger.debug(f"Copied {size_bytes} bytes from {src_handle.device_id} (offset {offset_bytes})")
            return bytes(dst_array)
        except Exception as e:
            logger.error(f"CUDA copy_from_device failed: {e}")
            raise RuntimeError(f"CUDA copy_from_device failed: {e}") from e

    async def copy_device_to_device(
        self,
        src_handle: MemoryHandle,
        dst_handle: MemoryHandle,
        size_bytes: int,
    ) -> None:
        """Copy between CUDA devices (P2P)."""
        try:
            if src_handle.handle_id not in self._memory_handles:
                raise RuntimeError(f"Invalid src handle: {src_handle.handle_id}")
            if dst_handle.handle_id not in self._memory_handles:
                raise RuntimeError(f"Invalid dst handle: {dst_handle.handle_id}")

            src_ptr, src_idx = self._memory_handles[src_handle.handle_id]
            dst_ptr, dst_idx = self._memory_handles[dst_handle.handle_id]

            # Enable P2P access if needed
            if src_idx != dst_idx:
                try:
                    cp.cuda.Device(src_idx).enable_peer_access(cp.cuda.Device(dst_idx))
                except (cp.cuda.runtime.CUDARuntimeError, Exception):
                    # P2P may not be available
                    logger.debug(f"P2P access from cuda:{src_idx} to cuda:{dst_idx} not available")

            # Perform P2P copy
            with cp.cuda.Device(src_idx):
                cp.cuda.memory.memcpy_dtod(
                    dst_ptr.as_raw_data()[0],
                    src_ptr.as_raw_data()[0],
                    size_bytes
                )

            logger.debug(f"Copied {size_bytes} bytes from {src_handle.device_id} to {dst_handle.device_id}")
        except Exception as e:
            logger.error(f"CUDA P2P copy failed: {e}")
            raise RuntimeError(f"CUDA P2P copy failed: {e}") from e

    async def synchronize(self, device_id: str) -> None:
        """Synchronize CUDA device."""
        try:
            device_idx = int(device_id.split(":")[1])
            with cp.cuda.Device(device_idx):
                cp.cuda.Stream.null.synchronize()
                logger.debug(f"Synchronized {device_id}")
        except Exception as e:
            logger.error(f"CUDA synchronize failed: {e}")
            raise RuntimeError(f"CUDA synchronize failed: {e}") from e

    async def get_device_memory_info(self, device_id: str) -> dict:
        """Get memory info for CUDA device."""
        try:
            device_idx = int(device_id.split(":")[1])
            with cp.cuda.Device(device_idx):
                free_bytes, total_bytes = cp.cuda.memory.get_memory_info()
                return {
                    "total_bytes": total_bytes,
                    "used_bytes": total_bytes - free_bytes,
                    "available_bytes": free_bytes,
                    "reserved_bytes": 0,
                }
        except Exception as e:
            logger.error(f"Failed to get memory info: {e}")
            raise RuntimeError(f"Failed to get memory info: {e}") from e

    async def get_device_temperature(self, device_id: str) -> Optional[float]:
        """Get CUDA device temperature.

        Requires nvidia-ml-py library for actual temperature.
        Returns None if not available.
        """
        try:
            from pynvml import nvmlInit, nvmlDeviceGetHandleByIndex, nvmlDeviceGetTemperature

            nvmlInit()
            device_idx = int(device_id.split(":")[1])
            handle = nvmlDeviceGetHandleByIndex(device_idx)
            temp = nvmlDeviceGetTemperature(handle, 0)  # 0 = GPU temperature
            return float(temp)
        except ImportError:
            logger.debug("nvidia-ml-py not installed, temperature unavailable")
            return None
        except Exception as e:
            logger.debug(f"Failed to get temperature: {e}")
            return None

    async def get_device_power_usage(self, device_id: str) -> Optional[float]:
        """Get CUDA device power usage in Watts.

        Requires nvidia-ml-py library.
        Returns None if not available.
        """
        try:
            from pynvml import nvmlInit, nvmlDeviceGetHandleByIndex, nvmlDeviceGetPowerUsage

            nvmlInit()
            device_idx = int(device_id.split(":")[1])
            handle = nvmlDeviceGetHandleByIndex(device_idx)
            power_mw = nvmlDeviceGetPowerUsage(handle)
            return float(power_mw) / 1000.0
        except ImportError:
            logger.debug("nvidia-ml-py not installed, power usage unavailable")
            return None
        except Exception as e:
            logger.debug(f"Failed to get power usage: {e}")
            return None

    async def get_device_clock_rate(self, device_id: str) -> Optional[int]:
        """Get CUDA device clock rate in MHz."""
        try:
            device_idx = int(device_id.split(":")[1])
            with cp.cuda.Device(device_idx):
                props = cp.cuda.Device(device_idx).attributes
                clock_khz = int(props.get("clockRate", 0))
                return clock_khz // 1000
        except Exception as e:
            logger.debug(f"Failed to get clock rate: {e}")
            return None
