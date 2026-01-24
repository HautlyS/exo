"""GPU telemetry collection for cluster state tracking.

This module handles periodic GPU device monitoring and sends telemetry
events to the master for CSP placement decisions.

Key responsibilities:
- Periodic device state collection (memory, thermal, utilization)
- Event emission for state changes
- Integration with GPU backend abstraction
"""

import asyncio
import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Callable

from exo.gpu.backend import GPUBackend
from exo.gpu.discovery import GPUDiscoveryService
from exo.shared.types.common import NodeId
from exo.shared.types.events import DeviceGPUStateUpdated
from exo.shared.types.state import DeviceGPUState

logger = logging.getLogger(__name__)


@dataclass
class GPUTelemetryConfig:
    """Configuration for GPU telemetry collection."""

    collection_interval_seconds: float = 2.0
    """How often to collect GPU metrics."""

    enable_temperature_monitoring: bool = True
    """Whether to collect temperature metrics."""

    enable_power_monitoring: bool = True
    """Whether to collect power metrics."""

    enable_memory_monitoring: bool = True
    """Whether to collect memory metrics."""

    enable_compute_monitoring: bool = True
    """Whether to collect utilization metrics."""


class GPUTelemetryCollector:
    """Collects GPU device state and emits telemetry events.

    Periodically queries GPU backend for device metrics and sends
    DeviceGPUStateUpdated events for cluster state management.
    """

    def __init__(
        self,
        node_id: NodeId,
        gpu_backend: GPUBackend,
        event_emitter: Callable[[DeviceGPUStateUpdated], Any],
        config: GPUTelemetryConfig | None = None,
    ):
        """Initialize GPU telemetry collector.

        Args:
            node_id: ID of this node (for state tracking)
            gpu_backend: GPU backend to query for metrics
            event_emitter: Callback to emit DeviceGPUStateUpdated events
            config: Optional telemetry configuration
        """
        self.node_id = node_id
        self.gpu_backend = gpu_backend
        self.event_emitter = event_emitter
        self.config = config or GPUTelemetryConfig()

        self._monitoring_task: asyncio.Task[None] | None = None
        self._is_running = False
        self._last_states: dict[str, DeviceGPUState] = {}

    async def start_monitoring(self) -> None:
        """Start periodic GPU telemetry collection.

        Launches background task that collects device metrics at regular
        intervals and emits events.

        Raises:
            RuntimeError: If monitoring is already running.
        """
        if self._is_running:
            raise RuntimeError("GPU telemetry monitoring already running")

        self._is_running = True
        self._monitoring_task = asyncio.create_task(self._monitoring_loop())
        logger.info(
            f"Started GPU telemetry monitoring (interval={self.config.collection_interval_seconds}s)"
        )

    async def stop_monitoring(self) -> None:
        """Stop GPU telemetry collection.

        Cancels background monitoring task and cleans up resources.
        """
        if not self._is_running:
            return

        self._is_running = False
        if self._monitoring_task:
            self._monitoring_task.cancel()
            try:
                await self._monitoring_task
            except asyncio.CancelledError:
                pass
        logger.info("Stopped GPU telemetry monitoring")

    async def collect_device_state(self) -> dict[str, DeviceGPUState]:
        """Collect current GPU device state.

        Returns:
            Dict mapping device_id -> DeviceGPUState with current metrics.
        """
        states: dict[str, DeviceGPUState] = {}

        try:
            devices = self.gpu_backend.list_devices()
        except Exception as e:
            logger.error(f"Failed to list GPU devices: {e}")
            return states

        for device in devices:
            device_id = device.device_id

            try:
                # Collect metrics (handle unavailable metrics gracefully)
                memory_info = await self._safe_call(
                    self.gpu_backend.get_device_memory_info, device_id
                )
                temperature = await self._safe_call(
                    self.gpu_backend.get_device_temperature, device_id
                )
                power_usage = await self._safe_call(
                    self.gpu_backend.get_device_power_usage, device_id
                )
                clock_rate = await self._safe_call(
                    self.gpu_backend.get_device_clock_rate, device_id
                )

                # Create state object
                state = DeviceGPUState(
                    device_id=device_id,
                    node_id=self.node_id,
                    memory_used_bytes=memory_info.get("used_bytes", 0),
                    memory_total_bytes=memory_info.get("total_bytes", device.memory_bytes),
                    compute_utilization_percent=memory_info.get("utilization_percent", 0.0),
                    thermal_temperature_c=temperature or -1.0,
                    thermal_throttle_threshold_c=device.max_clock_rate_mhz * 2.0 / 100.0 + 70.0,  # Rough estimate
                    battery_percent=100.0,
                    is_plugged_in=True,
                    last_update=datetime.now(),
                )

                states[device_id] = state

            except Exception as e:
                logger.error(f"Failed to collect telemetry for device {device_id}: {e}")
                continue

        return states

    async def _monitoring_loop(self) -> None:
        """Background monitoring loop.

        Periodically collects device state and emits events if changes detected.
        """
        while self._is_running:
            try:
                await asyncio.sleep(self.config.collection_interval_seconds)

                # Collect current state
                current_states = await self.collect_device_state()

                # Emit events for changed devices
                for device_id, device_state in current_states.items():
                    last_state = self._last_states.get(device_id)

                    # Emit if new device or state changed significantly
                    if self._should_emit_event(last_state, device_state):
                        try:
                            event = DeviceGPUStateUpdated(device_state=device_state)
                            self.event_emitter(event)
                        except Exception as e:
                            logger.error(f"Failed to emit GPU state event: {e}")

                # Update last known state
                self._last_states = current_states

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Unexpected error in GPU telemetry loop: {e}")
                await asyncio.sleep(1.0)

    def _should_emit_event(
        self,
        last_state: DeviceGPUState | None,
        current_state: DeviceGPUState,
    ) -> bool:
        """Determine if state change warrants event emission.

        Emits events for:
        - New devices (no last_state)
        - Memory changes >1% absolute
        - Temperature changes >5°C
        - Utilization changes >10% absolute

        Args:
            last_state: Previous device state (or None if new)
            current_state: Current device state

        Returns:
            True if event should be emitted.
        """
        if last_state is None:
            return True

        # Check memory change
        if last_state.memory_total_bytes > 0:
            memory_change_pct = abs(
                last_state.memory_utilization_percent - current_state.memory_utilization_percent
            )
            if memory_change_pct > 1.0:
                return True

        # Check temperature change
        if last_state.thermal_temperature_c >= 0 and current_state.thermal_temperature_c >= 0:
            temp_change = abs(
                last_state.thermal_temperature_c - current_state.thermal_temperature_c
            )
            if temp_change > 5.0:
                return True

        # Check compute utilization change
        if abs(
            last_state.compute_utilization_percent - current_state.compute_utilization_percent
        ) > 10.0:
            return True

        # Check thermal throttling status
        if last_state.is_thermal_throttling != current_state.is_thermal_throttling:
            return True

        return False

    async def _safe_call(self, coro_func: Callable, *args: Any, **kwargs: Any) -> Any:
        """Safely call async GPU backend method.

        Returns empty dict/None on error rather than raising.
        """
        try:
            return await coro_func(*args, **kwargs)
        except Exception as e:
            logger.warning(f"GPU backend call failed: {e}")
            return None if "return" not in str(coro_func) else {}
