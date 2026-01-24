"""AMD ROCm backend implementation via CuPy HIP interface.

Uses CuPy with HIP support for AMD GPUs. CuPy transparently handles HIP backend.
Implementation mirrors CUDA pattern but identifies AMD architecture families (RDNA, CDNA).
"""

import logging
from typing import Optional

try:
    import cupy as cp
except ImportError:
    cp = None

from exo.gpu.backend import GPUBackend, GPUDevice, MemoryHandle

logger = logging.getLogger(__name__)


class ROCmBackend(GPUBackend):
    """AMD ROCm backend using CuPy HIP interface."""

    def __init__(self):
        if cp is None:
            raise ImportError(
                "CuPy not installed for ROCm support. Install with: pip install cupy-rocm5x"
            )
        self._initialized = False
        self._devices = []
        self._device_count = 0
        self._memory_handles: dict[str, tuple] = {}

    async def initialize(self) -> None:
        """Initialize ROCm backend via CuPy HIP interface."""
        try:
            # Detect ROCm/HIP devices via CuPy
            self._device_count = cp.cuda.runtime.getDeviceCount()
            logger.info(f"Detected {self._device_count} ROCm devices")

            if self._device_count == 0:
                raise RuntimeError("No ROCm devices detected")

            for i in range(self._device_count):
                try:
                    device = self._create_device_info(i)
                    self._devices.append(device)
                    logger.info(f"Registered device {device.device_id}: {device.name}")
                except Exception as e:
                    logger.warning(f"Failed to register ROCm device {i}: {e}")

            if not self._devices:
                raise RuntimeError("No ROCm devices could be registered")

            self._initialized = True

        except Exception as e:
            logger.error(f"ROCm initialization failed: {e}")
            raise RuntimeError(f"ROCm initialization failed: {e}") from e

    def _create_device_info(self, device_index: int) -> GPUDevice:
        """Create GPUDevice metadata for a ROCm device."""
        with cp.cuda.Device(device_index):
            device = cp.cuda.Device(device_index)
            props = device.attributes

            # Extract properties
            try:
                name = str(props.get("deviceName", f"ROCm Device {device_index}"))
            except (AttributeError, KeyError):
                name = f"ROCm Device {device_index}"

            # For ROCm, compute capability maps to RDNA/CDNA architecture
            compute_major = int(props.get("computeCapabilityMajor", 9))
            compute_minor = int(props.get("computeCapabilityMinor", 0))
            compute_capability = self._map_rocm_architecture(compute_major, compute_minor)

            memory_bytes = int(props.get("totalGlobalMem", 4 * 1024 * 1024 * 1024))
            compute_units = int(props.get("multiProcessorCount", 1))
            max_threads = int(props.get("maxThreadsPerBlock", 1024))
            clock_rate_khz = int(props.get("clockRate", 1000000))
            clock_rate_mhz = clock_rate_khz // 1000

            try:
                driver_version = str(cp.cuda.runtime.getDriverVersion())
            except Exception:
                driver_version = "unknown"

            # Estimate bandwidth based on RDNA/CDNA family
            bandwidth_gbps = self._estimate_rocm_bandwidth(compute_major, compute_minor)

            return GPUDevice(
                device_id=f"rocm:{device_index}",
                name=name,
                vendor="amd",
                backend="rocm",
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
                backend_name="rocm",
            )

    @staticmethod
    def _map_rocm_architecture(major: int, minor: int) -> str:
        """Map ROCm compute capability to architecture family."""
        rocm_arch_map = {
            (9, 0): "RDNA3",
            (10, 0): "RDNA4",  # Future
            (8, 0): "RDNA2",
            (7, 0): "CDNA2",
            (6, 0): "CDNA",
        }
        return rocm_arch_map.get((major, minor), f"RDNA{major}")

    @staticmethod
    def _estimate_rocm_bandwidth(major: int, minor: int) -> float:
        """Estimate ROCm memory bandwidth based on architecture."""
        bandwidth_map = {
            (6, 0): 576.0,  # CDNA
            (7, 0): 768.0,  # CDNA2
            (8, 0): 576.0,  # RDNA2
            (9, 0): 576.0,  # RDNA3
            (10, 0): 864.0,  # RDNA4 (estimated)
        }
        return bandwidth_map.get((major, minor), 500.0)

    async def shutdown(self) -> None:
        """Cleanup ROCm resources."""
        self._devices.clear()
        self._memory_handles.clear()
        self._initialized = False
        logger.info("ROCm backend shutdown")

    def list_devices(self):
        """Return list of ROCm devices."""
        return self._devices

    def get_device(self, device_id: str) -> Optional[GPUDevice]:
        """Get ROCm device by ID."""
        for device in self._devices:
            if device.device_id == device_id:
                return device
        return None

    async def allocate(self, device_id: str, size_bytes: int) -> MemoryHandle:
        """Allocate ROCm device memory."""
        try:
            device_idx = int(device_id.split(":")[1])
            with cp.cuda.Device(device_idx):
                ptr = cp.cuda.memory.alloc(size_bytes)
                handle = MemoryHandle(device_id=device_id, size_bytes=size_bytes)
                self._memory_handles[handle.handle_id] = (ptr, device_idx)
                logger.debug(f"Allocated {size_bytes} bytes on {device_id}")
                return handle
        except Exception as e:
            logger.error(f"ROCm allocation failed: {e}")
            raise RuntimeError(f"ROCm allocation failed: {e}") from e

    async def deallocate(self, handle: MemoryHandle) -> None:
        """Free ROCm device memory."""
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
            logger.error(f"ROCm deallocation failed: {e}")
            raise RuntimeError(f"ROCm deallocation failed: {e}") from e

    async def copy_to_device(
        self,
        src: bytes,
        dst_handle: MemoryHandle,
        offset_bytes: int = 0,
    ) -> None:
        """Copy host memory to ROCm device."""
        try:
            if dst_handle.handle_id not in self._memory_handles:
                raise RuntimeError(f"Invalid memory handle: {dst_handle.handle_id}")

            ptr, device_idx = self._memory_handles[dst_handle.handle_id]
            with cp.cuda.Device(device_idx):
                src_array = cp.asarray(src, dtype=cp.uint8)
                dst_ptr = ptr.as_raw_data()[0]
                cp.cuda.memory.memcpy_dtod(
                    dst_ptr + offset_bytes,
                    src_array.data.ptr,
                    len(src)
                )
            logger.debug(f"Copied {len(src)} bytes to {dst_handle.device_id} (offset {offset_bytes})")
        except Exception as e:
            logger.error(f"ROCm copy_to_device failed: {e}")
            raise RuntimeError(f"ROCm copy_to_device failed: {e}") from e

    async def copy_from_device(
        self,
        src_handle: MemoryHandle,
        offset_bytes: int,
        size_bytes: int,
    ) -> bytes:
        """Copy ROCm device memory to host."""
        try:
            if src_handle.handle_id not in self._memory_handles:
                raise RuntimeError(f"Invalid memory handle: {src_handle.handle_id}")

            ptr, device_idx = self._memory_handles[src_handle.handle_id]
            with cp.cuda.Device(device_idx):
                dst_array = cp.asnumpy(cp.cuda.asarray(
                    cp.cuda.memory.MemoryPointer(ptr, offset_bytes),
                    dtype=cp.uint8
                ))[:size_bytes]
            logger.debug(f"Copied {size_bytes} bytes from {src_handle.device_id} (offset {offset_bytes})")
            return bytes(dst_array)
        except Exception as e:
            logger.error(f"ROCm copy_from_device failed: {e}")
            raise RuntimeError(f"ROCm copy_from_device failed: {e}") from e

    async def copy_device_to_device(
        self,
        src_handle: MemoryHandle,
        dst_handle: MemoryHandle,
        size_bytes: int,
    ) -> None:
        """Copy between ROCm devices (P2P via HIP)."""
        try:
            if src_handle.handle_id not in self._memory_handles:
                raise RuntimeError(f"Invalid src handle: {src_handle.handle_id}")
            if dst_handle.handle_id not in self._memory_handles:
                raise RuntimeError(f"Invalid dst handle: {dst_handle.handle_id}")

            src_ptr, src_idx = self._memory_handles[src_handle.handle_id]
            dst_ptr, dst_idx = self._memory_handles[dst_handle.handle_id]

            # Enable P2P access if different devices
            if src_idx != dst_idx:
                try:
                    cp.cuda.Device(src_idx).enable_peer_access(cp.cuda.Device(dst_idx))
                except (Exception,):
                    logger.debug(f"P2P access from rocm:{src_idx} to rocm:{dst_idx} not available")

            with cp.cuda.Device(src_idx):
                cp.cuda.memory.memcpy_dtod(
                    dst_ptr.as_raw_data()[0],
                    src_ptr.as_raw_data()[0],
                    size_bytes
                )

            logger.debug(f"Copied {size_bytes} bytes from {src_handle.device_id} to {dst_handle.device_id}")
        except Exception as e:
            logger.error(f"ROCm P2P copy failed: {e}")
            raise RuntimeError(f"ROCm P2P copy failed: {e}") from e

    async def synchronize(self, device_id: str) -> None:
        """Synchronize ROCm device."""
        try:
            device_idx = int(device_id.split(":")[1])
            with cp.cuda.Device(device_idx):
                cp.cuda.Stream.null.synchronize()
                logger.debug(f"Synchronized {device_id}")
        except Exception as e:
            logger.error(f"ROCm synchronize failed: {e}")
            raise RuntimeError(f"ROCm synchronize failed: {e}") from e

    async def get_device_memory_info(self, device_id: str) -> dict:
        """Get memory info for ROCm device."""
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
        """Get ROCm device temperature.

        ROCm temperature monitoring varies by implementation.
        Returns None if unavailable.
        """
        try:
            # Try rocm-smi command line tool
            import subprocess
            device_idx = int(device_id.split(":")[1])
            result = subprocess.run(
                ["rocm-smi", "--json"],
                capture_output=True,
                text=True,
                timeout=5
            )
            if result.returncode == 0:
                import json
                data = json.loads(result.stdout)
                if device_idx < len(data):
                    temp_str = data[device_idx].get("gpu_temp", "0")
                    # Parse "XX.X'C" format
                    temp_val = float(temp_str.replace("'C", "").strip())
                    return temp_val
        except (ImportError, subprocess.TimeoutExpired, json.JSONDecodeError, Exception):
            pass
        logger.debug("ROCm temperature unavailable")
        return None

    async def get_device_power_usage(self, device_id: str) -> Optional[float]:
        """Get ROCm device power usage in Watts."""
        try:
            import subprocess
            device_idx = int(device_id.split(":")[1])
            result = subprocess.run(
                ["rocm-smi", "--json"],
                capture_output=True,
                text=True,
                timeout=5
            )
            if result.returncode == 0:
                import json
                data = json.loads(result.stdout)
                if device_idx < len(data):
                    power_str = data[device_idx].get("gpu_power", "0")
                    # Parse "XXW" format
                    power_val = float(power_str.replace("W", "").strip())
                    return power_val
        except (ImportError, subprocess.TimeoutExpired, json.JSONDecodeError, Exception):
            pass
        logger.debug("ROCm power usage unavailable")
        return None

    async def get_device_clock_rate(self, device_id: str) -> Optional[int]:
        """Get ROCm device clock rate in MHz."""
        try:
            device_idx = int(device_id.split(":")[1])
            with cp.cuda.Device(device_idx):
                props = cp.cuda.Device(device_idx).attributes
                clock_khz = int(props.get("clockRate", 0))
                return clock_khz // 1000
        except Exception as e:
            logger.debug(f"Failed to get clock rate: {e}")
            return None
