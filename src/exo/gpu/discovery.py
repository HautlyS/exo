"""GPU Discovery Service - detects and registers GPU devices at startup.

Runs at Worker startup before runner initialization. Uses GPU backends to detect
devices and maintains a persistent registry. Integrates with node info gathering
to expose GPU capabilities to the cluster.
"""

import asyncio
import json
import logging
from pathlib import Path
from typing import Optional

from exo.gpu.backend import GPUDevice
from exo.gpu.factory import GPUBackendFactory

logger = logging.getLogger(__name__)


class GPUDiscoveryService:
    """GPU discovery service for Worker startup."""

    def __init__(self, registry_path: Optional[Path] = None):
        """Initialize GPU discovery service.

        Args:
            registry_path: Path to persistent device registry JSON file.
                          Default: ~/.exo/gpu_registry.json
        """
        if registry_path is None:
            registry_path = Path.home() / ".exo" / "gpu_registry.json"

        self.registry_path = registry_path
        self._devices = []
        self._backend = None

    async def discover_all_devices(self) -> dict:
        """Discover all GPU devices on this node.

        Process:
        1. Initialize GPU backend
        2. Query available devices
        3. Verify each device (test allocate/deallocate)
        4. Save to persistent registry
        5. Return device list

        Returns:
            dict with keys:
                - devices: List[GPUDevice] - discovered devices
                - backend_name: str - selected backend name
                - discovery_status: str - "success" or "partial"
                - timestamp: str - discovery timestamp

        Raises:
            RuntimeError: If discovery completely fails
        """
        try:
            logger.info("Starting GPU device discovery...")

            # Step 1: Create backend
            self._backend = await GPUBackendFactory.create_backend()
            logger.info(f"Using GPU backend: {self._backend.__class__.__name__}")

            # Step 2: List devices
            devices = self._backend.list_devices()
            logger.info(f"Found {len(devices)} GPU device(s)")

            # Step 3: Verify each device
            verified_devices = []
            for device in devices:
                try:
                    if await self._verify_device(device):
                        verified_devices.append(device)
                        logger.info(f"Verified device: {device.device_id} ({device.name})")
                    else:
                        logger.warning(f"Failed to verify device: {device.device_id}")
                except Exception as e:
                    logger.warning(f"Device verification failed for {device.device_id}: {e}")

            self._devices = verified_devices

            # Step 4: Save registry
            await self._save_registry()

            # Step 5: Return results
            backend_name = self._backend.__class__.__name__
            status = "success" if verified_devices else "partial"

            result = {
                "devices": verified_devices,
                "backend_name": backend_name,
                "discovery_status": status,
                "timestamp": self._get_timestamp(),
            }

            logger.info(f"GPU discovery complete: {status}")
            return result

        except Exception as e:
            logger.error(f"GPU discovery failed: {e}")
            raise RuntimeError(f"GPU discovery failed: {e}") from e

    async def _verify_device(self, device: GPUDevice) -> bool:
        """Verify device is functional by testing memory operations.

        Args:
            device: GPU device to verify

        Returns:
            bool: True if device is functional, False otherwise
        """
        try:
            # Test memory allocation
            test_size = 1024 * 1024  # 1MB
            handle = await self._backend.allocate(device.device_id, test_size)

            # Test copy to device
            test_data = b"\x00" * 1024
            await self._backend.copy_to_device(test_data, handle)

            # Test synchronization
            await self._backend.synchronize(device.device_id)

            # Cleanup
            await self._backend.deallocate(handle)

            return True

        except Exception as e:
            logger.debug(f"Device verification failed for {device.device_id}: {e}")
            return False

    async def _save_registry(self) -> None:
        """Save discovered devices to persistent registry."""
        try:
            self.registry_path.parent.mkdir(parents=True, exist_ok=True)

            registry = {
                "devices": [
                    {
                        "device_id": d.device_id,
                        "name": d.name,
                        "vendor": d.vendor,
                        "backend": d.backend,
                        "memory_bytes": d.memory_bytes,
                        "compute_units": d.compute_units,
                        "support_level": d.support_level,
                    }
                    for d in self._devices
                ],
                "timestamp": self._get_timestamp(),
            }

            with open(self.registry_path, "w") as f:
                json.dump(registry, f, indent=2)

            logger.info(f"Saved GPU registry to {self.registry_path}")

        except Exception as e:
            logger.warning(f"Failed to save GPU registry: {e}")

    async def load_registry(self) -> Optional[dict]:
        """Load previously discovered devices from registry.

        Useful for quick startup when hardware hasn't changed.

        Returns:
            dict or None if registry doesn't exist
        """
        try:
            if not self.registry_path.exists():
                return None

            with open(self.registry_path, "r") as f:
                registry = json.load(f)

            logger.info(f"Loaded GPU registry from {self.registry_path}")
            return registry

        except Exception as e:
            logger.debug(f"Failed to load GPU registry: {e}")
            return None

    def get_device_by_id(self, device_id: str) -> Optional[GPUDevice]:
        """Get device by ID from discovered devices.

        Args:
            device_id: Device identifier (e.g., 'cuda:0')

        Returns:
            GPUDevice or None if not found
        """
        for device in self._devices:
            if device.device_id == device_id:
                return device
        return None

    @staticmethod
    def _get_timestamp() -> str:
        """Get ISO 8601 timestamp."""
        from datetime import datetime, timezone

        return datetime.now(tz=timezone.utc).isoformat()

    async def shutdown(self) -> None:
        """Cleanup discovery service and backend."""
        if self._backend:
            await self._backend.shutdown()
            self._backend = None
        self._devices.clear()
        logger.info("GPU discovery service shutdown")


# ===== Helper Functions =====


async def discover_gpu_devices(
    registry_path: Optional[Path] = None,
) -> dict:
    """Convenience function to discover GPU devices.

    Args:
        registry_path: Optional custom registry path

    Returns:
        dict with discovered devices and metadata
    """
    service = GPUDiscoveryService(registry_path)
    try:
        return await service.discover_all_devices()
    finally:
        await service.shutdown()


def get_total_gpu_memory(devices: list[GPUDevice]) -> int:
    """Calculate total GPU memory across all devices.

    Args:
        devices: List of GPU devices

    Returns:
        int: Total memory in bytes
    """
    return sum(d.memory_bytes for d in devices)


def get_peak_flops(devices: list[GPUDevice]) -> float:
    """Estimate peak FLOPS across all devices.

    Rough estimate: compute_units * clock_rate * 2 (for FMA)

    Args:
        devices: List of GPU devices

    Returns:
        float: Estimated FLOPS per second
    """
    total_flops = 0.0
    for device in devices:
        # Very rough estimate: CUs * clock * threads per CU
        device_flops = device.compute_units * device.clock_rate_mhz * 1e6 * 64
        total_flops += device_flops

    return total_flops
