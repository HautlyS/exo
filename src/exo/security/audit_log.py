"""Audit Logging - comprehensive logging of GPU operations for security and compliance.

Logs all GPU operations with:
- Timestamp
- Principal (user/service)
- Operation type
- Device ID
- Result (success/failure)
- Additional metadata

Supports multiple backends:
- File-based logging (JSON lines)
- Syslog integration
- Remote logging service
"""

import asyncio
import json
import logging
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Optional, Any
from uuid import uuid4

logger = logging.getLogger(__name__)


class AuditEventType(str, Enum):
    """Types of auditable GPU events."""

    # Device operations
    DEVICE_LIST = "device.list"
    DEVICE_INFO = "device.info"
    DEVICE_ALLOCATE = "device.allocate"

    # Memory operations
    MEMORY_ALLOCATE = "memory.allocate"
    MEMORY_DEALLOCATE = "memory.deallocate"
    MEMORY_COPY_TO_DEVICE = "memory.copy_to_device"
    MEMORY_COPY_FROM_DEVICE = "memory.copy_from_device"
    MEMORY_COPY_DEVICE_TO_DEVICE = "memory.copy_device_to_device"

    # Compute operations
    COMPUTE_EXECUTE = "compute.execute"
    COMPUTE_SYNCHRONIZE = "compute.synchronize"

    # Monitoring
    MONITOR_MEMORY = "monitor.memory"
    MONITOR_TEMPERATURE = "monitor.temperature"
    MONITOR_POWER = "monitor.power"
    MONITOR_CLOCK = "monitor.clock"

    # Security events
    ACCESS_DENIED = "security.access_denied"
    QUOTA_EXCEEDED = "security.quota_exceeded"
    POLICY_ADDED = "security.policy_added"
    POLICY_REMOVED = "security.policy_removed"
    POLICY_UPDATED = "security.policy_updated"

    # System events
    BACKEND_INITIALIZED = "system.backend_initialized"
    BACKEND_SHUTDOWN = "system.backend_shutdown"
    DISCOVERY_STARTED = "system.discovery_started"
    DISCOVERY_COMPLETED = "system.discovery_completed"


class AuditEventSeverity(str, Enum):
    """Severity levels for audit events."""

    DEBUG = "debug"
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


@dataclass
class AuditEvent:
    """Audit event record."""

    event_id: str = field(default_factory=lambda: str(uuid4()))
    """Unique event identifier"""

    timestamp: datetime = field(default_factory=lambda: datetime.now(tz=timezone.utc))
    """Event timestamp (UTC)"""

    event_type: AuditEventType = AuditEventType.DEVICE_LIST
    """Type of event"""

    severity: AuditEventSeverity = AuditEventSeverity.INFO
    """Event severity"""

    principal_id: Optional[str] = None
    """Principal (user/service) performing the operation"""

    device_id: Optional[str] = None
    """GPU device ID (if applicable)"""

    operation: Optional[str] = None
    """Operation description"""

    result: str = "success"
    """Operation result: 'success', 'failure', 'denied'"""

    error_message: Optional[str] = None
    """Error message (if result is failure)"""

    metadata: dict[str, Any] = field(default_factory=dict)
    """Additional event metadata"""

    node_id: Optional[str] = None
    """Node ID where event occurred"""

    session_id: Optional[str] = None
    """Session ID (for tracking related operations)"""

    def to_dict(self) -> dict:
        """Convert to dictionary for serialization."""
        data = asdict(self)
        # Convert datetime to ISO format
        data["timestamp"] = self.timestamp.isoformat()
        # Convert enums to strings
        data["event_type"] = self.event_type.value
        data["severity"] = self.severity.value
        return data

    def to_json(self) -> str:
        """Convert to JSON string."""
        return json.dumps(self.to_dict())


class AuditLogger:
    """Audit logger for GPU operations.

    Supports multiple backends and async logging to avoid blocking GPU operations.
    """

    def __init__(
        self,
        log_file: Optional[Path] = None,
        enable_console: bool = True,
        buffer_size: int = 100,
    ):
        """Initialize audit logger.

        Args:
            log_file: Path to audit log file (JSON lines format)
            enable_console: Whether to log to console (via Python logging)
            buffer_size: Number of events to buffer before flushing
        """
        if log_file is None:
            log_file = Path.home() / ".exo" / "audit.log"

        self.log_file = log_file
        self.enable_console = enable_console
        self.buffer_size = buffer_size

        self._buffer: list[AuditEvent] = []
        self._lock = asyncio.Lock()
        self._flush_task: Optional[asyncio.Task] = None
        self._shutdown = False

        # Ensure log directory exists
        self.log_file.parent.mkdir(parents=True, exist_ok=True)

        logger.info(f"Audit logger initialized: {self.log_file}")

    async def log_event(self, event: AuditEvent) -> None:
        """Log an audit event.

        Args:
            event: AuditEvent to log
        """
        async with self._lock:
            self._buffer.append(event)

            # Console logging
            if self.enable_console:
                self._log_to_console(event)

            # Flush if buffer is full
            if len(self._buffer) >= self.buffer_size:
                await self._flush_buffer()

    async def log_gpu_operation(
        self,
        event_type: AuditEventType,
        principal_id: str,
        device_id: Optional[str] = None,
        result: str = "success",
        error_message: Optional[str] = None,
        metadata: Optional[dict] = None,
    ) -> None:
        """Log a GPU operation.

        Args:
            event_type: Type of operation
            principal_id: Principal performing operation
            device_id: Device ID (if applicable)
            result: Operation result
            error_message: Error message (if failed)
            metadata: Additional metadata
        """
        severity = AuditEventSeverity.INFO
        if result == "failure":
            severity = AuditEventSeverity.ERROR
        elif result == "denied":
            severity = AuditEventSeverity.WARNING

        event = AuditEvent(
            event_type=event_type,
            severity=severity,
            principal_id=principal_id,
            device_id=device_id,
            result=result,
            error_message=error_message,
            metadata=metadata or {},
        )

        await self.log_event(event)

    async def log_access_denied(
        self,
        principal_id: str,
        operation: str,
        device_id: Optional[str] = None,
        reason: Optional[str] = None,
    ) -> None:
        """Log an access denied event.

        Args:
            principal_id: Principal that was denied
            operation: Operation that was denied
            device_id: Device ID (if applicable)
            reason: Reason for denial
        """
        event = AuditEvent(
            event_type=AuditEventType.ACCESS_DENIED,
            severity=AuditEventSeverity.WARNING,
            principal_id=principal_id,
            device_id=device_id,
            operation=operation,
            result="denied",
            metadata={"reason": reason} if reason else {},
        )

        await self.log_event(event)

    async def log_quota_exceeded(
        self,
        principal_id: str,
        requested_bytes: int,
        quota_bytes: int,
        current_usage: int,
    ) -> None:
        """Log a quota exceeded event.

        Args:
            principal_id: Principal that exceeded quota
            requested_bytes: Requested memory size
            quota_bytes: Memory quota
            current_usage: Current memory usage
        """
        event = AuditEvent(
            event_type=AuditEventType.QUOTA_EXCEEDED,
            severity=AuditEventSeverity.WARNING,
            principal_id=principal_id,
            result="denied",
            metadata={
                "requested_bytes": requested_bytes,
                "quota_bytes": quota_bytes,
                "current_usage": current_usage,
            },
        )

        await self.log_event(event)

    async def log_policy_change(
        self,
        principal_id: str,
        action: str,
        roles: Optional[list[str]] = None,
    ) -> None:
        """Log a policy change event.

        Args:
            principal_id: Principal whose policy changed
            action: Action performed (policy_added, policy_removed, policy_updated)
            roles: Roles assigned (if applicable)
        """
        event_type_map = {
            "policy_added": AuditEventType.POLICY_ADDED,
            "policy_removed": AuditEventType.POLICY_REMOVED,
            "policy_updated": AuditEventType.POLICY_UPDATED,
        }

        event = AuditEvent(
            event_type=event_type_map.get(action, AuditEventType.POLICY_UPDATED),
            severity=AuditEventSeverity.INFO,
            principal_id=principal_id,
            result="success",
            metadata={"roles": roles} if roles else {},
        )

        await self.log_event(event)

    async def log_system_event(
        self,
        event_type: AuditEventType,
        message: str,
        metadata: Optional[dict] = None,
    ) -> None:
        """Log a system event.

        Args:
            event_type: Type of system event
            message: Event message
            metadata: Additional metadata
        """
        event = AuditEvent(
            event_type=event_type,
            severity=AuditEventSeverity.INFO,
            operation=message,
            result="success",
            metadata=metadata or {},
        )

        await self.log_event(event)

    async def _flush_buffer(self) -> None:
        """Flush buffered events to log file."""
        if not self._buffer:
            return

        try:
            with open(self.log_file, "a") as f:
                for event in self._buffer:
                    f.write(event.to_json() + "\n")

            logger.debug(f"Flushed {len(self._buffer)} audit events to {self.log_file}")
            self._buffer.clear()

        except Exception as e:
            logger.error(f"Failed to flush audit log: {e}")

    def _log_to_console(self, event: AuditEvent) -> None:
        """Log event to console via Python logging."""
        log_level = {
            AuditEventSeverity.DEBUG: logging.DEBUG,
            AuditEventSeverity.INFO: logging.INFO,
            AuditEventSeverity.WARNING: logging.WARNING,
            AuditEventSeverity.ERROR: logging.ERROR,
            AuditEventSeverity.CRITICAL: logging.CRITICAL,
        }.get(event.severity, logging.INFO)

        message = (
            f"[AUDIT] {event.event_type.value} | "
            f"principal={event.principal_id} | "
            f"device={event.device_id} | "
            f"result={event.result}"
        )

        if event.error_message:
            message += f" | error={event.error_message}"

        logger.log(log_level, message)

    async def start_auto_flush(self, interval_seconds: float = 5.0) -> None:
        """Start automatic periodic flushing.

        Args:
            interval_seconds: Flush interval in seconds
        """
        if self._flush_task is not None:
            return

        async def auto_flush():
            while not self._shutdown:
                await asyncio.sleep(interval_seconds)
                async with self._lock:
                    await self._flush_buffer()

        self._flush_task = asyncio.create_task(auto_flush())
        logger.info(f"Started auto-flush with interval {interval_seconds}s")

    async def shutdown(self) -> None:
        """Shutdown audit logger and flush remaining events."""
        self._shutdown = True

        if self._flush_task:
            self._flush_task.cancel()
            try:
                await self._flush_task
            except asyncio.CancelledError:
                pass

        async with self._lock:
            await self._flush_buffer()

        logger.info("Audit logger shutdown")

    async def query_events(
        self,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        principal_id: Optional[str] = None,
        event_type: Optional[AuditEventType] = None,
        limit: int = 100,
    ) -> list[AuditEvent]:
        """Query audit events from log file.

        Args:
            start_time: Filter events after this time
            end_time: Filter events before this time
            principal_id: Filter by principal
            event_type: Filter by event type
            limit: Maximum number of events to return

        Returns:
            list[AuditEvent]: Matching events
        """
        events = []

        try:
            if not self.log_file.exists():
                return events

            with open(self.log_file, "r") as f:
                for line in f:
                    if len(events) >= limit:
                        break

                    try:
                        data = json.loads(line)

                        # Parse timestamp
                        timestamp = datetime.fromisoformat(data["timestamp"])

                        # Apply filters
                        if start_time and timestamp < start_time:
                            continue
                        if end_time and timestamp > end_time:
                            continue
                        if principal_id and data.get("principal_id") != principal_id:
                            continue
                        if event_type and data.get("event_type") != event_type.value:
                            continue

                        # Reconstruct event
                        event = AuditEvent(
                            event_id=data["event_id"],
                            timestamp=timestamp,
                            event_type=AuditEventType(data["event_type"]),
                            severity=AuditEventSeverity(data["severity"]),
                            principal_id=data.get("principal_id"),
                            device_id=data.get("device_id"),
                            operation=data.get("operation"),
                            result=data["result"],
                            error_message=data.get("error_message"),
                            metadata=data.get("metadata", {}),
                            node_id=data.get("node_id"),
                            session_id=data.get("session_id"),
                        )

                        events.append(event)

                    except Exception as e:
                        logger.debug(f"Failed to parse audit log line: {e}")
                        continue

        except Exception as e:
            logger.error(f"Failed to query audit log: {e}")

        return events
