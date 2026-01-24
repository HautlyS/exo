"""GPU Inference Engine - Base class for GPU-based inference.

Integrates GPU backend abstraction with exo's worker task execution model.
Handles tensor lifecycle: allocate → copy_to_device → inference → copy_from_device → deallocate.

This engine serves as the foundation for distributed GPU inference across heterogeneous devices.
"""

import logging
from abc import ABC, abstractmethod
from typing import Any, AsyncIterator, Optional

from exo.gpu.backend import GPUBackend, GPUDevice, MemoryHandle
from exo.gpu.factory import GPUBackendFactory
from exo.shared.types.tasks import Task

logger = logging.getLogger(__name__)


class GPUInferenceEngine(ABC):
    """Base class for GPU-based inference engines.
    
    This engine abstracts GPU operations and integrates with exo's Worker task model.
    Subclasses should implement specific frameworks (TensorRT, vLLM, etc.).
    
    Design Principles:
    1. All GPU operations are async, non-blocking
    2. Tensor lifecycle is explicit and observable
    3. OOM errors trigger graceful fallback or layer offloading
    4. Events integrate with Worker's event-sourcing model
    """

    def __init__(
        self,
        backend: GPUBackend,
        device_id: str,
        model_path: str,
        enable_p2p: bool = True,
    ):
        """Initialize GPU inference engine.
        
        Args:
            backend: GPU backend (CUDA, ROCm, Metal, DirectML, etc.)
            device_id: Device identifier (e.g., 'cuda:0', 'rocm:1')
            model_path: Path to model weights
            enable_p2p: Enable device-to-device communication for multi-GPU
        """
        self.backend = backend
        self.device_id = device_id
        self.model_path = model_path
        self.enable_p2p = enable_p2p

        self._initialized = False
        self._device: Optional[GPUDevice] = None
        self._model_handle: Optional[MemoryHandle] = None
        self._kv_cache_handles: dict[int, MemoryHandle] = {}  # layer_idx -> handle
        self._temporary_buffers: dict[str, MemoryHandle] = {}  # buffer_name -> handle

    async def initialize(self) -> None:
        """Initialize the inference engine.
        
        - Validate device availability
        - Load model weights onto GPU
        - Pre-allocate KV cache and temporary buffers
        
        Raises:
            RuntimeError: If device unavailable or model loading fails
        """
        try:
            # Get device info
            self._device = self.backend.get_device(self.device_id)
            logger.info(
                f"GPU Engine initializing on {self._device.name} "
                f"({self._device.memory_bytes // (1024**3)}GB)"
            )

            # Load model weights
            model_size = await self._estimate_model_size()
            if model_size > self._device.memory_available:
                raise RuntimeError(
                    f"Model size ({model_size} bytes) exceeds available device memory "
                    f"({self._device.memory_available} bytes). Requires offloading."
                )

            self._model_handle = await self.backend.allocate(
                self.device_id, model_size
            )
            logger.debug(f"Allocated {model_size} bytes for model on {self.device_id}")

            # Load model data to device
            model_data = await self._load_model_data()
            await self.backend.copy_to_device(model_data, self._model_handle)
            logger.info(f"Model loaded to {self.device_id}")

            # Pre-allocate KV cache for common sequence lengths
            await self._allocate_kv_cache()

            self._initialized = True
            await self.backend.synchronize(self.device_id)
            logger.info(f"GPU Engine initialized successfully on {self.device_id}")

        except Exception as e:
            logger.error(f"GPU Engine initialization failed: {e}")
            await self.shutdown()
            raise RuntimeError(f"GPU Engine initialization failed: {e}") from e

    async def shutdown(self) -> None:
        """Clean up GPU resources.
        
        - Deallocate model weights
        - Clear KV cache
        - Free temporary buffers
        """
        try:
            if self._model_handle:
                await self.backend.deallocate(self._model_handle)
                self._model_handle = None

            for layer_idx, handle in self._kv_cache_handles.items():
                try:
                    await self.backend.deallocate(handle)
                except Exception as e:
                    logger.warning(f"Failed to deallocate KV cache for layer {layer_idx}: {e}")
            self._kv_cache_handles.clear()

            for buf_name, handle in self._temporary_buffers.items():
                try:
                    await self.backend.deallocate(handle)
                except Exception as e:
                    logger.warning(f"Failed to deallocate temporary buffer {buf_name}: {e}")
            self._temporary_buffers.clear()

            self._initialized = False
            logger.info(f"GPU Engine shutdown complete on {self.device_id}")

        except Exception as e:
            logger.error(f"Error during GPU Engine shutdown: {e}")

    async def run_inference(
        self,
        task: Task,
        input_tensors: dict[str, bytes],
        sequence_length: int,
    ) -> AsyncIterator[dict[str, bytes]]:
        """Run inference on the GPU.
        
        Yields results incrementally (for streaming inference).
        
        Args:
            task: Task specification
            input_tensors: Input data (host memory)
            sequence_length: Expected sequence length
            
        Yields:
            Output tensors (host memory)
            
        Raises:
            RuntimeError: If inference fails (OOM, kernel timeout, etc.)
        """
        if not self._initialized:
            raise RuntimeError("GPU Engine not initialized")

        try:
            # Allocate I/O buffers on device
            input_handles = await self._allocate_inputs(input_tensors)
            output_handles = await self._allocate_outputs(sequence_length)

            try:
                # Copy inputs to device
                for name, handle in input_handles.items():
                    await self.backend.copy_to_device(input_tensors[name], handle)

                # Run inference (streaming)
                async for output_data in self._infer_streaming(
                    task, input_handles, output_handles, sequence_length
                ):
                    # Copy outputs back to host
                    host_output = {}
                    for name, handle in output_handles.items():
                        host_output[name] = await self.backend.copy_from_device(
                            handle, 0, handle.size_bytes
                        )
                    yield host_output

            finally:
                # Clean up I/O buffers
                for handle in input_handles.values():
                    await self.backend.deallocate(handle)
                for handle in output_handles.values():
                    await self.backend.deallocate(handle)

        except Exception as e:
            logger.error(f"Inference failed on {self.device_id}: {e}")
            raise RuntimeError(f"Inference failed: {e}") from e

    async def copy_shard_from_peer(
        self,
        peer_device_id: str,
        peer_backend: GPUBackend,
        layer_indices: list[int],
    ) -> None:
        """Copy model shard from peer device (P2P transfer).
        
        Used in multi-device tensor-parallel setup.
        
        Args:
            peer_device_id: Peer device identifier
            peer_backend: Peer's GPU backend
            layer_indices: Which model layers to copy
            
        Raises:
            RuntimeError: If P2P not supported or transfer fails
        """
        if not self.enable_p2p:
            raise RuntimeError("P2P transfer disabled")

        try:
            logger.info(
                f"Copying layers {layer_indices} from {peer_device_id} to {self.device_id}"
            )

            # Device-to-device copy (backend handles P2P negotiation)
            for layer_idx in layer_indices:
                peer_handle = await peer_backend.allocate(
                    peer_device_id, self._estimate_layer_size(layer_idx)
                )
                dst_handle = await self.backend.allocate(
                    self.device_id, self._estimate_layer_size(layer_idx)
                )

                # P2P copy
                await self.backend.copy_device_to_device(
                    peer_handle, dst_handle, dst_handle.size_bytes
                )

                # Cache local handle
                self._kv_cache_handles[layer_idx] = dst_handle

            await self.backend.synchronize(self.device_id)
            logger.info(f"P2P transfer complete: layers {layer_indices}")

        except Exception as e:
            logger.error(f"P2P transfer failed: {e}")
            raise RuntimeError(f"P2P transfer failed: {e}") from e

    async def handle_oom(self, offload_strategy: str = "lru") -> None:
        """Handle out-of-memory condition.
        
        Strategies:
        - 'lru': Offload least-recently-used layers to host memory
        - 'quantize': Reduce precision of weights
        - 'fallback': Switch to CPU inference
        
        Args:
            offload_strategy: Which strategy to use
        """
        logger.warning(f"OOM on {self.device_id}, attempting recovery with {offload_strategy}")

        try:
            if offload_strategy == "lru":
                # Offload oldest KV cache entries
                if self._kv_cache_handles:
                    oldest_layer = min(self._kv_cache_handles.keys())
                    handle = self._kv_cache_handles.pop(oldest_layer)
                    await self.backend.deallocate(handle)
                    logger.info(f"Offloaded KV cache for layer {oldest_layer}")

            elif offload_strategy == "quantize":
                logger.warning("Quantization fallback not yet implemented")

            elif offload_strategy == "fallback":
                logger.warning("Falling back to CPU inference")
                await self.shutdown()
                raise RuntimeError("OOM - switching to CPU fallback")

        except Exception as e:
            logger.error(f"OOM recovery failed: {e}")
            raise RuntimeError(f"OOM recovery failed: {e}") from e

    # ===== Abstract Methods (Subclass Implementation) =====

    @abstractmethod
    async def _estimate_model_size(self) -> int:
        """Estimate total model size in bytes (including weights, buffers)."""
        pass

    @abstractmethod
    async def _load_model_data(self) -> bytes:
        """Load model weights from disk."""
        pass

    @abstractmethod
    async def _allocate_kv_cache(self) -> None:
        """Pre-allocate KV cache for inference."""
        pass

    @abstractmethod
    async def _allocate_inputs(self, input_tensors: dict[str, bytes]) -> dict[str, MemoryHandle]:
        """Allocate device memory for input tensors."""
        pass

    @abstractmethod
    async def _allocate_outputs(self, sequence_length: int) -> dict[str, MemoryHandle]:
        """Allocate device memory for output tensors."""
        pass

    @abstractmethod
    async def _infer_streaming(
        self,
        task: Task,
        input_handles: dict[str, MemoryHandle],
        output_handles: dict[str, MemoryHandle],
        sequence_length: int,
    ) -> AsyncIterator[bytes]:
        """Run actual inference (streaming, yields tokens/batches)."""
        pass

    @abstractmethod
    def _estimate_layer_size(self, layer_idx: int) -> int:
        """Estimate size of a single model layer in bytes."""
        pass


class GPUEngineFactory:
    """Factory for creating GPU inference engines."""

    @staticmethod
    async def create_engine(
        device_id: str,
        model_path: str,
        engine_type: str = "auto",
        enable_p2p: bool = True,
    ) -> GPUInferenceEngine:
        """Create a GPU inference engine.
        
        Args:
            device_id: Device identifier
            model_path: Path to model weights
            engine_type: Engine implementation ('auto', 'tensorrt', 'vllm', 'custom')
            enable_p2p: Enable device-to-device communication
            
        Returns:
            Initialized GPU inference engine
            
        Raises:
            RuntimeError: If engine creation or initialization fails
        """
        try:
            # Create GPU backend
            backend = await GPUBackendFactory.create_backend()

            # Select engine implementation
            if engine_type == "auto":
                engine = await _create_auto_engine(backend, device_id, model_path, enable_p2p)
            else:
                raise ValueError(f"Unknown engine type: {engine_type}")

            # Initialize engine
            await engine.initialize()
            return engine

        except Exception as e:
            logger.error(f"Failed to create GPU engine: {e}")
            raise RuntimeError(f"GPU engine creation failed: {e}") from e


async def _create_auto_engine(
    backend: GPUBackend,
    device_id: str,
    model_path: str,
    enable_p2p: bool,
) -> GPUInferenceEngine:
    """Create engine automatically based on device type."""
    device = backend.get_device(device_id)

    # For now, use a simple placeholder engine
    # Actual implementations would be framework-specific (TensorRT, vLLM, etc.)
    class SimpleGPUEngine(GPUInferenceEngine):
        async def _estimate_model_size(self) -> int:
            return 4 * 1024 * 1024  # 4MB placeholder

        async def _load_model_data(self) -> bytes:
            return b"\x00" * (4 * 1024 * 1024)

        async def _allocate_kv_cache(self) -> None:
            pass

        async def _allocate_inputs(self, input_tensors: dict[str, bytes]) -> dict[str, MemoryHandle]:
            handles = {}
            for name, data in input_tensors.items():
                handle = await self.backend.allocate(self.device_id, len(data))
                handles[name] = handle
            return handles

        async def _allocate_outputs(self, sequence_length: int) -> dict[str, MemoryHandle]:
            # Allocate output buffer
            handle = await self.backend.allocate(self.device_id, sequence_length * 1024)
            return {"output": handle}

        async def _infer_streaming(
            self,
            task: Task,
            input_handles: dict[str, MemoryHandle],
            output_handles: dict[str, MemoryHandle],
            sequence_length: int,
        ):
            yield b"placeholder_inference_output"

        def _estimate_layer_size(self, layer_idx: int) -> int:
            return 1024 * 1024

    return SimpleGPUEngine(backend, device_id, model_path, enable_p2p)
