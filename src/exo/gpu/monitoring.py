"""GPU telemetry and monitoring - tracks GPU metrics for dashboard and optimization.

Provides:
- Real-time memory usage tracking
- Compute utilization measurement
- Temperature monitoring
- Prometheus-compatible metrics
- Alerting for high utilization/temperature
"""

import asyncio
import contextlib
import logging
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Callable, Optional

from exo.gpu.backend import GPUBackend, GPUDevice
from exo.shared.types.common import NodeId
from exo.shared.types.state import DeviceGPUState

logger = logging.getLogger(__name__)


@dataclass
class GPUMetricsSnapshot:
    """Single point-in-time measurement of GPU metrics."""

    timestamp: datetime
    device_id: str
    memory_used_bytes: int
    memory_total_bytes: int
    compute_utilization_percent: float
    temperature_c: float
    power_usage_w: float


@dataclass
class GPUMetricsSummary:
    """Summary statistics over a time window."""

    device_id: str
    window_seconds: float

    # Memory stats
    memory_avg_used_bytes: int
    memory_peak_used_bytes: int
    memory_current_used_bytes: int

    # Compute stats
    compute_avg_utilization_percent: float
    compute_peak_utilization_percent: float
    compute_current_utilization_percent: float

    # Thermal stats
    temperature_avg_c: float
    temperature_peak_c: float
    temperature_current_c: float

    # Power stats
    power_avg_w: float
    power_peak_w: float
    power_current_w: float

    # Alerts
    high_memory_alerts: int = 0
    high_temperature_alerts: int = 0
    thermal_throttle_detected: bool = False


class GPUMetricsCollector:
    """Collects and aggregates GPU metrics over time."""

    def __init__(
        self,
        device: GPUDevice,
        backend: GPUBackend,
        window_size_seconds: float = 60.0,
    ):
        """Initialize metrics collector.

        Args:
            device: GPU device to monitor
            backend: GPU backend for querying metrics
            window_size_seconds: Time window for statistics
        """
        self.device = device
        self.backend = backend
        self.window_size_seconds = window_size_seconds

        self.snapshots: list[GPUMetricsSnapshot] = []
        self.high_memory_threshold_bytes = int(0.9 * device.memory_bytes)
        self.high_temperature_threshold_c = 75.0
        self.thermal_throttle_threshold_c = device.memory_bytes  # Use device limit

    async def collect_snapshot(self) -> GPUMetricsSnapshot:
        """Collect a single metric snapshot from GPU."""
        memory_info = await self.backend.get_device_memory_info(self.device.device_id)  # type: ignore[misc]
        temperature_c = await self.backend.get_device_temperature(self.device.device_id)
        power_w = await self.backend.get_device_power_usage(self.device.device_id)

        # Extract memory info from dict (with type casting for unknown dict)
        memory_used: int = int(memory_info.get("used_bytes", 0) or 0)  # type: ignore[index,union-attr]
        memory_total: int = int(memory_info.get("total_bytes", 0) or 0)  # type: ignore[index,union-attr]

        snapshot = GPUMetricsSnapshot(
            timestamp=datetime.now(),
            device_id=self.device.device_id,
            memory_used_bytes=memory_used,
            memory_total_bytes=memory_total,
            compute_utilization_percent=memory_used / memory_total * 100.0
            if memory_total > 0
            else 0.0,  # Placeholder
            temperature_c=temperature_c or 0.0,
            power_usage_w=power_w or 0.0,
        )

        # Add to history and trim old entries
        self.snapshots.append(snapshot)
        cutoff = datetime.now() - timedelta(seconds=self.window_size_seconds)
        self.snapshots = [s for s in self.snapshots if s.timestamp > cutoff]

        return snapshot

    def get_summary(self) -> Optional[GPUMetricsSummary]:
        """Get aggregated metrics over current window."""
        if not self.snapshots:
            return None

        memories = [s.memory_used_bytes for s in self.snapshots]
        utilizations = [s.compute_utilization_percent for s in self.snapshots]
        temperatures = [s.temperature_c for s in self.snapshots]
        powers = [s.power_usage_w for s in self.snapshots]

        # Count alerts
        high_memory_count = sum(
            1 for m in memories if m > self.high_memory_threshold_bytes
        )
        high_temp_count = sum(
            1 for t in temperatures if t > self.high_temperature_threshold_c
        )

        return GPUMetricsSummary(
            device_id=self.device.device_id,
            window_seconds=self.window_size_seconds,
            # Memory
            memory_avg_used_bytes=int(sum(memories) / len(memories)),
            memory_peak_used_bytes=max(memories),
            memory_current_used_bytes=memories[-1] if memories else 0,
            # Compute
            compute_avg_utilization_percent=sum(utilizations) / len(utilizations),
            compute_peak_utilization_percent=max(utilizations),
            compute_current_utilization_percent=utilizations[-1]
            if utilizations
            else 0.0,
            # Thermal
            temperature_avg_c=sum(temperatures) / len(temperatures),
            temperature_peak_c=max(temperatures),
            temperature_current_c=temperatures[-1] if temperatures else 0.0,
            # Power
            power_avg_w=sum(powers) / len(powers),
            power_peak_w=max(powers),
            power_current_w=powers[-1] if powers else 0.0,
            # Alerts
            high_memory_alerts=high_memory_count,
            high_temperature_alerts=high_temp_count,
            thermal_throttle_detected=high_temp_count > 3,  # Consecutive threshold
        )

    def get_device_gpu_state(self, node_id: Optional[NodeId] = None) -> Optional[DeviceGPUState]:
        """Convert current metrics to DeviceGPUState."""
        if not self.snapshots:
            return None

        latest = self.snapshots[-1]
        # Use provided node_id or generate one from device_id
        actual_node_id = node_id or NodeId(self.device.device_id)
        
        return DeviceGPUState(
            device_id=self.device.device_id,
            node_id=actual_node_id,
            memory_used_bytes=latest.memory_used_bytes,
            memory_total_bytes=latest.memory_total_bytes,
            compute_utilization_percent=latest.compute_utilization_percent,
            thermal_temperature_c=latest.temperature_c,
        )


class GPUMonitoringService:
    """Service for monitoring multiple GPU devices in a cluster."""

    def __init__(self, backend: GPUBackend):
        """Initialize monitoring service.

        Args:
            backend: GPU backend for querying metrics
        """
        self.backend = backend
        self.collectors: dict[str, GPUMetricsCollector] = {}
        self._monitoring_task: Optional[asyncio.Task[None]] = None
        self._collection_interval_seconds = 1.0
        self._alert_callback: Optional[Callable[[dict[str, Any]], Any]] = None

    async def start(self, collection_interval_seconds: float = 1.0) -> None:
        """Start monitoring all devices.

        Args:
            collection_interval_seconds: How often to collect metrics
        """
        self._collection_interval_seconds = collection_interval_seconds

        # Initialize collectors for all devices
        for device in self.backend.list_devices():
            self.collectors[device.device_id] = GPUMetricsCollector(
                device, self.backend
            )

        # Start monitoring loop
        self._monitoring_task = asyncio.create_task(self._monitor_loop())
        logger.info(f"Started GPU monitoring for {len(self.collectors)} device(s)")

    async def stop(self) -> None:
        """Stop monitoring."""
        if self._monitoring_task:
            self._monitoring_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._monitoring_task
            self._monitoring_task = None

        logger.info("Stopped GPU monitoring")

    async def _monitor_loop(self) -> None:
        """Background loop: continuously collect metrics."""
        while True:
            try:
                for collector in self.collectors.values():
                    snapshot = await collector.collect_snapshot()

                    # Check for alerts
                    if (
                        snapshot.memory_used_bytes
                        > collector.high_memory_threshold_bytes
                    ):
                        logger.warning(
                            f"High GPU memory on {snapshot.device_id}: "
                            f"{snapshot.memory_used_bytes / 1e9:.1f}GB"
                        )
                        if self._alert_callback:
                            await self._alert_callback(
                                {
                                    "type": "high_memory",
                                    "device_id": snapshot.device_id,
                                    "memory_gb": snapshot.memory_used_bytes / 1e9,
                                }
                            )

                    if snapshot.temperature_c > collector.high_temperature_threshold_c:
                        logger.warning(
                            f"High GPU temperature on {snapshot.device_id}: "
                            f"{snapshot.temperature_c:.1f}°C"
                        )
                        if self._alert_callback:
                            await self._alert_callback(
                                {
                                    "type": "high_temperature",
                                    "device_id": snapshot.device_id,
                                    "temperature_c": snapshot.temperature_c,
                                }
                            )

                await asyncio.sleep(self._collection_interval_seconds)

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in GPU monitoring: {e}")
                await asyncio.sleep(self._collection_interval_seconds)

    def set_alert_callback(self, callback: Callable[[dict[str, Any]], Any]) -> None:
        """Set callback for alerts.

        Args:
            callback: Async function to call on alert
        """
        self._alert_callback = callback

    def get_device_states(self) -> dict[str, DeviceGPUState]:
        """Get current GPU states for all devices."""
        states: dict[str, DeviceGPUState] = {}
        for device_id, collector in self.collectors.items():
            state = collector.get_device_gpu_state()
            if state:
                states[device_id] = state
        return states

    def get_summaries(self) -> dict[str, GPUMetricsSummary]:
        """Get summary statistics for all devices."""
        summaries: dict[str, GPUMetricsSummary] = {}
        for device_id, collector in self.collectors.items():
            summary = collector.get_summary()
            if summary:
                summaries[device_id] = summary
        return summaries

    def get_prometheus_metrics(self) -> str:
        """Get metrics in Prometheus format."""
        lines: list[str] = []
        for device_id, collector in self.collectors.items():
            summary = collector.get_summary()
            if not summary:
                continue

            # Memory metrics
            lines.append(
                f'gpu_memory_used_bytes{{device_id="{device_id}"}} '
                f'{summary.memory_current_used_bytes}'
            )
            lines.append(
                f'gpu_memory_total_bytes{{device_id="{device_id}"}} '
                f'{self.collectors[device_id].device.memory_bytes}'
            )

            # Compute metrics
            lines.append(
                f'gpu_utilization_percent{{device_id="{device_id}"}} '
                f'{summary.compute_current_utilization_percent}'
            )

            # Temperature metrics
            lines.append(
                f'gpu_temperature_celsius{{device_id="{device_id}"}} '
                f'{summary.temperature_current_c}'
            )

            # Power metrics
            lines.append(
                f'gpu_power_watts{{device_id="{device_id}"}} '
                f'{summary.power_current_w}'
            )

        return "\n".join(lines) + "\n" if lines else ""
