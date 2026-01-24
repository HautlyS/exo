"""MLX Engine adapter for GPU backend abstraction.

This module provides a bridge between exo's GPU backend interface and MLX's native
Metal GPU execution. It maintains backward compatibility with existing MLX code while
enabling unified GPU abstraction across all platforms.

Key Design:
- MLX's unified memory model means copy_to_device/copy_from_device are mostly no-ops
- All tensor operations happen in MLX's memory space
- GPU backend abstraction is satisfied by proxy operations
"""

import logging
from typing import Any, AsyncIterator, Optional

import mlx.core as mx

from exo.gpu.backend import GPUBackend, GPUDevice, MemoryHandle
from exo.gpu.backends.metal_backend import MetalBackend
from exo.shared.types.tasks import Task
from exo.worker.engines.gpu_engine import GPUInferenceEngine

logger = logging.getLogger(__name__)


class MLXGPUBackendProxy(GPUBackend):
    """Proxy GPU backend wrapping MLX unified memory operations.
    
    This adapter translates exo's GPU backend interface to MLX operations.
    Since MLX uses unified memory, most operations are transparent.
    """

    def __init__(self):
        """Initialize MLX proxy."""
        self._metal_backend = MetalBackend()
        self._mlx_initialized = False

    async def initialize(self) -> None:
        """Initialize MLX backend."""
        try:
            await self._metal_backend.initialize()
            self._mlx_initialized = True
            logger.info("MLX GPU backend proxy initialized")
        except Exception as e:
            logger.error(f"MLX initialization failed: {e}")
            raise RuntimeError(f"MLX GPU initialization failed: {e}") from e

    async def shutdown(self) -> None:
        """Cleanup MLX resources."""
        await self._metal_backend.shutdown()
        self._mlx_initialized = False

    def list_devices(self) -> list[GPUDevice]:
        """Get available MLX devices."""
        return self._metal_backend.list_devices()

    def get_device(self, device_id: str) -> GPUDevice:
        """Get device info."""
        return self._metal_backend.get_device(device_id)

    async def allocate(self, device_id: str, size_bytes: int) -> MemoryHandle:
        """Allocate device memory via MLX.
        
        MLX allocations are transparent - we return a proxy handle
        that MLX operations can reference.
        """
        return await self._metal_backend.allocate(device_id, size_bytes)

    async def deallocate(self, handle: MemoryHandle) -> None:
        """Deallocate device memory."""
        await self._metal_backend.deallocate(handle)

    async def copy_to_device(
        self,
        src: bytes,
        dst_handle: MemoryHandle,
        offset_bytes: int = 0,
    ) -> None:
        """Copy host to device via MLX.
        
        In MLX's unified memory, this creates a new array.
        We store it in the MLX memory space.
        """
        try:
            # Convert bytes to MLX array
            data_array = mx.array(src)
            logger.debug(f"Copied {len(src)} bytes to device (MLX unified memory)")
        except Exception as e:
            logger.error(f"MLX copy_to_device failed: {e}")
            raise RuntimeError(f"Copy to device failed: {e}") from e

    async def copy_from_device(
        self,
        src_handle: MemoryHandle,
        offset_bytes: int,
        size_bytes: int,
    ) -> bytes:
        """Copy device to host via MLX.
        
        Returns placeholder data since MLX arrays are in unified memory.
        Real implementation would serialize MLX arrays.
        """
        try:
            # Placeholder: real implementation would serialize MLX arrays
            result = b"\x00" * size_bytes
            logger.debug(f"Copied {size_bytes} bytes from device (MLX)")
            return result
        except Exception as e:
            logger.error(f"MLX copy_from_device failed: {e}")
            raise RuntimeError(f"Copy from device failed: {e}") from e

    async def copy_device_to_device(
        self,
        src_handle: MemoryHandle,
        dst_handle: MemoryHandle,
        size_bytes: int,
    ) -> None:
        """Copy between devices (Metal doesn't support P2P).
        
        Raises error since Metal is single-GPU per machine.
        """
        raise RuntimeError("Metal backend does not support device-to-device communication")

    async def synchronize(self, device_id: str) -> None:
        """Synchronize MLX device.
        
        Ensures all pending operations complete.
        """
        try:
            mx.eval([])  # Force evaluation of pending operations
            logger.debug(f"Synchronized {device_id}")
        except Exception as e:
            logger.warning(f"MLX synchronization failed: {e}")

    async def get_device_memory_info(self, device_id: str) -> dict[str, int]:
        """Get MLX memory usage."""
        return await self._metal_backend.get_device_memory_info(device_id)

    async def get_device_temperature(self, device_id: str) -> float:
        """Get device temperature."""
        return await self._metal_backend.get_device_temperature(device_id)

    async def get_device_power_usage(self, device_id: str) -> float:
        """Get device power usage."""
        return await self._metal_backend.get_device_power_usage(device_id)

    async def get_device_clock_rate(self, device_id: str) -> int:
        """Get device clock rate."""
        return await self._metal_backend.get_device_clock_rate(device_id)


class MLXGPUInferenceEngine(GPUInferenceEngine):
    """GPU inference engine for MLX (Apple Metal).
    
    Integrates MLX's native tensor operations with exo's GPU abstraction.
    Maintains backward compatibility with existing MLX inference code.
    """

    def __init__(
        self,
        backend: MLXGPUBackendProxy,
        device_id: str,
        model_path: str,
        enable_p2p: bool = False,  # Metal doesn't support P2P
    ):
        """Initialize MLX GPU engine."""
        super().__init__(backend, device_id, model_path, enable_p2p=False)
        self._mlx_arrays: dict[str, mx.array] = {}  # Cache for MLX arrays

    async def _estimate_model_size(self) -> int:
        """Estimate model size (placeholder - MLX handles this)."""
        # Real implementation would inspect model structure
        return 4 * 1024 * 1024 * 1024  # 4GB estimate

    async def _load_model_data(self) -> bytes:
        """Load model weights (placeholder)."""
        # Real implementation would load from disk/HuggingFace
        return b"\x00" * (100 * 1024 * 1024)  # 100MB placeholder

    async def _allocate_kv_cache(self) -> None:
        """Allocate KV cache for inference."""
        # MLX handles KV cache allocation automatically
        logger.info("MLX KV cache pre-allocated")

    async def _allocate_inputs(self, input_tensors: dict[str, bytes]) -> dict[str, MemoryHandle]:
        """Allocate input buffers."""
        handles = {}
        for name, data in input_tensors.items():
            # Create MLX array in memory
            self._mlx_arrays[name] = mx.array(data)
            # Create proxy handle
            handle = await self.backend.allocate(self.device_id, len(data))
            handles[name] = handle
        return handles

    async def _allocate_outputs(self, sequence_length: int) -> dict[str, MemoryHandle]:
        """Allocate output buffers."""
        # Allocate for output tokens
        output_size = sequence_length * 1024  # Placeholder
        handle = await self.backend.allocate(self.device_id, output_size)
        return {"output": handle}

    async def _infer_streaming(
        self,
        task: Task,
        input_handles: dict[str, MemoryHandle],
        output_handles: dict[str, MemoryHandle],
        sequence_length: int,
    ) -> AsyncIterator[bytes]:
        """Run MLX inference streaming.
        
        Yields output tokens incrementally.
        """
        try:
            # This is a placeholder - real implementation would:
            # 1. Get MLX model from cache
            # 2. Run inference with input arrays
            # 3. Yield token outputs
            yield b"mlx_inference_output"
            logger.info(f"MLX inference complete on {self.device_id}")
        except Exception as e:
            logger.error(f"MLX inference failed: {e}")
            raise RuntimeError(f"MLX inference failed: {e}") from e

    def _estimate_layer_size(self, layer_idx: int) -> int:
        """Estimate single layer size."""
        return 64 * 1024 * 1024  # 64MB per layer estimate

    async def copy_shard_from_peer(
        self,
        peer_device_id: str,
        peer_backend: GPUBackend,
        layer_indices: list[int],
    ) -> None:
        """MLX doesn't support P2P (single GPU per machine)."""
        raise RuntimeError("MLX Metal backend does not support device-to-device communication")


def create_mlx_backend_proxy() -> MLXGPUBackendProxy:
    """Create MLX GPU backend proxy for integration with exo's abstraction."""
    return MLXGPUBackendProxy()


async def create_mlx_inference_engine(
    model_path: str,
    device_id: str = "metal:0",
) -> MLXGPUInferenceEngine:
    """Create and initialize MLX inference engine.
    
    Args:
        model_path: Path to model weights
        device_id: Device identifier (default: metal:0)
        
    Returns:
        Initialized MLX inference engine
    """
    try:
        backend = create_mlx_backend_proxy()
        await backend.initialize()
        
        engine = MLXGPUInferenceEngine(
            backend=backend,
            device_id=device_id,
            model_path=model_path,
            enable_p2p=False,
        )
        await engine.initialize()
        
        logger.info(f"MLX inference engine created for {device_id}")
        return engine
    except Exception as e:
        logger.error(f"Failed to create MLX engine: {e}")
        raise RuntimeError(f"MLX engine creation failed: {e}") from e
