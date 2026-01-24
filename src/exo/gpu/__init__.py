"""GPU abstraction layer for cross-device GPU clustering."""

from exo.gpu.backend import GPUBackend, GPUDevice, MemoryHandle
from exo.gpu.factory import GPUBackendFactory

__all__ = [
    "GPUBackend",
    "GPUDevice",
    "MemoryHandle",
    "GPUBackendFactory",
]
