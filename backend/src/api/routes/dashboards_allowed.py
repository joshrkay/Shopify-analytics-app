"""
Dashboard Allowed API route.

Returns the list of dashboards a user is allowed to access
based on their billing tier and roles.

Phase 5 - Dashboard Visibility Gate
"""

import logging

from fastapi import APIRouter, Request

from src.platform.tenant_context import get_tenant_context
from src.platform.rbac import require_permission
from src.constants.permissions import Permission
from src.services.dashboard_access_service import DashboardAccessService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/dashboards", tags=["dashboards"])


@router.get("/allowed")
@require_permission(Permission.ANALYTICS_VIEW)
async def get_allowed_dashboards(request: Request):
    """Return dashboards allowed for the current user.

    Requires ANALYTICS_VIEW permission.

    Returns:
        JSON with allowed_dashboards list, tenant_id, and billing_tier.
    """
    tenant_ctx = get_tenant_context(request)

    service = DashboardAccessService(
        tenant_id=tenant_ctx.tenant_id,
        roles=tenant_ctx.roles,
        billing_tier=tenant_ctx.billing_tier,
    )

    allowed = service.get_allowed_dashboards()

    logger.info(
        "Returning allowed dashboards",
        extra={
            "tenant_id": tenant_ctx.tenant_id,
            "user_id": tenant_ctx.user_id,
            "billing_tier": tenant_ctx.billing_tier,
            "dashboard_count": len(allowed),
        },
    )

    return {
        "allowed_dashboards": allowed,
        "tenant_id": tenant_ctx.tenant_id,
        "billing_tier": tenant_ctx.billing_tier,
    }
