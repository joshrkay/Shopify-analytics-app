"""
Multi-signal freshness calculator.

Combines ingestion (Airbyte) and transformation (dbt) timestamps into a single
freshness state. Missing signals degrade to STALE, and the worst status wins.

SECURITY: This module is pure calculation — caller must enforce tenant scope.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import List, Optional

from src.services.data_availability_service import minutes_since_sync
from src.services.data_health_service import (
    DEFAULT_CRITICAL_THRESHOLD_MINUTES,
    DEFAULT_FRESHNESS_THRESHOLD_MINUTES,
    FreshnessStatus,
)

logger = logging.getLogger(__name__)


# ── Data structures ──────────────────────────────────────────────────────────


@dataclass(frozen=True)
class FreshnessSignal:
    """One signal contributing to overall freshness."""

    name: str
    status: FreshnessStatus
    observed_at: Optional[datetime]
    minutes_since: Optional[int]
    reason: Optional[str] = None


@dataclass(frozen=True)
class FreshnessComputation:
    """Aggregate freshness result."""

    overall_status: FreshnessStatus
    signals: List[FreshnessSignal]


# ── Calculator ───────────────────────────────────────────────────────────────


class FreshnessCalculator:
    """
    Compute freshness from multiple signals (Airbyte, dbt run, dbt freshness).

    Missing signals are treated as STALE to avoid false freshness.
    """

    def __init__(
        self,
        warn_threshold_minutes: int = DEFAULT_FRESHNESS_THRESHOLD_MINUTES,
        critical_threshold_minutes: int = DEFAULT_CRITICAL_THRESHOLD_MINUTES,
        missing_status: FreshnessStatus = FreshnessStatus.STALE,
    ):
        self.warn_threshold_minutes = warn_threshold_minutes
        self.critical_threshold_minutes = critical_threshold_minutes
        self.missing_status = missing_status

    def _classify_timestamp(self, ts: Optional[datetime]) -> tuple[FreshnessStatus, Optional[int]]:
        """Classify a timestamp into FreshnessStatus with minutes_since."""
        mins = minutes_since_sync(ts)
        if mins is None:
            return self.missing_status, None

        if mins <= self.warn_threshold_minutes:
            return FreshnessStatus.FRESH, mins
        if mins <= self.critical_threshold_minutes:
            return FreshnessStatus.STALE, mins
        return FreshnessStatus.CRITICAL, mins

    @staticmethod
    def _severity(status: FreshnessStatus) -> int:
        """Higher value means worse freshness."""
        if status == FreshnessStatus.CRITICAL:
            return 3
        if status in (FreshnessStatus.STALE, FreshnessStatus.NEVER_SYNCED):
            return 2
        if status == FreshnessStatus.FRESH:
            return 1
        return 0

    def _build_signal(self, name: str, ts: Optional[datetime]) -> FreshnessSignal:
        """Build a FreshnessSignal for a timestamp (or missing)."""
        status, minutes_since = self._classify_timestamp(_normalize(ts))
        reason = None if ts else "missing signal"
        return FreshnessSignal(
            name=name,
            status=status,
            observed_at=_normalize(ts),
            minutes_since=minutes_since,
            reason=reason,
        )

    def calculate(
        self,
        airbyte_last_sync_at: Optional[datetime],
        dbt_run_completed_at: Optional[datetime],
        dbt_freshness_snapshotted_at: Optional[datetime],
    ) -> FreshnessComputation:
        """
        Compute overall freshness across three signals.

        Args:
            airbyte_last_sync_at: Last successful ingestion sync.
            dbt_run_completed_at: Completion time of the latest dbt run.
            dbt_freshness_snapshotted_at: Timestamp from dbt freshness.json.
        """
        signals = [
            self._build_signal("airbyte_sync", airbyte_last_sync_at),
            self._build_signal("dbt_run", dbt_run_completed_at),
            self._build_signal("dbt_freshness", dbt_freshness_snapshotted_at),
        ]

        worst = max(signals, key=lambda s: self._severity(s.status)).status
        return FreshnessComputation(overall_status=worst, signals=signals)


# ── Utility ──────────────────────────────────────────────────────────────────


def _normalize(ts: Optional[datetime]) -> Optional[datetime]:
    """Normalize timestamps to timezone-aware UTC."""
    if ts is None:
        return None
    if ts.tzinfo is None:
        return ts.replace(tzinfo=timezone.utc)
    return ts.astimezone(timezone.utc)
