"""
Sync status ingestor for Airbyte OSS sync metadata.

Parses Airbyte sync job metadata to extract last_successful_sync timestamps
per source for freshness signal computation.

Responsibilities:
- Fetch latest sync job metadata for each Airbyte connection mapped to a tenant
- Extract sync timestamps, records/bytes synced, and duration
- Persist ingestion timestamps on TenantAirbyteConnection
- Degrade safely to STALE when signals are missing (never assume FRESH)

SECURITY: All operations are tenant-scoped via tenant_id from JWT.
The tenant_id must come from JWT (org_id), never from client input.
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import List, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from src.integrations.airbyte.client import AirbyteClient, get_airbyte_client
from src.integrations.airbyte.exceptions import AirbyteError, AirbyteNotFoundError
from src.integrations.airbyte.models import AirbyteJobStatus
from src.models.airbyte_connection import TenantAirbyteConnection, ConnectionStatus

logger = logging.getLogger(__name__)


@dataclass
class SyncStatusResult:
    """
    Result of ingesting sync status for a single Airbyte connection.

    Captures the latest sync metadata extracted from the Airbyte API
    and correlated back to a tenant via TenantAirbyteConnection.

    Attributes:
        connection_id: Internal TenantAirbyteConnection.id
        airbyte_connection_id: Airbyte's connection UUID
        source_type: Data source type (e.g. 'shopify', 'facebook')
        last_successful_sync_at: Timestamp of most recent successful sync
        last_sync_status: Status string (success/failed/running)
        records_synced: Number of records synced in latest successful job
        bytes_synced: Number of bytes synced in latest successful job
        sync_duration_seconds: Duration of latest successful sync
        ingested_at: When this status was ingested
        error_message: Error details if ingestion failed
    """

    connection_id: str
    airbyte_connection_id: str
    source_type: Optional[str]
    last_successful_sync_at: Optional[datetime]
    last_sync_status: Optional[str]
    records_synced: int = 0
    bytes_synced: int = 0
    sync_duration_seconds: Optional[float] = None
    ingested_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    error_message: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "connection_id": self.connection_id,
            "airbyte_connection_id": self.airbyte_connection_id,
            "source_type": self.source_type,
            "last_successful_sync_at": (
                self.last_successful_sync_at.isoformat()
                if self.last_successful_sync_at
                else None
            ),
            "last_sync_status": self.last_sync_status,
            "records_synced": self.records_synced,
            "bytes_synced": self.bytes_synced,
            "sync_duration_seconds": self.sync_duration_seconds,
            "ingested_at": self.ingested_at.isoformat(),
            "error_message": self.error_message,
        }


class SyncStatusIngestor:
    """
    Ingests Airbyte sync status metadata for a tenant's connections.

    Fetches the latest sync job for each TenantAirbyteConnection, extracts
    sync timestamps and metrics, and persists them back to the connection
    record for downstream freshness evaluation.

    Safe degradation: if sync metadata cannot be fetched for any reason,
    the result degrades to a missing signal (last_successful_sync_at=None),
    which downstream consumers treat as STALE -- never as FRESH.

    SECURITY: All operations are scoped to the tenant_id provided at
    construction. The tenant_id must originate from JWT (org_id).

    Usage:
        ingestor = SyncStatusIngestor(db_session=session, tenant_id=tid)
        results = await ingestor.ingest_all()
    """

    def __init__(
        self,
        db_session: Session,
        tenant_id: str,
        airbyte_client: Optional[AirbyteClient] = None,
    ):
        """
        Initialize sync status ingestor.

        Args:
            db_session: Database session for persistence
            tenant_id: Tenant identifier from JWT (org_id)
            airbyte_client: Optional Airbyte client (creates default if not provided)

        Raises:
            ValueError: If tenant_id is empty or None
        """
        if not tenant_id:
            raise ValueError("tenant_id is required")

        self.db = db_session
        self.tenant_id = tenant_id
        self._airbyte_client = airbyte_client

    def _get_airbyte_client(self) -> AirbyteClient:
        """Get or create the Airbyte API client."""
        if self._airbyte_client is None:
            self._airbyte_client = get_airbyte_client()
        return self._airbyte_client

    def _get_tenant_connections(self) -> List[TenantAirbyteConnection]:
        """
        Return enabled, non-deleted connections for this tenant.

        SECURITY: Scoped to self.tenant_id from JWT.
        """
        stmt = (
            select(TenantAirbyteConnection)
            .where(TenantAirbyteConnection.tenant_id == self.tenant_id)
            .where(TenantAirbyteConnection.is_enabled.is_(True))
            .where(
                TenantAirbyteConnection.status.notin_([
                    ConnectionStatus.DELETED,
                ])
            )
        )
        return self.db.execute(stmt).scalars().all()

    async def ingest_sync_status(
        self,
        airbyte_connection_id: str,
    ) -> SyncStatusResult:
        """
        Fetch and ingest sync metadata for a single Airbyte connection.

        Queries the Airbyte API for recent jobs on this connection,
        finds the latest successful sync, and extracts its metadata.

        If no successful sync is found or the API call fails, the result
        contains last_successful_sync_at=None, which signals downstream
        consumers to treat the data as STALE (safe degradation).

        Args:
            airbyte_connection_id: Airbyte's connection UUID

        Returns:
            SyncStatusResult with extracted sync metadata or error details
        """
        # Look up the internal connection record
        connection = self._find_connection(airbyte_connection_id)
        if connection is None:
            logger.warning(
                "Connection not found for tenant during sync status ingestion",
                extra={
                    "tenant_id": self.tenant_id,
                    "airbyte_connection_id": airbyte_connection_id,
                },
            )
            return SyncStatusResult(
                connection_id="",
                airbyte_connection_id=airbyte_connection_id,
                source_type=None,
                last_successful_sync_at=None,
                last_sync_status=None,
                error_message="Connection not found for tenant",
            )

        now = datetime.now(timezone.utc)

        try:
            client = self._get_airbyte_client()
            job = await client.get_job(airbyte_connection_id)

            # Determine sync status from the job
            if job.status == AirbyteJobStatus.SUCCEEDED:
                last_sync_status = "success"
                last_successful_sync_at = job.updated_at or now

                # Extract metrics from the last attempt
                records_synced = 0
                bytes_synced = 0
                sync_duration_seconds = None
                if job.attempts:
                    last_attempt = job.attempts[-1]
                    records_synced = last_attempt.records_synced
                    bytes_synced = last_attempt.bytes_synced
                    if last_attempt.created_at and last_attempt.ended_at:
                        sync_duration_seconds = (
                            last_attempt.ended_at - last_attempt.created_at
                        ).total_seconds()

                result = SyncStatusResult(
                    connection_id=connection.id,
                    airbyte_connection_id=airbyte_connection_id,
                    source_type=connection.source_type,
                    last_successful_sync_at=last_successful_sync_at,
                    last_sync_status=last_sync_status,
                    records_synced=records_synced,
                    bytes_synced=bytes_synced,
                    sync_duration_seconds=sync_duration_seconds,
                    ingested_at=now,
                )

            elif job.status in (AirbyteJobStatus.PENDING, AirbyteJobStatus.RUNNING):
                # Sync is in progress -- preserve existing last_successful_sync_at
                result = SyncStatusResult(
                    connection_id=connection.id,
                    airbyte_connection_id=airbyte_connection_id,
                    source_type=connection.source_type,
                    last_successful_sync_at=connection.last_sync_at,
                    last_sync_status="running",
                    ingested_at=now,
                )

            else:
                # Failed, cancelled, incomplete -- degrade to existing or None
                result = SyncStatusResult(
                    connection_id=connection.id,
                    airbyte_connection_id=airbyte_connection_id,
                    source_type=connection.source_type,
                    last_successful_sync_at=connection.last_sync_at,
                    last_sync_status="failed",
                    ingested_at=now,
                    error_message=f"Latest job status: {job.status.value}",
                )

            # Persist the result
            self._persist_sync_status(connection, result)

            logger.info(
                "Sync status ingested",
                extra={
                    "tenant_id": self.tenant_id,
                    "connection_id": connection.id,
                    "airbyte_connection_id": airbyte_connection_id,
                    "source_type": connection.source_type,
                    "last_sync_status": result.last_sync_status,
                    "last_successful_sync_at": (
                        result.last_successful_sync_at.isoformat()
                        if result.last_successful_sync_at
                        else None
                    ),
                },
            )

            return result

        except AirbyteNotFoundError:
            logger.warning(
                "Airbyte job not found for connection",
                extra={
                    "tenant_id": self.tenant_id,
                    "airbyte_connection_id": airbyte_connection_id,
                },
            )
            return SyncStatusResult(
                connection_id=connection.id,
                airbyte_connection_id=airbyte_connection_id,
                source_type=connection.source_type,
                last_successful_sync_at=None,
                last_sync_status=None,
                ingested_at=now,
                error_message="No job found for connection",
            )

        except AirbyteError as e:
            logger.error(
                "Failed to fetch sync status from Airbyte",
                extra={
                    "tenant_id": self.tenant_id,
                    "airbyte_connection_id": airbyte_connection_id,
                    "error": str(e),
                },
            )
            return SyncStatusResult(
                connection_id=connection.id,
                airbyte_connection_id=airbyte_connection_id,
                source_type=connection.source_type,
                last_successful_sync_at=None,
                last_sync_status=None,
                ingested_at=now,
                error_message=f"Airbyte API error: {str(e)[:500]}",
            )

        except Exception as e:
            logger.error(
                "Unexpected error ingesting sync status",
                extra={
                    "tenant_id": self.tenant_id,
                    "airbyte_connection_id": airbyte_connection_id,
                    "error": str(e),
                },
                exc_info=True,
            )
            return SyncStatusResult(
                connection_id=connection.id,
                airbyte_connection_id=airbyte_connection_id,
                source_type=connection.source_type,
                last_successful_sync_at=None,
                last_sync_status=None,
                ingested_at=now,
                error_message=f"Unexpected error: {str(e)[:500]}",
            )

    async def ingest_all(self) -> List[SyncStatusResult]:
        """
        Ingest sync status for all enabled connections belonging to this tenant.

        Iterates over every enabled TenantAirbyteConnection, fetches sync
        metadata from Airbyte, and persists the results. Failures on
        individual connections do not block processing of remaining
        connections.

        Returns:
            List of SyncStatusResult, one per tenant connection.
        """
        connections = self._get_tenant_connections()

        if not connections:
            logger.info(
                "No enabled connections for tenant",
                extra={"tenant_id": self.tenant_id},
            )
            return []

        results: List[SyncStatusResult] = []

        for connection in connections:
            result = await self.ingest_sync_status(connection.airbyte_connection_id)
            results.append(result)

        logger.info(
            "Sync status ingestion completed for tenant",
            extra={
                "tenant_id": self.tenant_id,
                "connections_processed": len(results),
                "successful": sum(
                    1 for r in results if r.error_message is None
                ),
                "failed": sum(
                    1 for r in results if r.error_message is not None
                ),
            },
        )

        return results

    def _find_connection(
        self,
        airbyte_connection_id: str,
    ) -> Optional[TenantAirbyteConnection]:
        """
        Find a TenantAirbyteConnection by Airbyte connection ID within
        tenant scope.

        SECURITY: Filtered by self.tenant_id to prevent cross-tenant access.

        Args:
            airbyte_connection_id: Airbyte's connection UUID

        Returns:
            TenantAirbyteConnection if found, None otherwise
        """
        stmt = (
            select(TenantAirbyteConnection)
            .where(TenantAirbyteConnection.tenant_id == self.tenant_id)
            .where(
                TenantAirbyteConnection.airbyte_connection_id
                == airbyte_connection_id
            )
        )
        return self.db.execute(stmt).scalars().first()

    def _persist_sync_status(
        self,
        connection: TenantAirbyteConnection,
        result: SyncStatusResult,
    ) -> None:
        """
        Update TenantAirbyteConnection with ingested sync metadata.

        Only updates last_sync_at when a successful sync timestamp is
        available. The last_sync_status is always updated to reflect the
        most recent observation.

        Args:
            connection: The TenantAirbyteConnection to update
            result: The ingested SyncStatusResult
        """
        if result.last_successful_sync_at is not None:
            connection.last_sync_at = result.last_successful_sync_at

        if result.last_sync_status is not None:
            connection.last_sync_status = result.last_sync_status

        self.db.flush()
