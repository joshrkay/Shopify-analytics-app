"""
Tests for Dashboard Visibility Gate.

Phase 5 (5.6.5) — Dashboard access based on billing tier and roles.

Verifies:
- Free tier gets base dashboards only
- Growth tier gets base + advanced dashboards
- Enterprise tier gets all dashboards (including agency if role present)
- Agency dashboards require agency role regardless of tier
- Non-agency user on enterprise doesn't get agency dashboards
"""

import pytest
from unittest.mock import patch

from src.services.dashboard_access_service import DashboardAccessService


class TestDashboardAccessService:
    """Test dashboard access based on billing tier and roles."""

    def test_free_tier_gets_base_dashboards(self):
        """Free tier users get overview, sales, marketing only."""
        service = DashboardAccessService(
            tenant_id="tenant-1",
            roles=["merchant_admin"],
            billing_tier="free",
        )
        allowed = service.get_allowed_dashboards()
        assert set(allowed) == {"overview", "sales", "marketing"}

    def test_growth_tier_gets_advanced_dashboards(self):
        """Growth tier users get base + advanced dashboards."""
        service = DashboardAccessService(
            tenant_id="tenant-1",
            roles=["merchant_admin"],
            billing_tier="growth",
        )
        allowed = service.get_allowed_dashboards()
        assert "advanced_analytics" in allowed
        assert "custom_reports" in allowed
        assert "overview" in allowed

    def test_enterprise_tier_without_agency_role(self):
        """Enterprise users without agency role don't get agency dashboards."""
        service = DashboardAccessService(
            tenant_id="tenant-1",
            roles=["merchant_admin"],
            billing_tier="enterprise",
        )
        allowed = service.get_allowed_dashboards()
        assert "agency_overview" not in allowed
        assert "multi_store_compare" not in allowed
        assert "advanced_analytics" in allowed

    def test_enterprise_tier_with_agency_role(self):
        """Enterprise users with agency role get all dashboards."""
        service = DashboardAccessService(
            tenant_id="tenant-1",
            roles=["agency_admin"],
            billing_tier="enterprise",
        )
        allowed = service.get_allowed_dashboards()
        assert "agency_overview" in allowed
        assert "multi_store_compare" in allowed
        assert "advanced_analytics" in allowed
        assert "overview" in allowed

    def test_is_dashboard_allowed_true(self):
        """is_dashboard_allowed returns True for allowed dashboards."""
        service = DashboardAccessService(
            tenant_id="tenant-1",
            roles=["merchant_admin"],
            billing_tier="growth",
        )
        assert service.is_dashboard_allowed("overview") is True
        assert service.is_dashboard_allowed("advanced_analytics") is True

    def test_is_dashboard_allowed_false(self):
        """is_dashboard_allowed returns False for disallowed dashboards."""
        service = DashboardAccessService(
            tenant_id="tenant-1",
            roles=["merchant_admin"],
            billing_tier="free",
        )
        assert service.is_dashboard_allowed("advanced_analytics") is False
        assert service.is_dashboard_allowed("agency_overview") is False

    def test_agency_viewer_role_grants_agency_dashboards(self):
        """agency_viewer role grants agency dashboards on enterprise tier."""
        service = DashboardAccessService(
            tenant_id="tenant-1",
            roles=["agency_viewer"],
            billing_tier="enterprise",
        )
        allowed = service.get_allowed_dashboards()
        assert "agency_overview" in allowed

    def test_unknown_tier_defaults_to_empty(self):
        """Unknown billing tier defaults to empty dashboard list."""
        service = DashboardAccessService(
            tenant_id="tenant-1",
            roles=["merchant_admin"],
            billing_tier="platinum",
        )
        allowed = service.get_allowed_dashboards()
        assert allowed == []

    def test_empty_roles_no_agency_access(self):
        """Empty roles means no agency dashboard access."""
        service = DashboardAccessService(
            tenant_id="tenant-1",
            roles=[],
            billing_tier="enterprise",
        )
        allowed = service.get_allowed_dashboards()
        assert "agency_overview" not in allowed

    def test_tenant_id_required(self):
        """tenant_id is required."""
        with pytest.raises(ValueError, match="tenant_id is required"):
            DashboardAccessService(
                tenant_id="",
                roles=["merchant_admin"],
                billing_tier="free",
            )

    @patch.dict("os.environ", {"DASHBOARD_ACCESS_CONFIG": '{"free": ["overview"]}'})
    def test_env_config_override(self):
        """DASHBOARD_ACCESS_CONFIG env var overrides defaults."""
        service = DashboardAccessService(
            tenant_id="tenant-1",
            roles=["merchant_admin"],
            billing_tier="free",
        )
        allowed = service.get_allowed_dashboards()
        assert allowed == ["overview"]
