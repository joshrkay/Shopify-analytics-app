"""
Tests for source disconnection and data retention.

Validates:
- DisconnectService: full disconnect lifecycle (cancel jobs, revoke creds,
  soft-delete creds, disable connection, audit)
- CredentialCleanupJob: hard-delete after 20-day deadline
- Retention policy compliance
- Audit trail completeness

Story: Secure Credential Vault - Disconnect & Retention
"""

import json
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch, call

import pytest

from src.services.disconnect_service import (
    DisconnectReason,
    DisconnectResult,
    DisconnectService,
)

# =============================================================================
# Constants
# =============================================================================

TENANT_ID = "tenant-disconnect-001"
CONNECTION_ID = "conn-disconnect-001"
USER_ID = "clerk_user_disconnect"


# =============================================================================
# Helpers
# =============================================================================


def _mock_session():
    """Create a mock database session."""
    session = MagicMock()
    session.flush = MagicMock()
    session.commit = MagicMock()
    session.rollback = MagicMock()
    return session


def _make_job(job_id, status, connector_id=CONNECTION_ID, **kwargs):
    """Create a mock IngestionJob."""
    from src.ingestion.jobs.models import JobStatus

    job = MagicMock()
    job.job_id = job_id
    job.tenant_id = TENANT_ID
    job.connector_id = connector_id
    job.status = status
    job.error_message = kwargs.get("error_message", None)
    job.error_code = kwargs.get("error_code", None)
    job.next_retry_at = kwargs.get("next_retry_at", None)
    job.completed_at = kwargs.get("completed_at", None)
    return job


def _make_credential(cred_id, source_type="shopify", status=None, **kwargs):
    """Create a mock ConnectorCredential."""
    from src.models.connector_credential import CredentialStatus

    cred = MagicMock()
    cred.id = cred_id
    cred.tenant_id = TENANT_ID
    cred.source_type = source_type
    cred.status = status or CredentialStatus.ACTIVE
    cred.soft_deleted_at = kwargs.get("soft_deleted_at", None)
    cred.hard_delete_after = kwargs.get("hard_delete_after", None)
    cred.encrypted_payload = kwargs.get("encrypted_payload", "encrypted-data")
    cred.credential_metadata = kwargs.get("credential_metadata", {})
    return cred


# =============================================================================
# DisconnectService Init
# =============================================================================


class TestDisconnectServiceInit:
    """DisconnectService initialization tests."""

    def test_requires_tenant_id(self):
        """Must raise ValueError without tenant_id."""
        with pytest.raises(ValueError, match="tenant_id is required"):
            DisconnectService(db_session=MagicMock(), tenant_id="")

    def test_accepts_valid_args(self):
        """Must accept valid db_session and tenant_id."""
        session = MagicMock()
        service = DisconnectService(db_session=session, tenant_id=TENANT_ID)
        assert service.tenant_id == TENANT_ID
        assert service.db is session


# =============================================================================
# DisconnectReason Enum
# =============================================================================


class TestDisconnectReason:
    """DisconnectReason enum tests."""

    def test_reason_values(self):
        """Must have all expected values."""
        expected = {
            "user_request", "admin_action", "token_revoked",
            "security_event", "app_uninstalled",
        }
        actual = {r.value for r in DisconnectReason}
        assert actual == expected

    def test_is_string_enum(self):
        """Must be a string enum."""
        for reason in DisconnectReason:
            assert isinstance(reason.value, str)
            assert isinstance(reason, str)


# =============================================================================
# DisconnectResult
# =============================================================================


class TestDisconnectResult:
    """DisconnectResult data class tests."""

    def test_success_when_no_errors(self):
        """success must be True when no errors."""
        result = DisconnectResult(
            source_type="shopify",
            connection_id=CONNECTION_ID,
            reason="user_request",
        )
        assert result.success is True

    def test_failure_when_errors(self):
        """success must be False when errors present."""
        result = DisconnectResult(
            source_type="shopify",
            connection_id=CONNECTION_ID,
            reason="user_request",
            errors=["something failed"],
        )
        assert result.success is False

    def test_to_dict_format(self):
        """to_dict must return expected keys."""
        result = DisconnectResult(
            source_type="meta",
            connection_id="conn-1",
            reason="admin_action",
            jobs_cancelled=3,
            credentials_revoked=2,
            credentials_soft_deleted=2,
            connection_disabled=True,
        )
        d = result.to_dict()
        assert d["source_type"] == "meta"
        assert d["connection_id"] == "conn-1"
        assert d["jobs_cancelled"] == 3
        assert d["credentials_revoked"] == 2
        assert d["credentials_soft_deleted"] == 2
        assert d["connection_disabled"] is True
        assert d["success"] is True
        assert d["error_count"] == 0


# =============================================================================
# Step 1: Cancel Active Jobs
# =============================================================================


class TestCancelActiveJobs:
    """Tests for job cancellation during disconnect."""

    @pytest.mark.asyncio
    @patch("src.platform.audit.log_system_audit_event_sync")
    @patch("src.services.token_manager.TokenManager")
    async def test_queued_jobs_cancelled(self, MockTM, mock_audit):
        """Queued jobs must be set to FAILED with disconnect error."""
        from src.ingestion.jobs.models import JobStatus

        job = _make_job("job-q1", JobStatus.QUEUED)
        session = _mock_session()

        # Mock execute to return active jobs for step 1, empty for steps 2-3
        call_count = [0]

        def mock_execute(stmt):
            result = MagicMock()
            nonlocal call_count
            if call_count[0] == 0:
                # Step 1: active jobs query
                result.scalars.return_value.all.return_value = [job]
            else:
                # Steps 2-3: credentials queries
                result.scalars.return_value.all.return_value = []
                result.scalar_one_or_none.return_value = None
            call_count[0] += 1
            return result

        session.execute.side_effect = mock_execute

        mock_tm_instance = MagicMock()
        mock_tm_instance.revoke_all_for_connection = AsyncMock(return_value=0)
        MockTM.return_value = mock_tm_instance

        service = DisconnectService(db_session=session, tenant_id=TENANT_ID)
        result = await service.disconnect_source(
            source_type="shopify",
            disconnected_by=USER_ID,
            reason=DisconnectReason.USER_REQUEST,
            connection_id=CONNECTION_ID,
        )

        assert result.jobs_cancelled >= 1
        assert job.status == JobStatus.FAILED
        assert "disconnected" in job.error_message
        assert job.error_code == "source_disconnected"
        assert job.next_retry_at is None

    @pytest.mark.asyncio
    @patch("src.platform.audit.log_system_audit_event_sync")
    @patch("src.services.token_manager.TokenManager")
    async def test_running_jobs_aborted(self, MockTM, mock_audit):
        """Running jobs must be marked with disconnect error."""
        from src.ingestion.jobs.models import JobStatus

        job = _make_job("job-r1", JobStatus.RUNNING)
        session = _mock_session()

        call_count = [0]

        def mock_execute(stmt):
            result = MagicMock()
            nonlocal call_count
            if call_count[0] == 0:
                result.scalars.return_value.all.return_value = [job]
            else:
                result.scalars.return_value.all.return_value = []
                result.scalar_one_or_none.return_value = None
            call_count[0] += 1
            return result

        session.execute.side_effect = mock_execute

        mock_tm_instance = MagicMock()
        mock_tm_instance.revoke_all_for_connection = AsyncMock(return_value=0)
        MockTM.return_value = mock_tm_instance

        service = DisconnectService(db_session=session, tenant_id=TENANT_ID)
        result = await service.disconnect_source(
            source_type="shopify",
            disconnected_by=USER_ID,
            reason=DisconnectReason.USER_REQUEST,
        )

        assert result.jobs_cancelled >= 1
        assert "disconnected" in job.error_message.lower()
        assert job.next_retry_at is None

    @pytest.mark.asyncio
    @patch("src.platform.audit.log_system_audit_event_sync")
    @patch("src.services.token_manager.TokenManager")
    async def test_failed_jobs_retry_cleared(self, MockTM, mock_audit):
        """Failed jobs awaiting retry must have retry schedule cleared."""
        from src.ingestion.jobs.models import JobStatus

        retry_time = datetime.now(timezone.utc) + timedelta(minutes=30)
        job = _make_job(
            "job-f1",
            JobStatus.FAILED,
            error_message="Server error",
            next_retry_at=retry_time,
        )
        session = _mock_session()

        call_count = [0]

        def mock_execute(stmt):
            result = MagicMock()
            nonlocal call_count
            if call_count[0] == 0:
                result.scalars.return_value.all.return_value = [job]
            else:
                result.scalars.return_value.all.return_value = []
                result.scalar_one_or_none.return_value = None
            call_count[0] += 1
            return result

        session.execute.side_effect = mock_execute

        mock_tm_instance = MagicMock()
        mock_tm_instance.revoke_all_for_connection = AsyncMock(return_value=0)
        MockTM.return_value = mock_tm_instance

        service = DisconnectService(db_session=session, tenant_id=TENANT_ID)
        result = await service.disconnect_source(
            source_type="shopify",
            disconnected_by=USER_ID,
            reason=DisconnectReason.USER_REQUEST,
        )

        assert result.jobs_cancelled >= 1
        assert job.next_retry_at is None
        assert "retry cancelled" in job.error_message

    @pytest.mark.asyncio
    @patch("src.platform.audit.log_system_audit_event_sync")
    @patch("src.services.token_manager.TokenManager")
    async def test_no_active_jobs(self, MockTM, mock_audit):
        """No active jobs → jobs_cancelled must be 0."""
        session = _mock_session()

        def mock_execute(stmt):
            result = MagicMock()
            result.scalars.return_value.all.return_value = []
            result.scalar_one_or_none.return_value = None
            return result

        session.execute.side_effect = mock_execute

        mock_tm_instance = MagicMock()
        mock_tm_instance.revoke_all_for_connection = AsyncMock(return_value=0)
        MockTM.return_value = mock_tm_instance

        service = DisconnectService(db_session=session, tenant_id=TENANT_ID)
        result = await service.disconnect_source(
            source_type="shopify",
            disconnected_by=USER_ID,
            reason=DisconnectReason.USER_REQUEST,
        )

        assert result.jobs_cancelled == 0

    @pytest.mark.asyncio
    @patch("src.platform.audit.log_system_audit_event_sync")
    @patch("src.services.token_manager.TokenManager")
    async def test_job_cancellation_error_does_not_crash(self, MockTM, mock_audit):
        """Job cancellation failure must not crash disconnect flow."""
        session = _mock_session()
        session.execute.side_effect = RuntimeError("DB connection lost")

        mock_tm_instance = MagicMock()
        mock_tm_instance.revoke_all_for_connection = AsyncMock(return_value=0)
        MockTM.return_value = mock_tm_instance

        service = DisconnectService(db_session=session, tenant_id=TENANT_ID)

        # Reset execute after first call fails for job cancellation
        original_side_effect = session.execute.side_effect

        call_count = [0]

        def failing_then_empty(stmt):
            nonlocal call_count
            if call_count[0] == 0:
                call_count[0] += 1
                raise RuntimeError("DB connection lost")
            result = MagicMock()
            result.scalars.return_value.all.return_value = []
            result.scalar_one_or_none.return_value = None
            call_count[0] += 1
            return result

        session.execute.side_effect = failing_then_empty

        result = await service.disconnect_source(
            source_type="shopify",
            disconnected_by=USER_ID,
            reason=DisconnectReason.USER_REQUEST,
        )

        assert result.jobs_cancelled == 0
        assert len(result.errors) >= 1
        assert "cancel" in result.errors[0].lower() or "Failed" in result.errors[0]


# =============================================================================
# Step 2: Revoke Credentials
# =============================================================================


class TestRevokeCredentials:
    """Tests for credential revocation during disconnect."""

    @pytest.mark.asyncio
    @patch("src.platform.audit.log_system_audit_event_sync")
    @patch("src.services.token_manager.TokenManager")
    async def test_credentials_revoked_via_token_manager(self, MockTM, mock_audit):
        """Must call TokenManager.revoke_all_for_connection."""
        session = _mock_session()

        def mock_execute(stmt):
            result = MagicMock()
            result.scalars.return_value.all.return_value = []
            result.scalar_one_or_none.return_value = None
            return result

        session.execute.side_effect = mock_execute

        mock_tm_instance = MagicMock()
        mock_tm_instance.revoke_all_for_connection = AsyncMock(return_value=3)
        MockTM.return_value = mock_tm_instance

        service = DisconnectService(db_session=session, tenant_id=TENANT_ID)
        result = await service.disconnect_source(
            source_type="meta",
            disconnected_by=USER_ID,
            reason=DisconnectReason.USER_REQUEST,
        )

        assert result.credentials_revoked == 3
        mock_tm_instance.revoke_all_for_connection.assert_called_once()
        call_kwargs = mock_tm_instance.revoke_all_for_connection.call_args
        assert call_kwargs.kwargs.get("source_type") == "meta"

    @pytest.mark.asyncio
    @patch("src.platform.audit.log_system_audit_event_sync")
    @patch("src.services.token_manager.TokenManager")
    async def test_reason_mapping_user_request(self, MockTM, mock_audit):
        """USER_REQUEST must map to RevocationReason.USER_DISCONNECT."""
        from src.services.token_manager import RevocationReason

        session = _mock_session()

        def mock_execute(stmt):
            result = MagicMock()
            result.scalars.return_value.all.return_value = []
            result.scalar_one_or_none.return_value = None
            return result

        session.execute.side_effect = mock_execute

        mock_tm_instance = MagicMock()
        mock_tm_instance.revoke_all_for_connection = AsyncMock(return_value=0)
        MockTM.return_value = mock_tm_instance

        service = DisconnectService(db_session=session, tenant_id=TENANT_ID)
        await service.disconnect_source(
            source_type="shopify",
            disconnected_by=USER_ID,
            reason=DisconnectReason.USER_REQUEST,
        )

        call_kwargs = mock_tm_instance.revoke_all_for_connection.call_args.kwargs
        assert call_kwargs["reason"] == RevocationReason.USER_DISCONNECT

    @pytest.mark.asyncio
    @patch("src.platform.audit.log_system_audit_event_sync")
    @patch("src.services.token_manager.TokenManager")
    async def test_reason_mapping_security_event(self, MockTM, mock_audit):
        """SECURITY_EVENT must map to RevocationReason.SECURITY_EVENT."""
        from src.services.token_manager import RevocationReason

        session = _mock_session()

        def mock_execute(stmt):
            result = MagicMock()
            result.scalars.return_value.all.return_value = []
            result.scalar_one_or_none.return_value = None
            return result

        session.execute.side_effect = mock_execute

        mock_tm_instance = MagicMock()
        mock_tm_instance.revoke_all_for_connection = AsyncMock(return_value=0)
        MockTM.return_value = mock_tm_instance

        service = DisconnectService(db_session=session, tenant_id=TENANT_ID)
        await service.disconnect_source(
            source_type="shopify",
            disconnected_by=USER_ID,
            reason=DisconnectReason.SECURITY_EVENT,
        )

        call_kwargs = mock_tm_instance.revoke_all_for_connection.call_args.kwargs
        assert call_kwargs["reason"] == RevocationReason.SECURITY_EVENT

    @pytest.mark.asyncio
    @patch("src.platform.audit.log_system_audit_event_sync")
    @patch("src.services.token_manager.TokenManager")
    async def test_revocation_error_does_not_crash(self, MockTM, mock_audit):
        """Credential revocation failure must not crash disconnect flow."""
        session = _mock_session()

        def mock_execute(stmt):
            result = MagicMock()
            result.scalars.return_value.all.return_value = []
            result.scalar_one_or_none.return_value = None
            return result

        session.execute.side_effect = mock_execute

        mock_tm_instance = MagicMock()
        mock_tm_instance.revoke_all_for_connection = AsyncMock(
            side_effect=RuntimeError("Token manager crashed")
        )
        MockTM.return_value = mock_tm_instance

        service = DisconnectService(db_session=session, tenant_id=TENANT_ID)
        result = await service.disconnect_source(
            source_type="shopify",
            disconnected_by=USER_ID,
            reason=DisconnectReason.USER_REQUEST,
        )

        assert result.credentials_revoked == 0
        assert any("revoke" in e.lower() for e in result.errors)


# =============================================================================
# Step 3: Soft-Delete Credentials
# =============================================================================


class TestSoftDeleteCredentials:
    """Tests for credential soft-deletion during disconnect."""

    @pytest.mark.asyncio
    @patch("src.platform.audit.log_system_audit_event_sync")
    @patch("src.services.token_manager.TokenManager")
    @patch("src.services.credential_vault.CredentialVault.soft_delete")
    async def test_soft_delete_called_for_each_credential(
        self, mock_soft_delete, MockTM, mock_audit
    ):
        """Must call soft_delete for each non-deleted credential."""
        cred1 = _make_credential("cred-1")
        cred2 = _make_credential("cred-2")
        session = _mock_session()

        call_count = [0]

        def mock_execute(stmt):
            result = MagicMock()
            nonlocal call_count
            if call_count[0] == 0:
                # Jobs query
                result.scalars.return_value.all.return_value = []
            elif call_count[0] == 1:
                # Credentials for soft-delete
                result.scalars.return_value.all.return_value = [cred1, cred2]
            else:
                result.scalars.return_value.all.return_value = []
                result.scalar_one_or_none.return_value = None
            call_count[0] += 1
            return result

        session.execute.side_effect = mock_execute

        mock_tm_instance = MagicMock()
        mock_tm_instance.revoke_all_for_connection = AsyncMock(return_value=2)
        MockTM.return_value = mock_tm_instance

        service = DisconnectService(db_session=session, tenant_id=TENANT_ID)
        result = await service.disconnect_source(
            source_type="shopify",
            disconnected_by=USER_ID,
            reason=DisconnectReason.USER_REQUEST,
        )

        assert result.credentials_soft_deleted == 2
        assert mock_soft_delete.call_count == 2

    @pytest.mark.asyncio
    @patch("src.platform.audit.log_system_audit_event_sync")
    @patch("src.services.token_manager.TokenManager")
    async def test_soft_delete_error_does_not_crash(self, MockTM, mock_audit):
        """Soft-delete failure must not crash disconnect flow."""
        session = _mock_session()

        call_count = [0]

        def mock_execute(stmt):
            result = MagicMock()
            nonlocal call_count
            if call_count[0] == 0:
                result.scalars.return_value.all.return_value = []
            elif call_count[0] == 1:
                # Make the soft-delete credentials query fail
                raise RuntimeError("DB error")
            else:
                result.scalars.return_value.all.return_value = []
                result.scalar_one_or_none.return_value = None
            call_count[0] += 1
            return result

        session.execute.side_effect = mock_execute

        mock_tm_instance = MagicMock()
        mock_tm_instance.revoke_all_for_connection = AsyncMock(return_value=0)
        MockTM.return_value = mock_tm_instance

        service = DisconnectService(db_session=session, tenant_id=TENANT_ID)
        result = await service.disconnect_source(
            source_type="shopify",
            disconnected_by=USER_ID,
            reason=DisconnectReason.USER_REQUEST,
        )

        assert result.credentials_soft_deleted == 0
        assert any("soft-delete" in e.lower() for e in result.errors)


# =============================================================================
# Step 4: Disable Connection
# =============================================================================


class TestDisableConnection:
    """Tests for connection disabling during disconnect."""

    @pytest.mark.asyncio
    @patch("src.platform.audit.log_system_audit_event_sync")
    @patch("src.services.token_manager.TokenManager")
    async def test_connection_disabled(self, MockTM, mock_audit):
        """Connection must be set to DELETED and disabled."""
        from src.models.airbyte_connection import ConnectionStatus

        conn = MagicMock()
        conn.status = ConnectionStatus.ACTIVE
        conn.is_enabled = True

        session = _mock_session()
        call_count = [0]

        def mock_execute(stmt):
            result = MagicMock()
            nonlocal call_count
            if call_count[0] <= 1:
                # Jobs + credentials queries
                result.scalars.return_value.all.return_value = []
            elif call_count[0] == 2:
                # Connection query
                result.scalar_one_or_none.return_value = conn
            else:
                result.scalars.return_value.all.return_value = []
                result.scalar_one_or_none.return_value = None
            call_count[0] += 1
            return result

        session.execute.side_effect = mock_execute

        mock_tm_instance = MagicMock()
        mock_tm_instance.revoke_all_for_connection = AsyncMock(return_value=0)
        MockTM.return_value = mock_tm_instance

        service = DisconnectService(db_session=session, tenant_id=TENANT_ID)
        result = await service.disconnect_source(
            source_type="shopify",
            disconnected_by=USER_ID,
            reason=DisconnectReason.USER_REQUEST,
            connection_id=CONNECTION_ID,
        )

        assert result.connection_disabled is True
        assert conn.status == ConnectionStatus.DELETED
        assert conn.is_enabled is False

    @pytest.mark.asyncio
    @patch("src.platform.audit.log_system_audit_event_sync")
    @patch("src.services.token_manager.TokenManager")
    async def test_no_connection_id_skips_disable(self, MockTM, mock_audit):
        """Without connection_id, disable step must be skipped."""
        session = _mock_session()

        def mock_execute(stmt):
            result = MagicMock()
            result.scalars.return_value.all.return_value = []
            result.scalar_one_or_none.return_value = None
            return result

        session.execute.side_effect = mock_execute

        mock_tm_instance = MagicMock()
        mock_tm_instance.revoke_all_for_connection = AsyncMock(return_value=0)
        MockTM.return_value = mock_tm_instance

        service = DisconnectService(db_session=session, tenant_id=TENANT_ID)
        result = await service.disconnect_source(
            source_type="shopify",
            disconnected_by=USER_ID,
            reason=DisconnectReason.USER_REQUEST,
            # No connection_id
        )

        assert result.connection_disabled is False

    @pytest.mark.asyncio
    @patch("src.platform.audit.log_system_audit_event_sync")
    @patch("src.services.token_manager.TokenManager")
    async def test_connection_not_found(self, MockTM, mock_audit):
        """Missing connection must not crash."""
        session = _mock_session()

        def mock_execute(stmt):
            result = MagicMock()
            result.scalars.return_value.all.return_value = []
            result.scalar_one_or_none.return_value = None
            return result

        session.execute.side_effect = mock_execute

        mock_tm_instance = MagicMock()
        mock_tm_instance.revoke_all_for_connection = AsyncMock(return_value=0)
        MockTM.return_value = mock_tm_instance

        service = DisconnectService(db_session=session, tenant_id=TENANT_ID)
        result = await service.disconnect_source(
            source_type="shopify",
            disconnected_by=USER_ID,
            reason=DisconnectReason.USER_REQUEST,
            connection_id="nonexistent",
        )

        assert result.connection_disabled is False
        # No error, just a warning
        assert result.success is True


# =============================================================================
# Step 5: Audit Trail
# =============================================================================


class TestDisconnectAudit:
    """Tests for audit trail during disconnect."""

    @pytest.mark.asyncio
    @patch("src.platform.audit.log_system_audit_event_sync")
    @patch("src.services.token_manager.TokenManager")
    async def test_disconnect_logs_audit_event(self, MockTM, mock_audit):
        """Disconnect must log an audit event."""
        mock_audit.return_value = "corr-123"
        session = _mock_session()

        def mock_execute(stmt):
            result = MagicMock()
            result.scalars.return_value.all.return_value = []
            result.scalar_one_or_none.return_value = None
            return result

        session.execute.side_effect = mock_execute

        mock_tm_instance = MagicMock()
        mock_tm_instance.revoke_all_for_connection = AsyncMock(return_value=0)
        MockTM.return_value = mock_tm_instance

        service = DisconnectService(db_session=session, tenant_id=TENANT_ID)
        result = await service.disconnect_source(
            source_type="shopify",
            disconnected_by=USER_ID,
            reason=DisconnectReason.USER_REQUEST,
            connection_id=CONNECTION_ID,
        )

        assert result.audit_correlation_id == "corr-123"
        mock_audit.assert_called_once()

        call_kwargs = mock_audit.call_args.kwargs
        assert call_kwargs["tenant_id"] == TENANT_ID
        assert call_kwargs["resource_type"] == "connection"
        assert call_kwargs["resource_id"] == CONNECTION_ID
        assert call_kwargs["metadata"]["source_type"] == "shopify"
        assert call_kwargs["metadata"]["reason"] == "user_request"
        assert call_kwargs["metadata"]["disconnected_by"] == USER_ID

    @pytest.mark.asyncio
    @patch("src.platform.audit.log_system_audit_event_sync")
    @patch("src.services.token_manager.TokenManager")
    async def test_audit_uses_store_disconnected_action(self, MockTM, mock_audit):
        """Must use AuditAction.STORE_DISCONNECTED."""
        from src.platform.audit import AuditAction

        session = _mock_session()

        def mock_execute(stmt):
            result = MagicMock()
            result.scalars.return_value.all.return_value = []
            result.scalar_one_or_none.return_value = None
            return result

        session.execute.side_effect = mock_execute

        mock_tm_instance = MagicMock()
        mock_tm_instance.revoke_all_for_connection = AsyncMock(return_value=0)
        MockTM.return_value = mock_tm_instance

        service = DisconnectService(db_session=session, tenant_id=TENANT_ID)
        await service.disconnect_source(
            source_type="shopify",
            disconnected_by=USER_ID,
            reason=DisconnectReason.USER_REQUEST,
        )

        call_kwargs = mock_audit.call_args.kwargs
        assert call_kwargs["action"] == AuditAction.STORE_DISCONNECTED

    @pytest.mark.asyncio
    @patch("src.platform.audit.log_system_audit_event_sync")
    @patch("src.services.token_manager.TokenManager")
    async def test_audit_failure_does_not_crash_disconnect(self, MockTM, mock_audit):
        """Audit logging failure must not crash disconnect."""
        mock_audit.side_effect = RuntimeError("Audit DB down")

        session = _mock_session()

        def mock_execute(stmt):
            result = MagicMock()
            result.scalars.return_value.all.return_value = []
            result.scalar_one_or_none.return_value = None
            return result

        session.execute.side_effect = mock_execute

        mock_tm_instance = MagicMock()
        mock_tm_instance.revoke_all_for_connection = AsyncMock(return_value=0)
        MockTM.return_value = mock_tm_instance

        service = DisconnectService(db_session=session, tenant_id=TENANT_ID)
        result = await service.disconnect_source(
            source_type="shopify",
            disconnected_by=USER_ID,
            reason=DisconnectReason.USER_REQUEST,
        )

        assert result.audit_correlation_id is None
        assert any("audit" in e.lower() for e in result.errors)


# =============================================================================
# Full Disconnect Flow (Integration-style)
# =============================================================================


class TestFullDisconnectFlow:
    """End-to-end disconnect flow tests."""

    @pytest.mark.asyncio
    @patch("src.platform.audit.log_system_audit_event_sync")
    @patch("src.services.token_manager.TokenManager")
    @patch("src.services.credential_vault.CredentialVault.soft_delete")
    async def test_full_disconnect_all_steps(
        self, mock_soft_delete, MockTM, mock_audit
    ):
        """Full disconnect must execute all 5 steps."""
        from src.ingestion.jobs.models import JobStatus
        from src.models.airbyte_connection import ConnectionStatus

        job = _make_job("job-full", JobStatus.QUEUED)
        cred = _make_credential("cred-full")
        conn = MagicMock()
        conn.status = ConnectionStatus.ACTIVE
        conn.is_enabled = True

        mock_audit.return_value = "corr-full"

        session = _mock_session()
        call_count = [0]

        def mock_execute(stmt):
            result = MagicMock()
            nonlocal call_count
            if call_count[0] == 0:
                result.scalars.return_value.all.return_value = [job]
            elif call_count[0] == 1:
                result.scalars.return_value.all.return_value = [cred]
            elif call_count[0] == 2:
                result.scalar_one_or_none.return_value = conn
            else:
                result.scalars.return_value.all.return_value = []
                result.scalar_one_or_none.return_value = None
            call_count[0] += 1
            return result

        session.execute.side_effect = mock_execute

        mock_tm_instance = MagicMock()
        mock_tm_instance.revoke_all_for_connection = AsyncMock(return_value=1)
        MockTM.return_value = mock_tm_instance

        service = DisconnectService(db_session=session, tenant_id=TENANT_ID)
        result = await service.disconnect_source(
            source_type="shopify",
            disconnected_by=USER_ID,
            reason=DisconnectReason.USER_REQUEST,
            connection_id=CONNECTION_ID,
        )

        # All steps completed
        assert result.jobs_cancelled == 1
        assert result.credentials_revoked == 1
        assert result.credentials_soft_deleted == 1
        assert result.connection_disabled is True
        assert result.audit_correlation_id == "corr-full"
        assert result.success is True

        # Verify job was cancelled
        assert job.status == JobStatus.FAILED
        # Verify connection was disabled
        assert conn.status == ConnectionStatus.DELETED
        assert conn.is_enabled is False


# =============================================================================
# Credential Cleanup Job
# =============================================================================


class TestCredentialCleanupJob:
    """Tests for the credential cleanup worker."""

    def test_cleanup_stats_to_dict(self):
        """CleanupStats must have all expected keys."""
        from src.workers.credential_cleanup_job import CleanupStats

        stats = CleanupStats(
            credentials_eligible=10,
            credentials_purged=8,
            dry_run=False,
            completed_at=datetime.now(timezone.utc),
        )
        d = stats.to_dict()
        assert d["credentials_eligible"] == 10
        assert d["credentials_purged"] == 8
        assert d["dry_run"] is False
        assert "started_at" in d
        assert "completed_at" in d
        assert "duration_seconds" in d
        assert d["error_count"] == 0

    @patch("src.workers.credential_cleanup_job._log_cleanup_audit")
    def test_dry_run_does_not_purge(self, mock_audit):
        """Dry run must count but not delete."""
        from src.workers.credential_cleanup_job import (
            run_cleanup,
            count_eligible_credentials,
        )

        session = MagicMock()

        with patch(
            "src.workers.credential_cleanup_job.count_eligible_credentials",
            return_value=5,
        ):
            stats = run_cleanup(session, dry_run=True)

        assert stats.credentials_eligible == 5
        assert stats.credentials_purged == 0
        assert stats.dry_run is True

    @patch("src.workers.credential_cleanup_job._log_cleanup_audit")
    @patch("src.services.credential_vault.CredentialVault.purge_expired")
    def test_real_run_calls_purge(self, mock_purge, mock_audit):
        """Non-dry-run must call CredentialVault.purge_expired."""
        from src.workers.credential_cleanup_job import run_cleanup

        mock_purge.return_value = 3

        session = MagicMock()

        with patch(
            "src.workers.credential_cleanup_job.count_eligible_credentials",
            return_value=5,
        ):
            stats = run_cleanup(session, dry_run=False)

        assert stats.credentials_eligible == 5
        assert stats.credentials_purged == 3
        mock_purge.assert_called_once_with(session)

    @patch("src.workers.credential_cleanup_job._log_cleanup_audit")
    def test_no_eligible_credentials(self, mock_audit):
        """No eligible credentials → 0 purged, quick exit."""
        from src.workers.credential_cleanup_job import run_cleanup

        session = MagicMock()

        with patch(
            "src.workers.credential_cleanup_job.count_eligible_credentials",
            return_value=0,
        ):
            stats = run_cleanup(session, dry_run=False)

        assert stats.credentials_eligible == 0
        assert stats.credentials_purged == 0

    @patch("src.workers.credential_cleanup_job._log_cleanup_audit")
    @patch("src.services.credential_vault.CredentialVault.purge_expired")
    def test_purge_failure_is_raised(self, mock_purge, mock_audit):
        """Purge failure must be raised for Render to detect."""
        from src.workers.credential_cleanup_job import run_cleanup

        mock_purge.side_effect = RuntimeError("DB error during purge")

        session = MagicMock()

        with (
            patch(
                "src.workers.credential_cleanup_job.count_eligible_credentials",
                return_value=3,
            ),
            pytest.raises(RuntimeError, match="DB error during purge"),
        ):
            run_cleanup(session, dry_run=False)

    @patch("src.workers.credential_cleanup_job._log_cleanup_audit")
    @patch("src.services.credential_vault.CredentialVault.purge_expired")
    def test_audit_logged_on_success(self, mock_purge, mock_audit):
        """Cleanup must log audit for started and completed phases."""
        from src.workers.credential_cleanup_job import run_cleanup

        mock_purge.return_value = 2
        session = MagicMock()

        with patch(
            "src.workers.credential_cleanup_job.count_eligible_credentials",
            return_value=2,
        ):
            run_cleanup(session, dry_run=False)

        # Should have at least "started" and "completed" calls
        phases = [c.args[1] for c in mock_audit.call_args_list]
        assert "started" in phases
        assert "completed" in phases

    @patch("src.workers.credential_cleanup_job._log_cleanup_audit")
    @patch("src.services.credential_vault.CredentialVault.purge_expired")
    def test_audit_logged_on_failure(self, mock_purge, mock_audit):
        """Cleanup failure must log 'failed' audit phase."""
        from src.workers.credential_cleanup_job import run_cleanup

        mock_purge.side_effect = RuntimeError("DB error")
        session = MagicMock()

        with (
            patch(
                "src.workers.credential_cleanup_job.count_eligible_credentials",
                return_value=1,
            ),
            pytest.raises(RuntimeError),
        ):
            run_cleanup(session, dry_run=False)

        phases = [c.args[1] for c in mock_audit.call_args_list]
        assert "failed" in phases


# =============================================================================
# Retention Policy Constants
# =============================================================================


class TestRetentionConstants:
    """Retention policy constants must remain stable."""

    def test_soft_delete_window_is_5_days(self):
        """Soft-delete restore window must be 5 days."""
        from src.models.connector_credential import SOFT_DELETE_RESTORE_WINDOW_DAYS

        assert SOFT_DELETE_RESTORE_WINDOW_DAYS == 5

    def test_hard_delete_after_20_days(self):
        """Hard delete must happen after 20 days."""
        from src.models.connector_credential import HARD_DELETE_AFTER_DAYS

        assert HARD_DELETE_AFTER_DAYS == 20

    def test_audit_retention_plan_defaults(self):
        """Audit retention defaults must be plan-based."""
        from src.config.retention import PLAN_RETENTION_DEFAULTS

        assert PLAN_RETENTION_DEFAULTS["free"] == 30
        assert PLAN_RETENTION_DEFAULTS["starter"] == 90
        assert PLAN_RETENTION_DEFAULTS["professional"] == 180
        assert PLAN_RETENTION_DEFAULTS["enterprise"] == 365

    def test_retention_minimum_30_days(self):
        """Minimum retention must be 30 days (SOC2 compliance)."""
        from src.config.retention import MINIMUM_RETENTION_DAYS

        assert MINIMUM_RETENTION_DAYS == 30

    def test_retention_clamping(self):
        """get_retention_days must clamp to min/max."""
        from src.config.retention import (
            get_retention_days,
            MINIMUM_RETENTION_DAYS,
            MAXIMUM_RETENTION_DAYS,
        )

        assert get_retention_days("free") >= MINIMUM_RETENTION_DAYS
        assert get_retention_days("enterprise") <= MAXIMUM_RETENTION_DAYS
        # Unknown plan gets default
        assert get_retention_days("unknown_plan") == 90


# =============================================================================
# Credential Hard Delete Lifecycle
# =============================================================================


class TestHardDeleteLifecycle:
    """CredentialVault.purge_expired must correctly hard-delete."""

    def test_purge_returns_zero_when_nothing_expired(self):
        """purge_expired must return 0 when no credentials are past deadline."""
        from src.services.credential_vault import CredentialVault

        session = MagicMock()
        session.execute.return_value.scalars.return_value.all.return_value = []

        count = CredentialVault.purge_expired(session)
        assert count == 0

    def test_purge_wipes_payload_then_deletes(self):
        """purge_expired must wipe payload to None then delete the row."""
        from src.services.credential_vault import CredentialVault

        cred = _make_credential(
            "cred-expired",
            soft_deleted_at=datetime.now(timezone.utc) - timedelta(days=25),
            hard_delete_after=datetime.now(timezone.utc) - timedelta(days=1),
            encrypted_payload="still-encrypted",
        )

        session = MagicMock()
        session.execute.return_value.scalars.return_value.all.return_value = [cred]

        count = CredentialVault.purge_expired(session)

        assert count == 1
        # Payload must be wiped
        assert cred.encrypted_payload is None
        # Row must be deleted
        session.delete.assert_called_once_with(cred)
        # Flush called before delete, commit after
        session.flush.assert_called()
        session.commit.assert_called()


# =============================================================================
# Edge Cases
# =============================================================================


class TestEdgeCases:
    """Edge case tests for disconnect and retention."""

    @pytest.mark.asyncio
    @patch("src.platform.audit.log_system_audit_event_sync")
    @patch("src.services.token_manager.TokenManager")
    async def test_disconnect_idempotent_no_resources(self, MockTM, mock_audit):
        """Disconnect with no jobs/credentials/connection must succeed."""
        session = _mock_session()

        def mock_execute(stmt):
            result = MagicMock()
            result.scalars.return_value.all.return_value = []
            result.scalar_one_or_none.return_value = None
            return result

        session.execute.side_effect = mock_execute

        mock_tm_instance = MagicMock()
        mock_tm_instance.revoke_all_for_connection = AsyncMock(return_value=0)
        MockTM.return_value = mock_tm_instance

        service = DisconnectService(db_session=session, tenant_id=TENANT_ID)
        result = await service.disconnect_source(
            source_type="shopify",
            disconnected_by=USER_ID,
            reason=DisconnectReason.USER_REQUEST,
        )

        assert result.success is True
        assert result.jobs_cancelled == 0
        assert result.credentials_revoked == 0
        assert result.credentials_soft_deleted == 0
        assert result.connection_disabled is False

    @pytest.mark.asyncio
    @patch("src.platform.audit.log_system_audit_event_sync")
    @patch("src.services.token_manager.TokenManager")
    async def test_disconnect_with_multiple_mixed_jobs(self, MockTM, mock_audit):
        """Must handle mix of queued, running, and failed jobs."""
        from src.ingestion.jobs.models import JobStatus

        job_q = _make_job("job-q", JobStatus.QUEUED)
        job_r = _make_job("job-r", JobStatus.RUNNING)
        job_f = _make_job(
            "job-f",
            JobStatus.FAILED,
            next_retry_at=datetime.now(timezone.utc) + timedelta(hours=1),
            error_message="Previous error",
        )

        session = _mock_session()
        call_count = [0]

        def mock_execute(stmt):
            result = MagicMock()
            nonlocal call_count
            if call_count[0] == 0:
                result.scalars.return_value.all.return_value = [job_q, job_r, job_f]
            else:
                result.scalars.return_value.all.return_value = []
                result.scalar_one_or_none.return_value = None
            call_count[0] += 1
            return result

        session.execute.side_effect = mock_execute

        mock_tm_instance = MagicMock()
        mock_tm_instance.revoke_all_for_connection = AsyncMock(return_value=0)
        MockTM.return_value = mock_tm_instance

        service = DisconnectService(db_session=session, tenant_id=TENANT_ID)
        result = await service.disconnect_source(
            source_type="shopify",
            disconnected_by=USER_ID,
            reason=DisconnectReason.USER_REQUEST,
        )

        assert result.jobs_cancelled == 3
        assert job_q.status == JobStatus.FAILED
        assert job_q.next_retry_at is None
        assert job_r.next_retry_at is None
        assert job_f.next_retry_at is None

    def test_cleanup_stats_error_tracking(self):
        """CleanupStats must correctly track errors."""
        from src.workers.credential_cleanup_job import CleanupStats

        stats = CleanupStats()
        stats.errors.append("Error 1")
        stats.errors.append("Error 2")

        d = stats.to_dict()
        assert d["error_count"] == 2


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
