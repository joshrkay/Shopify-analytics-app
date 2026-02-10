"""
Dashboard Visibility Gate - Dashboard Access Service.

Controls which dashboards a user can access based on their billing tier and roles.
Used by the embed token generation endpoint and the /api/v1/dashboards/allowed
endpoint to enforce plan-based dashboard restrictions.

Access Rules:
- Base dashboards (overview, sales, marketing): available to ALL tiers
- Advanced dashboards (advanced_analytics, custom_reports): require 'growth' or 'enterprise'
- Agency dashboards (agency_overview, multi_store_compare): require agency roles

Configuration:
- Override defaults via DASHBOARD_ACCESS_CONFIG env var (JSON string)
- Falls back to DEFAULT_DASHBOARD_ACCESS hardcoded mapping

Phase 5 - Dashboard Visibility Gate
"""

import json
import logging
import os
from typing import Optional

logger = logging.getLogger(__name__)

# =============================================================================
# Default Dashboard Access Configuration
# =============================================================================

DEFAULT_DASHBOARD_ACCESS: dict[str, list[str]] = {
    "free": ["overview", "sales", "marketing"],
    "growth": ["overview", "sales", "marketing", "advanced_analytics", "custom_reports"],
    "enterprise": [
        "overview", "sales", "marketing",
        "advanced_analytics", "custom_reports",
        "agency_overview", "multi_store_compare",
    ],
}

# Agency-only dashboards: require an agency role regardless of billing tier
AGENCY_DASHBOARDS = frozenset({"agency_overview", "multi_store_compare"})

# Roles that qualify as agency roles (multi-tenant access)
AGENCY_ROLES = frozenset({"agency_admin", "agency_viewer"})


def _load_dashboard_access_config() -> dict[str, list[str]]:
    """Load dashboard access config from env var or fall back to defaults.

    The DASHBOARD_ACCESS_CONFIG env var should be a JSON string with the same
    structure as DEFAULT_DASHBOARD_ACCESS, e.g.:
        {"free": ["overview"], "growth": ["overview", "sales"], ...}

    Returns:
        Mapping of billing tier to list of allowed dashboard IDs.
    """
    env_config = os.getenv("DASHBOARD_ACCESS_CONFIG")
    if env_config:
        try:
            parsed = json.loads(env_config)
            if isinstance(parsed, dict):
                logger.info(
                    "Loaded dashboard access config from DASHBOARD_ACCESS_CONFIG env var",
                    extra={"tiers": list(parsed.keys())},
                )
                return parsed
            else:
                logger.warning(
                    "DASHBOARD_ACCESS_CONFIG is not a dict, falling back to defaults"
                )
        except (json.JSONDecodeError, TypeError) as e:
            logger.warning(
                "Failed to parse DASHBOARD_ACCESS_CONFIG, falling back to defaults",
                extra={"error": str(e)},
            )
    return DEFAULT_DASHBOARD_ACCESS


class DashboardAccessService:
    """Service for determining dashboard access based on billing tier and roles.

    Usage:
        service = DashboardAccessService(
            tenant_id="tenant-123",
            roles=["merchant_admin"],
            billing_tier="growth",
        )
        allowed = service.get_allowed_dashboards()
        # ["overview", "sales", "marketing", "advanced_analytics", "custom_reports"]

        service.is_dashboard_allowed("advanced_analytics")
        # True
    """

    def __init__(
        self,
        tenant_id: str,
        roles: list[str],
        billing_tier: str,
    ):
        """Initialize the DashboardAccessService.

        Args:
            tenant_id: The tenant ID (for logging/audit context).
            roles: List of role strings from the user's JWT claims.
            billing_tier: The billing tier ('free', 'growth', 'enterprise').
        """
        if not tenant_id:
            raise ValueError("tenant_id is required")

        self.tenant_id = tenant_id
        self.roles = [r.lower() for r in roles] if roles else []
        self.billing_tier = billing_tier.lower() if billing_tier else "free"
        self._config = _load_dashboard_access_config()

    @property
    def _has_agency_role(self) -> bool:
        """Check if any of the user's roles qualify as an agency role."""
        return bool(AGENCY_ROLES.intersection(self.roles))

    def get_allowed_dashboards(self) -> list[str]:
        """Return list of dashboard IDs allowed for this user.

        Combines billing-tier-based access with agency role checks:
        - Tier-based dashboards come from the config mapping.
        - Agency dashboards are only included if the user has an agency role.

        Returns:
            List of dashboard ID strings the user is allowed to access.
        """
        tier_dashboards = self._config.get(self.billing_tier, [])

        # If user does not have an agency role, exclude agency dashboards
        if not self._has_agency_role:
            tier_dashboards = [
                d for d in tier_dashboards if d not in AGENCY_DASHBOARDS
            ]

        return tier_dashboards

    def is_dashboard_allowed(self, dashboard_id: str) -> bool:
        """Check if a specific dashboard is allowed for this user.

        Args:
            dashboard_id: The dashboard ID to check.

        Returns:
            True if the dashboard is in the user's allowed list.
        """
        return dashboard_id in self.get_allowed_dashboards()
