"""Tests for audit logging."""

import pytest
import tempfile
from pathlib import Path
from datetime import datetime, timedelta, timezone

from exo.security.audit_log import (
    AuditLogger,
    AuditEvent,
    AuditEventType,
    AuditEventSeverity,
)


class TestAuditEvent:
    """Test audit event."""

    def test_event_creation(self):
        """Test creating an audit event."""
        event = AuditEvent(
            event_type=AuditEventType.MEMORY_ALLOCATE,
            principal_id="user1",
            device_id="cuda:0",
            result="success",
        )

        assert event.event_type == AuditEventType.MEMORY_ALLOCATE
        assert event.principal_id == "user1"
        assert event.device_id == "cuda:0"
        assert event.result == "success"

    def test_event_to_dict(self):
        """Test converting event to dictionary."""
        event = AuditEvent(
            event_type=AuditEventType.MEMORY_ALLOCATE,
            principal_id="user1",
            device_id="cuda:0",
            result="success",
        )

        data = event.to_dict()

        assert data["event_type"] == "memory.allocate"
        assert data["principal_id"] == "user1"
        assert data["device_id"] == "cuda:0"
        assert "timestamp" in data

    def test_event_to_json(self):
        """Test converting event to JSON."""
        event = AuditEvent(
            event_type=AuditEventType.MEMORY_ALLOCATE,
            principal_id="user1",
        )

        json_str = event.to_json()

        assert isinstance(json_str, str)
        assert "memory.allocate" in json_str
        assert "user1" in json_str


class TestAuditLogger:
    """Test audit logger."""

    @pytest.mark.asyncio
    async def test_logger_initialization(self):
        """Test initializing audit logger."""
        with tempfile.TemporaryDirectory() as tmpdir:
            log_file = Path(tmpdir) / "audit.log"

            logger = AuditLogger(log_file=log_file, enable_console=False)

            assert logger.log_file == log_file
            assert log_file.parent.exists()

            await logger.shutdown()

    @pytest.mark.asyncio
    async def test_log_event(self):
        """Test logging an event."""
        with tempfile.TemporaryDirectory() as tmpdir:
            log_file = Path(tmpdir) / "audit.log"

            logger = AuditLogger(
                log_file=log_file,
                enable_console=False,
                buffer_size=1,  # Flush immediately
            )

            event = AuditEvent(
                event_type=AuditEventType.MEMORY_ALLOCATE,
                principal_id="user1",
                device_id="cuda:0",
                result="success",
            )

            await logger.log_event(event)
            await logger.shutdown()

            # Check log file
            assert log_file.exists()
            content = log_file.read_text()
            assert "memory.allocate" in content
            assert "user1" in content

    @pytest.mark.asyncio
    async def test_log_gpu_operation(self):
        """Test logging GPU operation."""
        with tempfile.TemporaryDirectory() as tmpdir:
            log_file = Path(tmpdir) / "audit.log"

            logger = AuditLogger(
                log_file=log_file,
                enable_console=False,
                buffer_size=1,
            )

            await logger.log_gpu_operation(
                event_type=AuditEventType.COMPUTE_EXECUTE,
                principal_id="user1",
                device_id="cuda:0",
                result="success",
            )

            await logger.shutdown()

            # Check log file
            content = log_file.read_text()
            assert "compute.execute" in content

    @pytest.mark.asyncio
    async def test_log_access_denied(self):
        """Test logging access denied event."""
        with tempfile.TemporaryDirectory() as tmpdir:
            log_file = Path(tmpdir) / "audit.log"

            logger = AuditLogger(
                log_file=log_file,
                enable_console=False,
                buffer_size=1,
            )

            await logger.log_access_denied(
                principal_id="user1",
                operation="memory_allocate",
                device_id="cuda:0",
                reason="insufficient permissions",
            )

            await logger.shutdown()

            # Check log file
            content = log_file.read_text()
            assert "security.access_denied" in content
            assert "insufficient permissions" in content

    @pytest.mark.asyncio
    async def test_log_quota_exceeded(self):
        """Test logging quota exceeded event."""
        with tempfile.TemporaryDirectory() as tmpdir:
            log_file = Path(tmpdir) / "audit.log"

            logger = AuditLogger(
                log_file=log_file,
                enable_console=False,
                buffer_size=1,
            )

            await logger.log_quota_exceeded(
                principal_id="user1",
                requested_bytes=2 * 1024**3,
                quota_bytes=1 * 1024**3,
                current_usage=512 * 1024**2,
            )

            await logger.shutdown()

            # Check log file
            content = log_file.read_text()
            assert "security.quota_exceeded" in content

    @pytest.mark.asyncio
    async def test_log_policy_change(self):
        """Test logging policy change event."""
        with tempfile.TemporaryDirectory() as tmpdir:
            log_file = Path(tmpdir) / "audit.log"

            logger = AuditLogger(
                log_file=log_file,
                enable_console=False,
                buffer_size=1,
            )

            await logger.log_policy_change(
                principal_id="user1",
                action="policy_added",
                roles=["user", "monitor"],
            )

            await logger.shutdown()

            # Check log file
            content = log_file.read_text()
            assert "security.policy_added" in content

    @pytest.mark.asyncio
    async def test_log_system_event(self):
        """Test logging system event."""
        with tempfile.TemporaryDirectory() as tmpdir:
            log_file = Path(tmpdir) / "audit.log"

            logger = AuditLogger(
                log_file=log_file,
                enable_console=False,
                buffer_size=1,
            )

            await logger.log_system_event(
                event_type=AuditEventType.BACKEND_INITIALIZED,
                message="CUDA backend initialized",
                metadata={"devices": 2},
            )

            await logger.shutdown()

            # Check log file
            content = log_file.read_text()
            assert "system.backend_initialized" in content

    @pytest.mark.asyncio
    async def test_buffer_flushing(self):
        """Test buffer flushing."""
        with tempfile.TemporaryDirectory() as tmpdir:
            log_file = Path(tmpdir) / "audit.log"

            logger = AuditLogger(
                log_file=log_file,
                enable_console=False,
                buffer_size=10,  # Buffer 10 events
            )

            # Log 5 events (should not flush yet)
            for i in range(5):
                await logger.log_gpu_operation(
                    event_type=AuditEventType.MEMORY_ALLOCATE,
                    principal_id=f"user{i}",
                    device_id="cuda:0",
                )

            # File should be empty or small
            if log_file.exists():
                size_before = log_file.stat().st_size
            else:
                size_before = 0

            # Log 10 more events (should trigger flush)
            for i in range(10):
                await logger.log_gpu_operation(
                    event_type=AuditEventType.MEMORY_ALLOCATE,
                    principal_id=f"user{i+5}",
                    device_id="cuda:0",
                )

            await logger.shutdown()

            # File should have content
            size_after = log_file.stat().st_size
            assert size_after > size_before

    @pytest.mark.asyncio
    async def test_query_events(self):
        """Test querying events from log."""
        with tempfile.TemporaryDirectory() as tmpdir:
            log_file = Path(tmpdir) / "audit.log"

            logger = AuditLogger(
                log_file=log_file,
                enable_console=False,
                buffer_size=1,
            )

            # Log multiple events
            await logger.log_gpu_operation(
                event_type=AuditEventType.MEMORY_ALLOCATE,
                principal_id="user1",
                device_id="cuda:0",
            )

            await logger.log_gpu_operation(
                event_type=AuditEventType.COMPUTE_EXECUTE,
                principal_id="user2",
                device_id="cuda:1",
            )

            await logger.log_gpu_operation(
                event_type=AuditEventType.MEMORY_ALLOCATE,
                principal_id="user1",
                device_id="cuda:0",
            )

            # Query events
            events = await logger.query_events(
                principal_id="user1",
                limit=10,
            )

            assert len(events) == 2
            assert all(e.principal_id == "user1" for e in events)

            # Query by event type
            events = await logger.query_events(
                event_type=AuditEventType.COMPUTE_EXECUTE,
                limit=10,
            )

            assert len(events) == 1
            assert events[0].event_type == AuditEventType.COMPUTE_EXECUTE

            await logger.shutdown()

    @pytest.mark.asyncio
    async def test_query_events_time_range(self):
        """Test querying events by time range."""
        with tempfile.TemporaryDirectory() as tmpdir:
            log_file = Path(tmpdir) / "audit.log"

            logger = AuditLogger(
                log_file=log_file,
                enable_console=False,
                buffer_size=1,
            )

            now = datetime.now(tz=timezone.utc)

            # Log event
            await logger.log_gpu_operation(
                event_type=AuditEventType.MEMORY_ALLOCATE,
                principal_id="user1",
                device_id="cuda:0",
            )

            # Query with time range
            events = await logger.query_events(
                start_time=now - timedelta(minutes=1),
                end_time=now + timedelta(minutes=1),
                limit=10,
            )

            assert len(events) >= 1

            # Query with future time range (should be empty)
            events = await logger.query_events(
                start_time=now + timedelta(hours=1),
                limit=10,
            )

            assert len(events) == 0

            await logger.shutdown()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
