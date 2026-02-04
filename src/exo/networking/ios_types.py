"""iOS GPU device types and data structures."""

from dataclasses import dataclass
from enum import Enum
from typing import Optional


class GPUVendor(Enum):
    """GPU vendor identification"""
    APPLE = "Apple"
    NVIDIA = "NVIDIA"
    AMD = "AMD"
    INTEL = "Intel"
    UNKNOWN = "Unknown"


@dataclass
class IOSGPUInfo:
    """GPU device information from iOS device"""
    device_id: str
    name: str
    vendor: str
    max_memory: int
    compute_units: int
    supports_family: str
    is_low_power: bool
    
    @property
    def memory_gb(self) -> float:
        """Convert memory to GB"""
        return self.max_memory / (1024 * 1024 * 1024)
    
    def __str__(self) -> str:
        return f"{self.name} ({self.vendor}) - {self.memory_gb:.1f}GB"


@dataclass
class DiscoveredIOSDevice:
    """Discovered iOS device with GPU capabilities"""
    peer_id: str
    display_name: str
    address: str
    port: int
    gpu_devices: list[IOSGPUInfo]
    is_low_power: bool = False
    
    def has_gpu(self) -> bool:
        """Check if device has any GPU"""
        return len(self.gpu_devices) > 0
    
    def total_gpu_memory(self) -> int:
        """Get total GPU memory across all devices"""
        return sum(gpu.max_memory for gpu in self.gpu_devices)
    
    @property
    def total_gpu_memory_gb(self) -> float:
        """Get total GPU memory in GB"""
        return self.total_gpu_memory() / (1024 * 1024 * 1024)
    
    def __str__(self) -> str:
        gpu_count = len(self.gpu_devices)
        return f"{self.display_name} - {gpu_count} GPU(s) @ {self.address}:{self.port}"
