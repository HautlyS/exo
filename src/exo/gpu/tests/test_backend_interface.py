"""Unit tests for GPU backend interface and base classes.

Tests verify:
1. GPUDevice dataclass functionality
2. MemoryHandle model validation
3. GPUBackend abstract methods are properly defined
4. Type annotations are correct
"""

import pytest
from datetime import datetime, timezone

from exo.gpu.backend import GPUDevice, MemoryHandle, GPUBackend


class TestGPUDevice:
    """Tests for GPUDevice dataclass."""

    def test_gpu_device_creation(self):
        """Test creating a GPUDevice instance."""
        device = GPUDevice(
            device_id="cuda:0",
            name="NVIDIA RTX 4090",
            vendor="nvidia",
            backend="cuda",
            compute_capability="8.9",
            memory_bytes=24 * 1024 * 1024 * 1024,  # 24GB
            memory_available=24 * 1024 * 1024 * 1024,
            compute_units=128,
            tensor_core_count=5888,
            max_threads_per_block=1024,
            clock_rate_mhz=2500,
            bandwidth_gbps=960.0,
            support_level="full",
            driver_version="535.104.05",
            backend_name="cuda",
        )

        assert device.device_id == "cuda:0"
        assert device.vendor == "nvidia"
        assert device.backend == "cuda"
        assert device.memory_bytes == 24 * 1024 * 1024 * 1024

    def test_gpu_device_immutable(self):
        """Test that GPUDevice is frozen/immutable."""
        device = GPUDevice(
            device_id="cuda:0",
            name="Test GPU",
            vendor="nvidia",
            backend="cuda",
            compute_capability="8.9",
            memory_bytes=1024,
            memory_available=1024,
            compute_units=1,
            tensor_core_count=0,
            max_threads_per_block=1024,
            clock_rate_mhz=2000,
            bandwidth_gbps=100.0,
            support_level="full",
            driver_version="1.0",
            backend_name="cuda",
        )

        # Frozen dataclass should prevent modification
        with pytest.raises((AttributeError, Exception)):
            device.device_id = "cuda:1"

    def test_gpu_device_repr(self):
        """Test GPUDevice string representation."""
        device = GPUDevice(
            device_id="rocm:0",
            name="AMD MI250X",
            vendor="amd",
            backend="rocm",
            compute_capability="CDNA2",
            memory_bytes=128 * 1024 * 1024 * 1024,
            memory_available=128 * 1024 * 1024 * 1024,
            compute_units=220,
            tensor_core_count=0,
            max_threads_per_block=1024,
            clock_rate_mhz=2100,
            bandwidth_gbps=1600.0,
            support_level="full",
            driver_version="5.4.0",
            backend_name="rocm",
        )

        repr_str = repr(device)
        assert "rocm:0" in repr_str or "AMD MI250X" in repr_str


class TestMemoryHandle:
    """Tests for MemoryHandle Pydantic model."""

    def test_memory_handle_creation(self):
        """Test creating a MemoryHandle instance."""
        handle = MemoryHandle(
            device_id="cuda:0",
            size_bytes=1024 * 1024,  # 1MB
        )

        assert handle.device_id == "cuda:0"
        assert handle.size_bytes == 1024 * 1024
        assert handle.handle_id is not None
        assert isinstance(handle.allocated_at, datetime)

    def test_memory_handle_unique_ids(self):
        """Test that each MemoryHandle gets unique ID."""
        handle1 = MemoryHandle(device_id="cuda:0", size_bytes=100)
        handle2 = MemoryHandle(device_id="cuda:0", size_bytes=100)

        assert handle1.handle_id != handle2.handle_id

    def test_memory_handle_frozen(self):
        """Test that MemoryHandle is frozen (immutable)."""
        handle = MemoryHandle(device_id="cuda:0", size_bytes=1024)

        # Frozen model should prevent modification
        with pytest.raises((AttributeError, Exception)):
            handle.size_bytes = 2048

    def test_memory_handle_json_serialization(self):
        """Test MemoryHandle can be serialized to JSON."""
        handle = MemoryHandle(device_id="cuda:0", size_bytes=1024)
        json_str = handle.model_dump_json()

        assert "cuda:0" in json_str
        assert "1024" in json_str
        assert "handle_id" in json_str


class TestGPUBackendInterface:
    """Tests for GPUBackend abstract interface."""

    def test_gpu_backend_is_abstract(self):
        """Test that GPUBackend cannot be instantiated directly."""
        with pytest.raises(TypeError):
            GPUBackend()

    def test_gpu_backend_has_required_methods(self):
        """Test that GPUBackend defines all required methods."""
        required_methods = [
            "initialize",
            "shutdown",
            "list_devices",
            "get_device",
            "allocate",
            "deallocate",
            "copy_to_device",
            "copy_from_device",
            "copy_device_to_device",
            "synchronize",
            "get_device_memory_info",
            "get_device_temperature",
            "get_device_power_usage",
            "get_device_clock_rate",
        ]

        for method_name in required_methods:
            assert hasattr(GPUBackend, method_name), f"Missing method: {method_name}"

    def test_gpu_backend_methods_are_abstract(self):
        """Test that backend methods are abstract (have @abstractmethod)."""
        # These should be abstract methods
        assert hasattr(GPUBackend.initialize, "__isabstractmethod__")
        assert hasattr(GPUBackend.shutdown, "__isabstractmethod__")
        assert hasattr(GPUBackend.list_devices, "__isabstractmethod__")
        assert hasattr(GPUBackend.allocate, "__isabstractmethod__")


class MockGPUBackend(GPUBackend):
    """Mock implementation of GPUBackend for testing."""

    def __init__(self):
        self._initialized = False
        self._devices = []

    async def initialize(self):
        self._initialized = True

    async def shutdown(self):
        self._initialized = False

    def list_devices(self):
        return self._devices

    def get_device(self, device_id: str):
        for device in self._devices:
            if device.device_id == device_id:
                return device
        return None

    async def allocate(self, device_id: str, size_bytes: int):
        return MemoryHandle(device_id=device_id, size_bytes=size_bytes)

    async def deallocate(self, handle: MemoryHandle):
        pass

    async def copy_to_device(self, src: bytes, dst_handle: MemoryHandle, offset_bytes: int = 0):
        pass

    async def copy_from_device(self, src_handle: MemoryHandle, offset_bytes: int, size_bytes: int):
        return b"\x00" * size_bytes

    async def copy_device_to_device(self, src_handle: MemoryHandle, dst_handle: MemoryHandle, size_bytes: int):
        pass

    async def synchronize(self, device_id: str):
        pass

    async def get_device_memory_info(self, device_id: str):
        return {
            "total_bytes": 1024 * 1024 * 1024,
            "used_bytes": 512 * 1024 * 1024,
            "available_bytes": 512 * 1024 * 1024,
            "reserved_bytes": 0,
        }

    async def get_device_temperature(self, device_id: str):
        return 65.0

    async def get_device_power_usage(self, device_id: str):
        return 150.0

    async def get_device_clock_rate(self, device_id: str):
        return 2000


class TestGPUBackendImplementation:
    """Tests for concrete backend implementations (using mock)."""

    @pytest.mark.asyncio
    async def test_mock_backend_initialization(self):
        """Test mock backend can be initialized."""
        backend = MockGPUBackend()
        assert not backend._initialized

        await backend.initialize()
        assert backend._initialized

        await backend.shutdown()
        assert not backend._initialized

    @pytest.mark.asyncio
    async def test_mock_backend_device_list(self):
        """Test backend returns device list."""
        backend = MockGPUBackend()
        await backend.initialize()

        devices = backend.list_devices()
        assert isinstance(devices, list)

    @pytest.mark.asyncio
    async def test_mock_backend_memory_allocation(self):
        """Test backend memory allocation."""
        backend = MockGPUBackend()
        await backend.initialize()

        handle = await backend.allocate("cuda:0", 1024 * 1024)
        assert handle.device_id == "cuda:0"
        assert handle.size_bytes == 1024 * 1024

        await backend.deallocate(handle)

    @pytest.mark.asyncio
    async def test_mock_backend_memory_copy(self):
        """Test backend memory operations."""
        backend = MockGPUBackend()
        await backend.initialize()

        src_data = b"test data"
        handle = await backend.allocate("cuda:0", len(src_data))

        # Copy to device
        await backend.copy_to_device(src_data, handle)

        # Copy from device
        result = await backend.copy_from_device(handle, 0, len(src_data))
        assert isinstance(result, bytes)

        await backend.deallocate(handle)

    @pytest.mark.asyncio
    async def test_mock_backend_monitoring(self):
        """Test backend monitoring operations."""
        backend = MockGPUBackend()
        await backend.initialize()

        memory_info = await backend.get_device_memory_info("cuda:0")
        assert "total_bytes" in memory_info
        assert "used_bytes" in memory_info

        temp = await backend.get_device_temperature("cuda:0")
        assert temp is None or isinstance(temp, float)

        power = await backend.get_device_power_usage("cuda:0")
        assert power is None or isinstance(power, float)

        clock = await backend.get_device_clock_rate("cuda:0")
        assert clock is None or isinstance(clock, int)
