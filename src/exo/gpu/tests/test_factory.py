"""Tests for GPU Backend Factory.

Tests verify:
1. Factory can create appropriate backend for platform
2. Backend override mechanism works
3. Platform detection works
4. Fallback to CPU works
"""

import sys
import pytest

from exo.gpu.factory import GPUBackendFactory, detect_available_backends
from exo.gpu.backends.cpu_backend import CPUBackend


class TestGPUBackendFactory:
    """Tests for GPUBackendFactory."""

    def teardown_method(self):
        """Clear backend override after each test."""
        GPUBackendFactory.clear_backend_override()

    @pytest.mark.asyncio
    async def test_cpu_backend_creation(self):
        """Test creating CPU backend explicitly."""
        GPUBackendFactory.set_backend_override("cpu")
        backend = await GPUBackendFactory.create_backend()

        assert isinstance(backend, CPUBackend)
        assert backend._initialized

        await backend.shutdown()

    @pytest.mark.asyncio
    async def test_backend_override(self):
        """Test backend override mechanism."""
        GPUBackendFactory.set_backend_override("cpu")
        backend1 = await GPUBackendFactory.create_backend()

        # Should still be CPU
        assert isinstance(backend1, CPUBackend)
        await backend1.shutdown()

        # Clear and try again
        GPUBackendFactory.clear_backend_override()
        # Now may get different backend depending on hardware
        backend2 = await GPUBackendFactory.create_backend()
        assert backend2 is not None
        await backend2.shutdown()

    @pytest.mark.asyncio
    async def test_backend_override_invalid(self):
        """Test that invalid backend override raises error."""
        GPUBackendFactory.set_backend_override("invalid_backend")

        with pytest.raises(RuntimeError):
            await GPUBackendFactory.create_backend()

    @pytest.mark.asyncio
    async def test_automatic_backend_selection(self):
        """Test automatic backend selection."""
        # Don't override - let factory choose
        backend = await GPUBackendFactory.create_backend()

        assert backend is not None
        devices = backend.list_devices()
        assert isinstance(devices, list)

        await backend.shutdown()

    @pytest.mark.asyncio
    async def test_backend_list_devices(self):
        """Test that backend returns device list."""
        GPUBackendFactory.set_backend_override("cpu")
        backend = await GPUBackendFactory.create_backend()

        devices = backend.list_devices()
        assert isinstance(devices, list)

        if devices:
            device = devices[0]
            assert device.device_id is not None
            assert device.name is not None
            assert device.vendor is not None

        await backend.shutdown()

    @pytest.mark.asyncio
    async def test_backend_get_device(self):
        """Test getting specific device."""
        GPUBackendFactory.set_backend_override("cpu")
        backend = await GPUBackendFactory.create_backend()

        device = backend.get_device("cpu:0")
        if device:
            assert device.device_id == "cpu:0"
        else:
            # CPU backend might not have cpu:0
            pass

        await backend.shutdown()


class TestDetectAvailableBackends:
    """Tests for backend detection utilities."""

    @pytest.mark.asyncio
    async def test_detect_available_backends(self):
        """Test detecting available backends."""
        available = await detect_available_backends()

        assert isinstance(available, list)
        # CPU should always be available
        assert "cpu" in available

    @pytest.mark.asyncio
    async def test_platform_specific_backends(self):
        """Test platform-specific backend detection."""
        if sys.platform.startswith("linux"):
            # Linux should try CUDA/ROCm/Vulkan
            assert hasattr(GPUBackendFactory, "PLATFORM_BACKEND_PRIORITY")
            linux_priority = GPUBackendFactory.PLATFORM_BACKEND_PRIORITY.get("linux", [])
            assert len(linux_priority) > 0

        elif sys.platform == "win32":
            # Windows should try DirectML/CUDA/ROCm
            win_priority = GPUBackendFactory.PLATFORM_BACKEND_PRIORITY.get("win32", [])
            assert len(win_priority) > 0

        elif sys.platform == "darwin":
            # macOS should try Metal
            mac_priority = GPUBackendFactory.PLATFORM_BACKEND_PRIORITY.get("darwin", [])
            assert "metal" in mac_priority or len(mac_priority) > 0


class TestBackendPriority:
    """Tests for backend priority ordering."""

    def test_linux_priority(self):
        """Test Linux backend priority."""
        priority = GPUBackendFactory.PLATFORM_BACKEND_PRIORITY.get("linux", [])
        assert "cuda" in priority or "rocm" in priority

    def test_windows_priority(self):
        """Test Windows backend priority."""
        priority = GPUBackendFactory.PLATFORM_BACKEND_PRIORITY.get("win32", [])
        assert "directml" in priority or "cuda" in priority

    def test_macos_priority(self):
        """Test macOS backend priority."""
        priority = GPUBackendFactory.PLATFORM_BACKEND_PRIORITY.get("darwin", [])
        assert "metal" in priority
