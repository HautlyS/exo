"""Integration tests for all GPU backends implementation.

Verifies:
1. All backend imports work
2. Factory can create backends
3. CPU backend initializes successfully
"""

import pytest
from exo.gpu.factory import GPUBackendFactory
from exo.gpu.backends.cpu_backend import CPUBackend


class TestBackendImports:
    """Test that all backend modules can be imported."""

    def test_import_cpu_backend(self):
        """Test CPUBackend import."""
        from exo.gpu.backends.cpu_backend import CPUBackend
        assert CPUBackend is not None

    def test_import_cuda_backend(self):
        """Test CUDABackend import (may not have cupy installed)."""
        try:
            from exo.gpu.backends.cuda_backend import CUDABackend
            assert CUDABackend is not None
        except ImportError:
            pytest.skip("CuPy not installed")

    def test_import_rocm_backend(self):
        """Test ROCmBackend import (may not have cupy installed)."""
        try:
            from exo.gpu.backends.rocm_backend import ROCmBackend
            assert ROCmBackend is not None
        except ImportError:
            pytest.skip("CuPy not installed for ROCm")

    def test_import_metal_backend(self):
        """Test MetalBackend import (macOS only)."""
        try:
            from exo.gpu.backends.metal_backend import MetalBackend
            assert MetalBackend is not None
        except ImportError:
            pytest.skip("MLX not installed")

    def test_import_directml_backend(self):
        """Test DirectMLBackend import (Windows only)."""
        try:
            from exo.gpu.backends.directml_backend import DirectMLBackend
            assert DirectMLBackend is not None
        except ImportError:
            pytest.skip("ONNX Runtime not installed")

    def test_import_tflite_backend(self):
        """Test TFLiteGPUBackend import (mobile)."""
        try:
            from exo.gpu.backends.tflite_gpu_backend import TFLiteGPUBackend
            assert TFLiteGPUBackend is not None
        except ImportError:
            pytest.skip("TensorFlow not installed")


class TestCPUBackendInitialization:
    """Test CPU backend initialization (always available)."""

    @pytest.mark.asyncio
    async def test_cpu_backend_init(self):
        """Test initializing CPU backend."""
        backend = CPUBackend()
        await backend.initialize()
        assert backend._initialized
        assert len(backend.list_devices()) == 1
        assert backend.list_devices()[0].device_id == "cpu:0"

    @pytest.mark.asyncio
    async def test_cpu_backend_allocation(self):
        """Test memory allocation on CPU backend."""
        backend = CPUBackend()
        await backend.initialize()

        handle = await backend.allocate("cpu:0", 1024)
        assert handle is not None
        assert handle.device_id == "cpu:0"
        assert handle.size_bytes == 1024

        await backend.deallocate(handle)

    @pytest.mark.asyncio
    async def test_cpu_backend_copy(self):
        """Test memory copy on CPU backend."""
        backend = CPUBackend()
        await backend.initialize()

        handle = await backend.allocate("cpu:0", 10)
        data = b"test_data"

        await backend.copy_to_device(data, handle, 0)
        copied = await backend.copy_from_device(handle, 0, len(data))

        assert copied == data
        await backend.deallocate(handle)


class TestFactoryFallback:
    """Test factory fallback to CPU."""

    @pytest.mark.asyncio
    async def test_factory_creates_backend(self):
        """Test that factory can create some backend."""
        # Force CPU backend for testing
        GPUBackendFactory.set_backend_override("cpu")
        backend = await GPUBackendFactory.create_backend()
        assert backend is not None
        GPUBackendFactory.clear_backend_override()

    @pytest.mark.asyncio
    async def test_cpu_backend_via_factory(self):
        """Test creating CPU backend via factory."""
        GPUBackendFactory.set_backend_override("cpu")
        backend = await GPUBackendFactory.create_backend()

        await backend.initialize()
        devices = backend.list_devices()
        assert len(devices) > 0
        assert "cpu" in devices[0].backend_name

        await backend.shutdown()
        GPUBackendFactory.clear_backend_override()
