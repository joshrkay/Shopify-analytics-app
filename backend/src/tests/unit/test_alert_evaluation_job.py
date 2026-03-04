"""
Unit tests for AlertEvaluationWorker.

Layer 1 — Tests the background job with mocked DB.
If these fail, the bug is in tenant iteration or error isolation.

Tests cover:
- run() iterates distinct tenants and evaluates rules per tenant
- Per-tenant error isolation
- Empty tenant list returns zero stats
- DB query failure returns zero stats
"""

from unittest.mock import MagicMock, Mock, patch

import pytest

from src.jobs.alert_evaluation_job import AlertEvaluationWorker


@pytest.fixture
def mock_db():
    return MagicMock()


@pytest.fixture
def worker(mock_db):
    return AlertEvaluationWorker(mock_db)


class TestAlertEvaluationWorkerRun:

    def test_evaluates_each_tenant(self, worker, mock_db):
        """Should create AlertRuleService per tenant and aggregate stats."""
        row1 = Mock()
        row1.tenant_id = "tenant-a"
        row2 = Mock()
        row2.tenant_id = "tenant-b"

        mock_result = MagicMock()
        mock_result.fetchall.return_value = [row1, row2]
        mock_db.execute.return_value = mock_result

        with patch("src.jobs.alert_evaluation_job.AlertRuleService") as MockService:
            mock_svc = MagicMock()
            mock_svc.evaluate_rules.return_value = {"evaluated": 3, "triggered": 1, "errors": 0}
            MockService.return_value = mock_svc

            stats = worker.run()

        assert stats["tenants"] == 2
        assert stats["evaluated"] == 6  # 3 per tenant * 2
        assert stats["triggered"] == 2  # 1 per tenant * 2
        assert MockService.call_count == 2

    def test_empty_tenant_list(self, worker, mock_db):
        """No tenants with enabled rules → zero stats."""
        mock_result = MagicMock()
        mock_result.fetchall.return_value = []
        mock_db.execute.return_value = mock_result

        stats = worker.run()

        assert stats == {"tenants": 0, "evaluated": 0, "triggered": 0, "errors": 0}

    def test_db_query_failure(self, worker, mock_db):
        """If the tenant query itself fails, return zero stats."""
        mock_db.execute.side_effect = Exception("connection refused")

        stats = worker.run()

        assert stats == {"tenants": 0, "evaluated": 0, "triggered": 0, "errors": 0}

    def test_per_tenant_error_isolation(self, worker, mock_db):
        """One tenant's failure shouldn't block others."""
        row1 = Mock()
        row1.tenant_id = "tenant-bad"
        row2 = Mock()
        row2.tenant_id = "tenant-good"

        mock_result = MagicMock()
        mock_result.fetchall.return_value = [row1, row2]
        mock_db.execute.return_value = mock_result

        call_count = 0

        with patch("src.jobs.alert_evaluation_job.AlertRuleService") as MockService:
            def service_factory(db, tenant_id):
                nonlocal call_count
                call_count += 1
                mock_svc = MagicMock()
                if tenant_id == "tenant-bad":
                    mock_svc.evaluate_rules.side_effect = Exception("tenant-bad DB error")
                else:
                    mock_svc.evaluate_rules.return_value = {"evaluated": 2, "triggered": 1, "errors": 0}
                return mock_svc

            MockService.side_effect = service_factory

            stats = worker.run()

        assert stats["tenants"] == 2
        assert stats["errors"] >= 1  # tenant-bad error counted
        assert stats["evaluated"] == 2  # tenant-good still ran

    def test_aggregates_stats_across_tenants(self, worker, mock_db):
        """Stats from multiple tenants are summed."""
        rows = [Mock(tenant_id="t1"), Mock(tenant_id="t2"), Mock(tenant_id="t3")]
        mock_result = MagicMock()
        mock_result.fetchall.return_value = rows
        mock_db.execute.return_value = mock_result

        with patch("src.jobs.alert_evaluation_job.AlertRuleService") as MockService:
            mock_svc = MagicMock()
            mock_svc.evaluate_rules.return_value = {"evaluated": 5, "triggered": 2, "errors": 1}
            MockService.return_value = mock_svc

            stats = worker.run()

        assert stats["tenants"] == 3
        assert stats["evaluated"] == 15
        assert stats["triggered"] == 6
        assert stats["errors"] == 3
