"""
Tests for GA Audit Log Retention Job.

ACCEPTANCE CRITERIA:
- Hard-deletes logs older than 90 days
- Batch deletion to avoid long transactions
- Dry-run mode (default)
- Immutability trigger disable/enable lifecycle
- No legal hold support (GA scope)
"""

import uuid
import pytest
from datetime import datetime, timezone, timedelta
from unittest.mock import Mock, MagicMock, patch, call

from src.workers.audit_retention_job import (
    GAAuditRetentionJob,
    RETENTION_DAYS,
    BATCH_SIZE,
)
from src.models.audit_log import GAAuditLog


# ============================================================================
# FIXTURES
# ============================================================================

@pytest.fixture
def mock_db():
    return MagicMock()


@pytest.fixture
def job(mock_db):
    """Create a retention job in dry-run mode (default)."""
    return GAAuditRetentionJob(mock_db)


@pytest.fixture
def live_job(mock_db):
    """Create a retention job with dry-run disabled."""
    j = GAAuditRetentionJob(mock_db)
    j.dry_run = False
    return j


# ============================================================================
# TEST SUITE: CONFIGURATION
# ============================================================================

class TestConfiguration:
    """Test retention job configuration."""

    def test_default_retention_is_90_days(self):
        """Default retention period is 90 days."""
        assert RETENTION_DAYS == 90

    def test_job_retention_days(self, job):
        """Job instance has correct retention period."""
        assert job.retention_days == 90

    def test_default_batch_size(self):
        """Default batch size is 1000."""
        assert BATCH_SIZE == 1000

    def test_default_is_dry_run(self, job):
        """Default mode is dry-run."""
        assert job.dry_run is True


# ============================================================================
# TEST SUITE: DRY RUN MODE
# ============================================================================

class TestDryRunMode:
    """Test dry-run mode (no actual deletions)."""

    def test_dry_run_counts_records(self, job, mock_db):
        """Dry run counts records that would be deleted."""
        mock_query = MagicMock()
        mock_query.filter.return_value = mock_query
        mock_query.count.return_value = 150
        mock_db.query.return_value = mock_query

        result = job.execute()

        assert result["dry_run"] is True
        assert result["would_delete"] == 150
        assert "cutoff" in result

    def test_dry_run_does_not_delete(self, job, mock_db):
        """Dry run does not perform any deletions."""
        mock_query = MagicMock()
        mock_query.filter.return_value = mock_query
        mock_query.count.return_value = 50
        mock_db.query.return_value = mock_query

        job.execute()

        # Should NOT call delete
        mock_query.delete.assert_not_called()
        mock_db.commit.assert_not_called()


# ============================================================================
# TEST SUITE: LIVE DELETION
# ============================================================================

class TestLiveDeletion:
    """Test actual deletion (dry-run disabled)."""

    def test_deletes_expired_records_in_batches(self, live_job, mock_db):
        """Deletes records in batches."""
        mock_query = MagicMock()
        mock_db.query.return_value = mock_query

        # First batch: 3 records, second batch: empty
        mock_query.filter.return_value = mock_query
        mock_query.limit.return_value = mock_query
        mock_query.all.side_effect = [
            [("id-1",), ("id-2",), ("id-3",)],
            [],
        ]
        mock_query.delete.return_value = 3

        result = live_job.execute()

        assert result["dry_run"] is False
        assert result["total_deleted"] == 3
        assert result["batches"] == 1

    def test_handles_empty_table(self, live_job, mock_db):
        """Handles case where no records need deletion."""
        mock_query = MagicMock()
        mock_db.query.return_value = mock_query
        mock_query.filter.return_value = mock_query
        mock_query.limit.return_value = mock_query
        mock_query.all.return_value = []

        result = live_job.execute()

        assert result["dry_run"] is False
        assert result["total_deleted"] == 0
        assert result["batches"] == 0


# ============================================================================
# TEST SUITE: IMMUTABILITY TRIGGER MANAGEMENT
# ============================================================================

class TestTriggerManagement:
    """Test immutability trigger disable/enable lifecycle."""

    def test_trigger_disabled_before_deletion(self, live_job, mock_db):
        """Trigger is disabled before deletion starts."""
        mock_query = MagicMock()
        mock_db.query.return_value = mock_query
        mock_query.filter.return_value = mock_query
        mock_query.limit.return_value = mock_query
        mock_query.all.return_value = []

        live_job.execute()

        # Should have called execute with DISABLE
        calls = [str(c) for c in mock_db.execute.call_args_list]
        assert any("DISABLE" in c for c in calls)

    def test_trigger_re_enabled_after_deletion(self, live_job, mock_db):
        """Trigger is re-enabled after deletion completes."""
        mock_query = MagicMock()
        mock_db.query.return_value = mock_query
        mock_query.filter.return_value = mock_query
        mock_query.limit.return_value = mock_query
        mock_query.all.return_value = []

        live_job.execute()

        # Should have called execute with ENABLE
        calls = [str(c) for c in mock_db.execute.call_args_list]
        assert any("ENABLE" in c for c in calls)

    def test_trigger_re_enabled_on_error(self, live_job, mock_db):
        """Trigger is re-enabled even if deletion fails."""
        mock_query = MagicMock()
        mock_db.query.return_value = mock_query
        mock_query.filter.return_value = mock_query
        mock_query.limit.return_value = mock_query
        mock_query.all.side_effect = Exception("DB error")

        # Should not crash
        with pytest.raises(Exception, match="DB error"):
            live_job.execute()

        # Trigger should still be re-enabled
        calls = [str(c) for c in mock_db.execute.call_args_list]
        assert any("ENABLE" in c for c in calls)


# ============================================================================
# TEST SUITE: CUTOFF CALCULATION
# ============================================================================

class TestCutoffCalculation:
    """Test that the correct cutoff date is used."""

    def test_cutoff_is_90_days_ago(self, job, mock_db):
        """Cutoff date is 90 days before execution time."""
        mock_query = MagicMock()
        mock_query.filter.return_value = mock_query
        mock_query.count.return_value = 0
        mock_db.query.return_value = mock_query

        result = job.execute()

        cutoff = datetime.fromisoformat(result["cutoff"])
        expected_cutoff = datetime.now(timezone.utc) - timedelta(days=90)

        # Should be within 5 seconds of expected
        diff = abs((cutoff - expected_cutoff).total_seconds())
        assert diff < 5


# ============================================================================
# TEST SUITE: RESULT FORMAT
# ============================================================================

class TestResultFormat:
    """Test execution result format."""

    def test_dry_run_result_format(self, job, mock_db):
        """Dry run result has correct fields."""
        mock_query = MagicMock()
        mock_query.filter.return_value = mock_query
        mock_query.count.return_value = 0
        mock_db.query.return_value = mock_query

        result = job.execute()

        assert "dry_run" in result
        assert "would_delete" in result
        assert "cutoff" in result
        assert "elapsed_seconds" in result

    def test_live_result_format(self, live_job, mock_db):
        """Live result has correct fields."""
        mock_query = MagicMock()
        mock_db.query.return_value = mock_query
        mock_query.filter.return_value = mock_query
        mock_query.limit.return_value = mock_query
        mock_query.all.return_value = []

        result = live_job.execute()

        assert "dry_run" in result
        assert "total_deleted" in result
        assert "batches" in result
        assert "cutoff" in result
        assert "elapsed_seconds" in result
        assert result["dry_run"] is False
