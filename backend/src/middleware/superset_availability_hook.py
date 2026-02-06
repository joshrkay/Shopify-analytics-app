"""
Superset availability hook for controlling dashboard query access.

Provides a backend service that Superset calls before executing queries.
Controls access based on the DataAvailabilityService state machine:

- UNAVAILABLE -> Query BLOCKED
- STALE       -> Query ALLOWED with warning message
- FRESH       -> Query ALLOWED

Messages are human-readable and never expose internal state machine details,
SLA thresholds, or technical error codes.

SECURITY: tenant_id must come from JWT (org_id), never from client input.

Usage:
    hook = SupersetAvailabilityHook(db_session=session)
    result = hook.check_query_access(tenant_id="tenant_123")
    if not result.is_allowed:
        block_query(reason=result.blocked_reason)

    # Static convenience
    result = SupersetAvailabilityHook.check_access(
        db_session=session,
        tenant_id="tenant_123",
        dashboard_id="dash_456",
    )
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Dict, List, Optional

from sqlalchemy.orm import Session

from src.models.data_availability import AvailabilityState
from src.services.data_availability_service import (
    DataAvailabilityResult,
    DataAvailabilityService,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Friendly source name mapping (shared with data_availability_guard)
# ---------------------------------------------------------------------------

SOURCE_FRIENDLY_NAMES: Dict[str, str] = {
    "shopify_orders": "Shopify Orders",
    "facebook_ads": "Facebook Ads",
    "google_ads": "Google Ads",
    "tiktok_ads": "TikTok Ads",
    "snapchat_ads": "Snapchat Ads",
    "email": "Email Marketing",
    "sms": "SMS Marketing",
}


def _friendly_name(source_type: str) -> str:
    """Return a user-facing name for a source type, falling back to title-case."""
    return SOURCE_FRIENDLY_NAMES.get(
        source_type,
        source_type.replace("_", " ").title(),
    )


# ---------------------------------------------------------------------------
# Human-readable messages (never expose internal details)
# ---------------------------------------------------------------------------

_MSG_BLOCKED = (
    "Dashboard queries are temporarily paused while we update your data. "
    "This usually resolves within a few minutes."
)

_MSG_WARNING = (
    "Some data may not reflect the very latest changes. "
    "An update is in progress."
)


# ---------------------------------------------------------------------------
# Result dataclass
# ---------------------------------------------------------------------------

@dataclass
class QueryAccessResult:
    """
    Result of a Superset query access check.

    Attributes:
        is_allowed:       Whether the query may proceed.
        warning_message:  Optional user-facing warning when data is stale.
        blocked_reason:   Optional user-facing reason when query is blocked.
        affected_sources: List of friendly source names that are not fresh.
        evaluated_at:     Timestamp of the evaluation.
    """

    is_allowed: bool
    warning_message: Optional[str] = None
    blocked_reason: Optional[str] = None
    affected_sources: List[str] = field(default_factory=list)
    evaluated_at: Optional[datetime] = None

    def to_dict(self) -> dict:
        return {
            "is_allowed": self.is_allowed,
            "warning_message": self.warning_message,
            "blocked_reason": self.blocked_reason,
            "affected_sources": self.affected_sources,
        }


# ---------------------------------------------------------------------------
# Hook service
# ---------------------------------------------------------------------------

class SupersetAvailabilityHook:
    """
    Backend service that Superset calls before executing queries.

    Evaluates the DataAvailabilityService state machine for the tenant and
    returns a :class:`QueryAccessResult` indicating whether the query may
    proceed, must be blocked, or should carry a warning.

    SECURITY: tenant_id must originate from JWT (org_id).
    """

    def __init__(
        self,
        db_session: Session,
        billing_tier: str = "free",
    ):
        """
        Args:
            db_session:   SQLAlchemy database session.
            billing_tier: Tenant billing tier for SLA threshold lookup.
        """
        self.db = db_session
        self.billing_tier = billing_tier

    # ── Public API ────────────────────────────────────────────────────────

    def check_query_access(
        self,
        tenant_id: str,
        dashboard_id: Optional[str] = None,
        required_sources: Optional[List[str]] = None,
    ) -> QueryAccessResult:
        """
        Check whether a Superset query may execute.

        Evaluation rules:
        1. Evaluate all enabled sources for the tenant (or just
           *required_sources* when provided).
        2. If **any** source is UNAVAILABLE -> BLOCKED.
        3. If **any** source is STALE -> ALLOWED with warning.
        4. Otherwise -> ALLOWED.

        Args:
            tenant_id:        Tenant ID from JWT.
            dashboard_id:     Optional Superset dashboard identifier (used
                              for logging; does not change evaluation logic).
            required_sources: Optional list of SLA source keys to check.
                              When ``None``, all enabled sources are checked.

        Returns:
            :class:`QueryAccessResult` with the access decision.
        """
        now = datetime.now(timezone.utc)

        service = DataAvailabilityService(
            db_session=self.db,
            tenant_id=tenant_id,
            billing_tier=self.billing_tier,
        )

        if required_sources:
            results = [
                service.get_data_availability(st) for st in required_sources
            ]
        else:
            results = service.evaluate_all()

        unavailable_sources: List[str] = []
        stale_sources: List[str] = []

        for r in results:
            friendly = _friendly_name(r.source_type)
            if r.state == AvailabilityState.UNAVAILABLE.value:
                unavailable_sources.append(friendly)
            elif r.state == AvailabilityState.STALE.value:
                stale_sources.append(friendly)

        # Decision: BLOCKED
        if unavailable_sources:
            logger.warning(
                "Superset query blocked: data unavailable",
                extra={
                    "tenant_id": tenant_id,
                    "dashboard_id": dashboard_id,
                    "unavailable_sources": unavailable_sources,
                },
            )
            return QueryAccessResult(
                is_allowed=False,
                blocked_reason=_MSG_BLOCKED,
                affected_sources=unavailable_sources,
                evaluated_at=now,
            )

        # Decision: ALLOWED with warning
        if stale_sources:
            logger.info(
                "Superset query allowed with warning: stale data",
                extra={
                    "tenant_id": tenant_id,
                    "dashboard_id": dashboard_id,
                    "stale_sources": stale_sources,
                },
            )
            return QueryAccessResult(
                is_allowed=True,
                warning_message=_MSG_WARNING,
                affected_sources=stale_sources,
                evaluated_at=now,
            )

        # Decision: ALLOWED (all fresh)
        logger.debug(
            "Superset query allowed: all sources fresh",
            extra={
                "tenant_id": tenant_id,
                "dashboard_id": dashboard_id,
            },
        )
        return QueryAccessResult(
            is_allowed=True,
            evaluated_at=now,
        )

    # ── Static convenience ────────────────────────────────────────────────

    @staticmethod
    def check_access(
        db_session: Session,
        tenant_id: str,
        dashboard_id: Optional[str] = None,
        required_sources: Optional[List[str]] = None,
        billing_tier: str = "free",
    ) -> QueryAccessResult:
        """
        Static convenience for one-shot query access checks.

        Usage::

            result = SupersetAvailabilityHook.check_access(
                db_session=session,
                tenant_id="tenant_123",
                dashboard_id="dash_456",
            )
            if not result.is_allowed:
                return {"error": result.blocked_reason}
        """
        hook = SupersetAvailabilityHook(
            db_session=db_session,
            billing_tier=billing_tier,
        )
        return hook.check_query_access(
            tenant_id=tenant_id,
            dashboard_id=dashboard_id,
            required_sources=required_sources,
        )
