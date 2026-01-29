"""
Unit tests for audit retention job.

Story 10.4 - Retention Enforcement
"""

import pytest
from datetime import datetime, timezone, timedelta
from unittest.mock import MagicMock, patch, call

from src.config.retention import get_retention_days, PLAN_RETENTION_DEFAULTS
from src.jobs.audit_retention_job import AuditRetentionJob


class TestRetentionConfig:
    """Test suite for retention configuration."""

    def test_get_retention_days_free_plan(self):
        """Free plan should have 30 day retention."""
        assert get_retention_days("free") == 30

    def test_get_retention_days_starter_plan(self):
        """Starter plan should have 90 day retention."""
        assert get_retention_days("starter") == 90

    def test_get_retention_days_professional_plan(self):
        """Professional plan should have 180 day retention."""
        assert get_retention_days("professional") == 180

    def test_get_retention_days_enterprise_plan(self):
        """Enterprise plan should have 365 day retention."""
        assert get_retention_days("enterprise") == 365

    def test_get_retention_days_unknown_plan_uses_default(self):
        """Unknown plan should use default 90 day retention."""
        assert get_retention_days("unknown_plan") == 90

    def test_retention_minimum_enforced(self):
        """Retention should never be less than 30 days."""
        # Even if somehow plan returns less, minimum is enforced
        with patch.dict(PLAN_RETENTION_DEFAULTS, {"test": 10}):
            assert get_retention_days("test") == 30


class TestAuditRetentionJob:
    """Test suite for AuditRetentionJob."""

    def test_dry_run_does_not_delete(self):
        """Dry run should count but not delete records."""
        mock_db = MagicMock()
        # Mock count query
        mock_db.execute.return_value.scalar.return_value = 100

        job = AuditRetentionJob(mock_db, dry_run=True)

        cutoff = datetime.now(timezone.utc) - timedelta(days=90)
        deleted = job.delete_expired_logs("tenant-1", cutoff)

        assert deleted == 100
        # Should not execute ALTER TABLE for trigger disable
        calls_str = str(mock_db.execute.call_args_list)
        assert "DISABLE TRIGGER" not in calls_str

    def test_process_tenant_uses_correct_retention(self):
        """Should use plan-specific retention period."""
        mock_db = MagicMock()
        mock_db.execute.return_value.scalar.return_value = 0

        job = AuditRetentionJob(mock_db, dry_run=True)

        # Mock get_tenant_plan to return enterprise
        with patch.object(job, "get_tenant_plan", return_value="enterprise"):
            with patch.object(job, "delete_expired_logs") as mock_delete:
                mock_delete.return_value = 0
                job.process_tenant("tenant-1")

                # Verify cutoff is approximately 365 days ago
                call_args = mock_delete.call_args
                cutoff_date = call_args[0][1]
                expected_cutoff = datetime.now(timezone.utc) - timedelta(days=365)
                # Allow 1 second tolerance
                assert abs((cutoff_date - expected_cutoff).total_seconds()) < 1

    def test_stats_accumulated_across_tenants(self):
        """Stats should accumulate across all processed tenants."""
        mock_db = MagicMock()

        # Mock distinct tenants query
        mock_execute = MagicMock()
        mock_execute.__iter__ = MagicMock(
            return_value=iter([("tenant-1",), ("tenant-2",)])
        )
        mock_db.execute.return_value = mock_execute
        mock_db.execute.return_value.scalar.return_value = 50

        job = AuditRetentionJob(mock_db, dry_run=True)

        # Mock process_tenant to return 50 each
        with patch.object(job, "process_tenant", return_value=50):
            with patch.object(job, "get_distinct_tenants", return_value=["tenant-1", "tenant-2"]):
                with patch("src.jobs.audit_retention_job.log_system_audit_event_sync"):
                    stats = job.run()

        assert stats["tenants_processed"] == 2
        assert stats["total_deleted"] == 100  # 50 * 2

    def test_job_logs_start_and_completion(self):
        """Job should log audit events for start and completion."""
        mock_db = MagicMock()

        job = AuditRetentionJob(mock_db, dry_run=True)

        with patch.object(job, "get_distinct_tenants", return_value=[]):
            with patch("src.jobs.audit_retention_job.log_system_audit_event_sync") as mock_log:
                job.run()

                # Should have logged start and completion
                assert mock_log.call_count == 2
                call_actions = [c[1]["action"].value for c in mock_log.call_args_list]
                assert "audit.retention.started" in call_actions
                assert "audit.retention.completed" in call_actions

    def test_error_handling_logs_failure(self):
        """Errors should be logged and alert sent."""
        mock_db = MagicMock()

        job = AuditRetentionJob(mock_db, dry_run=True)

        with patch.object(job, "get_distinct_tenants", side_effect=Exception("DB error")):
            with patch("src.jobs.audit_retention_job.log_system_audit_event_sync") as mock_log:
                with patch("src.jobs.audit_retention_job.get_audit_alert_manager") as mock_alert:
                    mock_alert_manager = MagicMock()
                    mock_alert.return_value = mock_alert_manager

                    with pytest.raises(Exception, match="DB error"):
                        job.run()

                    # Should have logged failure
                    call_actions = [c[1]["action"].value for c in mock_log.call_args_list]
                    assert "audit.retention.failed" in call_actions

                    # Should have sent alert
                    mock_alert_manager.alert_retention_job_failed.assert_called_once()

    def test_tenant_error_does_not_stop_job(self):
        """Error processing one tenant should not stop the entire job."""
        mock_db = MagicMock()

        job = AuditRetentionJob(mock_db, dry_run=True)

        def process_tenant_side_effect(tenant_id):
            if tenant_id == "tenant-1":
                raise Exception("Tenant error")
            return 50

        with patch.object(job, "get_distinct_tenants", return_value=["tenant-1", "tenant-2"]):
            with patch.object(job, "process_tenant", side_effect=process_tenant_side_effect):
                with patch("src.jobs.audit_retention_job.log_system_audit_event_sync"):
                    stats = job.run()

        # Should have processed both tenants
        assert stats["tenants_processed"] == 2
        # Only tenant-2 contributed deletions
        assert stats["total_deleted"] == 50
        # Error should be recorded
        assert len(stats["errors"]) == 1


class TestAuditRetentionJobIntegration:
    """Integration-style tests for retention job."""

    def test_get_tenant_plan_with_subscription(self):
        """Should get plan from active subscription."""
        mock_db = MagicMock()

        # Mock subscription query
        mock_subscription = MagicMock()
        mock_subscription.plan_id = "plan_enterprise"
        mock_db.query.return_value.filter.return_value.first.return_value = mock_subscription

        # Mock plan query
        mock_plan = MagicMock()
        mock_plan.name = "enterprise"

        def query_side_effect(model):
            mock_result = MagicMock()
            if model.__name__ == "Subscription":
                mock_result.filter.return_value.first.return_value = mock_subscription
            elif model.__name__ == "Plan":
                mock_result.filter.return_value.first.return_value = mock_plan
            return mock_result

        mock_db.query.side_effect = query_side_effect

        job = AuditRetentionJob(mock_db, dry_run=True)
        plan = job.get_tenant_plan("tenant-1")

        assert plan == "enterprise"

    def test_get_tenant_plan_without_subscription(self):
        """Should return default plan when no subscription exists."""
        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.first.return_value = None

        job = AuditRetentionJob(mock_db, dry_run=True)
        plan = job.get_tenant_plan("tenant-1")

        assert plan == "professional"  # default

    def test_delete_enables_and_disables_trigger(self):
        """Should disable trigger before delete and re-enable after."""
        mock_db = MagicMock()
        mock_db.execute.return_value.rowcount = 0  # No records deleted

        job = AuditRetentionJob(mock_db, dry_run=False)

        with patch.object(job, "count_expired_logs", return_value=0):
            cutoff = datetime.now(timezone.utc) - timedelta(days=90)
            job.delete_expired_logs("tenant-1", cutoff)

        # Check that DISABLE and ENABLE TRIGGER were called
        call_args_list = [str(c) for c in mock_db.execute.call_args_list]
        disable_called = any("DISABLE TRIGGER" in c for c in call_args_list)
        enable_called = any("ENABLE TRIGGER" in c for c in call_args_list)

        assert disable_called, "Should disable trigger before deletion"
        assert enable_called, "Should enable trigger after deletion"

    def test_delete_records_metric(self):
        """Should record metric when records are deleted."""
        mock_db = MagicMock()
        mock_db.execute.return_value.rowcount = 50

        job = AuditRetentionJob(mock_db, dry_run=False)

        with patch.object(job.metrics, "record_retention_deletion") as mock_metric:
            # Return 0 on second iteration to break loop
            mock_db.execute.return_value.rowcount = 50

            def execute_side_effect(*args, **kwargs):
                result = MagicMock()
                if "DELETE" in str(args[0]):
                    # First call returns 50, second returns 0
                    result.rowcount = 50 if mock_metric.call_count == 0 else 0
                return result

            mock_db.execute.side_effect = execute_side_effect

            cutoff = datetime.now(timezone.utc) - timedelta(days=90)
            deleted = job.delete_expired_logs("tenant-1", cutoff)

            mock_metric.assert_called_with(50, "tenant-1")
