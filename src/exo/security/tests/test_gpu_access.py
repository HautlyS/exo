"""Tests for GPU access control."""

import pytest
from datetime import datetime, timedelta, timezone

from exo.security.gpu_access import (
    GPUAccessControl,
    GPUAccessPolicy,
    GPUPermission,
    GPURole,
    create_default_policy,
    create_admin_policy,
)


class TestGPUAccessPolicy:
    """Test GPU access policy."""

    def test_policy_creation(self):
        """Test creating a policy."""
        policy = GPUAccessPolicy(
            principal_id="user1",
            roles={GPURole.USER},
        )

        assert policy.principal_id == "user1"
        assert GPURole.USER in policy.roles
        assert not policy.is_expired()

    def test_effective_permissions(self):
        """Test calculating effective permissions."""
        policy = GPUAccessPolicy(
            principal_id="user1",
            roles={GPURole.USER},
        )

        perms = policy.get_effective_permissions()

        assert GPUPermission.MEMORY_ALLOCATE in perms
        assert GPUPermission.COMPUTE_EXECUTE in perms
        assert GPUPermission.ADMIN_FULL_ACCESS not in perms

    def test_admin_role(self):
        """Test admin role grants all permissions."""
        policy = GPUAccessPolicy(
            principal_id="admin1",
            roles={GPURole.ADMIN},
        )

        perms = policy.get_effective_permissions()

        # Admin should have all permissions
        assert len(perms) == len(GPUPermission)

    def test_custom_permissions(self):
        """Test custom permissions."""
        policy = GPUAccessPolicy(
            principal_id="user1",
            roles={GPURole.MONITOR},
            custom_permissions={GPUPermission.MEMORY_ALLOCATE},
        )

        perms = policy.get_effective_permissions()

        # Should have monitor permissions + custom
        assert GPUPermission.MONITOR_MEMORY in perms
        assert GPUPermission.MEMORY_ALLOCATE in perms

    def test_denied_permissions(self):
        """Test denied permissions override grants."""
        policy = GPUAccessPolicy(
            principal_id="user1",
            roles={GPURole.USER},
            denied_permissions={GPUPermission.MEMORY_ALLOCATE},
        )

        perms = policy.get_effective_permissions()

        # Should not have denied permission
        assert GPUPermission.MEMORY_ALLOCATE not in perms
        assert GPUPermission.COMPUTE_EXECUTE in perms

    def test_device_restrictions(self):
        """Test device access restrictions."""
        policy = GPUAccessPolicy(
            principal_id="user1",
            roles={GPURole.USER},
            device_restrictions={"cuda:0", "cuda:1"},
        )

        assert policy.can_access_device("cuda:0")
        assert policy.can_access_device("cuda:1")
        assert not policy.can_access_device("cuda:2")

    def test_no_device_restrictions(self):
        """Test no device restrictions allows all."""
        policy = GPUAccessPolicy(
            principal_id="user1",
            roles={GPURole.USER},
        )

        assert policy.can_access_device("cuda:0")
        assert policy.can_access_device("any_device")

    def test_policy_expiration(self):
        """Test policy expiration."""
        # Expired policy
        policy = GPUAccessPolicy(
            principal_id="user1",
            roles={GPURole.USER},
            expires_at=datetime.now(tz=timezone.utc) - timedelta(hours=1),
        )

        assert policy.is_expired()
        assert not policy.has_permission(GPUPermission.MEMORY_ALLOCATE)

    def test_policy_not_expired(self):
        """Test policy not expired."""
        policy = GPUAccessPolicy(
            principal_id="user1",
            roles={GPURole.USER},
            expires_at=datetime.now(tz=timezone.utc) + timedelta(hours=1),
        )

        assert not policy.is_expired()
        assert policy.has_permission(GPUPermission.MEMORY_ALLOCATE)


class TestGPUAccessControl:
    """Test GPU access control manager."""

    @pytest.mark.asyncio
    async def test_add_policy(self):
        """Test adding a policy."""
        control = GPUAccessControl()

        policy = create_default_policy("user1", GPURole.USER)
        await control.add_policy(policy)

        retrieved = await control.get_policy("user1")
        assert retrieved is not None
        assert retrieved.principal_id == "user1"

    @pytest.mark.asyncio
    async def test_remove_policy(self):
        """Test removing a policy."""
        control = GPUAccessControl()

        policy = create_default_policy("user1", GPURole.USER)
        await control.add_policy(policy)

        await control.remove_policy("user1")

        retrieved = await control.get_policy("user1")
        assert retrieved is None

    @pytest.mark.asyncio
    async def test_check_permission_granted(self):
        """Test checking granted permission."""
        control = GPUAccessControl()

        policy = create_default_policy("user1", GPURole.USER)
        await control.add_policy(policy)

        has_perm = await control.check_permission(
            "user1",
            GPUPermission.MEMORY_ALLOCATE,
        )

        assert has_perm

    @pytest.mark.asyncio
    async def test_check_permission_denied(self):
        """Test checking denied permission."""
        control = GPUAccessControl()

        policy = create_default_policy("user1", GPURole.MONITOR)
        await control.add_policy(policy)

        has_perm = await control.check_permission(
            "user1",
            GPUPermission.MEMORY_ALLOCATE,
        )

        assert not has_perm

    @pytest.mark.asyncio
    async def test_check_permission_no_policy(self):
        """Test checking permission with no policy."""
        control = GPUAccessControl()

        has_perm = await control.check_permission(
            "unknown_user",
            GPUPermission.MEMORY_ALLOCATE,
        )

        assert not has_perm

    @pytest.mark.asyncio
    async def test_check_device_access(self):
        """Test checking device access."""
        control = GPUAccessControl()

        policy = GPUAccessPolicy(
            principal_id="user1",
            roles={GPURole.USER},
            device_restrictions={"cuda:0"},
        )
        await control.add_policy(policy)

        # Allowed device
        has_access = await control.check_permission(
            "user1",
            GPUPermission.MEMORY_ALLOCATE,
            device_id="cuda:0",
        )
        assert has_access

        # Denied device
        has_access = await control.check_permission(
            "user1",
            GPUPermission.MEMORY_ALLOCATE,
            device_id="cuda:1",
        )
        assert not has_access

    @pytest.mark.asyncio
    async def test_memory_quota(self):
        """Test memory quota enforcement."""
        control = GPUAccessControl()

        policy = GPUAccessPolicy(
            principal_id="user1",
            roles={GPURole.USER},
            memory_quota_bytes=1024 * 1024 * 1024,  # 1GB
        )
        await control.add_policy(policy)

        # Within quota
        within = await control.check_memory_quota("user1", 512 * 1024 * 1024)
        assert within

        # Exceeds quota
        exceeds = await control.check_memory_quota("user1", 2 * 1024 * 1024 * 1024)
        assert not exceeds

    @pytest.mark.asyncio
    async def test_memory_tracking(self):
        """Test memory allocation tracking."""
        control = GPUAccessControl()

        policy = GPUAccessPolicy(
            principal_id="user1",
            roles={GPURole.USER},
            memory_quota_bytes=1024 * 1024 * 1024,  # 1GB
        )
        await control.add_policy(policy)

        # Allocate memory
        await control.track_memory_allocation("user1", 512 * 1024 * 1024)

        # Check remaining quota
        within = await control.check_memory_quota("user1", 600 * 1024 * 1024)
        assert not within  # Would exceed quota

        # Deallocate memory
        await control.track_memory_deallocation("user1", 512 * 1024 * 1024)

        # Check quota again
        within = await control.check_memory_quota("user1", 600 * 1024 * 1024)
        assert within  # Now within quota

    @pytest.mark.asyncio
    async def test_list_policies(self):
        """Test listing all policies."""
        control = GPUAccessControl()

        await control.add_policy(create_default_policy("user1", GPURole.USER))
        await control.add_policy(create_default_policy("user2", GPURole.MONITOR))
        await control.add_policy(create_admin_policy("admin1"))

        policies = await control.list_policies()

        assert len(policies) == 3
        principal_ids = {p.principal_id for p in policies}
        assert principal_ids == {"user1", "user2", "admin1"}

    @pytest.mark.asyncio
    async def test_cleanup_expired_policies(self):
        """Test cleaning up expired policies."""
        control = GPUAccessControl()

        # Add expired policy
        expired_policy = GPUAccessPolicy(
            principal_id="user1",
            roles={GPURole.USER},
            expires_at=datetime.now(tz=timezone.utc) - timedelta(hours=1),
        )
        await control.add_policy(expired_policy)

        # Add valid policy
        valid_policy = create_default_policy("user2", GPURole.USER)
        await control.add_policy(valid_policy)

        # Cleanup
        removed = await control.cleanup_expired_policies()

        assert removed == 1

        # Check remaining policies
        policies = await control.list_policies()
        assert len(policies) == 1
        assert policies[0].principal_id == "user2"


class TestHelperFunctions:
    """Test helper functions."""

    def test_create_default_policy(self):
        """Test creating default policy."""
        policy = create_default_policy("user1", GPURole.USER)

        assert policy.principal_id == "user1"
        assert GPURole.USER in policy.roles

    def test_create_admin_policy(self):
        """Test creating admin policy."""
        policy = create_admin_policy("admin1")

        assert policy.principal_id == "admin1"
        assert GPURole.ADMIN in policy.roles
        assert policy.has_permission(GPUPermission.ADMIN_FULL_ACCESS)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
