"""GPU Backend Factory - platform detection and backend selection.

Provides intelligent backend selection based on platform, available drivers,
and configuration overrides. Uses priority ordering:
- Linux: CUDA → ROCm → Vulkan (fallback to CPU)
- Windows: DirectML → CUDA → ROCm (fallback to CPU)
- macOS: Metal (via MLX) (fallback to CPU)
- Android: TensorFlow Lite GPU (fallback to CPU)
- iOS: Metal (via MLX) (fallback to CPU)
"""

import logging
import sys
from typing import Optional
from abc import ABC

from exo.gpu.backend import GPUBackend

logger = logging.getLogger(__name__)


class GPUBackendFactory:
    """Factory for creating GPU backend instances based on platform."""

    # Platform priority order for backend selection
    PLATFORM_BACKEND_PRIORITY = {
        "linux": ["cuda", "rocm", "vulkan"],
        "linux2": ["cuda", "rocm", "vulkan"],  # Python 2 legacy
        "win32": ["directml", "cuda", "rocm"],
        "darwin": ["metal"],  # macOS - Metal via MLX
        "android": ["tensorflow_lite_gpu"],
        "ios": ["metal"],
    }

    # Configuration override (set via environment or explicit parameter)
    _override_backend: Optional[str] = None

    @classmethod
    def set_backend_override(cls, backend_name: str) -> None:
        """Set explicit backend override for testing/debugging.

        Args:
            backend_name: Backend name ('cuda', 'rocm', 'metal', 'directml', 'vulkan', 'cpu')
        """
        cls._override_backend = backend_name
        logger.info(f"GPU backend override set to: {backend_name}")

    @classmethod
    def clear_backend_override(cls) -> None:
        """Clear backend override and restore auto-detection."""
        cls._override_backend = None

    @classmethod
    async def create_backend(cls) -> GPUBackend:
        """Create appropriate GPU backend for current platform.

        Returns:
            GPUBackend: Initialized backend instance (CUDA, ROCm, Metal, DirectML, or CPU)

        The selection process:
        1. If override is set, use that backend
        2. Query available backends on platform
        3. Try each backend in priority order until one initializes successfully
        4. Fall back to CPU backend if no GPU backend available

        Raises:
            RuntimeError: If backend creation fails (though CPU fallback should prevent this)
        """
        # Step 1: Check override
        if cls._override_backend:
            return await cls._create_specific_backend(cls._override_backend)

        # Step 2: Determine platform
        platform = sys.platform
        priority_backends = cls.PLATFORM_BACKEND_PRIORITY.get(platform, ["vulkan"])

        logger.info(f"Platform: {platform}, trying backends in order: {priority_backends}")

        # Step 3: Try backends in priority order
        last_error = None
        for backend_name in priority_backends:
            try:
                logger.info(f"Attempting to initialize {backend_name} backend...")
                backend = await cls._create_specific_backend(backend_name)
                logger.info(f"Successfully initialized {backend_name} backend")
                return backend
            except Exception as e:
                logger.debug(f"Failed to initialize {backend_name}: {e}")
                last_error = e
                continue

        # Step 4: Fall back to CPU backend
        logger.warning(
            f"No GPU backends available (last error: {last_error}). "
            "Using CPU backend."
        )
        return await cls._create_specific_backend("cpu")

    @classmethod
    async def _create_specific_backend(cls, backend_name: str) -> GPUBackend:
        """Create specific backend by name.

        Args:
            backend_name: Backend name ('cuda', 'rocm', 'metal', 'directml', 'vulkan', 'cpu')

        Returns:
            GPUBackend: Initialized backend instance

        Raises:
            RuntimeError: If backend is not available or fails to initialize
        """
        backend_name = backend_name.lower().strip()

        if backend_name == "cuda":
            try:
                from exo.gpu.backends.cuda_backend import CUDABackend

                backend = CUDABackend()
                await backend.initialize()
                return backend
            except ImportError as e:
                raise RuntimeError(
                    f"CUDA backend not available: {e}. "
                    "Install cupy-cuda11x or cupy-cuda12x"
                ) from e

        elif backend_name == "rocm":
            try:
                from exo.gpu.backends.rocm_backend import ROCmBackend

                backend = ROCmBackend()
                await backend.initialize()
                return backend
            except ImportError as e:
                raise RuntimeError(
                    f"ROCm backend not available: {e}. "
                    "Install cupy with HIP support"
                ) from e

        elif backend_name == "metal":
            try:
                from exo.gpu.backends.metal_backend import MetalBackend

                backend = MetalBackend()
                await backend.initialize()
                return backend
            except ImportError as e:
                raise RuntimeError(
                    f"Metal backend not available: {e}. "
                    "MLX not installed on macOS"
                ) from e

        elif backend_name == "directml":
            try:
                from exo.gpu.backends.directml_backend import DirectMLBackend

                backend = DirectMLBackend()
                await backend.initialize()
                return backend
            except ImportError as e:
                raise RuntimeError(
                    f"DirectML backend not available: {e}. "
                    "Install onnxruntime-directml"
                ) from e

        elif backend_name == "vulkan":
            try:
                from exo.gpu.backends.vulkan_backend import VulkanBackend

                backend = VulkanBackend()
                await backend.initialize()
                return backend
            except ImportError as e:
                raise RuntimeError(
                    f"Vulkan backend not available: {e}. "
                    "Install vulkan support"
                ) from e

        elif backend_name == "tensorflow_lite_gpu":
            try:
                from exo.gpu.backends.tflite_gpu_backend import TFLiteGPUBackend

                backend = TFLiteGPUBackend()
                await backend.initialize()
                return backend
            except ImportError as e:
                raise RuntimeError(
                    f"TensorFlow Lite GPU backend not available: {e}. "
                    "Install tensorflow"
                ) from e

        elif backend_name == "cpu":
            # CPU backend - always available
            from exo.gpu.backends.cpu_backend import CPUBackend

            backend = CPUBackend()
            await backend.initialize()
            return backend

        else:
            raise RuntimeError(f"Unknown backend: {backend_name}")


# ===== Helper Functions =====


async def detect_available_backends() -> list[str]:
    """Detect which GPU backends are available on this system.

    Returns:
        list[str]: Names of available backends (e.g., ['cuda', 'metal'])
    """
    available = []

    # Try each backend
    for backend_name in ["cuda", "rocm", "metal", "directml", "vulkan", "tensorflow_lite_gpu"]:
        try:
            await GPUBackendFactory._create_specific_backend(backend_name)
            available.append(backend_name)
        except Exception:
            pass

    # CPU is always available
    available.append("cpu")

    return available


async def get_gpu_backend_info() -> dict:
    """Get detailed information about available GPU backends.

    Returns:
        dict: Mapping of backend name to device list
              {
                  'cuda': [GPUDevice(...), ...],
                  'rocm': [GPUDevice(...), ...],
                  ...
              }
    """
    info = {}

    try:
        backend = await GPUBackendFactory.create_backend()
        devices = backend.list_devices()

        if devices:
            # Determine backend name from first device
            backend_name = devices[0].backend
            info[backend_name] = devices
        else:
            # CPU backend
            info["cpu"] = []

        await backend.shutdown()
    except Exception as e:
        logger.error(f"Failed to get backend info: {e}")
        info["cpu"] = []

    return info
