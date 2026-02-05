"""
Source disconnection service for AI Growth Analytics.

Orchestrates the full disconnection lifecycle when a merchant disconnects
a data source (Shopify, Meta, Google, etc.):

1. Cancel all active/queued syncs immediately
2. Revoke credentials (marks as REVOKED)
3. Soft-delete credentials (5-day restore window, 20-day hard delete)
4. Disable the Airbyte connection
5. Audit every step for compliance

SECURITY:
- tenant_id MUST come from JWT (org_id), never client input
- All credential handling delegated to CredentialVault and TokenManager
- Every state change emits an audit event

Usage:
    from src.services.disconnect_service import DisconnectService

    service = DisconnectService(db_session=session, tenant_id=tenant_id)
    result = await service.disconnect_source(
        source_type="shopify",
        connection_id="conn-123",
        disconnected_by="clerk_user_abc",
        reason=DisconnectReason.USER_REQUEST,
    )
"""

import enum
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


# =============================================================================
# Enums & Data Classes
# =============================================================================


class DisconnectReason(str, enum.Enum):
    """Reason for disconnecting a source."""

    USER_REQUEST = "user_request"
    ADMIN_ACTION = "admin_action"
    TOKEN_REVOKED = "token_revoked"
    SECURITY_EVENT = "security_event"
    APP_UNINSTALLED = "app_uninstalled"


@dataclass
class DisconnectResult:
    """Result of a disconnect operation."""

    source_type: str
    connection_id: Optional[str]
    reason: str
    jobs_cancelled: int = 0
    credentials_revoked: int = 0
    credentials_soft_deleted: int = 0
    connection_disabled: bool = False
    audit_correlation_id: Optional[str] = None
    errors: list = field(default_factory=list)

    @property
    def success(self) -> bool:
        return len(self.errors) == 0

    def to_dict(self) -> dict:
        return {
            "source_type": self.source_type,
            "connection_id": self.connection_id,
            "reason": self.reason,
            "jobs_cancelled": self.jobs_cancelled,
            "credentials_revoked": self.credentials_revoked,
            "credentials_soft_deleted": self.credentials_soft_deleted,
            "connection_disabled": self.connection_disabled,
            "success": self.success,
            "error_count": len(self.errors),
        }


# =============================================================================
# Disconnect Service
# =============================================================================


class DisconnectService:
    """
    Orchestrates source disconnection with full audit trail.

    Coordinates across JobDispatcher, TokenManager, CredentialVault,
    and AirbyteService to ensure clean, auditable disconnection.
    """

    def __init__(self, db_session: Session, tenant_id: str):
        if not tenant_id:
            raise ValueError("tenant_id is required")

        self.db = db_session
        self.tenant_id = tenant_id

    async def disconnect_source(
        self,
        source_type: str,
        disconnected_by: str,
        reason: DisconnectReason,
        connection_id: Optional[str] = None,
    ) -> DisconnectResult:
        """
        Disconnect a data source completely.

        Steps executed in order:
        1. Cancel active/queued ingestion jobs
        2. Revoke all credentials for this source
        3. Soft-delete all credentials (5-day restore, 20-day hard delete)
        4. Disable the Airbyte connection
        5. Log audit event

        Args:
            source_type: Platform being disconnected (shopify, meta, google, etc.)
            disconnected_by: clerk_user_id performing the disconnect
            reason: Why the source is being disconnected
            connection_id: Optional specific connection ID to disconnect

        Returns:
            DisconnectResult with summary of actions taken
        """
        result = DisconnectResult(
            source_type=source_type,
            connection_id=connection_id,
            reason=reason.value,
        )

        logger.info(
            "Starting source disconnect",
            extra={
                "tenant_id": self.tenant_id,
                "source_type": source_type,
                "connection_id": connection_id,
                "reason": reason.value,
                "disconnected_by": disconnected_by,
            },
        )

        # Step 1: Cancel active syncs
        result.jobs_cancelled = self._cancel_active_jobs(
            source_type, connection_id, result
        )

        # Step 2: Revoke credentials
        result.credentials_revoked = await self._revoke_credentials(
            source_type, reason, disconnected_by, result
        )

        # Step 3: Soft-delete credentials
        result.credentials_soft_deleted = self._soft_delete_credentials(
            source_type, disconnected_by, result
        )

        # Step 4: Disable connection
        result.connection_disabled = self._disable_connection(
            connection_id, result
        )

        # Step 5: Audit the full disconnect
        result.audit_correlation_id = self._log_disconnect_audit(
            source_type, connection_id, reason, disconnected_by, result
        )

        logger.info(
            "Source disconnect completed",
            extra={
                "tenant_id": self.tenant_id,
                **result.to_dict(),
            },
        )

        return result

    # =========================================================================
    # Step 1: Cancel Active Jobs
    # =========================================================================

    def _cancel_active_jobs(
        self,
        source_type: str,
        connection_id: Optional[str],
        result: DisconnectResult,
    ) -> int:
        """Cancel all active (queued/running) ingestion jobs for the source."""
        try:
            from src.ingestion.jobs.models import IngestionJob, JobStatus
            from sqlalchemy import select

            # Find active jobs for this source
            stmt = (
                select(IngestionJob)
                .where(IngestionJob.tenant_id == self.tenant_id)
                .where(IngestionJob.status.in_([
                    JobStatus.QUEUED,
                    JobStatus.RUNNING,
                    JobStatus.FAILED,
                ]))
            )

            if connection_id:
                stmt = stmt.where(IngestionJob.connector_id == connection_id)

            active_jobs = self.db.execute(stmt).scalars().all()

            cancelled = 0
            for job in active_jobs:
                if job.status == JobStatus.QUEUED:
                    job.status = JobStatus.FAILED
                    job.error_message = f"Cancelled: source disconnected ({source_type})"
                    job.error_code = "source_disconnected"
                    job.completed_at = datetime.now(timezone.utc)
                    job.next_retry_at = None
                    cancelled += 1
                elif job.status == JobStatus.RUNNING:
                    # Running jobs: mark failed so they won't retry
                    job.error_message = f"Aborted: source disconnected ({source_type})"
                    job.error_code = "source_disconnected"
                    job.next_retry_at = None
                    cancelled += 1
                elif job.status == JobStatus.FAILED:
                    # Failed jobs awaiting retry: clear retry schedule
                    job.next_retry_at = None
                    job.error_message = (
                        f"{job.error_message or ''} "
                        f"[retry cancelled: source disconnected]"
                    ).strip()
                    cancelled += 1

            if cancelled:
                self.db.flush()

            logger.info(
                "Active jobs cancelled for disconnect",
                extra={
                    "tenant_id": self.tenant_id,
                    "source_type": source_type,
                    "jobs_cancelled": cancelled,
                },
            )

            return cancelled

        except Exception as exc:
            error_msg = f"Failed to cancel active jobs: {exc}"
            logger.error(error_msg, extra={"tenant_id": self.tenant_id})
            result.errors.append(error_msg)
            return 0

    # =========================================================================
    # Step 2: Revoke Credentials
    # =========================================================================

    async def _revoke_credentials(
        self,
        source_type: str,
        reason: DisconnectReason,
        disconnected_by: str,
        result: DisconnectResult,
    ) -> int:
        """Revoke all active credentials for this source type."""
        try:
            from src.services.token_manager import TokenManager, RevocationReason

            reason_map = {
                DisconnectReason.USER_REQUEST: RevocationReason.USER_DISCONNECT,
                DisconnectReason.ADMIN_ACTION: RevocationReason.ADMIN_ACTION,
                DisconnectReason.TOKEN_REVOKED: RevocationReason.PROVIDER_REVOKED,
                DisconnectReason.SECURITY_EVENT: RevocationReason.SECURITY_EVENT,
                DisconnectReason.APP_UNINSTALLED: RevocationReason.USER_DISCONNECT,
            }

            revocation_reason = reason_map.get(
                reason, RevocationReason.USER_DISCONNECT
            )

            manager = TokenManager(
                db_session=self.db, tenant_id=self.tenant_id
            )
            count = await manager.revoke_all_for_connection(
                source_type=source_type,
                reason=revocation_reason,
                revoked_by=disconnected_by,
            )

            logger.info(
                "Credentials revoked for disconnect",
                extra={
                    "tenant_id": self.tenant_id,
                    "source_type": source_type,
                    "credentials_revoked": count,
                },
            )

            return count

        except Exception as exc:
            error_msg = f"Failed to revoke credentials: {exc}"
            logger.error(error_msg, extra={"tenant_id": self.tenant_id})
            result.errors.append(error_msg)
            return 0

    # =========================================================================
    # Step 3: Soft-Delete Credentials
    # =========================================================================

    def _soft_delete_credentials(
        self,
        source_type: str,
        deleted_by: str,
        result: DisconnectResult,
    ) -> int:
        """Soft-delete all credentials for this source (5-day restore window)."""
        try:
            from src.models.connector_credential import (
                ConnectorCredential,
                CredentialStatus,
            )
            from src.services.credential_vault import CredentialVault
            from sqlalchemy import select

            # Find all non-soft-deleted credentials for this source
            stmt = (
                select(ConnectorCredential)
                .where(ConnectorCredential.tenant_id == self.tenant_id)
                .where(ConnectorCredential.source_type == source_type)
                .where(ConnectorCredential.soft_deleted_at.is_(None))
            )
            credentials = self.db.execute(stmt).scalars().all()

            if not credentials:
                return 0

            vault = CredentialVault(
                db_session=self.db, tenant_id=self.tenant_id
            )

            deleted = 0
            for cred in credentials:
                try:
                    vault.soft_delete(
                        credential_id=cred.id,
                        deleted_by=deleted_by,
                    )
                    deleted += 1
                except Exception as exc:
                    # Credential may already be soft-deleted (race condition)
                    logger.warning(
                        "Failed to soft-delete individual credential",
                        extra={
                            "tenant_id": self.tenant_id,
                            "credential_id": cred.id,
                            "error": str(exc),
                        },
                    )

            logger.info(
                "Credentials soft-deleted for disconnect",
                extra={
                    "tenant_id": self.tenant_id,
                    "source_type": source_type,
                    "credentials_soft_deleted": deleted,
                },
            )

            return deleted

        except Exception as exc:
            error_msg = f"Failed to soft-delete credentials: {exc}"
            logger.error(error_msg, extra={"tenant_id": self.tenant_id})
            result.errors.append(error_msg)
            return 0

    # =========================================================================
    # Step 4: Disable Connection
    # =========================================================================

    def _disable_connection(
        self,
        connection_id: Optional[str],
        result: DisconnectResult,
    ) -> bool:
        """Disable the Airbyte connection to prevent future syncs."""
        if not connection_id:
            return False

        try:
            from src.models.airbyte_connection import (
                TenantAirbyteConnection,
                ConnectionStatus,
            )
            from sqlalchemy import select

            stmt = (
                select(TenantAirbyteConnection)
                .where(TenantAirbyteConnection.id == connection_id)
                .where(TenantAirbyteConnection.tenant_id == self.tenant_id)
            )
            connection = self.db.execute(stmt).scalar_one_or_none()

            if not connection:
                logger.warning(
                    "Connection not found for disable",
                    extra={
                        "tenant_id": self.tenant_id,
                        "connection_id": connection_id,
                    },
                )
                return False

            connection.status = ConnectionStatus.DELETED
            connection.is_enabled = False
            self.db.flush()

            logger.info(
                "Connection disabled for disconnect",
                extra={
                    "tenant_id": self.tenant_id,
                    "connection_id": connection_id,
                },
            )

            return True

        except Exception as exc:
            error_msg = f"Failed to disable connection: {exc}"
            logger.error(error_msg, extra={"tenant_id": self.tenant_id})
            result.errors.append(error_msg)
            return False

    # =========================================================================
    # Step 5: Audit
    # =========================================================================

    def _log_disconnect_audit(
        self,
        source_type: str,
        connection_id: Optional[str],
        reason: DisconnectReason,
        disconnected_by: str,
        result: DisconnectResult,
    ) -> Optional[str]:
        """Log disconnect as an auditable event."""
        try:
            from src.platform.audit import (
                AuditAction,
                AuditOutcome,
                log_system_audit_event_sync,
            )

            outcome = (
                AuditOutcome.SUCCESS if result.success
                else AuditOutcome.FAILURE
            )

            correlation_id = log_system_audit_event_sync(
                db=self.db,
                tenant_id=self.tenant_id,
                action=AuditAction.STORE_DISCONNECTED,
                resource_type="connection",
                resource_id=connection_id or source_type,
                metadata={
                    "source_type": source_type,
                    "reason": reason.value,
                    "disconnected_by": disconnected_by,
                    "jobs_cancelled": result.jobs_cancelled,
                    "credentials_revoked": result.credentials_revoked,
                    "credentials_soft_deleted": result.credentials_soft_deleted,
                    "connection_disabled": result.connection_disabled,
                    "error_count": len(result.errors),
                },
                source="service",
                outcome=outcome,
            )

            return correlation_id

        except Exception as exc:
            logger.error(
                "Failed to log disconnect audit event",
                extra={"tenant_id": self.tenant_id, "error": str(exc)},
            )
            result.errors.append(f"Audit logging failed: {exc}")
            return None
