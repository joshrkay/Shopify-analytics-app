"""
Airbyte sync metadata ingestor.

Parses Airbyte OSS job history payloads and propagates the latest sync
timestamps to `TenantAirbyteConnection` in a tenant-scoped, idempotent way.

SECURITY: tenant_id is supplied by the caller (JWT), never from user input.
Only connection rows for the tenant are updated. Payload bodies are not logged.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Dict, Iterable, List, Optional

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from src.integrations.airbyte.models import AirbyteJob, AirbyteJobStatus
from src.models.airbyte_connection import TenantAirbyteConnection

logger = logging.getLogger(__name__)


# ── Data structures ──────────────────────────────────────────────────────────


@dataclass(frozen=True)
class SyncStatusRecord:
    """Flattened view of a single Airbyte job."""

    connection_id: str  # Airbyte connection ID
    job_id: str
    status: AirbyteJobStatus
    completed_at: Optional[datetime]
    records_synced: int = 0
    bytes_synced: int = 0


@dataclass
class AggregatedSync:
    """Latest sync metadata for a connection."""

    latest_seen_at: datetime
    latest_status: AirbyteJobStatus
    latest_success_at: Optional[datetime] = None

    def update(self, record: SyncStatusRecord) -> None:
        """Fold a new record into the aggregate."""
        if _is_newer(record.completed_at, self.latest_seen_at):
            self.latest_seen_at = record.completed_at  # type: ignore[assignment]
            self.latest_status = record.status
        if (
            record.status == AirbyteJobStatus.SUCCEEDED
            and _is_newer(record.completed_at, self.latest_success_at)
        ):
            self.latest_success_at = record.completed_at


# ── Helpers ──────────────────────────────────────────────────────────────────


def _normalize_timestamp(ts: Optional[datetime]) -> Optional[datetime]:
    """Force timezone-aware UTC timestamps."""
    if ts is None:
        return None
    if ts.tzinfo is None:
        return ts.replace(tzinfo=timezone.utc)
    return ts.astimezone(timezone.utc)


def _is_newer(candidate: Optional[datetime], current: Optional[datetime]) -> bool:
    """Return True when candidate is newer than current (None treated as older)."""
    if candidate is None:
        return False
    if current is None:
        return True
    return candidate > current


def _job_completed_at(job: AirbyteJob) -> Optional[datetime]:
    """Derive the best-effort completion timestamp for a job."""
    candidates: List[datetime] = []
    for attempt in job.attempts:
        if attempt.ended_at:
            normalized = _normalize_timestamp(attempt.ended_at)
            if normalized:
                candidates.append(normalized)
    for ts in (job.updated_at, job.created_at):
        normalized = _normalize_timestamp(ts)
        if normalized:
            candidates.append(normalized)
    if not candidates:
        return None
    return max(candidates)


def _to_record(raw: dict) -> Optional[SyncStatusRecord]:
    """Convert raw API dict into a SyncStatusRecord."""
    job = AirbyteJob.from_dict(raw)
    completed_at = _job_completed_at(job)
    if not job.config_id:
        return None
    return SyncStatusRecord(
        connection_id=job.config_id,
        job_id=job.job_id,
        status=job.status,
        completed_at=completed_at,
        records_synced=max((a.records_synced for a in job.attempts), default=0),
        bytes_synced=max((a.bytes_synced for a in job.attempts), default=0),
    )


# ── Ingestor ─────────────────────────────────────────────────────────────────


class SyncStatusIngestor:
    """
    Apply Airbyte job history to TenantAirbyteConnection rows.

    Idempotent: only forward-updates timestamps; never rewinds last_sync_at.
    """

    def __init__(self, db_session: Session, tenant_id: str):
        if not tenant_id:
            raise ValueError("tenant_id is required")
        self.db = db_session
        self.tenant_id = tenant_id

    def ingest(self, job_history: Iterable[dict]) -> Dict[str, AggregatedSync]:
        """
        Ingest Airbyte job history payloads.

        Args:
            job_history: Iterable of job dicts from Airbyte API (/jobs/list).

        Returns:
            Mapping of airbyte_connection_id -> AggregatedSync that was applied.
        """
        aggregates = self._aggregate(job_history)
        if not aggregates:
            return {}

        updated = self._persist(aggregates)
        logger.info(
            "sync_status_ingestor.applied",
            extra={
                "tenant_id": self.tenant_id,
                "connections_updated": len(updated),
            },
        )
        return aggregates

    def _aggregate(self, job_history: Iterable[dict]) -> Dict[str, AggregatedSync]:
        """Collapse job history into latest-per-connection aggregates."""
        aggregates: Dict[str, AggregatedSync] = {}
        for raw in job_history:
            record = _to_record(raw)
            if record is None or record.completed_at is None:
                continue

            record = SyncStatusRecord(
                connection_id=record.connection_id,
                job_id=record.job_id,
                status=record.status,
                completed_at=_normalize_timestamp(record.completed_at),
                records_synced=record.records_synced,
                bytes_synced=record.bytes_synced,
            )

            if record.connection_id not in aggregates:
                aggregates[record.connection_id] = AggregatedSync(
                    latest_seen_at=record.completed_at,
                    latest_status=record.status,
                    latest_success_at=(
                        record.completed_at
                        if record.status == AirbyteJobStatus.SUCCEEDED
                        else None
                    ),
                )
                continue

            aggregates[record.connection_id].update(record)

        return aggregates

    def _persist(self, aggregates: Dict[str, AggregatedSync]) -> List[str]:
        """Apply aggregates to DB rows, forward-only."""
        connection_ids = list(aggregates.keys())
        if not connection_ids:
            return []

        stmt = (
            select(TenantAirbyteConnection)
            .where(TenantAirbyteConnection.tenant_id == self.tenant_id)
            .where(TenantAirbyteConnection.airbyte_connection_id.in_(connection_ids))
        )
        rows = self.db.execute(stmt).scalars().all()

        updated_ids: List[str] = []
        for row in rows:
            agg = aggregates.get(row.airbyte_connection_id)
            if agg is None:
                continue

            values: Dict[str, object] = {"last_sync_status": agg.latest_status.value}

            if agg.latest_success_at and _is_newer(agg.latest_success_at, row.last_sync_at):
                values["last_sync_at"] = agg.latest_success_at

            # Only issue an update when something changes.
            should_update = (
                values.get("last_sync_at") is not None
                or values["last_sync_status"] != row.last_sync_status
            )
            if not should_update:
                continue

            update_stmt = (
                update(TenantAirbyteConnection)
                .where(
                    TenantAirbyteConnection.id == row.id,
                    TenantAirbyteConnection.tenant_id == self.tenant_id,
                )
                .values(**values)
            )
            self.db.execute(update_stmt)
            updated_ids.append(row.id)

        if updated_ids:
            self.db.commit()

        return updated_ids
