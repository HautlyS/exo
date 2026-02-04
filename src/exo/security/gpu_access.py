"""GPU Access Control - manages permissions for GPU resource access.

Implements role-based access control (RBAC) for GPU operations:
- Device allocation/deallocation
- Memory operations
- Compute operations
- Monitoring/telemetry access

Integrates with Worker's security model and audit logging.
"""

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Optional, Set
from uuid import uuid4

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


class GPUPermission(str, Enum):
    """GPU operation permissions."""

    # Device management
    DEVICE_LIST = "device:list"
    DEVICE_INFO = "device:info"
    DEVICE_ALLOCATE = "device:allocate"

    # Memory operations
    MEMORY_ALLOCATE = "memory:allocate"
    MEMORY_DEALLOCATE = "memory:deallocate"
    MEMORY_COPY_TO_DEVICE = "memory:copy_to_device"
    MEMORY_COPY_FROM_DEVICE = "memory:copy_from_device"
    MEMORY_COPY_DEVICE_TO_DEVICE = "memory:copy_device_to_device"

    # Compute operations
    COMPUTE_EXECUTE = "compute:execute"
    COMPUTE_SYNCHRONIZE = "compute:synchronize"

    # Monitoring
    MONITOR_MEMORY = "monitor:memory"
    MONITOR_TEMPERATURE = "monitor:temperature"
    MONITOR_POWER = "monitor:power"
    MONITOR_CLOCK = "monitor:clock"

    # Administrative
    ADMIN_FULL_ACCESS = "admin:full_access"


class GPURole(str, Enum):
    """Predefined GPU access roles."""

    # Read-only monitoring
    MONITOR = "monitor"

    # Standard compute user
    USER = "user"

    # Power user with advanced features
    POWER_USER = "power_user"

    # Full administrative access
    ADMIN = "admin"


# Role to permissions mapping
ROLE_PERMISSIONS = {
    GPURole.MONITOR: {
        GPUPermission.DEVICE_LIST,
        GPUPermission.DEVICE_INFO,
        GPUPermission.MONITOR_MEMORY,
        GPUPermission.MONITOR_TEMPERATURE,
        GPUPermission.MONITOR_POWER,
        GPUPermission.MONITOR_CLOCK,
    },
    GPURole.USER: {
        GPUPermission.DEVICE_LIST,
        GPUPermission.DEVICE_INFO,
        GPUPermission.MEMORY_ALLOCATE,
        GPUPermission.MEMORY_DEALLOCATE,
        GPUPermission.MEMORY_COPY_TO_DEVICE,
        GPUPermission.MEMORY_COPY_FROM_DEVICE,
        GPUPermission.COMPUTE_EXECUTE,
        GPUPermission.COMPUTE_SYNCHRONIZE,
        GPUPermission.MONITOR_MEMORY,
    },
    GPURole.POWER_USER: {
        GPUPermission.DEVICE_LIST,
        GPUPermission.DEVICE_INFO,
        GPUPermission.DEVICE_ALLOCATE,
        GPUPermission.MEMORY_ALLOCATE,
        GPUPermission.MEMORY_DEALLOCATE,
        GPUPermission.MEMORY_COPY_TO_DEVICE,
        GPUPermission.MEMORY_COPY_FROM_DEVICE,
        GPUPermission.MEMORY_COPY_DEVICE_TO_DEVICE,
        GPUPermission.COMPUTE_EXECUTE,
        GPUPermission.COMPUTE_SYNCHRONIZE,
        GPUPermission.MONITOR_MEMORY,
        GPUPermission.MONITOR_TEMPERATURE,
        GPUPermission.MONITOR_POWER,
        GPUPermission.MONITOR_CLOCK,
    },
    GPURole.ADMIN: {GPUPermission.ADMIN_FULL_ACCESS},  # Grants all permissions
}


@dataclass
class GPUAccessPolicy:
    """GPU access policy for a principal (user/service)."""

    principal_id: str
    """Unique identifier for the principal (user ID, service ID, node ID)"""

    roles: Set[GPURole] = field(default_factory=set)
    """Assigned roles"""

    custom_permissions: Set[GPUPermission] = field(default_factory=set)
    """Additional custom permissions beyond roles"""

    denied_permissions: Set[GPUPermission] = field(default_factory=set)
    """Explicitly denied permissions (overrides grants)"""

    device_restrictions: Optional[Set[str]] = None
    """Restrict access to specific device IDs (None = all devices)"""

    memory_quota_bytes: Optional[int] = None
    """Maximum memory allocation quota (None = unlimited)"""

    created_at: datetime = field(default_factory=lambda: datetime.now(tz=timezone.utc))
    """Policy creation timestamp"""

    expires_at: Optional[datetime] = None
    """Policy expiration (None = never expires)"""

    def get_effective_permissions(self) -> Set[GPUPermission]:
        """Calculate effective permissions from roles and custom permissions."""
        permissions = set(self.custom_permissions)

        # Add role permissions
        for role in self.roles:
            if role == GPURole.ADMIN:
                # Admin has all permissions
                return set(GPUPermission)
            permissions.update(ROLE_PERMISSIONS.get(role, set()))

        # Remove denied permissions
        permissions -= self.denied_permissions

        return permissions

    def has_permission(self, permission: GPUPermission) -> bool:
        """Check if policy grants a specific permission."""
        if self.is_expired():
            return False

        effective = self.get_effective_permissions()

        # Admin role grants everything
        if GPUPermission.ADMIN_FULL_ACCESS in effective:
            return True

        return permission in effective

    def can_access_device(self, device_id: str) -> bool:
        """Check if policy allows access to a specific device."""
        if self.is_expired():
            return False

        if self.device_restrictions is None:
            return True

        return device_id in self.device_restrictions

    def is_expired(self) -> bool:
        """Check if policy has expired."""
        if self.expires_at is None:
            return False

        return datetime.now(tz=timezone.utc) > self.expires_at


class GPUAccessControl:
    """GPU access control manager.

    Manages policies, enforces permissions, integrates with audit logging.
    """

    def __init__(self, audit_logger=None):
        """Initialize GPU access control.

        Args:
            audit_logger: Optional AuditLogger instance for logging access events
        """
        self._policies: dict[str, GPUAccessPolicy] = {}
        self._audit_logger = audit_logger
        self._lock = asyncio.Lock()

        # Track active memory allocations per principal
        self._memory_usage: dict[str, int] = {}

        logger.info("GPU access control initialized")

    async def add_policy(self, policy: GPUAccessPolicy) -> None:
        """Add or update access policy for a principal.

        Args:
            policy: GPUAccessPolicy to add/update
        """
        async with self._lock:
            self._policies[policy.principal_id] = policy
            logger.info(
                f"Added GPU access policy for principal {policy.principal_id} "
                f"with roles: {policy.roles}"
            )

            if self._audit_logger:
                await self._audit_logger.log_policy_change(
                    principal_id=policy.principal_id,
                    action="policy_added",
                    roles=list(policy.roles),
                )

    async def remove_policy(self, principal_id: str) -> None:
        """Remove access policy for a principal.

        Args:
            principal_id: Principal identifier
        """
        async with self._lock:
            if principal_id in self._policies:
                del self._policies[principal_id]
                logger.info(f"Removed GPU access policy for principal {principal_id}")

                if self._audit_logger:
                    await self._audit_logger.log_policy_change(
                        principal_id=principal_id,
                        action="policy_removed",
                    )

    async def check_permission(
        self,
        principal_id: str,
        permission: GPUPermission,
        device_id: Optional[str] = None,
    ) -> bool:
        """Check if principal has permission for an operation.

        Args:
            principal_id: Principal identifier
            permission: Required permission
            device_id: Optional device ID for device-specific checks

        Returns:
            bool: True if permission granted, False otherwise
        """
        async with self._lock:
            policy = self._policies.get(principal_id)

            if policy is None:
                logger.warning(f"No policy found for principal {principal_id}")
                return False

            # Check permission
            if not policy.has_permission(permission):
                logger.warning(
                    f"Permission denied: {principal_id} lacks {permission}"
                )
                return False

            # Check device restriction
            if device_id and not policy.can_access_device(device_id):
                logger.warning(
                    f"Device access denied: {principal_id} cannot access {device_id}"
                )
                return False

            return True

    async def check_memory_quota(
        self,
        principal_id: str,
        requested_bytes: int,
    ) -> bool:
        """Check if memory allocation is within quota.

        Args:
            principal_id: Principal identifier
            requested_bytes: Requested memory size

        Returns:
            bool: True if within quota, False otherwise
        """
        async with self._lock:
            policy = self._policies.get(principal_id)

            if policy is None:
                return False

            # No quota = unlimited
            if policy.memory_quota_bytes is None:
                return True

            current_usage = self._memory_usage.get(principal_id, 0)
            new_usage = current_usage + requested_bytes

            if new_usage > policy.memory_quota_bytes:
                logger.warning(
                    f"Memory quota exceeded: {principal_id} "
                    f"(current: {current_usage}, requested: {requested_bytes}, "
                    f"quota: {policy.memory_quota_bytes})"
                )
                return False

            return True

    async def track_memory_allocation(
        self,
        principal_id: str,
        size_bytes: int,
    ) -> None:
        """Track memory allocation for quota enforcement.

        Args:
            principal_id: Principal identifier
            size_bytes: Allocated memory size
        """
        async with self._lock:
            current = self._memory_usage.get(principal_id, 0)
            self._memory_usage[principal_id] = current + size_bytes

    async def track_memory_deallocation(
        self,
        principal_id: str,
        size_bytes: int,
    ) -> None:
        """Track memory deallocation for quota enforcement.

        Args:
            principal_id: Principal identifier
            size_bytes: Deallocated memory size
        """
        async with self._lock:
            current = self._memory_usage.get(principal_id, 0)
            self._memory_usage[principal_id] = max(0, current - size_bytes)

    async def get_policy(self, principal_id: str) -> Optional[GPUAccessPolicy]:
        """Get policy for a principal.

        Args:
            principal_id: Principal identifier

        Returns:
            GPUAccessPolicy or None if not found
        """
        async with self._lock:
            return self._policies.get(principal_id)

    async def list_policies(self) -> list[GPUAccessPolicy]:
        """List all active policies.

        Returns:
            list[GPUAccessPolicy]: All policies
        """
        async with self._lock:
            return list(self._policies.values())

    async def cleanup_expired_policies(self) -> int:
        """Remove expired policies.

        Returns:
            int: Number of policies removed
        """
        async with self._lock:
            expired = [
                pid for pid, policy in self._policies.items() if policy.is_expired()
            ]

            for pid in expired:
                del self._policies[pid]
                logger.info(f"Removed expired policy for principal {pid}")

            return len(expired)


# ===== Helper Functions =====


def create_default_policy(principal_id: str, role: GPURole) -> GPUAccessPolicy:
    """Create a default policy with a single role.

    Args:
        principal_id: Principal identifier
        role: GPU role to assign

    Returns:
        GPUAccessPolicy: New policy
    """
    return GPUAccessPolicy(
        principal_id=principal_id,
        roles={role},
    )


def create_admin_policy(principal_id: str) -> GPUAccessPolicy:
    """Create an admin policy with full access.

    Args:
        principal_id: Principal identifier

    Returns:
        GPUAccessPolicy: Admin policy
    """
    return GPUAccessPolicy(
        principal_id=principal_id,
        roles={GPURole.ADMIN},
    )
