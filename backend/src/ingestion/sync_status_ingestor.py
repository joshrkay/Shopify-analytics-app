"""
Airbyte sync status ingestor.

Parses Airbyte OSS job history to extract last_successful_sync per source.
Updates TenantAirbyteConnection.last_sync_at with forward-only semantics
(newer timestamps only overwrite older ones).

SECURITY: All operations are tenant-scoped via tenant_id from JWT.

Usage:
    from src.ingestion.sync_status_ingestor import SyncStatusIngestor

    ingestor = SyncStatusIngestor(db_session=session, tenant_id=tenant_id)
    result = await ingestor.ingest_sync_status(airbyte_connection_id, sync_metadata)
"""

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional, List

from sqlalchemy import update
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


@dataclass
class AirbyteSyncMetadata:
    """
    Metadata extracted from an Airbyte sync job.

    Attributes:
        job_id: Airbyte job ID
        connection_id: Airbyte connection ID
        status: Job status (succeeded, failed, cancelled, running)
        started_at: Job start timestamp
        completed_at: Job completion timestamp (None if still running)
        records_synced: Number of records synced
        bytes_synced: Number of bytes synced
        error_message: Error message if failed
    """
    job_id: str
    connection_id: str
    status: str
    started_at: Optional[datetime]
    completed_at: Optional[datetime]
    records_synced: int = 0
    bytes_synced: int = 0
    error_message: Optional[str] = None


@dataclass
class SyncIngestionResult:
    """
    Result of sync status ingestion.

    Attributes:
        connection_id: Internal connection ID
        updated: Whether the connection was updated
        previous_sync_at: Previous last_sync_at value
        new_sync_at: New last_sync_at value (if updated)
        skipped_reason: Reason if update was skipped
    """
    connection_id: str
    updated: bool
    previous_sync_at: Optional[datetime] = None
    new_sync_at: Optional[datetime] = None
    skipped_reason: Optional[str] = None


class SyncStatusIngestorError(Exception):
    """Base exception for sync status ingestor errors."""
    pass


class SyncStatusIngestor:
    """
    Ingests Airbyte sync status and updates connection freshness.

    Forward-only update semantics: only updates last_sync_at if the new
    timestamp is newer than the existing one. This ensures idempotency
    when processing out-of-order job completions.

    SECURITY: tenant_id must come from JWT (org_id), never client input.
    """

    def __init__(self, db_session: Session, tenant_id: str):
        """
        Initialize sync status ingestor.

        Args:
            db_session: Database session
            tenant_id: Tenant ID from JWT (org_id)

        Raises:
            ValueError: If tenant_id is empty or None
        """
        if not tenant_id:
            raise ValueError("tenant_id is required")

        self.db = db_session
        self.tenant_id = tenant_id

    def _get_connection_by_airbyte_id(
        self,
        airbyte_connection_id: str,
    ):
        """
        Get TenantAirbyteConnection by Airbyte connection ID.

        SECURITY: Only returns connections belonging to current tenant.
        """
        from src.models.airbyte_connection import TenantAirbyteConnection

        return (
            self.db.query(TenantAirbyteConnection)
            .filter(
                TenantAirbyteConnection.tenant_id == self.tenant_id,
                TenantAirbyteConnection.airbyte_connection_id == airbyte_connection_id,
            )
            .first()
        )

    def _parse_timestamp(self, ts: Optional[str | datetime]) -> Optional[datetime]:
        """
        Parse timestamp from various formats.

        Handles:
        - datetime objects (returned as-is with UTC timezone)
        - ISO 8601 strings
        - Unix epoch seconds
        """
        if ts is None:
            return None

        if isinstance(ts, datetime):
            if ts.tzinfo is None:
                return ts.replace(tzinfo=timezone.utc)
            return ts

        if isinstance(ts, (int, float)):
            return datetime.fromtimestamp(ts, tz=timezone.utc)

        if isinstance(ts, str):
            # Try ISO 8601 format
            try:
                parsed = datetime.fromisoformat(ts.replace("Z", "+00:00"))
                if parsed.tzinfo is None:
                    parsed = parsed.replace(tzinfo=timezone.utc)
                return parsed
            except ValueError:
                pass

            # Try Unix epoch as string
            try:
                return datetime.fromtimestamp(float(ts), tz=timezone.utc)
            except ValueError:
                pass

        logger.warning(
            "Failed to parse timestamp",
            extra={"tenant_id": self.tenant_id, "timestamp": str(ts)},
        )
        return None

    def parse_airbyte_job_response(
        self,
        job_response: dict,
    ) -> Optional[AirbyteSyncMetadata]:
        """
        Parse Airbyte API job response into SyncMetadata.

        Expected format (Airbyte OSS API v1):
        {
            "job": {
                "id": 123,
                "configType": "sync",
                "status": "succeeded",
                "createdAt": 1700000000,
                "updatedAt": 1700000100
            },
            "attempts": [{
                "id": 0,
                "status": "succeeded",
                "recordsSynced": 1000,
                "bytesSynced": 50000,
                "endedAt": 1700000100
            }]
        }

        Args:
            job_response: Raw Airbyte job API response

        Returns:
            AirbyteSyncMetadata if parseable, None otherwise
        """
        if not job_response:
            return None

        job = job_response.get("job", {})
        attempts = job_response.get("attempts", [])

        job_id = str(job.get("id", ""))
        connection_id = str(job.get("configId", ""))
        status = job.get("status", "unknown")

        if not job_id:
            logger.warning(
                "Missing job_id in Airbyte response",
                extra={"tenant_id": self.tenant_id},
            )
            return None

        # Extract timestamps
        started_at = self._parse_timestamp(job.get("createdAt"))
        completed_at = self._parse_timestamp(job.get("updatedAt"))

        # Aggregate metrics from attempts
        records_synced = 0
        bytes_synced = 0
        error_message = None

        for attempt in attempts:
            records_synced += attempt.get("recordsSynced", 0) or 0
            bytes_synced += attempt.get("bytesSynced", 0) or 0

            if attempt.get("status") == "failed":
                error_message = attempt.get("failureSummary", {}).get("message")

            # Use attempt end time if available
            attempt_ended = self._parse_timestamp(attempt.get("endedAt"))
            if attempt_ended and (completed_at is None or attempt_ended > completed_at):
                completed_at = attempt_ended

        return AirbyteSyncMetadata(
            job_id=job_id,
            connection_id=connection_id,
            status=status,
            started_at=started_at,
            completed_at=completed_at,
            records_synced=records_synced,
            bytes_synced=bytes_synced,
            error_message=error_message,
        )

    def ingest_sync_status(
        self,
        airbyte_connection_id: str,
        sync_metadata: AirbyteSyncMetadata,
    ) -> SyncIngestionResult:
        """
        Ingest sync status and update connection freshness.

        Forward-only semantics: only updates if new timestamp > existing.
        Only successful syncs update last_sync_at.

        Args:
            airbyte_connection_id: Airbyte connection ID
            sync_metadata: Parsed sync metadata

        Returns:
            SyncIngestionResult indicating whether update occurred
        """
        connection = self._get_connection_by_airbyte_id(airbyte_connection_id)

        if connection is None:
            logger.warning(
                "Connection not found for sync ingestion",
                extra={
                    "tenant_id": self.tenant_id,
                    "airbyte_connection_id": airbyte_connection_id,
                },
            )
            return SyncIngestionResult(
                connection_id=airbyte_connection_id,
                updated=False,
                skipped_reason="Connection not found",
            )

        # Only update on successful syncs
        if sync_metadata.status != "succeeded":
            # Update status but not timestamp
            self._update_connection_status(
                connection.id,
                sync_status="failed",
            )
            logger.info(
                "Sync status ingested (non-success)",
                extra={
                    "tenant_id": self.tenant_id,
                    "connection_id": connection.id,
                    "airbyte_connection_id": airbyte_connection_id,
                    "status": sync_metadata.status,
                },
            )
            return SyncIngestionResult(
                connection_id=connection.id,
                updated=False,
                previous_sync_at=connection.last_sync_at,
                skipped_reason=f"Sync status was {sync_metadata.status}",
            )

        new_sync_at = sync_metadata.completed_at
        if new_sync_at is None:
            return SyncIngestionResult(
                connection_id=connection.id,
                updated=False,
                previous_sync_at=connection.last_sync_at,
                skipped_reason="No completion timestamp",
            )

        # Forward-only: skip if existing is newer
        if connection.last_sync_at is not None:
            existing_sync_at = connection.last_sync_at
            if existing_sync_at.tzinfo is None:
                existing_sync_at = existing_sync_at.replace(tzinfo=timezone.utc)

            if existing_sync_at >= new_sync_at:
                logger.debug(
                    "Skipping sync update (existing is newer)",
                    extra={
                        "tenant_id": self.tenant_id,
                        "connection_id": connection.id,
                        "existing": existing_sync_at.isoformat(),
                        "new": new_sync_at.isoformat(),
                    },
                )
                return SyncIngestionResult(
                    connection_id=connection.id,
                    updated=False,
                    previous_sync_at=existing_sync_at,
                    skipped_reason="Existing timestamp is newer or equal",
                )

        # Perform update
        previous_sync_at = connection.last_sync_at
        self._update_connection_timestamp(connection.id, new_sync_at)

        logger.info(
            "Sync status ingested successfully",
            extra={
                "tenant_id": self.tenant_id,
                "connection_id": connection.id,
                "airbyte_connection_id": airbyte_connection_id,
                "previous_sync_at": (
                    previous_sync_at.isoformat() if previous_sync_at else None
                ),
                "new_sync_at": new_sync_at.isoformat(),
                "records_synced": sync_metadata.records_synced,
            },
        )

        return SyncIngestionResult(
            connection_id=connection.id,
            updated=True,
            previous_sync_at=previous_sync_at,
            new_sync_at=new_sync_at,
        )

    def _update_connection_timestamp(
        self,
        connection_id: str,
        sync_at: datetime,
    ) -> None:
        """Update connection last_sync_at and status."""
        from src.models.airbyte_connection import TenantAirbyteConnection

        stmt = (
            update(TenantAirbyteConnection)
            .where(TenantAirbyteConnection.id == connection_id)
            .where(TenantAirbyteConnection.tenant_id == self.tenant_id)
            .values(
                last_sync_at=sync_at,
                last_sync_status="success",
            )
        )
        self.db.execute(stmt)
        self.db.flush()

    def _update_connection_status(
        self,
        connection_id: str,
        sync_status: str,
    ) -> None:
        """Update connection sync status without changing timestamp."""
        from src.models.airbyte_connection import TenantAirbyteConnection

        stmt = (
            update(TenantAirbyteConnection)
            .where(TenantAirbyteConnection.id == connection_id)
            .where(TenantAirbyteConnection.tenant_id == self.tenant_id)
            .values(last_sync_status=sync_status)
        )
        self.db.execute(stmt)
        self.db.flush()

    def ingest_from_job_list(
        self,
        jobs: List[dict],
    ) -> List[SyncIngestionResult]:
        """
        Batch ingest sync statuses from a list of Airbyte job responses.

        Processes jobs in order, applying forward-only semantics.

        Args:
            jobs: List of Airbyte job API responses

        Returns:
            List of SyncIngestionResult for each processed job
        """
        results = []

        for job_response in jobs:
            metadata = self.parse_airbyte_job_response(job_response)
            if metadata is None:
                continue

            result = self.ingest_sync_status(
                airbyte_connection_id=metadata.connection_id,
                sync_metadata=metadata,
            )
            results.append(result)

        logger.info(
            "Batch sync ingestion complete",
            extra={
                "tenant_id": self.tenant_id,
                "total_jobs": len(jobs),
                "processed": len(results),
                "updated": sum(1 for r in results if r.updated),
            },
        )

        return results
