"""Thermal-aware inference executor for mobile and high-performance GPUs.

Monitors device temperature and adapts inference execution to prevent
thermal throttling and ensure safe operation on all platforms.

Features:
- Temperature monitoring via GPU backend
- Predictive thermal model (physics-based RC model)
- Proactive pause/resume before overheating
- Precision reduction under thermal stress
- Battery-aware execution on mobile
"""

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Callable, Optional

from exo.gpu.backend import GPUBackend

logger = logging.getLogger(__name__)


@dataclass
class ThermalState:
    """Current thermal state of a GPU device."""

    device_id: str
    current_temperature_c: float
    ambient_temperature_c: float = 25.0
    thermal_throttle_threshold_c: float = 85.0  # Hardware limit
    safe_operating_max_c: float = 75.0  # Conservative safe limit
    junction_to_case_resistance: float = 0.001  # K/W
    case_to_ambient_resistance: float = 0.05  # K/W
    
    # Thermal history
    temperature_history: list[tuple[datetime, float]] = field(default_factory=list)
    power_history: list[tuple[datetime, float]] = field(default_factory=list)
    
    # State flags
    is_throttling: bool = False
    is_paused_for_cooling: bool = False
    last_update: datetime = field(default_factory=datetime.now)

    @property
    def thermal_margin_c(self) -> float:
        """Margin to throttle threshold (positive = safe)."""
        return self.thermal_throttle_threshold_c - self.current_temperature_c

    @property
    def operating_margin_c(self) -> float:
        """Margin to conservative operating limit."""
        return self.safe_operating_max_c - self.current_temperature_c

    def should_pause_inference(self) -> bool:
        """Check if inference should be paused for thermal safety."""
        # Pause if within 5°C of throttle threshold
        return self.thermal_margin_c < 5.0

    def can_resume_inference(self) -> bool:
        """Check if cooled enough to resume inference."""
        # Resume when 10°C below throttle threshold
        return self.thermal_margin_c > 10.0


@dataclass
class ThermalPredictionModel:
    """Physics-based thermal prediction model (RC network).
    
    Uses first-order RC (resistor-capacitor) model:
    dT/dt = (P*R - dT) / tau
    
    Where:
    - P: Power dissipation (W)
    - R: Thermal resistance (K/W)
    - tau: Time constant (seconds)
    """

    device_id: str
    thermal_mass: float = 200.0  # Effective thermal capacity (J/K)
    junction_resistance_k_w: float = 0.001
    case_ambient_resistance_k_w: float = 0.05
    time_constant_seconds: float = 30.0  # Response time

    def predict_temperature(
        self,
        current_temp_c: float,
        power_w: float,
        duration_seconds: float,
        ambient_c: float = 25.0,
    ) -> float:
        """Predict temperature after duration.
        
        Args:
            current_temp_c: Current junction temperature
            power_w: Power dissipation (watts)
            duration_seconds: Time duration
            ambient_c: Ambient temperature
            
        Returns:
            Predicted temperature
        """
        if power_w <= 0:
            # Cooling down exponentially
            temp_drop = (current_temp_c - ambient_c) * (
                1 - (1 / 2.718) ** (duration_seconds / self.time_constant_seconds)
            )
            return current_temp_c - temp_drop
        
        # Heating up with exponential approach to steady-state
        total_resistance = self.junction_resistance_k_w + self.case_ambient_resistance_k_w
        steady_state_temp = ambient_c + power_w * total_resistance
        
        temp_rise = (steady_state_temp - current_temp_c) * (
            1 - (1 / 2.718) ** (duration_seconds / self.time_constant_seconds)
        )
        return current_temp_c + temp_rise

    def estimate_power_for_temperature(
        self,
        current_temp_c: float,
        target_temp_c: float,
        duration_seconds: float,
        ambient_c: float = 25.0,
    ) -> float:
        """Estimate power needed to reach target temperature.
        
        Used for precision reduction planning.
        """
        if duration_seconds <= 0:
            return 0.0
        
        total_resistance = self.junction_resistance_k_w + self.case_ambient_resistance_k_w
        
        # Inverse of heating equation
        exponent = -duration_seconds / self.time_constant_seconds
        factor = (1 - (1 / 2.718) ** exponent) if exponent != 0 else 1.0
        
        if factor > 0:
            required_power = (target_temp_c - ambient_c - (current_temp_c - ambient_c) / factor) / total_resistance
            return max(0.0, required_power)
        
        return 0.0


class ThermalAdaptiveExecutor:
    """Manages thermally-adaptive inference execution.
    
    Monitors GPU temperature and:
    1. Pauses inference before overheating
    2. Reduces precision if temperature climbing
    3. Resumes when cooled
    4. Respects mobile power constraints
    """

    def __init__(
        self,
        backend: GPUBackend,
        device_id: str,
        monitoring_interval_ms: float = 500,
    ):
        """Initialize thermal executor.
        
        Args:
            backend: GPU backend for temperature monitoring
            device_id: Device to monitor
            monitoring_interval_ms: How often to check temperature
        """
        self.backend = backend
        self.device_id = device_id
        self.monitoring_interval = monitoring_interval_ms / 1000.0

        self.thermal_state = ThermalState(device_id=device_id, current_temperature_c=25.0)
        self.prediction_model = ThermalPredictionModel(device_id=device_id)
        
        self._monitoring_task: Optional[asyncio.Task] = None
        self._pause_callback: Optional[Callable[[], None]] = None
        self._resume_callback: Optional[Callable[[], None]] = None
        self._precision_reduce_callback: Optional[Callable[[float], None]] = None

    async def start_monitoring(self) -> None:
        """Start background temperature monitoring."""
        if self._monitoring_task:
            return
        
        self._monitoring_task = asyncio.create_task(self._monitor_loop())
        logger.info(f"Started thermal monitoring for {self.device_id}")

    async def stop_monitoring(self) -> None:
        """Stop temperature monitoring."""
        if self._monitoring_task:
            self._monitoring_task.cancel()
            try:
                await self._monitoring_task
            except asyncio.CancelledError:
                pass
            self._monitoring_task = None
        
        logger.info(f"Stopped thermal monitoring for {self.device_id}")

    async def _monitor_loop(self) -> None:
        """Background loop: monitor temperature and adapt execution."""
        while True:
            try:
                # Get current temperature
                temp = await self.backend.get_device_temperature(self.device_id)
                power = await self.backend.get_device_power_usage(self.device_id)
                
                self.thermal_state.current_temperature_c = temp
                self.thermal_state.temperature_history.append((datetime.now(), temp))
                self.thermal_state.power_history.append((datetime.now(), power))
                
                # Trim history (keep last 60 seconds)
                cutoff = datetime.now() - timedelta(seconds=60)
                self.thermal_state.temperature_history = [
                    (t, v) for t, v in self.thermal_state.temperature_history if t > cutoff
                ]
                self.thermal_state.power_history = [
                    (t, v) for t, v in self.thermal_state.power_history if t > cutoff
                ]
                
                # Check thermal state
                await self._handle_thermal_state()
                
                self.thermal_state.last_update = datetime.now()
                await asyncio.sleep(self.monitoring_interval)
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in thermal monitoring: {e}")
                await asyncio.sleep(self.monitoring_interval)

    async def _handle_thermal_state(self) -> None:
        """Handle thermal state changes."""
        # Check for throttling
        if self.thermal_state.should_pause_inference():
            if not self.thermal_state.is_paused_for_cooling:
                logger.warning(
                    f"Temperature {self.thermal_state.current_temperature_c:.1f}°C "
                    f"approaching limit {self.thermal_state.thermal_throttle_threshold_c}°C, pausing"
                )
                self.thermal_state.is_paused_for_cooling = True
                if self._pause_callback:
                    self._pause_callback()
        
        # Check for resume
        elif self.thermal_state.can_resume_inference() and self.thermal_state.is_paused_for_cooling:
            logger.info(
                f"Temperature {self.thermal_state.current_temperature_c:.1f}°C cooled down, resuming"
            )
            self.thermal_state.is_paused_for_cooling = False
            if self._resume_callback:
                self._resume_callback()
        
        # Reduce precision if needed
        if self.thermal_state.operating_margin_c < 10.0:
            # Predict future temperature under current power
            if self.thermal_state.power_history:
                current_power = self.thermal_state.power_history[-1][1]
                predicted_temp = self.prediction_model.predict_temperature(
                    current_temp_c=self.thermal_state.current_temperature_c,
                    power_w=current_power,
                    duration_seconds=5.0,
                )
                
                if predicted_temp > self.thermal_state.safe_operating_max_c:
                    # Reduce precision
                    precision_ratio = min(1.0, self.thermal_state.operating_margin_c / 10.0)
                    logger.warning(
                        f"Reducing precision to {precision_ratio:.1%} to manage thermal load"
                    )
                    if self._precision_reduce_callback:
                        self._precision_reduce_callback(precision_ratio)

    def set_pause_callback(self, callback: Callable[[], None]) -> None:
        """Set callback when inference should pause."""
        self._pause_callback = callback

    def set_resume_callback(self, callback: Callable[[], None]) -> None:
        """Set callback when inference can resume."""
        self._resume_callback = callback

    def set_precision_reduce_callback(self, callback: Callable[[float], None]) -> None:
        """Set callback when precision should reduce (passed 0.0-1.0 ratio)."""
        self._precision_reduce_callback = callback

    async def get_thermal_status(self) -> dict:
        """Get current thermal status for monitoring/UI."""
        return {
            "device_id": self.device_id,
            "temperature_c": self.thermal_state.current_temperature_c,
            "thermal_margin_c": self.thermal_state.thermal_margin_c,
            "operating_margin_c": self.thermal_state.operating_margin_c,
            "is_throttling": self.thermal_state.is_throttling,
            "is_paused_for_cooling": self.thermal_state.is_paused_for_cooling,
            "last_update_utc": self.thermal_state.last_update.isoformat(),
        }


class ThermalMonitoringDashboard:
    """Multi-device thermal monitoring for cluster overview."""

    def __init__(self):
        self.executors: dict[str, ThermalAdaptiveExecutor] = {}

    def register_executor(self, executor: ThermalAdaptiveExecutor) -> None:
        """Register executor for monitoring."""
        self.executors[executor.device_id] = executor

    async def get_cluster_thermal_status(self) -> dict:
        """Get thermal status of all monitored devices."""
        status = {}
        for device_id, executor in self.executors.items():
            status[device_id] = await executor.get_thermal_status()
        return status

    async def get_highest_temperature(self) -> tuple[str, float]:
        """Get device with highest temperature."""
        max_temp = -1.0
        hottest_device = None
        
        for device_id, executor in self.executors.items():
            if executor.thermal_state.current_temperature_c > max_temp:
                max_temp = executor.thermal_state.current_temperature_c
                hottest_device = device_id
        
        return hottest_device or "unknown", max_temp
