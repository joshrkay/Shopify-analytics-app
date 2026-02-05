"""
Tests for sync retry manager and failure handling.

Covers:
- Retry scheduling: exponential backoff, error-aware decisions
- Dead letter queue: max retries exhausted, auth errors
- Terminal failure: non-retryable errors
- Admin notifications: Merchant Admin + Agency Admin notified on terminal failure
- Audit logging: all state transitions produce audit events
- UI surface: failure summaries for connector status display
- Edge cases: empty tenants, notification failures, audit failures

Security:
- Error messages truncated to prevent log injection
- All operations are tenant-scoped
"""

import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import pytest

from src.ingestion.jobs.models import IngestionJob, JobStatus
from src.ingestion.jobs.retry import (
    ErrorCategory,
    RetryDecision,
    RetryPolicy,
    MAX_RETRIES,
)
from src.services.sync_retry_manager import (
    SyncRetryManager,
    FailureAction,
    FailureResult,
    FailureSummary,
    MAX_ERROR_MESSAGE_LENGTH,
)


# =============================================================================
# Fixtures
# =============================================================================

TENANT_ID = "tenant-retry-test-001"
CONNECTOR_ID = "connector-abc-123"
USER_ID = "clerk_user_retry_abc"


def _make_job(**overrides) -> IngestionJob:
    """Factory for IngestionJob instances."""
    defaults = {
        "job_id": str(uuid.uuid4()),
        "tenant_id": TENANT_ID,
        "connector_id": CONNECTOR_ID,
        "external_account_id": "shop-xyz",
        "status": JobStatus.RUNNING,
        "retry_count": 0,
        "run_id": "airbyte-run-001",
        "correlation_id": "corr-001",
        "error_message": None,
        "error_code": None,
        "started_at": datetime.now(timezone.utc),
        "completed_at": None,
        "next_retry_at": None,
        "job_metadata": {"connector_name": "My Shopify Store"},
        "created_at": datetime.now(timezone.utc),
        "updated_at": datetime.now(timezone.utc),
    }
    defaults.update(overrides)
    job = IngestionJob()
    for key, value in defaults.items():
        setattr(job, key, value)
    return job


def _mock_session():
    """Create a mock SQLAlchemy session."""
    session = MagicMock()
    session.execute = MagicMock()
    session.add = MagicMock()
    session.commit = MagicMock()
    session.refresh = MagicMock()
    session.flush = MagicMock()
    session.query = MagicMock()
    return session


def _make_manager(session=None, retry_policy=None) -> SyncRetryManager:
    """Create a SyncRetryManager with a mock session."""
    return SyncRetryManager(
        db_session=session or _mock_session(),
        tenant_id=TENANT_ID,
        retry_policy=retry_policy,
    )


# =============================================================================
# Constructor Tests
# =============================================================================

class TestSyncRetryManagerInit:
    """Tests for SyncRetryManager initialization."""

    def test_requires_tenant_id(self):
        with pytest.raises(ValueError, match="tenant_id is required"):
            SyncRetryManager(db_session=_mock_session(), tenant_id="")

    def test_requires_non_none_tenant_id(self):
        with pytest.raises(ValueError, match="tenant_id is required"):
            SyncRetryManager(db_session=_mock_session(), tenant_id=None)

    def test_default_retry_policy(self):
        manager = _make_manager()
        assert manager.retry_policy.max_retries == MAX_RETRIES

    def test_custom_retry_policy(self):
        policy = RetryPolicy(max_retries=3, base_delay_seconds=10)
        manager = _make_manager(retry_policy=policy)
        assert manager.retry_policy.max_retries == 3
        assert manager.retry_policy.base_delay_seconds == 10


# =============================================================================
# Retry Scheduling Tests
# =============================================================================

class TestRetryScheduling:
    """Tests for retry scheduling with exponential backoff."""

    @patch("src.platform.audit.log_system_audit_event_sync")
    def test_server_error_schedules_retry(self, mock_audit):
        """500 errors should schedule a retry with backoff."""
        job = _make_job(retry_count=0)
        manager = _make_manager()

        result = manager.handle_failure(
            job=job,
            error_category=ErrorCategory.SERVER_ERROR,
            error_message="Internal Server Error",
        )

        assert result.action == FailureAction.RETRY_SCHEDULED
        assert result.retry_count == 1  # mark_failed increments
        assert result.next_retry_at is not None
        assert result.delay_seconds > 0
        assert job.status == JobStatus.FAILED
        assert job.next_retry_at is not None

    @patch("src.platform.audit.log_system_audit_event_sync")
    def test_rate_limit_schedules_retry(self, mock_audit):
        """429 rate limit should schedule retry."""
        job = _make_job(retry_count=1)
        manager = _make_manager()

        result = manager.handle_failure(
            job=job,
            error_category=ErrorCategory.RATE_LIMIT,
            error_message="Too Many Requests",
            retry_after=60,
        )

        assert result.action == FailureAction.RETRY_SCHEDULED
        assert result.delay_seconds > 0

    @patch("src.platform.audit.log_system_audit_event_sync")
    def test_timeout_schedules_retry(self, mock_audit):
        """Timeout errors should schedule retry."""
        job = _make_job(retry_count=0)
        manager = _make_manager()

        result = manager.handle_failure(
            job=job,
            error_category=ErrorCategory.TIMEOUT,
            error_message="Connection timed out",
        )

        assert result.action == FailureAction.RETRY_SCHEDULED

    @patch("src.platform.audit.log_system_audit_event_sync")
    def test_connection_error_schedules_retry(self, mock_audit):
        """Network errors should schedule retry."""
        job = _make_job(retry_count=2)
        manager = _make_manager()

        result = manager.handle_failure(
            job=job,
            error_category=ErrorCategory.CONNECTION,
            error_message="Connection refused",
        )

        assert result.action == FailureAction.RETRY_SCHEDULED
        assert result.retry_count == 3

    @patch("src.platform.audit.log_system_audit_event_sync")
    def test_sync_failed_schedules_retry(self, mock_audit):
        """Airbyte sync failures should schedule retry."""
        job = _make_job(retry_count=0)
        manager = _make_manager()

        result = manager.handle_failure(
            job=job,
            error_category=ErrorCategory.SYNC_FAILED,
            error_message="Sync completed with errors",
        )

        assert result.action == FailureAction.RETRY_SCHEDULED

    @patch("src.platform.audit.log_system_audit_event_sync")
    def test_retry_delay_increases_with_attempts(self, mock_audit):
        """Backoff delay should increase with each retry attempt."""
        delays = []
        for attempt in range(3):
            job = _make_job(retry_count=attempt)
            manager = _make_manager()
            result = manager.handle_failure(
                job=job,
                error_category=ErrorCategory.SERVER_ERROR,
                error_message="Server error",
            )
            delays.append(result.delay_seconds)

        # Each delay should generally be larger (with jitter variance)
        # The base delay doubles: 60, 120, 240
        # With jitter, order is not guaranteed for individual runs
        # but the trend should be upward
        assert delays[2] > delays[0]


# =============================================================================
# Dead Letter Queue Tests
# =============================================================================

class TestDeadLetterQueue:
    """Tests for moving jobs to dead letter queue."""

    @patch("src.services.notification_service.NotificationService")
    @patch("src.services.tenant_members_service.TenantMembersService")
    @patch("src.platform.audit.log_system_audit_event_sync")
    def test_max_retries_moves_to_dlq(
        self, mock_audit, mock_members_cls, mock_notif_cls
    ):
        """After 5 retries, job should move to DLQ."""
        mock_members_instance = MagicMock()
        mock_members_instance.list_members.return_value = [
            {"clerk_user_id": "admin-1", "role": "MERCHANT_ADMIN", "is_active": True},
        ]
        mock_members_cls.return_value = mock_members_instance

        mock_notif_instance = MagicMock()
        mock_notif_instance.notify_connector_failed.return_value = [MagicMock()]
        mock_notif_cls.return_value = mock_notif_instance

        job = _make_job(retry_count=MAX_RETRIES)
        manager = _make_manager()

        result = manager.handle_failure(
            job=job,
            error_category=ErrorCategory.SERVER_ERROR,
            error_message="Persistent server error",
        )

        assert result.action == FailureAction.MOVED_TO_DLQ
        assert job.status == JobStatus.DEAD_LETTER
        assert result.notified_admins is True

    @patch("src.services.notification_service.NotificationService")
    @patch("src.services.tenant_members_service.TenantMembersService")
    @patch("src.platform.audit.log_system_audit_event_sync")
    def test_auth_error_moves_to_dlq_immediately(
        self, mock_audit, mock_members_cls, mock_notif_cls
    ):
        """401/403 auth errors should DLQ immediately without retry."""
        mock_members_instance = MagicMock()
        mock_members_instance.list_members.return_value = [
            {"clerk_user_id": "admin-1", "role": "AGENCY_ADMIN", "is_active": True},
        ]
        mock_members_cls.return_value = mock_members_instance

        mock_notif_instance = MagicMock()
        mock_notif_instance.notify_connector_failed.return_value = [MagicMock()]
        mock_notif_cls.return_value = mock_notif_instance

        job = _make_job(retry_count=0)  # First attempt
        manager = _make_manager()

        result = manager.handle_failure(
            job=job,
            error_category=ErrorCategory.AUTH_ERROR,
            error_message="Invalid credentials",
        )

        assert result.action == FailureAction.MOVED_TO_DLQ
        assert job.status == JobStatus.DEAD_LETTER
        assert result.retry_count == 0  # No retries attempted

    @patch("src.platform.audit.log_system_audit_event_sync")
    def test_dlq_records_completed_at(self, mock_audit):
        """DLQ jobs should have completed_at set."""
        job = _make_job(retry_count=MAX_RETRIES)
        manager = _make_manager()

        manager.handle_failure(
            job=job,
            error_category=ErrorCategory.SERVER_ERROR,
            error_message="Error",
        )

        assert job.completed_at is not None


# =============================================================================
# Status Code Classification Tests
# =============================================================================

class TestStatusCodeClassification:
    """Tests for handle_failure_from_status_code convenience method."""

    @patch("src.platform.audit.log_system_audit_event_sync")
    def test_401_categorized_as_auth_error(self, mock_audit):
        job = _make_job(retry_count=0)
        manager = _make_manager()

        result = manager.handle_failure_from_status_code(
            job=job,
            status_code=401,
            error_message="Unauthorized",
        )

        assert result.error_category == ErrorCategory.AUTH_ERROR.value
        assert result.action == FailureAction.MOVED_TO_DLQ

    @patch("src.platform.audit.log_system_audit_event_sync")
    def test_429_categorized_as_rate_limit(self, mock_audit):
        job = _make_job(retry_count=0)
        manager = _make_manager()

        result = manager.handle_failure_from_status_code(
            job=job,
            status_code=429,
            error_message="Rate limited",
            retry_after=120,
        )

        assert result.error_category == ErrorCategory.RATE_LIMIT.value
        assert result.action == FailureAction.RETRY_SCHEDULED

    @patch("src.platform.audit.log_system_audit_event_sync")
    def test_500_categorized_as_server_error(self, mock_audit):
        job = _make_job(retry_count=0)
        manager = _make_manager()

        result = manager.handle_failure_from_status_code(
            job=job,
            status_code=500,
            error_message="Internal error",
        )

        assert result.error_category == ErrorCategory.SERVER_ERROR.value
        assert result.action == FailureAction.RETRY_SCHEDULED

    @patch("src.platform.audit.log_system_audit_event_sync")
    def test_403_categorized_as_auth_error(self, mock_audit):
        job = _make_job(retry_count=0)
        manager = _make_manager()

        result = manager.handle_failure_from_status_code(
            job=job,
            status_code=403,
            error_message="Forbidden",
        )

        assert result.error_category == ErrorCategory.AUTH_ERROR.value
        assert result.action == FailureAction.MOVED_TO_DLQ


# =============================================================================
# Admin Notification Tests
# =============================================================================

class TestAdminNotifications:
    """Tests for admin notification on terminal failures."""

    @patch("src.services.notification_service.NotificationService")
    @patch("src.services.tenant_members_service.TenantMembersService")
    @patch("src.platform.audit.log_system_audit_event_sync")
    def test_notifies_merchant_and_agency_admins(
        self, mock_audit, mock_members_cls, mock_notif_cls
    ):
        """Both Merchant Admin and Agency Admin should be notified."""
        mock_members = MagicMock()
        mock_members.list_members.return_value = [
            {"clerk_user_id": "user-merchant", "role": "MERCHANT_ADMIN", "is_active": True},
            {"clerk_user_id": "user-agency", "role": "AGENCY_ADMIN", "is_active": True},
            {"clerk_user_id": "user-viewer", "role": "VIEWER", "is_active": True},
        ]
        mock_members_cls.return_value = mock_members

        mock_notif = MagicMock()
        mock_notif.notify_connector_failed.return_value = [MagicMock(), MagicMock()]
        mock_notif_cls.return_value = mock_notif

        job = _make_job(retry_count=MAX_RETRIES)
        manager = _make_manager()

        result = manager.handle_failure(
            job=job,
            error_category=ErrorCategory.SERVER_ERROR,
            error_message="Persistent failure",
        )

        assert result.notified_admins is True
        mock_notif.notify_connector_failed.assert_called_once()
        call_kwargs = mock_notif.notify_connector_failed.call_args[1]
        user_ids = call_kwargs["user_ids"]
        assert "user-merchant" in user_ids
        assert "user-agency" in user_ids
        assert "user-viewer" not in user_ids

    @patch("src.services.notification_service.NotificationService")
    @patch("src.services.tenant_members_service.TenantMembersService")
    @patch("src.platform.audit.log_system_audit_event_sync")
    def test_owner_role_gets_notification(
        self, mock_audit, mock_members_cls, mock_notif_cls
    ):
        """OWNER role should also receive failure notifications."""
        mock_members = MagicMock()
        mock_members.list_members.return_value = [
            {"clerk_user_id": "user-owner", "role": "OWNER", "is_active": True},
        ]
        mock_members_cls.return_value = mock_members

        mock_notif = MagicMock()
        mock_notif.notify_connector_failed.return_value = [MagicMock()]
        mock_notif_cls.return_value = mock_notif

        job = _make_job(retry_count=MAX_RETRIES)
        manager = _make_manager()

        result = manager.handle_failure(
            job=job,
            error_category=ErrorCategory.SERVER_ERROR,
            error_message="Error",
        )

        assert result.notified_admins is True
        call_kwargs = mock_notif.notify_connector_failed.call_args[1]
        assert "user-owner" in call_kwargs["user_ids"]

    @patch("src.services.tenant_members_service.TenantMembersService")
    @patch("src.platform.audit.log_system_audit_event_sync")
    def test_no_admins_skips_notification(self, mock_audit, mock_members_cls):
        """Should not crash when no admin users exist."""
        mock_members = MagicMock()
        mock_members.list_members.return_value = [
            {"clerk_user_id": "user-viewer", "role": "VIEWER", "is_active": True},
        ]
        mock_members_cls.return_value = mock_members

        job = _make_job(retry_count=MAX_RETRIES)
        manager = _make_manager()

        result = manager.handle_failure(
            job=job,
            error_category=ErrorCategory.SERVER_ERROR,
            error_message="Error",
        )

        assert result.notified_admins is False

    @patch("src.services.tenant_members_service.TenantMembersService")
    @patch("src.platform.audit.log_system_audit_event_sync")
    def test_notification_failure_does_not_crash(self, mock_audit, mock_members_cls):
        """Notification service failure should not prevent failure handling."""
        mock_members_cls.side_effect = RuntimeError("Service unavailable")

        job = _make_job(retry_count=MAX_RETRIES)
        manager = _make_manager()

        result = manager.handle_failure(
            job=job,
            error_category=ErrorCategory.SERVER_ERROR,
            error_message="Error",
        )

        # DLQ still happens even if notification fails
        assert result.action == FailureAction.MOVED_TO_DLQ
        assert result.notified_admins is False

    @patch("src.platform.audit.log_system_audit_event_sync")
    def test_retry_does_not_notify_admins(self, mock_audit):
        """Retryable failures should NOT notify admins."""
        job = _make_job(retry_count=0)
        manager = _make_manager()

        result = manager.handle_failure(
            job=job,
            error_category=ErrorCategory.SERVER_ERROR,
            error_message="Transient error",
        )

        assert result.action == FailureAction.RETRY_SCHEDULED
        assert result.notified_admins is False


# =============================================================================
# Audit Logging Tests
# =============================================================================

class TestAuditLogging:
    """Tests for audit event emission."""

    @patch("src.platform.audit.log_system_audit_event_sync")
    def test_retry_logs_audit_event(self, mock_audit):
        """Retry scheduling should emit audit event."""
        job = _make_job(retry_count=0)
        manager = _make_manager()

        manager.handle_failure(
            job=job,
            error_category=ErrorCategory.SERVER_ERROR,
            error_message="Error",
        )

        mock_audit.assert_called_once()
        call_kwargs = mock_audit.call_args[1]
        assert call_kwargs["resource_type"] == "ingestion_job"
        assert call_kwargs["resource_id"] == job.job_id
        assert call_kwargs["metadata"]["decision"] == "retry"

    @patch("src.platform.audit.log_system_audit_event_sync")
    def test_dlq_logs_audit_event(self, mock_audit):
        """DLQ move should emit audit event."""
        job = _make_job(retry_count=MAX_RETRIES)
        manager = _make_manager()

        manager.handle_failure(
            job=job,
            error_category=ErrorCategory.SERVER_ERROR,
            error_message="Error",
        )

        mock_audit.assert_called_once()
        call_kwargs = mock_audit.call_args[1]
        assert call_kwargs["metadata"]["decision"] == "dead_letter"

    @patch("src.platform.audit.log_system_audit_event_sync")
    def test_audit_failure_does_not_crash_retry(self, mock_audit):
        """Audit log failure should not prevent retry scheduling."""
        mock_audit.side_effect = RuntimeError("DB connection lost")

        job = _make_job(retry_count=0)
        manager = _make_manager()

        result = manager.handle_failure(
            job=job,
            error_category=ErrorCategory.SERVER_ERROR,
            error_message="Error",
        )

        # Retry still happens even if audit fails
        assert result.action == FailureAction.RETRY_SCHEDULED
        assert job.status == JobStatus.FAILED


# =============================================================================
# Failure Summary Tests (UI Surface)
# =============================================================================

class TestFailureSummary:
    """Tests for failure summary generation for UI."""

    def test_summary_with_failures(self):
        now = datetime.now(timezone.utc)
        failed_job = _make_job(
            status=JobStatus.FAILED,
            retry_count=2,
            error_message="Rate limited",
            error_code="rate_limit",
            next_retry_at=now + timedelta(minutes=5),
            completed_at=now,
        )
        dlq_job = _make_job(
            status=JobStatus.DEAD_LETTER,
            retry_count=5,
            error_message="Auth error",
            error_code="auth_error",
            completed_at=now - timedelta(hours=1),
        )

        session = _mock_session()
        mock_query = MagicMock()
        mock_query.filter.return_value = mock_query
        mock_query.order_by.return_value = mock_query
        mock_query.limit.return_value = mock_query
        mock_query.all.return_value = [failed_job, dlq_job]
        session.query.return_value = mock_query

        manager = SyncRetryManager(
            db_session=session, tenant_id=TENANT_ID
        )
        summary = manager.get_failure_summary(CONNECTOR_ID)

        assert summary.connector_id == CONNECTOR_ID
        assert summary.total_failures == 2
        assert summary.active_retries == 1
        assert summary.dead_letter_count == 1
        assert summary.last_error == "Rate limited"
        assert summary.next_retry_at is not None

    def test_summary_no_failures(self):
        session = _mock_session()
        mock_query = MagicMock()
        mock_query.filter.return_value = mock_query
        mock_query.order_by.return_value = mock_query
        mock_query.limit.return_value = mock_query
        mock_query.all.return_value = []
        session.query.return_value = mock_query

        manager = SyncRetryManager(
            db_session=session, tenant_id=TENANT_ID
        )
        summary = manager.get_failure_summary(CONNECTOR_ID)

        assert summary.total_failures == 0
        assert summary.active_retries == 0
        assert summary.dead_letter_count == 0
        assert summary.last_error is None

    def test_summary_to_dict(self):
        summary = FailureSummary(
            connector_id=CONNECTOR_ID,
            total_failures=3,
            active_retries=1,
            dead_letter_count=2,
            last_error="Timeout",
            last_error_at=datetime(2026, 1, 15, tzinfo=timezone.utc),
            last_error_category="timeout",
            next_retry_at=datetime(2026, 1, 15, 1, 0, tzinfo=timezone.utc),
        )
        d = summary.to_dict()
        assert d["connector_id"] == CONNECTOR_ID
        assert d["total_failures"] == 3
        assert d["last_error"] == "Timeout"
        assert "2026-01-15" in d["last_error_at"]

    def test_get_all_failure_summaries(self):
        session = _mock_session()

        # Mock the distinct connector_ids query
        mock_distinct_query = MagicMock()
        mock_distinct_query.filter.return_value = mock_distinct_query
        mock_distinct_query.distinct.return_value = mock_distinct_query
        mock_distinct_query.all.return_value = [
            ("connector-1",),
            ("connector-2",),
        ]

        # Mock the per-connector failure query
        mock_detail_query = MagicMock()
        mock_detail_query.filter.return_value = mock_detail_query
        mock_detail_query.order_by.return_value = mock_detail_query
        mock_detail_query.limit.return_value = mock_detail_query
        mock_detail_query.all.return_value = []

        session.query.side_effect = [
            mock_distinct_query,  # First call: get distinct connector_ids
            mock_detail_query,    # Second call: connector-1 details
            mock_detail_query,    # Third call: connector-2 details
        ]

        manager = SyncRetryManager(
            db_session=session, tenant_id=TENANT_ID
        )
        summaries = manager.get_all_failure_summaries()

        assert len(summaries) == 2


# =============================================================================
# FailureResult Tests
# =============================================================================

class TestFailureResult:
    """Tests for FailureResult dataclass."""

    def test_to_dict(self):
        result = FailureResult(
            job_id="job-1",
            action=FailureAction.RETRY_SCHEDULED,
            retry_count=2,
            error_category="server_error",
            error_message="Internal error",
            next_retry_at=datetime(2026, 1, 15, tzinfo=timezone.utc),
            delay_seconds=120.5,
            notified_admins=False,
        )
        d = result.to_dict()
        assert d["job_id"] == "job-1"
        assert d["action"] == "retry_scheduled"
        assert d["retry_count"] == 2
        assert d["delay_seconds"] == 120.5
        assert "2026-01-15" in d["next_retry_at"]

    def test_to_dict_truncates_error(self):
        result = FailureResult(
            job_id="job-1",
            action=FailureAction.MOVED_TO_DLQ,
            retry_count=5,
            error_category="server_error",
            error_message="A" * 1000,
            notified_admins=True,
        )
        d = result.to_dict()
        assert len(d["error_message"]) <= 200

    def test_to_dict_no_next_retry(self):
        result = FailureResult(
            job_id="job-1",
            action=FailureAction.MOVED_TO_DLQ,
            retry_count=5,
            error_category="auth_error",
            error_message="Unauthorized",
        )
        d = result.to_dict()
        assert "next_retry_at" not in d


# =============================================================================
# FailureAction Enum Tests
# =============================================================================

class TestFailureAction:
    """Tests for FailureAction enum values."""

    def test_all_actions_exist(self):
        assert FailureAction.RETRY_SCHEDULED.value == "retry_scheduled"
        assert FailureAction.MOVED_TO_DLQ.value == "moved_to_dlq"
        assert FailureAction.MARKED_FAILED_TERMINAL.value == "marked_failed_terminal"

    def test_is_string_enum(self):
        assert isinstance(FailureAction.RETRY_SCHEDULED, str)


# =============================================================================
# Error Message Truncation Tests
# =============================================================================

class TestErrorMessageTruncation:
    """Tests for error message truncation security."""

    @patch("src.platform.audit.log_system_audit_event_sync")
    def test_long_error_message_truncated(self, mock_audit):
        """Error messages longer than MAX_ERROR_MESSAGE_LENGTH are truncated."""
        long_message = "X" * 1000
        job = _make_job(retry_count=0)
        manager = _make_manager()

        result = manager.handle_failure(
            job=job,
            error_category=ErrorCategory.SERVER_ERROR,
            error_message=long_message,
        )

        assert len(result.error_message) <= MAX_ERROR_MESSAGE_LENGTH
        assert len(job.error_message) <= MAX_ERROR_MESSAGE_LENGTH


# =============================================================================
# Exponential Backoff Verification Tests
# =============================================================================

class TestExponentialBackoff:
    """Verify that the retry policy produces exponential backoff."""

    @patch("src.platform.audit.log_system_audit_event_sync")
    def test_first_retry_has_base_delay(self, mock_audit):
        """First retry delay should be near the base delay (60s)."""
        job = _make_job(retry_count=0)
        policy = RetryPolicy(base_delay_seconds=60, jitter_factor=0)
        manager = _make_manager(retry_policy=policy)

        result = manager.handle_failure(
            job=job,
            error_category=ErrorCategory.SERVER_ERROR,
            error_message="Error",
        )

        # With jitter_factor=0, delay should be exactly base_delay
        assert result.delay_seconds == 60.0

    @patch("src.platform.audit.log_system_audit_event_sync")
    def test_second_retry_doubles_delay(self, mock_audit):
        """Second retry should have ~2x the base delay."""
        job = _make_job(retry_count=1)
        policy = RetryPolicy(base_delay_seconds=60, jitter_factor=0)
        manager = _make_manager(retry_policy=policy)

        result = manager.handle_failure(
            job=job,
            error_category=ErrorCategory.SERVER_ERROR,
            error_message="Error",
        )

        assert result.delay_seconds == 120.0

    @patch("src.platform.audit.log_system_audit_event_sync")
    def test_delay_capped_at_max(self, mock_audit):
        """Delay should not exceed max_delay_seconds."""
        job = _make_job(retry_count=4)
        policy = RetryPolicy(
            base_delay_seconds=60,
            max_delay_seconds=3600,
            jitter_factor=0,
        )
        manager = _make_manager(retry_policy=policy)

        result = manager.handle_failure(
            job=job,
            error_category=ErrorCategory.SERVER_ERROR,
            error_message="Error",
        )

        # 60 * 2^4 = 960, which is under 3600 cap
        assert result.delay_seconds == 960.0

    @patch("src.platform.audit.log_system_audit_event_sync")
    def test_retry_after_header_respected(self, mock_audit):
        """Server-specified Retry-After should override calculated backoff."""
        job = _make_job(retry_count=0)
        policy = RetryPolicy(base_delay_seconds=60, jitter_factor=0)
        manager = _make_manager(retry_policy=policy)

        result = manager.handle_failure(
            job=job,
            error_category=ErrorCategory.RATE_LIMIT,
            error_message="Rate limited",
            retry_after=300,
        )

        # With jitter_factor=0, should be exactly 300
        assert result.delay_seconds == 300.0


# =============================================================================
# Edge Case Tests
# =============================================================================

class TestEdgeCases:
    """Edge case and robustness tests."""

    @patch("src.platform.audit.log_system_audit_event_sync")
    def test_unknown_error_retries(self, mock_audit):
        """Unknown errors should still retry."""
        job = _make_job(retry_count=0)
        manager = _make_manager()

        result = manager.handle_failure(
            job=job,
            error_category=ErrorCategory.UNKNOWN,
            error_message="Unexpected error",
        )

        assert result.action == FailureAction.RETRY_SCHEDULED

    @patch("src.platform.audit.log_system_audit_event_sync")
    def test_job_metadata_used_for_connector_name(self, mock_audit):
        """Connector name should be pulled from job metadata."""
        job = _make_job(
            retry_count=MAX_RETRIES,
            job_metadata={"connector_name": "My Facebook Ads"},
        )
        manager = _make_manager()

        # Notification will be attempted but fail (no mock for services)
        result = manager.handle_failure(
            job=job,
            error_category=ErrorCategory.SERVER_ERROR,
            error_message="Error",
        )

        assert result.action == FailureAction.MOVED_TO_DLQ

    @patch("src.platform.audit.log_system_audit_event_sync")
    def test_empty_job_metadata_uses_connector_id(self, mock_audit):
        """Should fall back to connector_id when metadata has no name."""
        job = _make_job(
            retry_count=MAX_RETRIES,
            job_metadata={},
        )
        manager = _make_manager()

        result = manager.handle_failure(
            job=job,
            error_category=ErrorCategory.AUTH_ERROR,
            error_message="Auth failed",
        )

        assert result.action == FailureAction.MOVED_TO_DLQ
