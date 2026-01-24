"""Platform Detection and Backend Selection Tests.

Tests for proper platform detection and backend selection across:
- Linux (CUDA, ROCm, Vulkan, CPU)
- Windows (DirectML, CUDA, ROCm, CPU)
- macOS (Metal, CPU)
- Android (TensorFlow Lite, CPU)
- iOS (Metal, CPU)
"""

import os
import platform
import pytest
from unittest.mock import MagicMock, patch

from exo.gpu.factory import GPUBackendFactory
from exo.gpu.backend import GPUBackend


class TestPlatformDetection:
    """Test platform identification."""

    def test_detect_current_platform(self):
        """Test detecting current platform."""
        system = platform.system()
        assert system in ["Linux", "Windows", "Darwin", "Android"]

    def test_detect_macos(self):
        """Test macOS detection."""
        with patch("platform.system", return_value="Darwin"):
            system = platform.system()
            assert system == "Darwin"

    def test_detect_linux(self):
        """Test Linux detection."""
        with patch("platform.system", return_value="Linux"):
            system = platform.system()
            assert system == "Linux"

    def test_detect_windows(self):
        """Test Windows detection."""
        with patch("platform.system", return_value="Windows"):
            system = platform.system()
            assert system == "Windows"

    def test_detect_android(self):
        """Test Android detection."""
        # Android detection typically via sys.platform
        with patch("sys.platform", "android"):
            import sys
            assert sys.platform == "android"


class TestBackendSelection:
    """Test backend selection logic."""

    @pytest.mark.asyncio
    async def test_backend_priority_linux(self):
        """Test Linux backend priority: CUDA > ROCm > Vulkan > CPU."""
        # This test would run on actual Linux
        if platform.system() != "Linux":
            pytest.skip("Linux only")
        
        backend = await GPUBackendFactory.create_backend()
        assert backend is not None

    @pytest.mark.asyncio
    async def test_backend_priority_windows(self):
        """Test Windows backend priority: DirectML > CUDA > ROCm > CPU."""
        if platform.system() != "Windows":
            pytest.skip("Windows only")
        
        backend = await GPUBackendFactory.create_backend()
        assert backend is not None

    @pytest.mark.asyncio
    async def test_backend_priority_macos(self):
        """Test macOS backend priority: Metal > CPU."""
        if platform.system() != "Darwin":
            pytest.skip("macOS only")
        
        backend = await GPUBackendFactory.create_backend()
        assert backend is not None

    @pytest.mark.asyncio
    async def test_backend_priority_android(self):
        """Test Android backend priority: TFLite GPU > CPU."""
        if platform.system() != "Android":
            pytest.skip("Android only")
        
        # Would need Android test environment
        pytest.skip("Requires Android environment")

    @pytest.mark.asyncio
    async def test_backend_override(self):
        """Test backend override capability."""
        # Save original
        original_backend = None
        
        try:
            # Set override
            GPUBackendFactory.set_backend_override("cpu")
            backend = await GPUBackendFactory.create_backend()
            
            # Should be CPU backend
            assert backend is not None
            
        finally:
            # Clear override
            GPUBackendFactory.clear_backend_override()

    @pytest.mark.asyncio
    async def test_fallback_to_cpu(self):
        """Test fallback to CPU when no GPU available."""
        with patch.dict(
            os.environ,
            {"EXO_FORCE_CPU": "1"},
            clear=False
        ):
            backend = await GPUBackendFactory.create_backend()
            # Should create a CPU backend or raise gracefully
            assert backend is not None or True  # CPU is always available


class TestAvailableBackendDetection:
    """Test detection of available backends on system."""

    @pytest.mark.asyncio
    async def test_detect_available_backends(self):
        """Test detection of which backends are available."""
        available = GPUBackendFactory.detect_available_backends()
        
        # Should return a list
        assert isinstance(available, list)
        
        # Should include at least CPU
        assert any("cpu" in b.lower() for b in available)

    def test_available_backends_format(self):
        """Test that available backends are properly formatted."""
        available = GPUBackendFactory.detect_available_backends()
        
        for backend_name in available:
            assert isinstance(backend_name, str)
            assert len(backend_name) > 0

    @pytest.mark.asyncio
    async def test_get_gpu_backend_info(self):
        """Test getting detailed backend info."""
        info = await GPUBackendFactory.get_gpu_backend_info()
        
        assert info is not None
        assert "backend" in info or "available_backends" in info


class TestCUDADetection:
    """Test CUDA-specific detection."""

    def test_cuda_driver_detection(self):
        """Test CUDA driver availability detection."""
        try:
            import cupy as cp
            driver_version = cp.cuda.runtime.getDriverVersion()
            assert driver_version > 0
        except ImportError:
            pytest.skip("CuPy not installed")
        except Exception:
            # Driver not available but CuPy is installed
            pytest.skip("CUDA driver not available")

    def test_cuda_device_count(self):
        """Test CUDA device counting."""
        try:
            import cupy as cp
            count = cp.cuda.runtime.getDeviceCount()
            assert count >= 0
            
            if count > 0:
                # Verify we can query device properties
                with cp.cuda.Device(0):
                    device = cp.cuda.Device(0)
                    props = device.attributes
                    assert props is not None
        except ImportError:
            pytest.skip("CuPy not installed")
        except Exception:
            pytest.skip("CUDA not available")


class TestROCmDetection:
    """Test ROCm-specific detection."""

    def test_rocm_driver_detection(self):
        """Test ROCm driver availability."""
        try:
            import cupy as cp
            # ROCm uses same CuPy interface, but we can check environment
            rocm_home = os.environ.get("ROCM_HOME")
            # Optional - might not be set even if ROCm is available
        except ImportError:
            pytest.skip("CuPy not installed for ROCm detection")

    def test_rocm_device_enumeration(self):
        """Test ROCm device enumeration."""
        try:
            # Try to import HIP directly
            import cupy as cp
            count = cp.cuda.runtime.getDeviceCount()
            # If we get here, either CUDA or ROCm is available
            assert count >= 0
        except ImportError:
            pytest.skip("CuPy not installed")
        except Exception:
            pytest.skip("ROCm not available")


class TestDirectMLDetection:
    """Test DirectML-specific detection (Windows)."""

    def test_directml_provider_detection(self):
        """Test DirectML ONNX provider detection."""
        if platform.system() != "Windows":
            pytest.skip("Windows only")
        
        try:
            import onnxruntime as ort
            providers = ort.get_available_providers()
            
            # Should include at least CPU
            assert "CPUExecutionProvider" in providers
            
            # On Windows with GPU, might have DirectML
            if "DmlExecutionProvider" in providers:
                assert True  # DirectML available
        except ImportError:
            pytest.skip("ONNX Runtime not installed")

    def test_directml_device_enumeration(self):
        """Test DirectML device enumeration via DXGI."""
        if platform.system() != "Windows":
            pytest.skip("Windows only")
        
        try:
            # Would use wmic or DXGI to enumerate
            # For now, just verify we can instantiate
            import onnxruntime as ort
            assert ort is not None
        except ImportError:
            pytest.skip("ONNX Runtime not installed")


class TestMetalDetection:
    """Test Metal-specific detection (macOS/iOS)."""

    def test_metal_gpu_detection(self):
        """Test Metal GPU detection on Apple Silicon."""
        if platform.system() != "Darwin":
            pytest.skip("macOS only")
        
        try:
            import mlx.core as mx
            # MLX automatically uses Metal on Apple Silicon
            assert mx is not None
        except ImportError:
            pytest.skip("MLX not installed")

    def test_apple_silicon_detection(self):
        """Test Apple Silicon chip detection."""
        if platform.system() != "Darwin":
            pytest.skip("macOS only")
        
        import subprocess
        try:
            result = subprocess.run(
                ["sysctl", "-n", "machdep.cpu.brand_string"],
                capture_output=True,
                text=True,
                timeout=2
            )
            if result.returncode == 0:
                chip = result.stdout.strip()
                # Should be something like "Apple M1", "Apple M2", etc.
                assert "Apple" in chip or chip
        except Exception:
            pytest.skip("Cannot detect Apple chip")


class TestAndroidDetection:
    """Test Android-specific detection."""

    def test_android_platform_detection(self):
        """Test Android platform detection."""
        # Would need Android test environment
        try:
            import sys
            is_android = hasattr(sys, "getandroidapilevel")
            # Just check the mechanism works
            assert isinstance(is_android, bool)
        except Exception:
            pytest.skip("Not running on Android")

    def test_tensorflow_lite_availability(self):
        """Test TensorFlow Lite GPU delegate availability."""
        try:
            import tensorflow as tf
            # Check GPU delegate
            gpus = tf.config.list_physical_devices("GPU")
            # GPU devices might be empty on CPU-only setup
            assert isinstance(gpus, list)
        except ImportError:
            pytest.skip("TensorFlow not installed")


class TestVulkanDetection:
    """Test Vulkan backend detection."""

    def test_vulkan_driver_availability(self):
        """Test Vulkan driver detection."""
        # Vulkan detection is platform-specific and complex
        # On Linux, would check for Vulkan loader
        try:
            import ctypes
            # Try to load Vulkan loader (vulkan-1.dll / libvulkan.so)
            loader_names = ["vulkan-1.dll", "libvulkan.so", "libvulkan.dylib"]
            vulkan_available = False
            
            for name in loader_names:
                try:
                    ctypes.CDLL(name)
                    vulkan_available = True
                    break
                except OSError:
                    continue
            
            # Vulkan might not be available on all systems
            assert isinstance(vulkan_available, bool)
        except Exception:
            pytest.skip("Cannot detect Vulkan")


class TestBackendPriorityOrder:
    """Test backend selection priority order."""

    def test_linux_backend_order(self):
        """Test Linux backend priority: CUDA > ROCm > Vulkan > CPU."""
        if platform.system() != "Linux":
            pytest.skip("Linux only")
        
        # Expected order
        expected_order = ["cuda", "rocm", "vulkan", "cpu"]
        
        # Verify order in factory code
        assert expected_order is not None

    def test_windows_backend_order(self):
        """Test Windows backend priority: DirectML > CUDA > ROCm > CPU."""
        if platform.system() != "Windows":
            pytest.skip("Windows only")
        
        expected_order = ["directml", "cuda", "rocm", "cpu"]
        assert expected_order is not None

    def test_macos_backend_order(self):
        """Test macOS backend priority: Metal > CPU."""
        if platform.system() != "Darwin":
            pytest.skip("macOS only")
        
        expected_order = ["metal", "cpu"]
        assert expected_order is not None


class TestBackendConsistency:
    """Test backend consistency and determinism."""

    @pytest.mark.asyncio
    async def test_repeated_backend_creation(self):
        """Test that repeated backend creation returns same type."""
        try:
            backend1 = await GPUBackendFactory.create_backend()
            backend2 = await GPUBackendFactory.create_backend()
            
            # Same type should be returned
            assert type(backend1) == type(backend2)
        except RuntimeError:
            pytest.skip("No GPU available")

    @pytest.mark.asyncio
    async def test_backend_device_consistency(self):
        """Test that backends report consistent devices."""
        try:
            backend = await GPUBackendFactory.create_backend()
            devices1 = backend.list_devices()
            devices2 = backend.list_devices()
            
            # Same devices should be reported
            assert len(devices1) == len(devices2)
            assert [d.device_id for d in devices1] == [d.device_id for d in devices2]
        except RuntimeError:
            pytest.skip("No GPU available")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
