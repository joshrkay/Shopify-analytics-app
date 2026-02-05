"""
Data availability state machine service.

Computes and persists availability state per tenant and per source based on
freshness SLAs defined in config/data_freshness_sla.yml.

States:
    FRESH       — Data within SLA (warn threshold)
    STALE       — SLA exceeded but within grace window (error threshold)
    UNAVAILABLE — Grace window exceeded or ingestion failed

Transitions:
    FRESH → STALE:       minutes_since_sync >= warn_after_minutes
    STALE → UNAVAILABLE: minutes_since_sync >= error_after_minutes
    ANY   → FRESH:       successful sync brings minutes_since_sync < warn

State is always computed from current timestamps and SLA thresholds — never
set manually.

SECURITY: All operations are tenant-scoped via tenant_id from JWT.

Usage:
    service = DataAvailabilityService(db_session=session, tenant_id=tenant_id)
    result = service.get_data_availability("shopify_orders")
    all_results = service.evaluate_all()
"""

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import List, Optional, Tuple

from sqlalchemy import select
from sqlalchemy.orm import Session

from src.config.freshness_sla import get_sla_thresholds, resolve_sla_key

logger = logging.getLogger(__name__)


# ─── Shared helpers (also used by FreshnessService) ─────────────────────────

def get_tenant_connections(db: Session, tenant_id: str):
    """
    Return enabled, non-deleted TenantAirbyteConnections for a tenant.

    Shared by DataAvailabilityService and FreshnessService to avoid
    duplicating the query.
    """
    from src.models.airbyte_connection import (
        TenantAirbyteConnection,
        ConnectionStatus,
    )

    stmt = (
        select(TenantAirbyteConnection)
        .where(TenantAirbyteConnection.tenant_id == tenant_id)
        .where(TenantAirbyteConnection.is_enabled.is_(True))
        .where(
            TenantAirbyteConnection.status.notin_([
                ConnectionStatus.DELETED,
            ])
        )
    )
    return db.execute(stmt).scalars().all()


def minutes_since_sync(
    ts: Optional[datetime],
    now: Optional[datetime] = None,
) -> Optional[int]:
    """
    Minutes elapsed since a timestamp.

    Shared by DataAvailabilityService and FreshnessService.

    Args:
        ts:  The timestamp to measure from (e.g. last_sync_at).
        now: Current time; defaults to utcnow if omitted.
    """
    if ts is None:
        return None
    if now is None:
        now = datetime.now(timezone.utc)
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    return int((now - ts).total_seconds() / 60)


# ─── Return dataclass ────────────────────────────────────────────────────────

@dataclass
class DataAvailabilityResult:
    """Result of a data availability evaluation for one source."""

    tenant_id: str
    source_type: str
    state: str
    reason: str
    warn_threshold_minutes: int
    error_threshold_minutes: int
    last_sync_at: Optional[datetime]
    last_sync_status: Optional[str]
    minutes_since_sync: Optional[int]
    state_changed_at: datetime
    previous_state: Optional[str]
    evaluated_at: datetime
    billing_tier: str

    def to_dict(self) -> dict:
        return {
            "tenant_id": self.tenant_id,
            "source_type": self.source_type,
            "state": self.state,
            "reason": self.reason,
            "warn_threshold_minutes": self.warn_threshold_minutes,
            "error_threshold_minutes": self.error_threshold_minutes,
            "last_sync_at": (
                self.last_sync_at.isoformat() if self.last_sync_at else None
            ),
            "last_sync_status": self.last_sync_status,
            "minutes_since_sync": self.minutes_since_sync,
            "state_changed_at": self.state_changed_at.isoformat(),
            "previous_state": self.previous_state,
            "evaluated_at": self.evaluated_at.isoformat(),
            "billing_tier": self.billing_tier,
        }


# ─── Service ─────────────────────────────────────────────────────────────────

class DataAvailabilityService:
    """
    Computes and persists data availability state per tenant + source.

    SECURITY: tenant_id must come from JWT (org_id), never client input.
    """

    def __init__(
        self,
        db_session: Session,
        tenant_id: str,
        billing_tier: str = "free",
    ):
        if not tenant_id:
            raise ValueError("tenant_id is required")

        self.db = db_session
        self.tenant_id = tenant_id
        self.billing_tier = billing_tier

    # ── Public API ───────────────────────────────────────────────────────

    def get_data_availability(
        self,
        source_type: str,
    ) -> DataAvailabilityResult:
        """
        Evaluate and persist the current availability state for one source.

        Reads the latest sync metadata from TenantAirbyteConnection,
        computes the state against SLA thresholds, persists the result,
        and returns it.

        Args:
            source_type: SLA config source key (e.g. 'shopify_orders').

        Returns:
            DataAvailabilityResult with computed state and metadata.
        """
        now = datetime.now(timezone.utc)
        warn, error = get_sla_thresholds(source_type, self.billing_tier)

        last_sync_at, last_sync_status = self._get_latest_sync(source_type)
        minutes = minutes_since_sync(last_sync_at, now)

        state, reason = self._compute_state(
            last_sync_at=last_sync_at,
            last_sync_status=last_sync_status,
            minutes_since_sync=minutes,
            warn_threshold=warn,
            error_threshold=error,
        )

        existing = self._get_existing(source_type)
        previous_state = existing.state if existing else None
        state_changed = (previous_state != state)
        state_changed_at = now if state_changed else (
            existing.state_changed_at if existing else now
        )

        row = self._upsert(
            source_type=source_type,
            state=state,
            reason=reason,
            warn_threshold=warn,
            error_threshold=error,
            last_sync_at=last_sync_at,
            last_sync_status=last_sync_status,
            minutes_since_sync=minutes,
            state_changed_at=state_changed_at,
            previous_state=previous_state,
            evaluated_at=now,
            existing=existing,
        )

        if state_changed:
            logger.info(
                "Availability state transitioned",
                extra={
                    "tenant_id": self.tenant_id,
                    "source_type": source_type,
                    "previous_state": previous_state,
                    "new_state": state,
                    "reason": reason,
                    "minutes_since_sync": minutes,
                },
            )

        return DataAvailabilityResult(
            tenant_id=self.tenant_id,
            source_type=source_type,
            state=state,
            reason=reason,
            warn_threshold_minutes=warn,
            error_threshold_minutes=error,
            last_sync_at=last_sync_at,
            last_sync_status=last_sync_status,
            minutes_since_sync=minutes,
            state_changed_at=state_changed_at,
            previous_state=previous_state,
            evaluated_at=now,
            billing_tier=self.billing_tier,
        )

    def evaluate_all(self) -> List[DataAvailabilityResult]:
        """
        Evaluate availability for every enabled source belonging to
        this tenant.

        Returns:
            List of DataAvailabilityResult, one per source.
        """
        connections = self._get_connections()
        seen_sources: dict[str, bool] = {}
        results: List[DataAvailabilityResult] = []

        for conn in connections:
            sla_key = resolve_sla_key(conn.source_type)
            if not sla_key or sla_key in seen_sources:
                continue
            seen_sources[sla_key] = True
            results.append(self.get_data_availability(sla_key))

        return results

    # ── Static convenience ───────────────────────────────────────────────

    @staticmethod
    def check_availability(
        db_session: Session,
        tenant_id: str,
        source_type: str,
        billing_tier: str = "free",
    ) -> DataAvailabilityResult:
        """
        Static convenience for callers that need a one-shot check.

        Usage:
            result = DataAvailabilityService.check_availability(
                db_session=session, tenant_id=tid, source_type="shopify_orders",
            )
            if result.state == "unavailable":
                block_dashboard()
        """
        service = DataAvailabilityService(
            db_session=db_session,
            tenant_id=tenant_id,
            billing_tier=billing_tier,
        )
        return service.get_data_availability(source_type)

    # ── State computation ────────────────────────────────────────────────

    @staticmethod
    def _compute_state(
        last_sync_at: Optional[datetime],
        last_sync_status: Optional[str],
        minutes_since_sync: Optional[int],
        warn_threshold: int,
        error_threshold: int,
    ) -> Tuple[str, str]:
        """
        Pure function: derive (state, reason) from sync metadata + thresholds.

        Transitions:
            never synced                            → UNAVAILABLE / never_synced
            last sync failed AND beyond warn        → UNAVAILABLE / sync_failed
            minutes >= error_threshold              → UNAVAILABLE / grace_window_exceeded
            minutes >= warn_threshold               → STALE / sla_exceeded
            otherwise                               → FRESH / sync_ok
        """
        from src.models.data_availability import (
            AvailabilityState,
            AvailabilityReason,
        )

        if last_sync_at is None:
            return (
                AvailabilityState.UNAVAILABLE.value,
                AvailabilityReason.NEVER_SYNCED.value,
            )

        if (
            last_sync_status == "failed"
            and minutes_since_sync is not None
            and minutes_since_sync >= warn_threshold
        ):
            return (
                AvailabilityState.UNAVAILABLE.value,
                AvailabilityReason.SYNC_FAILED.value,
            )

        if minutes_since_sync is not None and minutes_since_sync >= error_threshold:
            return (
                AvailabilityState.UNAVAILABLE.value,
                AvailabilityReason.GRACE_WINDOW_EXCEEDED.value,
            )

        if minutes_since_sync is not None and minutes_since_sync >= warn_threshold:
            return (
                AvailabilityState.STALE.value,
                AvailabilityReason.SLA_EXCEEDED.value,
            )

        return (
            AvailabilityState.FRESH.value,
            AvailabilityReason.SYNC_OK.value,
        )

    # ── Internal helpers ─────────────────────────────────────────────────

    def _get_connections(self):
        """Return enabled TenantAirbyteConnections for this tenant."""
        return get_tenant_connections(self.db, self.tenant_id)

    def _get_latest_sync(
        self,
        source_type: str,
    ) -> Tuple[Optional[datetime], Optional[str]]:
        """
        Find the most recent sync timestamp and status across all
        connections that map to the given SLA source key.

        Returns:
            (last_sync_at, last_sync_status) — both None when no
            connection exists.
        """
        connections = self._get_connections()

        best_sync_at: Optional[datetime] = None
        best_status: Optional[str] = None

        for conn in connections:
            sla_key = resolve_sla_key(conn.source_type)
            if sla_key != source_type:
                continue

            if conn.last_sync_at is not None:
                if best_sync_at is None or conn.last_sync_at > best_sync_at:
                    best_sync_at = conn.last_sync_at
                    best_status = conn.last_sync_status

        return best_sync_at, best_status

    def _get_existing(self, source_type: str):
        """Load the current DataAvailability row (or None)."""
        from src.models.data_availability import DataAvailability

        stmt = (
            select(DataAvailability)
            .where(DataAvailability.tenant_id == self.tenant_id)
            .where(DataAvailability.source_type == source_type)
        )
        return self.db.execute(stmt).scalars().first()

    def _upsert(
        self,
        source_type: str,
        state: str,
        reason: str,
        warn_threshold: int,
        error_threshold: int,
        last_sync_at: Optional[datetime],
        last_sync_status: Optional[str],
        minutes_since_sync: Optional[int],
        state_changed_at: datetime,
        previous_state: Optional[str],
        evaluated_at: datetime,
        existing=None,
    ):
        """Insert or update the DataAvailability row."""
        from src.models.data_availability import DataAvailability

        if existing is None:
            row = DataAvailability(
                tenant_id=self.tenant_id,
                source_type=source_type,
                state=state,
                reason=reason,
                warn_threshold_minutes=warn_threshold,
                error_threshold_minutes=error_threshold,
                last_sync_at=last_sync_at,
                last_sync_status=last_sync_status,
                minutes_since_sync=minutes_since_sync,
                state_changed_at=state_changed_at,
                previous_state=previous_state,
                evaluated_at=evaluated_at,
                billing_tier=self.billing_tier,
            )
            self.db.add(row)
        else:
            row = existing
            row.state = state
            row.reason = reason
            row.warn_threshold_minutes = warn_threshold
            row.error_threshold_minutes = error_threshold
            row.last_sync_at = last_sync_at
            row.last_sync_status = last_sync_status
            row.minutes_since_sync = minutes_since_sync
            row.state_changed_at = state_changed_at
            row.previous_state = previous_state
            row.evaluated_at = evaluated_at
            row.billing_tier = self.billing_tier

        self.db.flush()
        return row
