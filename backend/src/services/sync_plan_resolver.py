"""
Sync plan resolver - maps subscription plan tiers to sync frequency SLAs.

Resolves the maximum allowed sync frequency for a tenant based on their
active subscription plan tier. Used by the scheduler to determine which
connections are due for sync.

SLA Map:
- Free (tier 0):       daily (1440 minutes)
- Growth (tier 1):     every 6 hours (360 minutes)
- Pro (tier 2):        hourly (60 minutes)
- Enterprise (tier 3): hourly (60 minutes)

SECURITY: tenant_id MUST come from JWT (org_id), never from client input.
"""

import logging
from datetime import datetime, timezone, timedelta
from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from src.models.subscription import Subscription, SubscriptionStatus
from src.models.plan import Plan

logger = logging.getLogger(__name__)

# Plan tier to sync interval mapping (minutes).
# These are the MINIMUM intervals between syncs for each tier.
# The scheduler will not dispatch a sync more frequently than this.
SYNC_INTERVAL_BY_TIER: dict[int, int] = {
    0: 1440,  # Free: daily
    1: 360,   # Growth: every 6 hours
    2: 60,    # Pro: hourly
    3: 60,    # Enterprise: hourly
}

# Default interval for tenants with no subscription or unrecognized tier.
DEFAULT_SYNC_INTERVAL_MINUTES = 1440  # daily (most restrictive)

# Plan name to tier mapping (fallback when tier field is unavailable).
_PLAN_NAME_TO_TIER: dict[str, int] = {
    "free": 0,
    "growth": 1,
    "pro": 2,
    "enterprise": 3,
}


class SyncPlanResolver:
    """
    Resolves sync frequency limits based on tenant subscription plan.

    All queries are tenant-scoped. The tenant_id comes from JWT only.
    """

    def __init__(self, db_session: Session):
        self.db = db_session

    def get_sync_interval_minutes(self, tenant_id: str) -> int:
        """
        Get the allowed sync interval for a tenant in minutes.

        Looks up the tenant's active subscription → plan → tier,
        then maps to the sync SLA.

        Args:
            tenant_id: Tenant ID from JWT

        Returns:
            Minimum sync interval in minutes
        """
        tier = self._resolve_plan_tier(tenant_id)
        interval = SYNC_INTERVAL_BY_TIER.get(tier, DEFAULT_SYNC_INTERVAL_MINUTES)

        logger.debug(
            "Resolved sync interval",
            extra={
                "tenant_id": tenant_id,
                "tier": tier,
                "interval_minutes": interval,
            },
        )

        return interval

    def is_sync_due(
        self,
        tenant_id: str,
        last_sync_at: Optional[datetime],
    ) -> bool:
        """
        Check if a connection is due for sync based on its plan SLA.

        A connection is due if:
        - It has never synced (last_sync_at is None), OR
        - Enough time has passed since last_sync_at per the plan interval

        Args:
            tenant_id: Tenant ID from JWT
            last_sync_at: Timestamp of last successful sync (None = never synced)

        Returns:
            True if connection should be synced
        """
        if last_sync_at is None:
            return True

        interval_minutes = self.get_sync_interval_minutes(tenant_id)
        threshold = last_sync_at + timedelta(minutes=interval_minutes)
        now = datetime.now(timezone.utc)

        return now >= threshold

    def _resolve_plan_tier(self, tenant_id: str) -> int:
        """
        Look up the plan tier for a tenant via their active subscription.

        Falls back to tier 0 (Free) if no active subscription found.

        Args:
            tenant_id: Tenant ID

        Returns:
            Plan tier integer (0-3)
        """
        stmt = (
            select(Plan)
            .join(
                Subscription,
                Subscription.plan_id == Plan.id,
            )
            .where(
                Subscription.tenant_id == tenant_id,
                Subscription.status == SubscriptionStatus.ACTIVE.value,
            )
            .order_by(Subscription.created_at.desc())
            .limit(1)
        )

        plan = self.db.execute(stmt).scalar_one_or_none()

        if plan is None:
            logger.debug(
                "No active subscription found, defaulting to free tier",
                extra={"tenant_id": tenant_id},
            )
            return 0

        # Derive tier from plan name
        plan_name = (plan.name or "").lower().strip()
        tier = _PLAN_NAME_TO_TIER.get(plan_name)

        if tier is not None:
            return tier

        # Fallback: if plan name doesn't match, default to free
        logger.warning(
            "Unknown plan name, defaulting to free tier",
            extra={"tenant_id": tenant_id, "plan_name": plan.name},
        )
        return 0
