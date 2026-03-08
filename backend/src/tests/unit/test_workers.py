"""
Unit tests for worker modules:
- BackfillWorker (backfill_worker.py)
- dbt_runner (dbt_runner.py)
- CredentialCleanupJob (credential_cleanup_job.py)
- AccessRevocationJob (access_revocation_job.py)
"""

import asyncio
from datetime import datetime, timezone, timedelta
from unittest.mock import Mock, MagicMock, AsyncMock, patch

import pytest

from src.workers.backfill_worker import WorkerStats, run_cycle
from src.workers.dbt_runner import run_dbt_incremental
from src.workers.credential_cleanup_job import (
    CleanupStats,
    count_eligible_credentials,
    run_cleanup,
)
from src.workers.access_revocation_job import run_cycle as revocation_run_cycle


# ---------------------------------------------------------------------------
# BackfillWorker — WorkerStats
# ---------------------------------------------------------------------------


class TestWorkerStats:
    """Tests for WorkerStats dataclass."""

    def test_initial_values(self):
        stats = WorkerStats()
        assert stats.cycles == 0
        assert stats.requests_created == 0
        assert stats.jobs_executed == 0
        assert stats.jobs_recovered == 0
        assert stats.errors == 0
        assert isinstance(stats.started_at, datetime)

    def test_to_dict_contains_uptime(self):
        started = datetime.now(timezone.utc) - timedelta(seconds=10)
        stats = WorkerStats(started_at=started)
        d = stats.to_dict()

        assert "uptime_seconds" in d
        assert d["uptime_seconds"] >= 10.0
        assert d["cycles"] == 0
        assert d["requests_created"] == 0
        assert d["jobs_executed"] == 0
        assert d["jobs_recovered"] == 0
        assert d["errors"] == 0

    def test_to_dict_reflects_mutations(self):
        stats = WorkerStats()
        stats.cycles = 5
        stats.jobs_executed = 12
        stats.errors = 2
        d = stats.to_dict()
        assert d["cycles"] == 5
        assert d["jobs_executed"] == 12
        assert d["errors"] == 2


# ---------------------------------------------------------------------------
# BackfillWorker — run_cycle
# ---------------------------------------------------------------------------


class TestBackfillRunCycle:
    """Tests for backfill_worker.run_cycle."""

    @pytest.fixture
    def mock_db(self):
        return MagicMock()

    @pytest.fixture
    def stats(self):
        return WorkerStats()

    @pytest.mark.asyncio
    async def test_run_cycle_full_happy_path(self, mock_db, stats):
        """Recovers stale jobs, creates chunk jobs, executes queued jobs."""
        mock_request = Mock(tenant_id="t1")
        mock_job = Mock(tenant_id="t1")

        with patch(
            "src.services.backfill_executor.BackfillExecutor"
        ) as MockExecutor:
            executor = MockExecutor.return_value
            executor.recover_stale_jobs.return_value = 2
            executor.find_approved_requests.return_value = [mock_request]
            executor.get_tenants_with_running_jobs.return_value = set()
            executor.pick_next_job.side_effect = [mock_job, None]
            executor.execute_job = AsyncMock()

            await run_cycle(mock_db, stats)

        assert stats.jobs_recovered == 2
        assert stats.requests_created == 1
        assert stats.jobs_executed == 1
        assert stats.cycles == 1
        assert stats.errors == 0
        executor.create_jobs_for_request.assert_called_once_with(mock_request)
        executor.execute_job.assert_awaited_once_with(mock_job)

    @pytest.mark.asyncio
    async def test_run_cycle_updates_stats(self, mock_db, stats):
        """Stats are correctly incremented across the cycle."""
        with patch(
            "src.services.backfill_executor.BackfillExecutor"
        ) as MockExecutor:
            executor = MockExecutor.return_value
            executor.recover_stale_jobs.return_value = 0
            executor.find_approved_requests.return_value = []
            executor.get_tenants_with_running_jobs.return_value = set()
            executor.pick_next_job.return_value = None

            await run_cycle(mock_db, stats)

        assert stats.cycles == 1
        assert stats.jobs_recovered == 0
        assert stats.requests_created == 0
        assert stats.jobs_executed == 0

    @pytest.mark.asyncio
    async def test_run_cycle_exception_increments_errors(self, mock_db, stats):
        """On exception, error count increments and session rolls back."""
        with patch(
            "src.services.backfill_executor.BackfillExecutor"
        ) as MockExecutor:
            executor = MockExecutor.return_value
            executor.recover_stale_jobs.side_effect = RuntimeError("db down")

            await run_cycle(mock_db, stats)

        assert stats.errors == 1
        mock_db.rollback.assert_called_once()
        # cycles should NOT increment on error (exception before stats.cycles += 1)
        assert stats.cycles == 0

    @pytest.mark.asyncio
    async def test_run_cycle_respects_max_jobs_per_cycle(self, mock_db, stats):
        """At most MAX_JOBS_PER_CYCLE jobs are executed."""
        jobs = [Mock(tenant_id=f"t{i}") for i in range(5)]

        with patch(
            "src.services.backfill_executor.BackfillExecutor"
        ) as MockExecutor, patch(
            "src.workers.backfill_worker.MAX_JOBS_PER_CYCLE", 2
        ):
            executor = MockExecutor.return_value
            executor.recover_stale_jobs.return_value = 0
            executor.find_approved_requests.return_value = []
            executor.get_tenants_with_running_jobs.return_value = set()
            # Provide more jobs than the limit
            executor.pick_next_job.side_effect = jobs
            executor.execute_job = AsyncMock()

            await run_cycle(mock_db, stats)

        assert stats.jobs_executed == 2
        assert executor.execute_job.await_count == 2

    @pytest.mark.asyncio
    async def test_run_cycle_rate_limits_per_tenant(self, mock_db, stats):
        """Tenant with a running job is excluded from pick_next_job."""
        job1 = Mock(tenant_id="t1")

        with patch(
            "src.services.backfill_executor.BackfillExecutor"
        ) as MockExecutor, patch(
            "src.workers.backfill_worker.MAX_JOBS_PER_CYCLE", 3
        ):
            executor = MockExecutor.return_value
            executor.recover_stale_jobs.return_value = 0
            executor.find_approved_requests.return_value = []
            executor.get_tenants_with_running_jobs.return_value = {"busy_t"}
            # First call returns a job, second returns None
            executor.pick_next_job.side_effect = [job1, None]
            executor.execute_job = AsyncMock()

            await run_cycle(mock_db, stats)

        # After executing job1 (tenant_id="t1"), busy_tenants set is mutated
        # in-place to include "t1". Since it's the same set object, the final
        # state should contain both "busy_t" and "t1".
        calls = executor.pick_next_job.call_args_list
        assert len(calls) == 2
        # The set is mutated in-place, so both calls see the final state
        final_exclusions = calls[1].kwargs["exclude_tenant_ids"]
        assert "t1" in final_exclusions
        assert "busy_t" in final_exclusions


# ---------------------------------------------------------------------------
# dbt_runner — run_dbt_incremental
# ---------------------------------------------------------------------------


class TestDbtRunner:
    """Tests for dbt_runner.run_dbt_incremental."""

    @pytest.mark.asyncio
    async def test_success_returns_true(self):
        """returncode=0 returns True."""
        mock_process = AsyncMock()
        mock_process.communicate.return_value = (b"ok", b"")
        mock_process.returncode = 0

        with patch("asyncio.create_subprocess_exec", return_value=mock_process):
            result = await run_dbt_incremental()

        assert result is True

    @pytest.mark.asyncio
    async def test_failure_returns_false(self):
        """returncode!=0 returns False."""
        mock_process = AsyncMock()
        mock_process.communicate.return_value = (b"", b"error")
        mock_process.returncode = 1

        with patch("asyncio.create_subprocess_exec", return_value=mock_process):
            result = await run_dbt_incremental()

        assert result is False

    @pytest.mark.asyncio
    async def test_exception_returns_false(self):
        """Exception during subprocess execution returns False."""
        with patch(
            "asyncio.create_subprocess_exec",
            side_effect=OSError("command not found"),
        ):
            result = await run_dbt_incremental()

        assert result is False

    @pytest.mark.asyncio
    async def test_skips_when_lock_held(self):
        """Returns False immediately when lock is already held."""
        from src.workers.dbt_runner import _dbt_lock

        # Acquire the lock externally so the function sees it as locked
        await _dbt_lock.acquire()
        try:
            result = await run_dbt_incremental()
            assert result is False
        finally:
            _dbt_lock.release()


# ---------------------------------------------------------------------------
# CredentialCleanupJob — CleanupStats
# ---------------------------------------------------------------------------


class TestCleanupStats:
    """Tests for CleanupStats dataclass."""

    def test_to_dict_with_duration(self):
        started = datetime(2025, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
        completed = datetime(2025, 1, 1, 0, 0, 30, tzinfo=timezone.utc)
        stats = CleanupStats(
            started_at=started,
            completed_at=completed,
            credentials_eligible=10,
            credentials_purged=8,
            dry_run=False,
        )
        d = stats.to_dict()

        assert d["duration_seconds"] == 30.0
        assert d["credentials_eligible"] == 10
        assert d["credentials_purged"] == 8
        assert d["dry_run"] is False
        assert d["error_count"] == 0
        assert d["started_at"] == started.isoformat()
        assert d["completed_at"] == completed.isoformat()

    def test_to_dict_no_completed(self):
        stats = CleanupStats()
        d = stats.to_dict()
        assert d["completed_at"] is None
        assert d["duration_seconds"] is None


# ---------------------------------------------------------------------------
# CredentialCleanupJob — count_eligible_credentials
# ---------------------------------------------------------------------------


class TestCountEligibleCredentials:
    """Tests for count_eligible_credentials."""

    def test_returns_count_from_query(self):
        mock_session = MagicMock()
        mock_session.execute.return_value.scalar.return_value = 5

        with patch(
            "src.workers.credential_cleanup_job.ConnectorCredential",
            create=True,
        ):
            result = count_eligible_credentials(mock_session)

        assert result == 5
        mock_session.execute.assert_called_once()

    def test_returns_zero_when_none(self):
        mock_session = MagicMock()
        mock_session.execute.return_value.scalar.return_value = None

        with patch(
            "src.workers.credential_cleanup_job.ConnectorCredential",
            create=True,
        ):
            result = count_eligible_credentials(mock_session)

        assert result == 0


# ---------------------------------------------------------------------------
# CredentialCleanupJob — run_cleanup
# ---------------------------------------------------------------------------


class TestRunCleanup:
    """Tests for run_cleanup."""

    @pytest.fixture
    def mock_db(self):
        return MagicMock()

    @patch("src.workers.credential_cleanup_job._log_cleanup_audit")
    @patch("src.workers.credential_cleanup_job.count_eligible_credentials")
    def test_no_eligible_credentials_returns_early(
        self, mock_count, mock_audit, mock_db
    ):
        mock_count.return_value = 0

        stats = run_cleanup(mock_db, dry_run=False)

        assert stats.credentials_eligible == 0
        assert stats.credentials_purged == 0
        assert stats.completed_at is not None

    @patch("src.workers.credential_cleanup_job._log_cleanup_audit")
    @patch("src.workers.credential_cleanup_job.count_eligible_credentials")
    def test_dry_run_counts_but_does_not_delete(
        self, mock_count, mock_audit, mock_db
    ):
        mock_count.return_value = 7

        stats = run_cleanup(mock_db, dry_run=True)

        assert stats.credentials_eligible == 7
        assert stats.credentials_purged == 0
        assert stats.dry_run is True
        assert stats.completed_at is not None

    @patch("src.workers.credential_cleanup_job._log_cleanup_audit")
    @patch("src.workers.credential_cleanup_job.count_eligible_credentials")
    def test_real_mode_delegates_to_credential_vault(
        self, mock_count, mock_audit, mock_db
    ):
        mock_count.return_value = 5

        with patch(
            "src.services.credential_vault.CredentialVault"
        ) as MockVault:
            MockVault.purge_expired.return_value = 4

            stats = run_cleanup(mock_db, dry_run=False)

        assert stats.credentials_eligible == 5
        assert stats.credentials_purged == 4
        assert stats.dry_run is False
        MockVault.purge_expired.assert_called_once_with(mock_db)

    @patch("src.workers.credential_cleanup_job._log_cleanup_audit")
    @patch("src.workers.credential_cleanup_job.count_eligible_credentials")
    def test_exception_handling(self, mock_count, mock_audit, mock_db):
        mock_count.side_effect = RuntimeError("db exploded")

        with pytest.raises(RuntimeError, match="db exploded"):
            run_cleanup(mock_db, dry_run=False)


# ---------------------------------------------------------------------------
# AccessRevocationJob — run_cycle
# ---------------------------------------------------------------------------


class TestAccessRevocationRunCycle:
    """Tests for access_revocation_job.run_cycle."""

    @patch("src.workers.access_revocation_job.get_db_session_sync")
    def test_calls_service_and_commits(self, mock_get_db):
        mock_db = MagicMock()
        mock_get_db.return_value = iter([mock_db])

        mock_revocations = [Mock(), Mock(), Mock()]

        with patch(
            "src.services.access_revocation_service.AccessRevocationService"
        ) as MockService:
            MockService.return_value.enforce_expired_revocations.return_value = (
                mock_revocations
            )

            result = revocation_run_cycle()

        assert result == 3
        mock_db.commit.assert_called_once()
        mock_db.close.assert_called_once()

    @patch("src.workers.access_revocation_job.get_db_session_sync")
    def test_exception_rolls_back_and_returns_zero(self, mock_get_db):
        mock_db = MagicMock()
        mock_get_db.return_value = iter([mock_db])

        with patch(
            "src.services.access_revocation_service.AccessRevocationService"
        ) as MockService:
            MockService.return_value.enforce_expired_revocations.side_effect = (
                RuntimeError("fail")
            )

            result = revocation_run_cycle()

        assert result == 0
        mock_db.rollback.assert_called_once()
        mock_db.close.assert_called_once()

    @patch("src.workers.access_revocation_job.get_db_session_sync")
    def test_returns_count_of_enforced(self, mock_get_db):
        mock_db = MagicMock()
        mock_get_db.return_value = iter([mock_db])

        with patch(
            "src.services.access_revocation_service.AccessRevocationService"
        ) as MockService:
            MockService.return_value.enforce_expired_revocations.return_value = []

            result = revocation_run_cycle()

        assert result == 0
        mock_db.commit.assert_called_once()
