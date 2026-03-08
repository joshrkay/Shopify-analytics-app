"""
Comprehensive tests for sync services:
- SyncOrchestrator (sync_orchestrator.py)
- SyncRetryManager (sync_retry_manager.py)
- SyncPlanResolver (sync_plan_resolver.py)

Uses pytest with unittest.mock for all external dependencies.
"""

import pytest
from datetime import datetime, timezone, timedelta
from unittest.mock import MagicMock, AsyncMock, patch, PropertyMock
from dataclasses import dataclass
from typing import Optional

from src.services.sync_orchestrator import (
    SyncOrchestrator,
    SyncResult,
    SyncOrchestratorError,
    ConnectionNotFoundError,
    SyncFailedError,
    DEFAULT_MAX_RETRIES,
    DEFAULT_BASE_DELAY_SECONDS,
    DEFAULT_MAX_DELAY_SECONDS,
)
from src.services.sync_retry_manager import (
    SyncRetryManager,
    FailureAction,
    FailureResult,
    FailureSummary,
    MAX_ERROR_MESSAGE_LENGTH,
)
from src.services.sync_plan_resolver import (
    SyncPlanResolver,
    SYNC_INTERVAL_BY_TIER,
    DEFAULT_SYNC_INTERVAL_MINUTES,
)
from src.integrations.airbyte.exceptions import (
    AirbyteError,
    AirbyteRateLimitError,
    AirbyteSyncError,
)
from src.ingestion.jobs.retry import (
    ErrorCategory,
    RetryDecision,
    RetryPolicy,
)
from src.ingestion.jobs.models import JobStatus


# =============================================================================
# Helpers & Fixtures
# =============================================================================


def _make_mock_connection(
    connection_id="conn-1",
    airbyte_connection_id="abc-123",
    status="active",
    is_enabled=True,
    can_sync=True,
    last_sync_at=None,
    last_sync_status=None,
    connection_name="test-connection",
):
    """Create a mock connection object."""
    conn = MagicMock()
    conn.id = connection_id
    conn.airbyte_connection_id = airbyte_connection_id
    conn.status = status
    conn.is_enabled = is_enabled
    conn.can_sync = can_sync
    conn.last_sync_at = last_sync_at
    conn.last_sync_status = last_sync_status
    conn.connection_name = connection_name
    return conn


def _make_mock_ingestion_job(
    job_id="job-1",
    tenant_id="tenant-1",
    connector_id="connector-1",
    retry_count=0,
    status=JobStatus.FAILED,
    error_message=None,
    can_retry=True,
    next_retry_at=None,
    completed_at=None,
    created_at=None,
    error_code=None,
    job_metadata=None,
):
    """Create a mock IngestionJob with required attributes and methods."""
    job = MagicMock()
    job.job_id = job_id
    job.tenant_id = tenant_id
    job.connector_id = connector_id
    job.retry_count = retry_count
    job.status = status
    job.error_message = error_message
    job.can_retry = can_retry
    job.next_retry_at = next_retry_at
    job.completed_at = completed_at
    job.created_at = created_at or datetime.now(timezone.utc)
    job.error_code = error_code
    job.job_metadata = job_metadata
    job.mark_failed = MagicMock()
    job.mark_dead_letter = MagicMock()
    return job


def _make_entitlement_result(is_allowed=True, reason=None, plan_id="plan-1"):
    """Create a mock JobEntitlementResult."""
    result = MagicMock()
    result.is_allowed = is_allowed
    result.reason = reason
    result.billing_state = MagicMock()
    result.billing_state.value = "active"
    result.plan_id = plan_id
    return result


def _make_sync_result(
    job_id="airbyte-job-1",
    status_value="succeeded",
    records_synced=100,
    bytes_synced=5000,
    duration_seconds=30.5,
):
    """Create a mock AirbyteSyncResult for _execute_sync."""
    from src.integrations.airbyte.models import AirbyteJobStatus

    result = MagicMock()
    result.job_id = job_id
    result.status = AirbyteJobStatus.SUCCEEDED
    result.records_synced = records_synced
    result.bytes_synced = bytes_synced
    result.duration_seconds = duration_seconds
    return result


@pytest.fixture
def mock_db():
    """Mock SQLAlchemy database session."""
    session = MagicMock()
    session.flush = MagicMock()
    session.query = MagicMock()
    session.execute = MagicMock()
    return session


@pytest.fixture
def mock_airbyte_client():
    """Mock AirbyteClient."""
    client = MagicMock()
    client.sync_and_wait = AsyncMock()
    return client


# =============================================================================
# SyncOrchestrator Tests
# =============================================================================


class TestSyncOrchestratorInit:
    """Tests for SyncOrchestrator.__init__ validation."""

    def test_init_with_valid_tenant_id(self, mock_db, mock_airbyte_client):
        with patch("src.services.sync_orchestrator.AirbyteService"), \
             patch("src.services.sync_orchestrator.DataChangeAggregator"):
            orch = SyncOrchestrator(mock_db, "tenant-1", mock_airbyte_client)
            assert orch.tenant_id == "tenant-1"
            assert orch.max_retries == DEFAULT_MAX_RETRIES

    def test_init_with_empty_tenant_id_raises(self, mock_db):
        with pytest.raises(ValueError, match="tenant_id is required"):
            SyncOrchestrator(mock_db, "")

    def test_init_with_none_tenant_id_raises(self, mock_db):
        with pytest.raises(ValueError, match="tenant_id is required"):
            SyncOrchestrator(mock_db, None)

    def test_init_custom_retry_config(self, mock_db, mock_airbyte_client):
        with patch("src.services.sync_orchestrator.AirbyteService"), \
             patch("src.services.sync_orchestrator.DataChangeAggregator"):
            orch = SyncOrchestrator(
                mock_db,
                "tenant-1",
                mock_airbyte_client,
                max_retries=5,
                base_delay_seconds=1.0,
                max_delay_seconds=30.0,
            )
            assert orch.max_retries == 5
            assert orch.base_delay_seconds == 1.0
            assert orch.max_delay_seconds == 30.0


class TestCalculateBackoffDelay:
    """Tests for SyncOrchestrator._calculate_backoff_delay."""

    @pytest.fixture
    def orchestrator(self, mock_db, mock_airbyte_client):
        with patch("src.services.sync_orchestrator.AirbyteService"), \
             patch("src.services.sync_orchestrator.DataChangeAggregator"):
            return SyncOrchestrator(
                mock_db,
                "tenant-1",
                mock_airbyte_client,
                base_delay_seconds=2.0,
                max_delay_seconds=60.0,
            )

    @pytest.mark.parametrize(
        "attempt, expected_delay",
        [
            (0, 2.0),    # 2 * 2^0 = 2
            (1, 4.0),    # 2 * 2^1 = 4
            (2, 8.0),    # 2 * 2^2 = 8
            (3, 16.0),   # 2 * 2^3 = 16
            (4, 32.0),   # 2 * 2^4 = 32
        ],
    )
    def test_exponential_backoff(self, orchestrator, attempt, expected_delay):
        assert orchestrator._calculate_backoff_delay(attempt) == expected_delay

    def test_backoff_capped_at_max_delay(self, orchestrator):
        # 2 * 2^6 = 128, should be capped at 60
        assert orchestrator._calculate_backoff_delay(6) == 60.0

    def test_backoff_exactly_at_max(self, mock_db, mock_airbyte_client):
        with patch("src.services.sync_orchestrator.AirbyteService"), \
             patch("src.services.sync_orchestrator.DataChangeAggregator"):
            orch = SyncOrchestrator(
                mock_db,
                "tenant-1",
                mock_airbyte_client,
                base_delay_seconds=2.0,
                max_delay_seconds=8.0,
            )
            # 2 * 2^2 = 8 == max_delay
            assert orch._calculate_backoff_delay(2) == 8.0
            # 2 * 2^3 = 16 > max_delay, should cap
            assert orch._calculate_backoff_delay(3) == 8.0


class TestTriggerSyncWithRetry:
    """Tests for SyncOrchestrator.trigger_sync_with_retry."""

    @pytest.fixture
    def setup_orchestrator(self, mock_db, mock_airbyte_client):
        """Create orchestrator with mocked dependencies."""
        with patch("src.services.sync_orchestrator.AirbyteService") as MockAirbyteService, \
             patch("src.services.sync_orchestrator.DataChangeAggregator") as MockAggregator:
            mock_airbyte_svc = MockAirbyteService.return_value
            mock_aggregator = MockAggregator.return_value

            orch = SyncOrchestrator(
                mock_db,
                "tenant-1",
                mock_airbyte_client,
                max_retries=2,
                base_delay_seconds=0.01,
                max_delay_seconds=0.1,
            )
            return orch, mock_airbyte_svc, mock_aggregator

    @pytest.mark.asyncio
    async def test_skips_when_entitlement_denied(self, setup_orchestrator):
        orch, mock_svc, _ = setup_orchestrator
        entitlement_result = _make_entitlement_result(is_allowed=False, reason="No active plan")

        with patch("src.services.sync_orchestrator.JobEntitlementChecker") as MockChecker:
            checker_instance = MockChecker.return_value
            checker_instance.check_job_entitlement.return_value = entitlement_result
            checker_instance.log_job_skipped = AsyncMock()

            result = await orch.trigger_sync_with_retry("conn-1")

            assert result is None
            checker_instance.log_job_skipped.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_raises_connection_not_found(self, setup_orchestrator):
        orch, mock_svc, _ = setup_orchestrator
        mock_svc.get_connection.return_value = None

        with patch("src.services.sync_orchestrator.JobEntitlementChecker") as MockChecker:
            checker_instance = MockChecker.return_value
            checker_instance.check_job_entitlement.return_value = _make_entitlement_result()
            checker_instance.log_job_allowed = AsyncMock()

            with pytest.raises(ConnectionNotFoundError, match="conn-1 not found"):
                await orch.trigger_sync_with_retry("conn-1")

    @pytest.mark.asyncio
    async def test_raises_error_when_connection_cannot_sync(self, setup_orchestrator):
        orch, mock_svc, _ = setup_orchestrator
        conn = _make_mock_connection(can_sync=False, status="inactive", is_enabled=False)
        mock_svc.get_connection.return_value = conn

        with patch("src.services.sync_orchestrator.JobEntitlementChecker") as MockChecker:
            checker_instance = MockChecker.return_value
            checker_instance.check_job_entitlement.return_value = _make_entitlement_result()
            checker_instance.log_job_allowed = AsyncMock()

            with pytest.raises(SyncOrchestratorError, match="cannot sync"):
                await orch.trigger_sync_with_retry("conn-1")

    @pytest.mark.asyncio
    async def test_succeeds_on_first_attempt(self, setup_orchestrator, mock_airbyte_client):
        orch, mock_svc, mock_agg = setup_orchestrator
        conn = _make_mock_connection()
        mock_svc.get_connection.return_value = conn

        sync_result = _make_sync_result()
        mock_airbyte_client.sync_and_wait = AsyncMock(return_value=sync_result)

        with patch("src.services.sync_orchestrator.JobEntitlementChecker") as MockChecker:
            checker_instance = MockChecker.return_value
            checker_instance.check_job_entitlement.return_value = _make_entitlement_result()
            checker_instance.log_job_allowed = AsyncMock()

            result = await orch.trigger_sync_with_retry("conn-1")

            assert result is not None
            assert result.is_successful is True
            assert result.status == "succeeded"
            assert result.attempt_count == 1
            assert result.records_synced == 100
            assert result.bytes_synced == 5000
            assert result.error_message is None
            mock_svc.record_sync_success.assert_called_once_with("conn-1")

    @pytest.mark.asyncio
    async def test_retries_on_airbyte_sync_error_then_succeeds(
        self, setup_orchestrator, mock_airbyte_client
    ):
        orch, mock_svc, mock_agg = setup_orchestrator
        conn = _make_mock_connection()
        mock_svc.get_connection.return_value = conn

        sync_result = _make_sync_result()
        # First call fails, second succeeds
        mock_airbyte_client.sync_and_wait = AsyncMock(
            side_effect=[
                AirbyteSyncError("Sync failed", job_id="j1", connection_id="abc-123"),
                sync_result,
            ]
        )

        with patch("src.services.sync_orchestrator.JobEntitlementChecker") as MockChecker:
            checker_instance = MockChecker.return_value
            checker_instance.check_job_entitlement.return_value = _make_entitlement_result()
            checker_instance.log_job_allowed = AsyncMock()

            result = await orch.trigger_sync_with_retry("conn-1")

            assert result is not None
            assert result.is_successful is True
            assert result.attempt_count == 2

    @pytest.mark.asyncio
    async def test_respects_rate_limit_retry_after(
        self, setup_orchestrator, mock_airbyte_client
    ):
        orch, mock_svc, mock_agg = setup_orchestrator
        conn = _make_mock_connection()
        mock_svc.get_connection.return_value = conn

        sync_result = _make_sync_result()
        rate_limit_error = AirbyteRateLimitError(retry_after=5)
        mock_airbyte_client.sync_and_wait = AsyncMock(
            side_effect=[rate_limit_error, sync_result]
        )

        with patch("src.services.sync_orchestrator.JobEntitlementChecker") as MockChecker, \
             patch("src.services.sync_orchestrator.asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
            checker_instance = MockChecker.return_value
            checker_instance.check_job_entitlement.return_value = _make_entitlement_result()
            checker_instance.log_job_allowed = AsyncMock()

            result = await orch.trigger_sync_with_retry("conn-1")

            assert result.is_successful is True
            # The delay should be at least the retry_after value (5s)
            actual_delay = mock_sleep.call_args[0][0]
            assert actual_delay >= 5.0

    @pytest.mark.asyncio
    async def test_returns_failed_result_after_all_retries_exhausted(
        self, setup_orchestrator, mock_airbyte_client
    ):
        orch, mock_svc, mock_agg = setup_orchestrator
        conn = _make_mock_connection()
        mock_svc.get_connection.return_value = conn

        # All attempts fail (initial + 2 retries = 3 total)
        mock_airbyte_client.sync_and_wait = AsyncMock(
            side_effect=AirbyteSyncError("Persistent failure", job_id="j1", connection_id="abc-123")
        )

        with patch("src.services.sync_orchestrator.JobEntitlementChecker") as MockChecker, \
             patch("src.services.sync_orchestrator.asyncio.sleep", new_callable=AsyncMock):
            checker_instance = MockChecker.return_value
            checker_instance.check_job_entitlement.return_value = _make_entitlement_result()
            checker_instance.log_job_allowed = AsyncMock()

            result = await orch.trigger_sync_with_retry("conn-1")

            assert result is not None
            assert result.is_successful is False
            assert result.status == "failed"
            assert result.attempt_count == 3  # max_retries(2) + 1
            assert result.error_message == "Persistent failure"
            mock_svc.mark_connection_failed.assert_called_once_with("conn-1", "Persistent failure")


class TestGetSyncState:
    """Tests for SyncOrchestrator.get_sync_state."""

    @pytest.fixture
    def orchestrator_with_svc(self, mock_db, mock_airbyte_client):
        with patch("src.services.sync_orchestrator.AirbyteService") as MockAirbyteService, \
             patch("src.services.sync_orchestrator.DataChangeAggregator"):
            mock_svc = MockAirbyteService.return_value
            orch = SyncOrchestrator(mock_db, "tenant-1", mock_airbyte_client)
            return orch, mock_svc

    def test_get_sync_state_happy_path(self, orchestrator_with_svc):
        orch, mock_svc = orchestrator_with_svc
        last_sync = datetime(2025, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        conn = _make_mock_connection(
            status="active",
            is_enabled=True,
            can_sync=True,
            last_sync_at=last_sync,
            last_sync_status="succeeded",
        )
        mock_svc.get_connection.return_value = conn

        state = orch.get_sync_state("conn-1")

        assert state["connection_id"] == "conn-1"
        assert state["status"] == "active"
        assert state["last_sync_at"] == last_sync.isoformat()
        assert state["last_sync_status"] == "succeeded"
        assert state["is_enabled"] is True
        assert state["can_sync"] is True

    def test_get_sync_state_never_synced(self, orchestrator_with_svc):
        orch, mock_svc = orchestrator_with_svc
        conn = _make_mock_connection(last_sync_at=None, last_sync_status=None)
        mock_svc.get_connection.return_value = conn

        state = orch.get_sync_state("conn-1")
        assert state["last_sync_at"] is None
        assert state["last_sync_status"] is None

    def test_get_sync_state_connection_not_found(self, orchestrator_with_svc):
        orch, mock_svc = orchestrator_with_svc
        mock_svc.get_connection.return_value = None

        with pytest.raises(ConnectionNotFoundError, match="conn-1 not found"):
            orch.get_sync_state("conn-1")


class TestGetFailedConnections:
    """Tests for SyncOrchestrator.get_failed_connections."""

    @pytest.fixture
    def orchestrator_with_svc(self, mock_db, mock_airbyte_client):
        with patch("src.services.sync_orchestrator.AirbyteService") as MockAirbyteService, \
             patch("src.services.sync_orchestrator.DataChangeAggregator"):
            mock_svc = MockAirbyteService.return_value
            orch = SyncOrchestrator(mock_db, "tenant-1", mock_airbyte_client)
            return orch, mock_svc

    def test_get_failed_connections_returns_list(self, orchestrator_with_svc):
        orch, mock_svc = orchestrator_with_svc
        last_sync = datetime(2025, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        conn1 = _make_mock_connection(
            connection_id="c1",
            connection_name="conn-one",
            last_sync_at=last_sync,
            last_sync_status="failed",
        )
        conn2 = _make_mock_connection(
            connection_id="c2",
            connection_name="conn-two",
            last_sync_at=None,
            last_sync_status="failed",
        )
        mock_result = MagicMock()
        mock_result.connections = [conn1, conn2]
        mock_svc.list_connections.return_value = mock_result

        failed = orch.get_failed_connections()

        assert len(failed) == 2
        assert failed[0]["connection_id"] == "c1"
        assert failed[0]["connection_name"] == "conn-one"
        assert failed[0]["last_sync_at"] == last_sync.isoformat()
        assert failed[1]["connection_id"] == "c2"
        assert failed[1]["last_sync_at"] is None
        mock_svc.list_connections.assert_called_once_with(status="failed")

    def test_get_failed_connections_empty(self, orchestrator_with_svc):
        orch, mock_svc = orchestrator_with_svc
        mock_result = MagicMock()
        mock_result.connections = []
        mock_svc.list_connections.return_value = mock_result

        failed = orch.get_failed_connections()
        assert failed == []


# =============================================================================
# SyncRetryManager Tests
# =============================================================================


class TestSyncRetryManagerInit:
    """Tests for SyncRetryManager.__init__ validation."""

    def test_init_with_valid_params(self, mock_db):
        manager = SyncRetryManager(mock_db, "tenant-1")
        assert manager.tenant_id == "tenant-1"
        assert manager.db is mock_db

    def test_init_with_empty_tenant_id_raises(self, mock_db):
        with pytest.raises(ValueError, match="tenant_id is required"):
            SyncRetryManager(mock_db, "")

    def test_init_with_none_tenant_id_raises(self, mock_db):
        with pytest.raises(ValueError, match="tenant_id is required"):
            SyncRetryManager(mock_db, None)

    def test_init_with_custom_retry_policy(self, mock_db):
        policy = RetryPolicy(max_retries=10)
        manager = SyncRetryManager(mock_db, "tenant-1", retry_policy=policy)
        assert manager.retry_policy.max_retries == 10

    def test_init_default_retry_policy(self, mock_db):
        manager = SyncRetryManager(mock_db, "tenant-1")
        assert isinstance(manager.retry_policy, RetryPolicy)


class TestHandleFailure:
    """Tests for SyncRetryManager.handle_failure."""

    @pytest.fixture
    def manager(self, mock_db):
        return SyncRetryManager(mock_db, "tenant-1")

    def test_schedules_retry_when_should_retry_is_true(self, manager):
        job = _make_mock_ingestion_job(retry_count=1)
        next_retry = datetime.now(timezone.utc) + timedelta(minutes=5)

        decision = RetryDecision(
            should_retry=True,
            delay_seconds=300.0,
            next_retry_at=next_retry,
            move_to_dlq=False,
            reason="Transient error - retry",
        )

        with patch("src.services.sync_retry_manager.should_retry", return_value=decision), \
             patch("src.services.sync_retry_manager.log_retry_decision"), \
             patch.object(manager, "_log_audit_retry"):
            result = manager.handle_failure(
                job, ErrorCategory.SERVER_ERROR, "Internal Server Error"
            )

            assert result.action == FailureAction.RETRY_SCHEDULED
            assert result.job_id == "job-1"
            assert result.next_retry_at == next_retry
            assert result.delay_seconds == 300.0
            job.mark_failed.assert_called_once_with(
                error_message="Internal Server Error",
                error_code=ErrorCategory.SERVER_ERROR.value,
                next_retry_at=next_retry,
            )

    def test_moves_to_dlq_when_move_to_dlq_is_true(self, manager):
        job = _make_mock_ingestion_job(retry_count=5)

        decision = RetryDecision(
            should_retry=False,
            delay_seconds=0,
            next_retry_at=None,
            move_to_dlq=True,
            reason="Auth error - requires manual intervention",
        )

        with patch("src.services.sync_retry_manager.should_retry", return_value=decision), \
             patch("src.services.sync_retry_manager.log_retry_decision"), \
             patch.object(manager, "_log_audit_dlq"), \
             patch.object(manager, "_notify_admins_of_failure", return_value=True):
            result = manager.handle_failure(
                job, ErrorCategory.AUTH_ERROR, "Unauthorized"
            )

            assert result.action == FailureAction.MOVED_TO_DLQ
            assert result.notified_admins is True
            job.mark_dead_letter.assert_called_once_with("Unauthorized")

    def test_marks_terminal_failure_when_neither_retry_nor_dlq(self, manager):
        job = _make_mock_ingestion_job(retry_count=3)

        decision = RetryDecision(
            should_retry=False,
            delay_seconds=0,
            next_retry_at=None,
            move_to_dlq=False,
            reason="Unhandled error category",
        )

        with patch("src.services.sync_retry_manager.should_retry", return_value=decision), \
             patch("src.services.sync_retry_manager.log_retry_decision"), \
             patch.object(manager, "_log_audit_terminal_failure"), \
             patch.object(manager, "_notify_admins_of_failure", return_value=False):
            result = manager.handle_failure(
                job, ErrorCategory.UNKNOWN, "Unknown failure"
            )

            assert result.action == FailureAction.MARKED_FAILED_TERMINAL
            assert result.notified_admins is False
            job.mark_failed.assert_called_once_with(
                error_message="Unknown failure",
                error_code=ErrorCategory.UNKNOWN.value,
            )


class TestHandleFailureFromStatusCode:
    """Tests for SyncRetryManager.handle_failure_from_status_code."""

    def test_delegates_to_handle_failure_with_categorized_error(self, mock_db):
        manager = SyncRetryManager(mock_db, "tenant-1")
        job = _make_mock_ingestion_job()

        with patch.object(manager, "handle_failure") as mock_handle:
            mock_handle.return_value = FailureResult(
                job_id="job-1",
                action=FailureAction.MOVED_TO_DLQ,
                retry_count=0,
                error_category="auth_error",
                error_message="Forbidden",
            )

            result = manager.handle_failure_from_status_code(
                job, status_code=403, error_message="Forbidden", retry_after=None
            )

            mock_handle.assert_called_once()
            call_args = mock_handle.call_args
            assert call_args.kwargs["error_category"] == ErrorCategory.AUTH_ERROR
            assert call_args.kwargs["status_code"] == 403

    @pytest.mark.parametrize(
        "status_code, expected_category",
        [
            (401, ErrorCategory.AUTH_ERROR),
            (403, ErrorCategory.AUTH_ERROR),
            (429, ErrorCategory.RATE_LIMIT),
            (500, ErrorCategory.SERVER_ERROR),
            (502, ErrorCategory.SERVER_ERROR),
            (503, ErrorCategory.SERVER_ERROR),
        ],
    )
    def test_categorizes_status_codes_correctly(self, mock_db, status_code, expected_category):
        manager = SyncRetryManager(mock_db, "tenant-1")
        job = _make_mock_ingestion_job()

        with patch.object(manager, "handle_failure") as mock_handle:
            mock_handle.return_value = FailureResult(
                job_id="job-1",
                action=FailureAction.RETRY_SCHEDULED,
                retry_count=0,
                error_category=expected_category.value,
                error_message="error",
            )

            manager.handle_failure_from_status_code(job, status_code, "error")

            call_args = mock_handle.call_args
            assert call_args.kwargs["error_category"] == expected_category


class TestGetFailureSummary:
    """Tests for SyncRetryManager.get_failure_summary."""

    def test_no_failures(self, mock_db):
        manager = SyncRetryManager(mock_db, "tenant-1")
        mock_query = mock_db.query.return_value
        mock_query.filter.return_value.order_by.return_value.limit.return_value.all.return_value = []

        summary = manager.get_failure_summary("connector-1")

        assert summary.connector_id == "connector-1"
        assert summary.total_failures == 0
        assert summary.active_retries == 0
        assert summary.dead_letter_count == 0
        assert summary.last_error is None
        assert summary.last_error_at is None
        assert summary.next_retry_at is None

    def test_with_failures_and_dlq(self, mock_db):
        manager = SyncRetryManager(mock_db, "tenant-1")
        now = datetime.now(timezone.utc)
        next_retry = now + timedelta(minutes=10)

        # Create mock failed jobs
        failed_job_1 = _make_mock_ingestion_job(
            job_id="j1",
            status=JobStatus.FAILED,
            can_retry=True,
            error_message="Connection timeout",
            completed_at=now,
            error_code="timeout",
            next_retry_at=next_retry,
        )
        failed_job_2 = _make_mock_ingestion_job(
            job_id="j2",
            status=JobStatus.FAILED,
            can_retry=False,
            error_message="Max retries exceeded",
            completed_at=now - timedelta(hours=1),
            error_code="server_error",
            next_retry_at=None,
        )
        dlq_job = _make_mock_ingestion_job(
            job_id="j3",
            status=JobStatus.DEAD_LETTER,
            can_retry=False,
            error_message="Auth failed permanently",
            completed_at=now - timedelta(hours=2),
            error_code="auth_error",
        )

        mock_query = mock_db.query.return_value
        mock_query.filter.return_value.order_by.return_value.limit.return_value.all.return_value = [
            failed_job_1, failed_job_2, dlq_job
        ]

        summary = manager.get_failure_summary("connector-1")

        assert summary.total_failures == 3
        assert summary.active_retries == 1  # only j1 has can_retry=True and status=FAILED
        assert summary.dead_letter_count == 1
        assert summary.last_error == "Connection timeout"
        assert summary.last_error_at == now
        assert summary.last_error_category == "timeout"
        assert summary.next_retry_at == next_retry

    def test_with_dlq_only(self, mock_db):
        manager = SyncRetryManager(mock_db, "tenant-1")
        now = datetime.now(timezone.utc)

        dlq_job = _make_mock_ingestion_job(
            status=JobStatus.DEAD_LETTER,
            error_message="Permanent failure",
            completed_at=now,
            error_code="auth_error",
        )

        mock_query = mock_db.query.return_value
        mock_query.filter.return_value.order_by.return_value.limit.return_value.all.return_value = [
            dlq_job
        ]

        summary = manager.get_failure_summary("connector-1")

        assert summary.total_failures == 1
        assert summary.active_retries == 0
        assert summary.dead_letter_count == 1
        assert summary.next_retry_at is None


class TestErrorMessageTruncation:
    """Tests for error message truncation at MAX_ERROR_MESSAGE_LENGTH."""

    def test_long_error_message_truncated(self, mock_db):
        manager = SyncRetryManager(mock_db, "tenant-1")
        job = _make_mock_ingestion_job()

        long_message = "x" * 1000
        assert len(long_message) > MAX_ERROR_MESSAGE_LENGTH

        decision = RetryDecision(
            should_retry=True,
            delay_seconds=60.0,
            next_retry_at=datetime.now(timezone.utc) + timedelta(seconds=60),
            move_to_dlq=False,
            reason="retry",
        )

        with patch("src.services.sync_retry_manager.should_retry", return_value=decision), \
             patch("src.services.sync_retry_manager.log_retry_decision"), \
             patch.object(manager, "_log_audit_retry"):
            result = manager.handle_failure(
                job, ErrorCategory.SERVER_ERROR, long_message
            )

            # The error_message passed to mark_failed should be truncated
            actual_msg = job.mark_failed.call_args.kwargs["error_message"]
            assert len(actual_msg) == MAX_ERROR_MESSAGE_LENGTH

    def test_short_error_message_not_truncated(self, mock_db):
        manager = SyncRetryManager(mock_db, "tenant-1")
        job = _make_mock_ingestion_job()

        short_message = "Short error"

        decision = RetryDecision(
            should_retry=True,
            delay_seconds=60.0,
            next_retry_at=datetime.now(timezone.utc) + timedelta(seconds=60),
            move_to_dlq=False,
            reason="retry",
        )

        with patch("src.services.sync_retry_manager.should_retry", return_value=decision), \
             patch("src.services.sync_retry_manager.log_retry_decision"), \
             patch.object(manager, "_log_audit_retry"):
            result = manager.handle_failure(
                job, ErrorCategory.SERVER_ERROR, short_message
            )

            actual_msg = job.mark_failed.call_args.kwargs["error_message"]
            assert actual_msg == short_message


class TestNotifyAdminsOfFailure:
    """Tests for SyncRetryManager._notify_admins_of_failure."""

    @pytest.fixture
    def manager(self, mock_db):
        return SyncRetryManager(mock_db, "tenant-1")

    def test_notify_success(self, manager):
        job = _make_mock_ingestion_job(job_metadata={"connector_name": "Shopify"})

        with patch.object(manager, "_get_admin_user_ids", return_value=["user-1", "user-2"]), \
             patch("src.services.notification_service.NotificationService") as MockNotif:
            notif_instance = MockNotif.return_value
            notif_instance.notify_connector_failed.return_value = [MagicMock(), MagicMock()]

            result = manager._notify_admins_of_failure(
                job, ErrorCategory.SERVER_ERROR, "Sync failed"
            )

            assert result is True
            notif_instance.notify_connector_failed.assert_called_once()

    def test_notify_no_admins_found(self, manager):
        job = _make_mock_ingestion_job()

        with patch.object(manager, "_get_admin_user_ids", return_value=[]):
            result = manager._notify_admins_of_failure(
                job, ErrorCategory.SERVER_ERROR, "Sync failed"
            )

            assert result is False

    def test_notify_exception_returns_false(self, manager):
        job = _make_mock_ingestion_job()

        with patch.object(manager, "_get_admin_user_ids", side_effect=Exception("DB error")):
            result = manager._notify_admins_of_failure(
                job, ErrorCategory.SERVER_ERROR, "Sync failed"
            )

            assert result is False


class TestFailureResultSerialization:
    """Tests for FailureResult.to_dict and FailureSummary.to_dict."""

    def test_failure_result_to_dict_without_next_retry(self):
        result = FailureResult(
            job_id="job-1",
            action=FailureAction.MARKED_FAILED_TERMINAL,
            retry_count=3,
            error_category="server_error",
            error_message="Internal Server Error",
            delay_seconds=0,
            notified_admins=True,
        )

        d = result.to_dict()

        assert d["job_id"] == "job-1"
        assert d["action"] == "marked_failed_terminal"
        assert d["retry_count"] == 3
        assert d["error_category"] == "server_error"
        assert d["delay_seconds"] == 0
        assert d["notified_admins"] is True
        assert "next_retry_at" not in d

    def test_failure_result_to_dict_with_next_retry(self):
        next_retry = datetime(2025, 6, 1, 12, 0, 0, tzinfo=timezone.utc)
        result = FailureResult(
            job_id="job-1",
            action=FailureAction.RETRY_SCHEDULED,
            retry_count=1,
            error_category="rate_limit",
            error_message="Rate limited",
            next_retry_at=next_retry,
            delay_seconds=120.0,
        )

        d = result.to_dict()

        assert d["next_retry_at"] == next_retry.isoformat()
        assert d["action"] == "retry_scheduled"

    def test_failure_result_to_dict_truncates_error_message(self):
        long_msg = "x" * 500
        result = FailureResult(
            job_id="job-1",
            action=FailureAction.RETRY_SCHEDULED,
            retry_count=0,
            error_category="server_error",
            error_message=long_msg,
        )

        d = result.to_dict()
        # to_dict truncates error_message to 200 chars
        assert len(d["error_message"]) == 200

    def test_failure_summary_to_dict_with_all_fields(self):
        now = datetime(2025, 6, 1, 12, 0, 0, tzinfo=timezone.utc)
        next_retry = now + timedelta(minutes=10)

        summary = FailureSummary(
            connector_id="conn-1",
            total_failures=5,
            active_retries=2,
            dead_letter_count=1,
            last_error="Connection reset",
            last_error_at=now,
            last_error_category="connection",
            next_retry_at=next_retry,
        )

        d = summary.to_dict()

        assert d["connector_id"] == "conn-1"
        assert d["total_failures"] == 5
        assert d["active_retries"] == 2
        assert d["dead_letter_count"] == 1
        assert d["last_error"] == "Connection reset"
        assert d["last_error_at"] == now.isoformat()
        assert d["last_error_category"] == "connection"
        assert d["next_retry_at"] == next_retry.isoformat()

    def test_failure_summary_to_dict_with_none_fields(self):
        summary = FailureSummary(
            connector_id="conn-1",
            total_failures=0,
            active_retries=0,
            dead_letter_count=0,
        )

        d = summary.to_dict()

        assert d["last_error"] is None
        assert d["last_error_at"] is None
        assert d["last_error_category"] is None
        assert d["next_retry_at"] is None


# =============================================================================
# SyncPlanResolver Tests
# =============================================================================


class TestGetSyncIntervalMinutes:
    """Tests for SyncPlanResolver.get_sync_interval_minutes per tier."""

    @pytest.fixture
    def resolver(self, mock_db):
        return SyncPlanResolver(mock_db)

    @pytest.mark.parametrize(
        "plan_name, expected_interval",
        [
            ("free", 1440),
            ("growth", 360),
            ("pro", 60),
            ("enterprise", 60),
        ],
    )
    def test_sync_interval_per_tier(self, resolver, mock_db, plan_name, expected_interval):
        mock_plan = MagicMock()
        mock_plan.name = plan_name
        mock_db.execute.return_value.scalar_one_or_none.return_value = mock_plan

        interval = resolver.get_sync_interval_minutes("tenant-1")

        assert interval == expected_interval

    def test_default_interval_when_no_subscription(self, resolver, mock_db):
        mock_db.execute.return_value.scalar_one_or_none.return_value = None

        interval = resolver.get_sync_interval_minutes("tenant-1")

        assert interval == DEFAULT_SYNC_INTERVAL_MINUTES
        assert interval == 1440

    def test_unknown_plan_name_defaults_to_free_tier(self, resolver, mock_db):
        mock_plan = MagicMock()
        mock_plan.name = "premium_custom_xyz"
        mock_db.execute.return_value.scalar_one_or_none.return_value = mock_plan

        interval = resolver.get_sync_interval_minutes("tenant-1")

        assert interval == DEFAULT_SYNC_INTERVAL_MINUTES

    def test_plan_name_case_insensitive(self, resolver, mock_db):
        mock_plan = MagicMock()
        mock_plan.name = "  Growth  "
        mock_db.execute.return_value.scalar_one_or_none.return_value = mock_plan

        interval = resolver.get_sync_interval_minutes("tenant-1")

        assert interval == 360  # Growth tier


class TestIsSyncDue:
    """Tests for SyncPlanResolver.is_sync_due."""

    @pytest.fixture
    def resolver(self, mock_db):
        return SyncPlanResolver(mock_db)

    def test_never_synced_returns_true(self, resolver, mock_db):
        # No subscription -> free tier (1440 min)
        mock_db.execute.return_value.scalar_one_or_none.return_value = None

        assert resolver.is_sync_due("tenant-1", last_sync_at=None) is True

    def test_recently_synced_returns_false(self, resolver, mock_db):
        # Free tier = 1440 minutes
        mock_db.execute.return_value.scalar_one_or_none.return_value = None

        # Last synced 30 minutes ago
        last_sync = datetime.now(timezone.utc) - timedelta(minutes=30)

        assert resolver.is_sync_due("tenant-1", last_sync_at=last_sync) is False

    def test_overdue_sync_returns_true(self, resolver, mock_db):
        # Free tier = 1440 minutes
        mock_db.execute.return_value.scalar_one_or_none.return_value = None

        # Last synced 25 hours ago (> 1440 minutes)
        last_sync = datetime.now(timezone.utc) - timedelta(hours=25)

        assert resolver.is_sync_due("tenant-1", last_sync_at=last_sync) is True

    def test_sync_due_respects_plan_tier(self, resolver, mock_db):
        # Pro tier = 60 minutes
        mock_plan = MagicMock()
        mock_plan.name = "pro"
        mock_db.execute.return_value.scalar_one_or_none.return_value = mock_plan

        # Last synced 90 minutes ago (> 60 minutes for pro)
        last_sync = datetime.now(timezone.utc) - timedelta(minutes=90)

        assert resolver.is_sync_due("tenant-1", last_sync_at=last_sync) is True

    def test_sync_not_due_for_pro_within_interval(self, resolver, mock_db):
        # Pro tier = 60 minutes
        mock_plan = MagicMock()
        mock_plan.name = "pro"
        mock_db.execute.return_value.scalar_one_or_none.return_value = mock_plan

        # Last synced 30 minutes ago (< 60 minutes for pro)
        last_sync = datetime.now(timezone.utc) - timedelta(minutes=30)

        assert resolver.is_sync_due("tenant-1", last_sync_at=last_sync) is False


class TestSyncIntervalByTierConstants:
    """Tests for SYNC_INTERVAL_BY_TIER constant mapping."""

    def test_tier_mapping_values(self):
        assert SYNC_INTERVAL_BY_TIER[0] == 1440   # Free: daily
        assert SYNC_INTERVAL_BY_TIER[1] == 360    # Growth: every 6 hours
        assert SYNC_INTERVAL_BY_TIER[2] == 60     # Pro: hourly
        assert SYNC_INTERVAL_BY_TIER[3] == 60     # Enterprise: hourly

    def test_default_interval_is_daily(self):
        assert DEFAULT_SYNC_INTERVAL_MINUTES == 1440
