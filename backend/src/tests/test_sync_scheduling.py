"""
Unit tests for sync scheduling and plan-based SLA enforcement.

Covers:
- SyncPlanResolver: interval resolution per plan tier, is_sync_due logic
- sync_scheduler: job dispatching, isolation skipping, entitlement gating
- sync_executor: cycle execution, timestamp propagation, graceful shutdown

Security:
- Verifies Free tier cannot exceed daily sync
- Verifies Growth tier capped at 6-hour interval
- Verifies one-active-job-per-connection isolation
- Verifies entitlement gating skips non-entitled tenants
"""

import uuid
from datetime import datetime, timezone, timedelta
from unittest.mock import MagicMock, patch

import pytest

from src.services.sync_plan_resolver import (
    SyncPlanResolver,
    SYNC_INTERVAL_BY_TIER,
    DEFAULT_SYNC_INTERVAL_MINUTES,
)


# =============================================================================
# Constants
# =============================================================================

TENANT_ID = "tenant-test-001"
TENANT_ID_2 = "tenant-test-002"
CONNECTION_ID = "conn-abc-123"
AIRBYTE_CONNECTION_ID = "airbyte-xyz-789"


# =============================================================================
# Helpers
# =============================================================================

def _mock_session():
    """Create a mock SQLAlchemy session."""
    session = MagicMock()
    session.execute = MagicMock()
    session.add = MagicMock()
    session.commit = MagicMock()
    session.flush = MagicMock()
    session.rollback = MagicMock()
    return session


def _mock_plan(name: str):
    """Create a mock Plan object."""
    plan = MagicMock()
    plan.name = name
    plan.id = f"plan_{name}"
    return plan


def _mock_connection(
    tenant_id=TENANT_ID,
    connection_id=None,
    airbyte_connection_id=AIRBYTE_CONNECTION_ID,
    last_sync_at=None,
    is_enabled=True,
    source_type="shopify",
    connection_name="Test Connection",
):
    """Create a mock TenantAirbyteConnection."""
    conn = MagicMock()
    conn.id = connection_id or str(uuid.uuid4())
    conn.tenant_id = tenant_id
    conn.airbyte_connection_id = airbyte_connection_id
    conn.last_sync_at = last_sync_at
    conn.is_enabled = is_enabled
    conn.source_type = source_type
    conn.connection_name = connection_name
    conn.can_sync = True
    return conn


# =============================================================================
# SyncPlanResolver Tests
# =============================================================================

class TestSyncPlanResolverConstants:
    """Tests for plan tier constants."""

    def test_free_tier_is_daily(self):
        assert SYNC_INTERVAL_BY_TIER[0] == 1440

    def test_growth_tier_is_six_hours(self):
        assert SYNC_INTERVAL_BY_TIER[1] == 360

    def test_pro_tier_is_hourly(self):
        assert SYNC_INTERVAL_BY_TIER[2] == 60

    def test_enterprise_tier_is_hourly(self):
        assert SYNC_INTERVAL_BY_TIER[3] == 60

    def test_default_interval_is_daily(self):
        assert DEFAULT_SYNC_INTERVAL_MINUTES == 1440


class TestSyncPlanResolverInterval:
    """Tests for SyncPlanResolver.get_sync_interval_minutes()."""

    def test_free_plan_returns_daily(self):
        session = _mock_session()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = _mock_plan("free")
        session.execute.return_value = mock_result

        resolver = SyncPlanResolver(session)
        assert resolver.get_sync_interval_minutes(TENANT_ID) == 1440

    def test_growth_plan_returns_six_hours(self):
        session = _mock_session()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = _mock_plan("growth")
        session.execute.return_value = mock_result

        resolver = SyncPlanResolver(session)
        assert resolver.get_sync_interval_minutes(TENANT_ID) == 360

    def test_pro_plan_returns_hourly(self):
        session = _mock_session()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = _mock_plan("pro")
        session.execute.return_value = mock_result

        resolver = SyncPlanResolver(session)
        assert resolver.get_sync_interval_minutes(TENANT_ID) == 60

    def test_enterprise_plan_returns_hourly(self):
        session = _mock_session()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = _mock_plan("enterprise")
        session.execute.return_value = mock_result

        resolver = SyncPlanResolver(session)
        assert resolver.get_sync_interval_minutes(TENANT_ID) == 60

    def test_no_subscription_returns_daily_default(self):
        session = _mock_session()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        session.execute.return_value = mock_result

        resolver = SyncPlanResolver(session)
        assert resolver.get_sync_interval_minutes(TENANT_ID) == DEFAULT_SYNC_INTERVAL_MINUTES

    def test_unknown_plan_name_returns_daily_default(self):
        session = _mock_session()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = _mock_plan("custom_plan_xyz")
        session.execute.return_value = mock_result

        resolver = SyncPlanResolver(session)
        assert resolver.get_sync_interval_minutes(TENANT_ID) == DEFAULT_SYNC_INTERVAL_MINUTES


class TestSyncPlanResolverIsSyncDue:
    """Tests for SyncPlanResolver.is_sync_due()."""

    def test_never_synced_is_always_due(self):
        session = _mock_session()
        resolver = SyncPlanResolver(session)
        assert resolver.is_sync_due(TENANT_ID, last_sync_at=None) is True

    def test_free_tier_not_due_within_24h(self):
        """Free tier (daily): sync 12 hours ago should NOT be due."""
        session = _mock_session()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = _mock_plan("free")
        session.execute.return_value = mock_result

        resolver = SyncPlanResolver(session)
        last_sync = datetime.now(timezone.utc) - timedelta(hours=12)
        assert resolver.is_sync_due(TENANT_ID, last_sync_at=last_sync) is False

    def test_free_tier_due_after_24h(self):
        """Free tier (daily): sync 25 hours ago should be due."""
        session = _mock_session()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = _mock_plan("free")
        session.execute.return_value = mock_result

        resolver = SyncPlanResolver(session)
        last_sync = datetime.now(timezone.utc) - timedelta(hours=25)
        assert resolver.is_sync_due(TENANT_ID, last_sync_at=last_sync) is True

    def test_growth_tier_not_due_within_6h(self):
        """Growth tier (6h): sync 3 hours ago should NOT be due."""
        session = _mock_session()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = _mock_plan("growth")
        session.execute.return_value = mock_result

        resolver = SyncPlanResolver(session)
        last_sync = datetime.now(timezone.utc) - timedelta(hours=3)
        assert resolver.is_sync_due(TENANT_ID, last_sync_at=last_sync) is False

    def test_growth_tier_due_after_6h(self):
        """Growth tier (6h): sync 7 hours ago should be due."""
        session = _mock_session()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = _mock_plan("growth")
        session.execute.return_value = mock_result

        resolver = SyncPlanResolver(session)
        last_sync = datetime.now(timezone.utc) - timedelta(hours=7)
        assert resolver.is_sync_due(TENANT_ID, last_sync_at=last_sync) is True

    def test_enterprise_tier_due_after_1h(self):
        """Enterprise tier (hourly): sync 2 hours ago should be due."""
        session = _mock_session()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = _mock_plan("enterprise")
        session.execute.return_value = mock_result

        resolver = SyncPlanResolver(session)
        last_sync = datetime.now(timezone.utc) - timedelta(hours=2)
        assert resolver.is_sync_due(TENANT_ID, last_sync_at=last_sync) is True

    def test_enterprise_tier_not_due_within_1h(self):
        """Enterprise tier (hourly): sync 30 minutes ago should NOT be due."""
        session = _mock_session()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = _mock_plan("enterprise")
        session.execute.return_value = mock_result

        resolver = SyncPlanResolver(session)
        last_sync = datetime.now(timezone.utc) - timedelta(minutes=30)
        assert resolver.is_sync_due(TENANT_ID, last_sync_at=last_sync) is False


# =============================================================================
# Scheduler Tests
# =============================================================================

class TestSyncScheduler:
    """Tests for sync_scheduler.run_scheduler()."""

    @patch("src.workers.sync_scheduler._check_entitlement")
    @patch("src.workers.sync_scheduler._get_enabled_connections")
    @patch("src.ingestion.jobs.dispatcher.JobDispatcher")
    @patch("src.services.sync_plan_resolver.SyncPlanResolver")
    def test_dispatches_job_for_due_connection(
        self, MockResolver, MockDispatcher, mock_get_conns, mock_entitlement
    ):
        from src.workers.sync_scheduler import run_scheduler

        conn = _mock_connection(last_sync_at=None)  # Never synced = due
        mock_get_conns.return_value = [conn]
        mock_entitlement.return_value = True
        MockResolver.return_value.is_sync_due.return_value = True

        session = _mock_session()
        stats = run_scheduler(session)

        assert stats.jobs_dispatched == 1
        assert stats.connections_evaluated == 1
        MockDispatcher.return_value.dispatch.assert_called_once()

    @patch("src.workers.sync_scheduler._check_entitlement")
    @patch("src.workers.sync_scheduler._get_enabled_connections")
    @patch("src.services.sync_plan_resolver.SyncPlanResolver")
    def test_skips_connection_not_due(
        self, MockResolver, mock_get_conns, mock_entitlement
    ):
        from src.workers.sync_scheduler import run_scheduler

        conn = _mock_connection(
            last_sync_at=datetime.now(timezone.utc) - timedelta(minutes=10)
        )
        mock_get_conns.return_value = [conn]
        mock_entitlement.return_value = True
        MockResolver.return_value.is_sync_due.return_value = False

        session = _mock_session()
        stats = run_scheduler(session)

        assert stats.jobs_dispatched == 0
        assert stats.jobs_skipped_not_due == 1

    @patch("src.workers.sync_scheduler._check_entitlement")
    @patch("src.workers.sync_scheduler._get_enabled_connections")
    @patch("src.ingestion.jobs.dispatcher.JobDispatcher")
    @patch("src.services.sync_plan_resolver.SyncPlanResolver")
    def test_skips_connection_with_active_job(
        self, MockResolver, MockDispatcher, mock_get_conns, mock_entitlement
    ):
        from src.workers.sync_scheduler import run_scheduler
        from src.ingestion.jobs.dispatcher import JobIsolationError

        conn = _mock_connection(last_sync_at=None)
        mock_get_conns.return_value = [conn]
        mock_entitlement.return_value = True
        MockResolver.return_value.is_sync_due.return_value = True
        MockDispatcher.return_value.dispatch.side_effect = JobIsolationError(
            "Active job exists", existing_job_id="job-123"
        )

        session = _mock_session()
        stats = run_scheduler(session)

        assert stats.jobs_dispatched == 0
        assert stats.jobs_skipped_active == 1

    @patch("src.workers.sync_scheduler._check_entitlement")
    @patch("src.workers.sync_scheduler._get_enabled_connections")
    @patch("src.services.sync_plan_resolver.SyncPlanResolver")
    def test_skips_non_entitled_tenant(
        self, MockResolver, mock_get_conns, mock_entitlement
    ):
        from src.workers.sync_scheduler import run_scheduler

        conn = _mock_connection(last_sync_at=None)
        mock_get_conns.return_value = [conn]
        mock_entitlement.return_value = False
        MockResolver.return_value.is_sync_due.return_value = True

        session = _mock_session()
        stats = run_scheduler(session)

        assert stats.jobs_dispatched == 0
        assert stats.jobs_skipped_entitlement == 1

    @patch("src.workers.sync_scheduler._check_entitlement")
    @patch("src.workers.sync_scheduler._get_enabled_connections")
    @patch("src.services.sync_plan_resolver.SyncPlanResolver")
    def test_handles_unexpected_error_gracefully(
        self, MockResolver, mock_get_conns, mock_entitlement
    ):
        from src.workers.sync_scheduler import run_scheduler

        conn = _mock_connection(last_sync_at=None)
        mock_get_conns.return_value = [conn]
        mock_entitlement.return_value = True
        MockResolver.return_value.is_sync_due.side_effect = RuntimeError("DB error")

        session = _mock_session()
        stats = run_scheduler(session)

        assert stats.errors == 1
        assert stats.jobs_dispatched == 0
        session.rollback.assert_called()

    @patch("src.workers.sync_scheduler._check_entitlement")
    @patch("src.workers.sync_scheduler._get_enabled_connections")
    @patch("src.ingestion.jobs.dispatcher.JobDispatcher")
    @patch("src.services.sync_plan_resolver.SyncPlanResolver")
    def test_multiple_connections_mixed_results(
        self, MockResolver, MockDispatcher, mock_get_conns, mock_entitlement
    ):
        """Test scheduler handles mix of due, not-due, and active connections."""
        from src.workers.sync_scheduler import run_scheduler
        from src.ingestion.jobs.dispatcher import JobIsolationError

        conn_due = _mock_connection(
            tenant_id=TENANT_ID, connection_id="conn-1", last_sync_at=None,
        )
        conn_not_due = _mock_connection(
            tenant_id=TENANT_ID, connection_id="conn-2",
            last_sync_at=datetime.now(timezone.utc),
        )
        conn_active = _mock_connection(
            tenant_id=TENANT_ID_2, connection_id="conn-3", last_sync_at=None,
        )

        mock_get_conns.return_value = [conn_due, conn_not_due, conn_active]
        mock_entitlement.return_value = True

        def _is_sync_due(tenant_id, last_sync_at):
            return last_sync_at is None

        MockResolver.return_value.is_sync_due.side_effect = _is_sync_due

        dispatch_call_count = 0

        def _dispatch_side_effect(**kwargs):
            nonlocal dispatch_call_count
            dispatch_call_count += 1
            if dispatch_call_count == 2:
                raise JobIsolationError("Active job", existing_job_id="j-99")
            return MagicMock()

        MockDispatcher.return_value.dispatch.side_effect = _dispatch_side_effect

        session = _mock_session()
        stats = run_scheduler(session)

        assert stats.connections_evaluated == 3
        assert stats.jobs_dispatched == 1
        assert stats.jobs_skipped_not_due == 1
        assert stats.jobs_skipped_active == 1

    @patch("src.workers.sync_scheduler._check_entitlement")
    @patch("src.workers.sync_scheduler._get_enabled_connections")
    def test_empty_connections_returns_clean_stats(
        self, mock_get_conns, mock_entitlement
    ):
        from src.workers.sync_scheduler import run_scheduler

        mock_get_conns.return_value = []
        session = _mock_session()
        stats = run_scheduler(session)

        assert stats.connections_evaluated == 0
        assert stats.jobs_dispatched == 0
        assert stats.errors == 0


# =============================================================================
# Executor Tests
# =============================================================================

class TestSyncExecutor:
    """Tests for sync_executor.run_cycle()."""

    @pytest.mark.asyncio
    @patch("src.workers.sync_executor._update_last_sync_timestamps")
    @patch("src.ingestion.jobs.runner.JobRunner")
    async def test_cycle_processes_queued_and_retry_jobs(
        self, MockRunner, mock_update_ts
    ):
        from src.workers.sync_executor import run_cycle, ExecutorStats

        session = _mock_session()
        stats = ExecutorStats()

        async def _process_queued(limit=10):
            return 3

        async def _process_retry(limit=10):
            return 1

        runner_instance = MockRunner.return_value
        runner_instance.process_queued_jobs = _process_queued
        runner_instance.process_retry_jobs = _process_retry

        await run_cycle(session, stats)

        assert stats.total_queued_processed == 3
        assert stats.total_retry_processed == 1
        assert stats.cycles == 1

    @pytest.mark.asyncio
    @patch("src.ingestion.jobs.runner.JobRunner")
    async def test_cycle_handles_error_gracefully(self, MockRunner):
        from src.workers.sync_executor import run_cycle, ExecutorStats

        session = _mock_session()
        stats = ExecutorStats()

        async def _process_queued_fail(limit=10):
            raise RuntimeError("DB connection lost")

        runner_instance = MockRunner.return_value
        runner_instance.process_queued_jobs = _process_queued_fail

        await run_cycle(session, stats)

        assert stats.total_errors == 1
        session.rollback.assert_called()

    def test_executor_stats_to_dict(self):
        from src.workers.sync_executor import ExecutorStats

        stats = ExecutorStats()
        stats.cycles = 5
        stats.total_queued_processed = 10
        stats.total_retry_processed = 2
        stats.total_errors = 1

        result = stats.to_dict()
        assert result["cycles"] == 5
        assert result["total_queued_processed"] == 10
        assert result["total_retry_processed"] == 2
        assert result["total_errors"] == 1
        assert "uptime_seconds" in result


# =============================================================================
# Scheduler Stats Tests
# =============================================================================

class TestSchedulerStats:
    """Tests for SchedulerStats dataclass."""

    def test_stats_to_dict(self):
        from src.workers.sync_scheduler import SchedulerStats

        stats = SchedulerStats()
        stats.connections_evaluated = 10
        stats.jobs_dispatched = 5
        stats.jobs_skipped_not_due = 3
        stats.jobs_skipped_active = 1
        stats.jobs_skipped_entitlement = 1
        stats.errors = 0

        result = stats.to_dict()
        assert result["connections_evaluated"] == 10
        assert result["jobs_dispatched"] == 5
        assert result["jobs_skipped_not_due"] == 3
        assert result["jobs_skipped_active"] == 1
        assert result["jobs_skipped_entitlement"] == 1
        assert result["errors"] == 0
        assert "duration_seconds" in result


# =============================================================================
# Plan SLA Enforcement Tests (Security)
# =============================================================================

class TestPlanSLAEnforcement:
    """Verify plan limits are respected strictly."""

    def test_free_cannot_sync_more_than_daily(self):
        """Free tier must wait 24h between syncs."""
        session = _mock_session()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = _mock_plan("free")
        session.execute.return_value = mock_result

        resolver = SyncPlanResolver(session)

        # 23 hours ago → NOT due
        recent = datetime.now(timezone.utc) - timedelta(hours=23)
        assert resolver.is_sync_due(TENANT_ID, last_sync_at=recent) is False

        # 24 hours + 1 minute ago → due
        old = datetime.now(timezone.utc) - timedelta(hours=24, minutes=1)
        assert resolver.is_sync_due(TENANT_ID, last_sync_at=old) is True

    def test_growth_cannot_sync_more_than_six_hourly(self):
        """Growth tier must wait 6h between syncs."""
        session = _mock_session()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = _mock_plan("growth")
        session.execute.return_value = mock_result

        resolver = SyncPlanResolver(session)

        # 5 hours 59 minutes ago → NOT due
        recent = datetime.now(timezone.utc) - timedelta(hours=5, minutes=59)
        assert resolver.is_sync_due(TENANT_ID, last_sync_at=recent) is False

        # 6 hours + 1 minute ago → due
        old = datetime.now(timezone.utc) - timedelta(hours=6, minutes=1)
        assert resolver.is_sync_due(TENANT_ID, last_sync_at=old) is True

    def test_enterprise_can_sync_hourly(self):
        """Enterprise tier can sync every hour."""
        session = _mock_session()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = _mock_plan("enterprise")
        session.execute.return_value = mock_result

        resolver = SyncPlanResolver(session)

        # 59 minutes ago → NOT due
        recent = datetime.now(timezone.utc) - timedelta(minutes=59)
        assert resolver.is_sync_due(TENANT_ID, last_sync_at=recent) is False

        # 61 minutes ago → due
        old = datetime.now(timezone.utc) - timedelta(minutes=61)
        assert resolver.is_sync_due(TENANT_ID, last_sync_at=old) is True
