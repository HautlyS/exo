"""Cross-device GPU telemetry protocol.

Defines message formats and handlers for collecting and aggregating GPU metrics
across heterogeneous devices in distributed clusters.
"""

import json
from dataclasses import dataclass, asdict, field
from enum import Enum
from typing import Optional, Dict, Any
from datetime import datetime


class DeviceType(Enum):
    """GPU device types for cross-platform identification"""
    CUDA = "cuda"
    ROCM = "rocm"
    METAL = "metal"
    VULKAN_ANDROID = "vulkan_android"
    VULKAN_LINUX = "vulkan_linux"
    INTEL_XE = "intel_xe"
    DIRECTML = "directml"
    CPU = "cpu"


@dataclass
class GPUMetrics:
    """Real-time GPU performance metrics"""
    device_id: str
    timestamp: float  # Unix timestamp (seconds since epoch)
    memory_used_bytes: int
    memory_total_bytes: int
    compute_utilization_percent: float  # 0.0 to 100.0
    power_watts: float
    temperature_celsius: float
    clock_rate_mhz: int
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        return asdict(self)
    
    def to_json(self) -> str:
        """Serialize to JSON"""
        return json.dumps(self.to_dict())
    
    @classmethod
    def from_json(cls, json_str: str) -> "GPUMetrics":
        """Deserialize from JSON"""
        data = json.loads(json_str)
        return cls(**data)


@dataclass
class DeviceCapabilities:
    """Static device properties and capabilities"""
    device_id: str
    device_type: DeviceType
    device_name: str
    vendor: str
    compute_units: int
    memory_bandwidth_gbps: float
    max_memory_bytes: int
    driver_version: str
    supports_fp64: bool = False
    supports_tensor_cores: bool = False
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        data = asdict(self)
        data['device_type'] = self.device_type.value
        return data
    
    def to_json(self) -> str:
        """Serialize to JSON"""
        return json.dumps(self.to_dict())
    
    @classmethod
    def from_json(cls, json_str: str) -> "DeviceCapabilities":
        """Deserialize from JSON"""
        data = json.loads(json_str)
        data['device_type'] = DeviceType(data['device_type'])
        return cls(**data)


@dataclass
class DeviceRegistration:
    """Register a device in the cross-device cluster"""
    hostname: str
    port: int
    device_id: str
    capabilities: DeviceCapabilities
    timestamp: float = field(default_factory=lambda: datetime.now().timestamp())
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        return {
            'hostname': self.hostname,
            'port': self.port,
            'device_id': self.device_id,
            'capabilities': self.capabilities.to_dict(),
            'timestamp': self.timestamp,
        }
    
    def to_json(self) -> str:
        """Serialize to JSON"""
        return json.dumps(self.to_dict())
    
    @classmethod
    def from_json(cls, json_str: str) -> "DeviceRegistration":
        """Deserialize from JSON"""
        data = json.loads(json_str)
        capabilities_data = data.pop('capabilities')
        capabilities = DeviceCapabilities.from_json(json.dumps(capabilities_data))
        return cls(capabilities=capabilities, **data)


@dataclass
class Heartbeat:
    """Periodic device status heartbeat"""
    device_id: str
    metrics: GPUMetrics
    timestamp: float = field(default_factory=lambda: datetime.now().timestamp())
    is_available: bool = True
    error_message: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        return {
            'device_id': self.device_id,
            'metrics': self.metrics.to_dict(),
            'timestamp': self.timestamp,
            'is_available': self.is_available,
            'error_message': self.error_message,
        }
    
    def to_json(self) -> str:
        """Serialize to JSON"""
        return json.dumps(self.to_dict())
    
    @classmethod
    def from_json(cls, json_str: str) -> "Heartbeat":
        """Deserialize from JSON"""
        data = json.loads(json_str)
        metrics_data = data.pop('metrics')
        metrics = GPUMetrics.from_json(json.dumps(metrics_data))
        return cls(metrics=metrics, **data)


class TelemetryProtocol:
    """Protocol handler for cross-device GPU telemetry"""
    
    # Message type constants
    MSG_TYPE_REGISTRATION = "device_registration"
    MSG_TYPE_HEARTBEAT = "heartbeat"
    MSG_TYPE_METRICS = "metrics"
    MSG_TYPE_TOPOLOGY = "topology"
    
    @staticmethod
    def create_registration_message(reg: DeviceRegistration) -> Dict[str, Any]:
        """Create a device registration message"""
        return {
            'type': TelemetryProtocol.MSG_TYPE_REGISTRATION,
            'version': '1.0',
            'timestamp': datetime.now().timestamp(),
            'payload': reg.to_dict(),
        }
    
    @staticmethod
    def create_heartbeat_message(heartbeat: Heartbeat) -> Dict[str, Any]:
        """Create a heartbeat message"""
        return {
            'type': TelemetryProtocol.MSG_TYPE_HEARTBEAT,
            'version': '1.0',
            'timestamp': datetime.now().timestamp(),
            'payload': heartbeat.to_dict(),
        }
    
    @staticmethod
    def create_metrics_message(metrics: GPUMetrics) -> Dict[str, Any]:
        """Create a metrics message"""
        return {
            'type': TelemetryProtocol.MSG_TYPE_METRICS,
            'version': '1.0',
            'timestamp': datetime.now().timestamp(),
            'payload': metrics.to_dict(),
        }
    
    @staticmethod
    def serialize_message(message: Dict[str, Any]) -> str:
        """Serialize message to JSON"""
        return json.dumps(message)
    
    @staticmethod
    def deserialize_message(json_str: str) -> Dict[str, Any]:
        """Deserialize message from JSON"""
        return json.loads(json_str)
    
    @staticmethod
    def parse_registration(payload: Dict[str, Any]) -> DeviceRegistration:
        """Parse registration message payload"""
        return DeviceRegistration.from_json(json.dumps(payload))
    
    @staticmethod
    def parse_heartbeat(payload: Dict[str, Any]) -> Heartbeat:
        """Parse heartbeat message payload"""
        return Heartbeat.from_json(json.dumps(payload))
    
    @staticmethod
    def parse_metrics(payload: Dict[str, Any]) -> GPUMetrics:
        """Parse metrics message payload"""
        return GPUMetrics.from_json(json.dumps(payload))


class DeviceScorer:
    """Score devices for task scheduling based on metrics"""
    
    @staticmethod
    def score_device(metrics: GPUMetrics, capabilities: DeviceCapabilities) -> float:
        """Score device suitability for computation: 0.0 to 1.0
        
        Considers:
        - Available memory (60% weight)
        - Compute utilization (40% weight)
        
        Args:
            metrics: Current device metrics
            capabilities: Device capabilities
            
        Returns:
            Device score from 0.0 (unavailable) to 1.0 (ideal)
        """
        if capabilities.max_memory_bytes == 0:
            return 0.0
        
        # Memory availability score
        available_bytes = metrics.memory_total_bytes - metrics.memory_used_bytes
        memory_score = available_bytes / capabilities.max_memory_bytes
        memory_score = max(0.0, min(1.0, memory_score))
        
        # Compute availability score (inverse of utilization)
        compute_score = 1.0 - (metrics.compute_utilization_percent / 100.0)
        compute_score = max(0.0, min(1.0, compute_score))
        
        # Temperature penalty (above 80°C reduces score)
        temp_penalty = 1.0
        if metrics.temperature_celsius > 80:
            temp_penalty = max(0.1, 1.0 - (metrics.temperature_celsius - 80) / 40)
        
        # Weighted score
        final_score = (0.6 * memory_score + 0.4 * compute_score) * temp_penalty
        
        return max(0.0, min(1.0, final_score))
    
    @staticmethod
    def rank_devices(
        devices: Dict[str, tuple[GPUMetrics, DeviceCapabilities]]
    ) -> list[tuple[str, float]]:
        """Rank devices by suitability for computation
        
        Args:
            devices: Dict of device_id -> (metrics, capabilities)
            
        Returns:
            List of (device_id, score) tuples sorted by score (highest first)
        """
        scores = []
        for device_id, (metrics, caps) in devices.items():
            score = DeviceScorer.score_device(metrics, caps)
            scores.append((device_id, score))
        
        # Sort by score descending
        return sorted(scores, key=lambda x: x[1], reverse=True)
    
    @staticmethod
    def find_best_device(
        devices: Dict[str, tuple[GPUMetrics, DeviceCapabilities]],
        min_memory_bytes: int = 0,
    ) -> Optional[str]:
        """Find best device for computation
        
        Args:
            devices: Dict of device_id -> (metrics, capabilities)
            min_memory_bytes: Minimum required device memory
            
        Returns:
            Best device_id or None if no suitable device
        """
        ranked = DeviceScorer.rank_devices(devices)
        
        for device_id, score in ranked:
            if score > 0.0:
                metrics, caps = devices[device_id]
                available_bytes = metrics.memory_total_bytes - metrics.memory_used_bytes
                if available_bytes >= min_memory_bytes:
                    return device_id
        
        return None


# Message format examples:

REGISTRATION_MESSAGE_EXAMPLE = {
    'type': 'device_registration',
    'version': '1.0',
    'timestamp': 1707043200.0,
    'payload': {
        'hostname': 'device-001',
        'port': 5000,
        'device_id': 'vulkan:0',
        'capabilities': {
            'device_id': 'vulkan:0',
            'device_type': 'vulkan_android',
            'device_name': 'Qualcomm Adreno 650',
            'vendor': 'Qualcomm',
            'compute_units': 128,
            'memory_bandwidth_gbps': 160.0,
            'max_memory_bytes': 8589934592,
            'driver_version': '1.2.0',
            'supports_fp64': False,
            'supports_tensor_cores': True,
        },
        'timestamp': 1707043200.0,
    }
}

HEARTBEAT_MESSAGE_EXAMPLE = {
    'type': 'heartbeat',
    'version': '1.0',
    'timestamp': 1707043210.0,
    'payload': {
        'device_id': 'vulkan:0',
        'metrics': {
            'device_id': 'vulkan:0',
            'timestamp': 1707043210.0,
            'memory_used_bytes': 2147483648,
            'memory_total_bytes': 8589934592,
            'compute_utilization_percent': 45.5,
            'power_watts': 12.3,
            'temperature_celsius': 65.0,
            'clock_rate_mhz': 750,
        },
        'is_available': True,
        'error_message': None,
    }
}
