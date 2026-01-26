"""
Tests for RBAC and Agency functionality.

Tests cover:
- Role definitions and permissions
- Tenant context for agency users
- Billing tier integration
- RLS clause generation
"""

import pytest
from typing import List

from src.constants.permissions import (
    Role,
    Permission,
    RoleCategory,
    ROLE_PERMISSIONS,
    BILLING_TIER_ALLOWED_ROLES,
    get_permissions_for_role,
    get_permissions_for_roles,
    role_has_permission,
    roles_have_permission,
    get_role_category,
    is_agency_role,
    is_merchant_role,
    has_multi_tenant_access,
    get_primary_role_category,
    is_role_allowed_for_billing_tier,
    get_allowed_roles_for_billing_tier,
)
from src.platform.tenant_context import TenantContext


class TestRoleDefinitions:
    """Tests for role definitions."""

    def test_all_roles_have_permissions(self):
        """Every defined role should have permissions."""
        for role in Role:
            permissions = ROLE_PERMISSIONS.get(role)
            assert permissions is not None, f"Role {role} has no permissions defined"
            assert len(permissions) > 0, f"Role {role} has empty permissions"

    def test_merchant_roles_exist(self):
        """Merchant roles should be defined."""
        assert Role.MERCHANT_ADMIN in Role
        assert Role.MERCHANT_VIEWER in Role

    def test_agency_roles_exist(self):
        """Agency roles should be defined."""
        assert Role.AGENCY_ADMIN in Role
        assert Role.AGENCY_VIEWER in Role

    def test_super_admin_has_all_permissions(self):
        """Super admin should have all permissions."""
        super_admin_perms = ROLE_PERMISSIONS[Role.SUPER_ADMIN]
        # Should have at least as many as the most permissive regular role
        assert len(super_admin_perms) >= 20


class TestRoleCategories:
    """Tests for role category classification."""

    def test_agency_roles_are_agency_category(self):
        """Agency roles should be in agency category."""
        assert get_role_category(Role.AGENCY_ADMIN) == RoleCategory.AGENCY
        assert get_role_category(Role.AGENCY_VIEWER) == RoleCategory.AGENCY

    def test_merchant_roles_are_merchant_category(self):
        """Merchant roles should be in merchant category."""
        assert get_role_category(Role.MERCHANT_ADMIN) == RoleCategory.MERCHANT
        assert get_role_category(Role.MERCHANT_VIEWER) == RoleCategory.MERCHANT

    def test_legacy_roles_are_platform_category(self):
        """Legacy roles should be in platform category."""
        assert get_role_category(Role.ADMIN) == RoleCategory.PLATFORM
        assert get_role_category(Role.OWNER) == RoleCategory.PLATFORM
        assert get_role_category(Role.EDITOR) == RoleCategory.PLATFORM
        assert get_role_category(Role.VIEWER) == RoleCategory.PLATFORM

    def test_is_agency_role(self):
        """Test agency role detection."""
        assert is_agency_role("agency_admin")
        assert is_agency_role("agency_viewer")
        assert not is_agency_role("merchant_admin")
        assert not is_agency_role("admin")

    def test_is_merchant_role(self):
        """Test merchant role detection."""
        assert is_merchant_role("merchant_admin")
        assert is_merchant_role("merchant_viewer")
        assert not is_merchant_role("agency_admin")
        assert not is_merchant_role("admin")


class TestMultiTenantAccess:
    """Tests for multi-tenant access detection."""

    def test_agency_roles_have_multi_tenant_access(self):
        """Agency roles should have multi-tenant access."""
        assert has_multi_tenant_access(["agency_admin"])
        assert has_multi_tenant_access(["agency_viewer"])

    def test_super_admin_has_multi_tenant_access(self):
        """Super admin should have multi-tenant access."""
        assert has_multi_tenant_access(["super_admin"])

    def test_merchant_roles_no_multi_tenant_access(self):
        """Merchant roles should not have multi-tenant access."""
        assert not has_multi_tenant_access(["merchant_admin"])
        assert not has_multi_tenant_access(["merchant_viewer"])

    def test_legacy_roles_no_multi_tenant_access(self):
        """Non-admin legacy roles should not have multi-tenant access."""
        # Note: admin has MULTI_TENANT_ACCESS as platform super-admin
        assert not has_multi_tenant_access(["owner"])
        assert not has_multi_tenant_access(["editor"])
        assert not has_multi_tenant_access(["viewer"])

    def test_admin_has_multi_tenant_access(self):
        """Admin role should have multi-tenant access as platform admin."""
        assert has_multi_tenant_access(["admin"])

    def test_mixed_roles_with_agency(self):
        """If any role has multi-tenant, result should be True."""
        assert has_multi_tenant_access(["viewer", "agency_viewer"])


class TestPrimaryRoleCategory:
    """Tests for primary role category detection."""

    def test_agency_takes_priority(self):
        """Agency should take priority over other categories."""
        assert get_primary_role_category(["viewer", "agency_admin"]) == RoleCategory.AGENCY
        assert get_primary_role_category(["merchant_viewer", "agency_viewer"]) == RoleCategory.AGENCY

    def test_merchant_over_platform(self):
        """Merchant should take priority over platform."""
        assert get_primary_role_category(["viewer", "merchant_admin"]) == RoleCategory.MERCHANT

    def test_single_role(self):
        """Single role should return its category."""
        assert get_primary_role_category(["agency_admin"]) == RoleCategory.AGENCY
        assert get_primary_role_category(["merchant_admin"]) == RoleCategory.MERCHANT
        assert get_primary_role_category(["viewer"]) == RoleCategory.PLATFORM


class TestBillingTierAllowedRoles:
    """Tests for billing tier to role mapping."""

    def test_free_tier_no_agency_roles(self):
        """Free tier should not allow agency roles."""
        assert not is_role_allowed_for_billing_tier("agency_admin", "free")
        assert not is_role_allowed_for_billing_tier("agency_viewer", "free")

    def test_free_tier_allows_merchant_roles(self):
        """Free tier should allow merchant roles."""
        assert is_role_allowed_for_billing_tier("merchant_admin", "free")
        assert is_role_allowed_for_billing_tier("merchant_viewer", "free")

    def test_growth_tier_limited_agency(self):
        """Growth tier should allow limited agency access."""
        assert is_role_allowed_for_billing_tier("agency_viewer", "growth")
        assert not is_role_allowed_for_billing_tier("agency_admin", "growth")

    def test_enterprise_tier_full_agency(self):
        """Enterprise tier should allow full agency access."""
        assert is_role_allowed_for_billing_tier("agency_admin", "enterprise")
        assert is_role_allowed_for_billing_tier("agency_viewer", "enterprise")

    def test_get_allowed_roles_for_tier(self):
        """Should return list of allowed role names."""
        free_roles = get_allowed_roles_for_billing_tier("free")
        assert "merchant_admin" in free_roles
        assert "agency_admin" not in free_roles

        enterprise_roles = get_allowed_roles_for_billing_tier("enterprise")
        assert "agency_admin" in enterprise_roles


class TestAgencyPermissions:
    """Tests for agency-specific permissions."""

    def test_agency_admin_has_agency_permissions(self):
        """Agency admin should have all agency permissions."""
        perms = ROLE_PERMISSIONS[Role.AGENCY_ADMIN]
        assert Permission.AGENCY_STORES_VIEW in perms
        assert Permission.AGENCY_STORES_SWITCH in perms
        assert Permission.AGENCY_REPORTS_VIEW in perms
        assert Permission.MULTI_TENANT_ACCESS in perms

    def test_agency_viewer_has_limited_permissions(self):
        """Agency viewer should have limited agency permissions."""
        perms = ROLE_PERMISSIONS[Role.AGENCY_VIEWER]
        assert Permission.AGENCY_STORES_VIEW in perms
        assert Permission.AGENCY_STORES_SWITCH in perms
        assert Permission.MULTI_TENANT_ACCESS in perms
        # Should NOT have reports view
        assert Permission.AGENCY_REPORTS_VIEW not in perms

    def test_merchant_admin_no_agency_permissions(self):
        """Merchant admin should not have agency permissions."""
        perms = ROLE_PERMISSIONS[Role.MERCHANT_ADMIN]
        assert Permission.AGENCY_STORES_VIEW not in perms
        assert Permission.MULTI_TENANT_ACCESS not in perms


class TestTenantContext:
    """Tests for TenantContext class."""

    def test_merchant_context_single_tenant(self):
        """Merchant context should have single tenant."""
        ctx = TenantContext(
            tenant_id="tenant_001",
            user_id="user_001",
            roles=["merchant_admin"],
            org_id="tenant_001",
        )
        assert ctx.tenant_id == "tenant_001"
        assert ctx.allowed_tenants == ["tenant_001"]
        assert not ctx.is_agency_user

    def test_agency_context_multi_tenant(self):
        """Agency context should support multiple tenants."""
        ctx = TenantContext(
            tenant_id="tenant_001",
            user_id="user_001",
            roles=["agency_admin"],
            org_id="agency_org_001",
            allowed_tenants=["tenant_001", "tenant_002", "tenant_003"],
        )
        assert ctx.tenant_id == "tenant_001"
        assert len(ctx.allowed_tenants) == 3
        assert ctx.is_agency_user

    def test_can_access_tenant_agency(self):
        """Agency user should be able to access allowed tenants."""
        ctx = TenantContext(
            tenant_id="tenant_001",
            user_id="user_001",
            roles=["agency_admin"],
            org_id="agency_org_001",
            allowed_tenants=["tenant_001", "tenant_002"],
        )
        assert ctx.can_access_tenant("tenant_001")
        assert ctx.can_access_tenant("tenant_002")
        assert not ctx.can_access_tenant("tenant_003")

    def test_can_access_tenant_merchant(self):
        """Merchant user should only access own tenant."""
        ctx = TenantContext(
            tenant_id="tenant_001",
            user_id="user_001",
            roles=["merchant_admin"],
            org_id="tenant_001",
        )
        assert ctx.can_access_tenant("tenant_001")
        assert not ctx.can_access_tenant("tenant_002")

    def test_rls_clause_single_tenant(self):
        """RLS clause for single tenant should use equals."""
        ctx = TenantContext(
            tenant_id="tenant_001",
            user_id="user_001",
            roles=["merchant_admin"],
            org_id="tenant_001",
        )
        clause = ctx.get_rls_clause()
        assert clause == "tenant_id = 'tenant_001'"

    def test_rls_clause_multi_tenant(self):
        """RLS clause for multi-tenant should use IN."""
        ctx = TenantContext(
            tenant_id="tenant_001",
            user_id="user_001",
            roles=["agency_admin"],
            org_id="agency_org_001",
            allowed_tenants=["tenant_001", "tenant_002"],
        )
        clause = ctx.get_rls_clause()
        assert "tenant_id IN" in clause
        assert "tenant_001" in clause
        assert "tenant_002" in clause

    def test_active_tenant_must_be_in_allowed(self):
        """Active tenant must be in allowed_tenants list."""
        with pytest.raises(ValueError):
            TenantContext(
                tenant_id="tenant_999",  # Not in allowed list
                user_id="user_001",
                roles=["agency_admin"],
                org_id="agency_org_001",
                allowed_tenants=["tenant_001", "tenant_002"],
            )

    def test_empty_tenant_id_raises(self):
        """Empty tenant_id should raise ValueError."""
        with pytest.raises(ValueError):
            TenantContext(
                tenant_id="",
                user_id="user_001",
                roles=["merchant_admin"],
                org_id="",
            )


class TestPermissionChecks:
    """Tests for permission check functions."""

    def test_role_has_permission(self):
        """Test single role permission check."""
        assert role_has_permission(Role.MERCHANT_ADMIN, Permission.ANALYTICS_VIEW)
        assert not role_has_permission(Role.MERCHANT_VIEWER, Permission.ANALYTICS_EXPLORE)

    def test_roles_have_permission(self):
        """Test multiple roles permission check."""
        assert roles_have_permission(["viewer"], Permission.ANALYTICS_VIEW)
        assert not roles_have_permission(["viewer"], Permission.ANALYTICS_EXPORT)
        # Should work if any role has permission
        assert roles_have_permission(["viewer", "editor"], Permission.ANALYTICS_EXPORT)

    def test_get_permissions_for_roles(self):
        """Test getting combined permissions for multiple roles."""
        perms = get_permissions_for_roles(["viewer", "editor"])
        # Should have permissions from both roles
        assert Permission.ANALYTICS_VIEW in perms
        assert Permission.ANALYTICS_EXPORT in perms
        assert Permission.ANALYTICS_EXPLORE in perms

    def test_invalid_role_ignored(self):
        """Invalid role names should be ignored."""
        perms = get_permissions_for_roles(["viewer", "invalid_role"])
        # Should still have viewer permissions
        assert Permission.ANALYTICS_VIEW in perms


class TestRolePermissionConsistency:
    """Tests for permission consistency across roles."""

    def test_viewer_is_subset_of_editor(self):
        """Viewer permissions should be subset of editor."""
        viewer_perms = ROLE_PERMISSIONS[Role.VIEWER]
        editor_perms = ROLE_PERMISSIONS[Role.EDITOR]
        assert viewer_perms.issubset(editor_perms)

    def test_editor_is_subset_of_owner(self):
        """Editor permissions should be subset of owner."""
        editor_perms = ROLE_PERMISSIONS[Role.EDITOR]
        owner_perms = ROLE_PERMISSIONS[Role.OWNER]
        assert editor_perms.issubset(owner_perms)

    def test_merchant_viewer_is_subset_of_merchant_admin(self):
        """Merchant viewer should be subset of merchant admin."""
        viewer_perms = ROLE_PERMISSIONS[Role.MERCHANT_VIEWER]
        admin_perms = ROLE_PERMISSIONS[Role.MERCHANT_ADMIN]
        assert viewer_perms.issubset(admin_perms)

    def test_agency_viewer_is_subset_of_agency_admin(self):
        """Agency viewer should be subset of agency admin."""
        viewer_perms = ROLE_PERMISSIONS[Role.AGENCY_VIEWER]
        admin_perms = ROLE_PERMISSIONS[Role.AGENCY_ADMIN]
        assert viewer_perms.issubset(admin_perms)
