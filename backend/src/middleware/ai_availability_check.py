"""
AI availability check that gates AI features based on data availability.

Bridges the DataAvailabilityService state machine with the existing
FreshnessService.check_ai_freshness_gate() to provide a unified AI access
decision.  The DataAvailability state takes precedence:

- UNAVAILABLE -> AI DISABLED (data not available)
- STALE       -> AI DISABLED (stale data produces unreliable insights)
- FRESH       -> Delegate to FreshnessService for fine-grained freshness check

Messages are human-readable and never expose SLA values, threshold numbers,
or internal state machine details.

SECURITY: tenant_id must come from JWT (org_id), never from client input.

Usage:
    checker = AIAvailabilityCheck(db_session=session, tenant_id=tenant_id)
    result = checker.check_ai_access(required_sources=["shopify_orders"])
    if not result.is_allowed:
        skip_ai_job(reason=result.reason)

    # Convenience boolean
    if not checker.is_ai_allowed():
        return

    # Static convenience
    result = check_ai_availability(
        db_session=session,
        tenant_id=tenant_id,
        billing_tier="growth",
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
from src.services.freshness_service import FreshnessService, FreshnessGateResult

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Human-readable messages (never expose internal details)
# ---------------------------------------------------------------------------

_MSG_UNAVAILABLE = (
    "AI insights are paused because your data is being updated. "
    "They will resume automatically once your data is current."
)

_MSG_STALE = (
    "AI insights are temporarily paused while your data catches up. "
    "This helps ensure recommendations are based on the latest information."
)

_MSG_FRESHNESS_GATE_BLOCKED = (
    "AI insights are temporarily paused while we verify your data quality. "
    "They will resume automatically once verification is complete."
)

_RECOMMENDATION_UNAVAILABLE = (
    "No action is required. Your data is being processed and AI features "
    "will resume automatically."
)

_RECOMMENDATION_STALE = (
    "Your data is being updated. AI features will resume once the update "
    "completes, usually within a few minutes."
)


# ---------------------------------------------------------------------------
# Result dataclass
# ---------------------------------------------------------------------------

@dataclass
class AIAccessResult:
    """
    Result of an AI availability check.

    Combines the DataAvailability state machine evaluation with the existing
    FreshnessService freshness gate to provide a single, unified decision.

    Attributes:
        is_allowed:          Whether AI features may proceed.
        reason:              Optional human-readable reason when blocked.
        availability_states: Dict mapping source type to its availability
                             state (e.g. ``{"shopify_orders": "fresh"}``).
        recommendation:      Optional human-readable suggestion for the user.
        evaluated_at:        Timestamp of the evaluation.
    """

    is_allowed: bool
    reason: Optional[str] = None
    availability_states: Dict[str, str] = field(default_factory=dict)
    recommendation: Optional[str] = None
    evaluated_at: Optional[datetime] = None

    def to_dict(self) -> dict:
        return {
            "is_allowed": self.is_allowed,
            "reason": self.reason,
            "availability_states": self.availability_states,
            "recommendation": self.recommendation,
        }


# ---------------------------------------------------------------------------
# AI availability check service
# ---------------------------------------------------------------------------

class AIAvailabilityCheck:
    """
    Gates AI features based on the combined DataAvailability state machine
    and FreshnessService freshness gate.

    Decision matrix:
    1. Evaluate DataAvailabilityService for the requested sources.
    2. If **any** source is UNAVAILABLE -> AI DISABLED.
    3. If **any** source is STALE -> AI DISABLED (stale data produces
       unreliable insights).
    4. If all sources are FRESH -> delegate to
       ``FreshnessService.check_ai_freshness_gate()`` for fine-grained
       freshness verification.

    SECURITY: tenant_id must originate from JWT (org_id).
    """

    def __init__(
        self,
        db_session: Session,
        tenant_id: str,
        billing_tier: str = "free",
    ):
        """
        Args:
            db_session:   SQLAlchemy database session.
            tenant_id:    Tenant ID from JWT.
            billing_tier: Tenant billing tier for SLA threshold lookup.
        """
        if not tenant_id:
            raise ValueError("tenant_id is required")

        self.db = db_session
        self.tenant_id = tenant_id
        self.billing_tier = billing_tier

    # ── Public API ────────────────────────────────────────────────────────

    def check_ai_access(
        self,
        required_sources: Optional[List[str]] = None,
    ) -> AIAccessResult:
        """
        Check whether AI features may execute for this tenant.

        Args:
            required_sources: Optional list of SLA source keys to evaluate.
                              When ``None``, all enabled sources are checked.

        Returns:
            :class:`AIAccessResult` with the access decision.
        """
        now = datetime.now(timezone.utc)

        # Step 1: Evaluate DataAvailability state machine.
        availability_service = DataAvailabilityService(
            db_session=self.db,
            tenant_id=self.tenant_id,
            billing_tier=self.billing_tier,
        )

        if required_sources:
            results = [
                availability_service.get_data_availability(st)
                for st in required_sources
            ]
        else:
            results = availability_service.evaluate_all()

        # Build state map for the response.
        availability_states: Dict[str, str] = {
            r.source_type: r.state for r in results
        }

        # Categorise sources by state.
        unavailable_sources: List[str] = []
        stale_sources: List[str] = []

        for r in results:
            if r.state == AvailabilityState.UNAVAILABLE.value:
                unavailable_sources.append(r.source_type)
            elif r.state == AvailabilityState.STALE.value:
                stale_sources.append(r.source_type)

        # Step 2: UNAVAILABLE -> AI DISABLED
        if unavailable_sources:
            self._log_ai_blocked(
                reason="data_unavailable",
                sources=unavailable_sources,
            )
            return AIAccessResult(
                is_allowed=False,
                reason=_MSG_UNAVAILABLE,
                availability_states=availability_states,
                recommendation=_RECOMMENDATION_UNAVAILABLE,
                evaluated_at=now,
            )

        # Step 3: STALE -> AI DISABLED
        if stale_sources:
            self._log_ai_blocked(
                reason="data_stale",
                sources=stale_sources,
            )
            return AIAccessResult(
                is_allowed=False,
                reason=_MSG_STALE,
                availability_states=availability_states,
                recommendation=_RECOMMENDATION_STALE,
                evaluated_at=now,
            )

        # Step 4: All FRESH -> delegate to FreshnessService for fine-grained
        # freshness verification (e.g. per-connection threshold checks).
        freshness_gate = FreshnessService.check_ai_freshness_gate(
            db_session=self.db,
            tenant_id=self.tenant_id,
            required_sources=required_sources,
            billing_tier=self.billing_tier,
        )

        if not freshness_gate.is_allowed:
            self._log_ai_blocked(
                reason="freshness_gate",
                sources=freshness_gate.stale_sources,
            )
            return AIAccessResult(
                is_allowed=False,
                reason=_MSG_FRESHNESS_GATE_BLOCKED,
                availability_states=availability_states,
                recommendation=_RECOMMENDATION_STALE,
                evaluated_at=now,
            )

        # All checks passed: AI is enabled.
        logger.info(
            "AI access allowed",
            extra={
                "tenant_id": self.tenant_id,
                "source_count": len(results),
            },
        )
        return AIAccessResult(
            is_allowed=True,
            availability_states=availability_states,
            evaluated_at=now,
        )

    def is_ai_allowed(
        self,
        required_sources: Optional[List[str]] = None,
    ) -> bool:
        """
        Convenience boolean: ``True`` when AI features may execute.

        Equivalent to ``self.check_ai_access(...).is_allowed``.
        """
        return self.check_ai_access(required_sources).is_allowed

    # ── Internal helpers ──────────────────────────────────────────────────

    def _log_ai_blocked(
        self,
        reason: str,
        sources: List[str],
    ) -> None:
        """Log and optionally audit-trail an AI block event."""
        logger.warning(
            "AI access blocked",
            extra={
                "tenant_id": self.tenant_id,
                "reason": reason,
                "affected_sources": sources,
            },
        )

        try:
            from src.platform.audit import (
                AuditAction,
                AuditOutcome,
                log_system_audit_event_sync,
            )

            log_system_audit_event_sync(
                db=self.db,
                tenant_id=self.tenant_id,
                action=AuditAction.AI_ACTION_BLOCKED,
                resource_type="ai_availability_check",
                metadata={
                    "gate": "data_availability",
                    "block_reason": reason,
                    "affected_sources": sources,
                },
                source="service",
                outcome=AuditOutcome.FAILURE,
            )
        except Exception as exc:
            logger.error(
                "Failed to log AI block audit event",
                extra={
                    "tenant_id": self.tenant_id,
                    "error": str(exc),
                },
            )


# ---------------------------------------------------------------------------
# Static convenience function
# ---------------------------------------------------------------------------

def check_ai_availability(
    db_session: Session,
    tenant_id: str,
    billing_tier: str = "free",
    required_sources: Optional[List[str]] = None,
) -> AIAccessResult:
    """
    Static convenience for one-shot AI availability checks.

    Intended for use in AI job runners and background tasks that do not
    have access to a class instance.

    Usage::

        result = check_ai_availability(
            db_session=session,
            tenant_id=job.tenant_id,
            billing_tier="growth",
            required_sources=["shopify_orders"],
        )
        if not result.is_allowed:
            job.mark_skipped(reason=result.reason)
            return
    """
    checker = AIAvailabilityCheck(
        db_session=db_session,
        tenant_id=tenant_id,
        billing_tier=billing_tier,
    )
    return checker.check_ai_access(required_sources=required_sources)
