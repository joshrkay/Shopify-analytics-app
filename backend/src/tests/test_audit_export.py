"""
Tests for GA Audit Log Export.

ACCEPTANCE CRITERIA:
- Export respects tenant scoping
- Large exports do not block API (async job)
- Export attempts are audited
- Rate limiting (3 per tenant per 24h)
- CSV and JSON formats
"""

import json
import uuid
import pytest
from datetime import datetime, timezone, timedelta
from unittest.mock import Mock, MagicMock, patch

from src.services.audit_exporter import (
    AuditExporterService,
    ExportFormat,
    ExportResult,
)
from src.models.audit_log import GAAuditLog


# ============================================================================
# FIXTURES
# ============================================================================

@pytest.fixture
def mock_db():
    return MagicMock()


@pytest.fixture
def exporter(mock_db):
    return AuditExporterService(mock_db)


@pytest.fixture
def sample_log():
    """Create a sample audit log row."""
    log = Mock(spec=GAAuditLog)
    log.id = str(uuid.uuid4())
    log.event_type = "auth.login_success"
    log.user_id = "user-123"
    log.tenant_id = "tenant-123"
    log.dashboard_id = None
    log.access_surface = "external_app"
    log.success = True
    log.metadata = {"ip_address": "10.0.0.1"}
    log.correlation_id = str(uuid.uuid4())
    log.created_at = datetime(2024, 6, 15, 10, 30, 0, tzinfo=timezone.utc)
    return log


# ============================================================================
# TEST SUITE: RATE LIMITING
# ============================================================================

class TestRateLimiting:
    """Test export rate limiting."""

    def test_initial_state_allows_export(self, exporter):
        """Initially, exports should be allowed."""
        allowed, remaining = exporter.check_rate_limit("tenant-123")
        assert allowed is True
        assert remaining == 3

    def test_rate_limit_decreases(self, exporter):
        """Rate limit remaining decreases after exports."""
        exporter._record_export("tenant-123")
        exporter._record_export("tenant-123")

        allowed, remaining = exporter.check_rate_limit("tenant-123")
        assert allowed is True
        assert remaining == 1

    def test_rate_limit_exceeded(self, exporter):
        """Exports are denied when rate limit is exceeded."""
        for _ in range(3):
            exporter._record_export("tenant-123")

        allowed, remaining = exporter.check_rate_limit("tenant-123")
        assert allowed is False
        assert remaining == 0

    def test_rate_limit_per_tenant(self, exporter):
        """Rate limits are per-tenant."""
        for _ in range(3):
            exporter._record_export("tenant-1")

        allowed, remaining = exporter.check_rate_limit("tenant-2")
        assert allowed is True
        assert remaining == 3


# ============================================================================
# TEST SUITE: CSV EXPORT FORMAT
# ============================================================================

class TestCSVFormat:
    """Test CSV export formatting."""

    def test_csv_empty_returns_header_only(self, exporter):
        """Empty export has header row only."""
        csv = exporter._format_csv([])
        lines = csv.strip().split("\n")
        assert len(lines) == 1
        assert "id,event_type,user_id,tenant_id" in lines[0]

    def test_csv_with_data(self, exporter, sample_log):
        """CSV includes data rows."""
        csv = exporter._format_csv([sample_log])
        lines = csv.strip().split("\n")
        assert len(lines) == 2  # header + 1 data row
        assert "auth.login_success" in lines[1]
        assert "tenant-123" in lines[1]

    def test_csv_handles_null_fields(self, exporter, sample_log):
        """CSV handles None fields."""
        sample_log.user_id = None
        sample_log.dashboard_id = None
        csv = exporter._format_csv([sample_log])
        assert "auth.login_success" in csv


# ============================================================================
# TEST SUITE: JSON EXPORT FORMAT
# ============================================================================

class TestJSONFormat:
    """Test JSON export formatting."""

    def test_json_empty_returns_empty_array(self, exporter):
        """Empty export returns empty array."""
        result = exporter._format_json([])
        data = json.loads(result)
        assert data["audit_logs"] == []
        assert data["count"] == 0

    def test_json_with_data(self, exporter, sample_log):
        """JSON includes log entries."""
        result = exporter._format_json([sample_log])
        data = json.loads(result)
        assert data["count"] == 1
        assert data["audit_logs"][0]["event_type"] == "auth.login_success"
        assert data["audit_logs"][0]["tenant_id"] == "tenant-123"

    def test_json_includes_metadata(self, exporter, sample_log):
        """JSON includes metadata field."""
        result = exporter._format_json([sample_log])
        data = json.loads(result)
        assert data["audit_logs"][0]["metadata"] == {"ip_address": "10.0.0.1"}


# ============================================================================
# TEST SUITE: EXPORT EXECUTION
# ============================================================================

class TestExportExecution:
    """Test end-to-end export execution."""

    @patch.object(AuditExporterService, "_audit_export_attempt")
    def test_export_returns_csv(self, mock_audit, mock_db):
        """Export returns CSV content."""
        exporter = AuditExporterService(mock_db)

        # Mock the query service
        mock_result = Mock()
        mock_result.items = []
        mock_result.total = 0
        with patch.object(
            exporter._query_service, "query_logs", return_value=mock_result
        ):
            result = exporter.export(
                tenant_id="tenant-123",
                fmt=ExportFormat.CSV,
            )

        assert result.success is True
        assert result.format == ExportFormat.CSV
        assert result.content is not None

    @patch.object(AuditExporterService, "_audit_export_attempt")
    def test_export_returns_json(self, mock_audit, mock_db):
        """Export returns JSON content."""
        exporter = AuditExporterService(mock_db)

        mock_result = Mock()
        mock_result.items = []
        mock_result.total = 0
        with patch.object(
            exporter._query_service, "query_logs", return_value=mock_result
        ):
            result = exporter.export(
                tenant_id="tenant-123",
                fmt=ExportFormat.JSON,
            )

        assert result.success is True
        assert result.format == ExportFormat.JSON
        data = json.loads(result.content)
        assert "audit_logs" in data

    @patch.object(AuditExporterService, "_audit_export_attempt")
    def test_rate_limit_blocks_export(self, mock_audit, mock_db):
        """Rate-limited export returns error."""
        exporter = AuditExporterService(mock_db)

        # Exhaust rate limit
        for _ in range(3):
            exporter._record_export("tenant-123")

        result = exporter.export(
            tenant_id="tenant-123",
            fmt=ExportFormat.CSV,
        )

        assert result.success is False
        assert "rate limit" in result.error.lower()

    @patch.object(AuditExporterService, "_audit_export_attempt")
    def test_large_export_triggers_async(self, mock_audit, mock_db):
        """Export >10K rows triggers async processing."""
        exporter = AuditExporterService(mock_db)

        mock_result = Mock()
        mock_result.items = []
        mock_result.total = 15_000  # Over threshold
        with patch.object(
            exporter._query_service, "query_logs", return_value=mock_result
        ):
            result = exporter.export(
                tenant_id="tenant-123",
                fmt=ExportFormat.CSV,
            )

        assert result.success is True
        assert result.is_async is True
        assert result.content is None

    @patch.object(AuditExporterService, "_audit_export_attempt")
    def test_export_failure_returns_error(self, mock_audit, mock_db):
        """Export failure returns error result."""
        exporter = AuditExporterService(mock_db)

        with patch.object(
            exporter._query_service, "query_logs",
            side_effect=Exception("DB error"),
        ):
            result = exporter.export(
                tenant_id="tenant-123",
                fmt=ExportFormat.CSV,
            )

        assert result.success is False
        assert "DB error" in result.error


# ============================================================================
# TEST SUITE: EXPORT AUDITING
# ============================================================================

class TestExportAuditing:
    """Test that export attempts are audited."""

    def test_successful_export_is_audited(self, mock_db):
        """Successful exports emit audit events."""
        exporter = AuditExporterService(mock_db)

        mock_result = Mock()
        mock_result.items = []
        mock_result.total = 0

        with patch.object(
            exporter._query_service, "query_logs", return_value=mock_result
        ), patch.object(
            exporter, "_audit_export_attempt"
        ) as mock_audit:
            exporter.export(tenant_id="tenant-123", fmt=ExportFormat.CSV)

            mock_audit.assert_called_once()
            call_kwargs = mock_audit.call_args[1]
            assert call_kwargs["success"] is True

    def test_rate_limited_export_is_audited(self, mock_db):
        """Rate-limited exports emit audit events."""
        exporter = AuditExporterService(mock_db)

        for _ in range(3):
            exporter._record_export("tenant-123")

        with patch.object(
            exporter, "_audit_export_attempt"
        ) as mock_audit:
            exporter.export(tenant_id="tenant-123", fmt=ExportFormat.CSV)

            mock_audit.assert_called_once()
            call_kwargs = mock_audit.call_args[1]
            assert call_kwargs["success"] is False
            assert call_kwargs["error"] == "rate_limit_exceeded"


# ============================================================================
# TEST SUITE: TENANT SCOPING
# ============================================================================

class TestExportTenantScoping:
    """Test that exports respect tenant scoping."""

    @patch.object(AuditExporterService, "_audit_export_attempt")
    def test_non_super_admin_scoped_to_tenant(self, mock_audit, mock_db):
        """Non-super-admin export is scoped to their tenant."""
        exporter = AuditExporterService(mock_db)

        mock_result = Mock()
        mock_result.items = []
        mock_result.total = 0

        with patch.object(
            exporter._query_service, "query_logs", return_value=mock_result
        ) as mock_query:
            exporter.export(
                tenant_id="tenant-123",
                fmt=ExportFormat.CSV,
                is_super_admin=False,
            )

            call_kwargs = mock_query.call_args[1]
            assert call_kwargs["tenant_id"] == "tenant-123"
            assert call_kwargs["is_super_admin"] is False
