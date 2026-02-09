"""
Tests for GA Audit Log API access control.

ACCEPTANCE CRITERIA:
- Tenant admin cannot see other tenants' logs
- Super admin can filter across tenants
- Non-admin users get 403
- Pagination works correctly
- Filters (date range, event_type, dashboard_id) work correctly
"""

import uuid
import pytest
from datetime import datetime, timezone, timedelta
from unittest.mock import Mock, patch, MagicMock

from src.services.audit_query_service import AuditQueryService, AuditQueryResult
from src.models.audit_log import GAAuditLog, AuditEventType, AccessSurface


# ============================================================================
# FIXTURES
# ============================================================================

@pytest.fixture
def mock_db():
    """Create a mock database session."""
    return MagicMock()


@pytest.fixture
def sample_logs():
    """Create sample GAAuditLog rows for testing."""
    now = datetime.now(timezone.utc)
    logs = []
    for i in range(5):
        log = Mock(spec=GAAuditLog)
        log.id = str(uuid.uuid4())
        log.event_type = "auth.login_success"
        log.user_id = f"user-{i}"
        log.tenant_id = "tenant-123"
        log.dashboard_id = None
        log.access_surface = "external_app"
        log.success = True
        log.metadata = {}
        log.correlation_id = str(uuid.uuid4())
        log.created_at = now - timedelta(minutes=i)
        logs.append(log)
    return logs


# ============================================================================
# TEST SUITE: TENANT SCOPING
# ============================================================================

class TestTenantScoping:
    """Test that queries are properly scoped to tenants."""

    def test_non_super_admin_scoped_to_tenant(self, mock_db):
        """Non-super-admin queries are restricted to their tenant."""
        service = AuditQueryService(mock_db)

        # Mock query chain
        mock_query = MagicMock()
        mock_query.filter.return_value = mock_query
        mock_query.order_by.return_value = mock_query
        mock_query.offset.return_value = mock_query
        mock_query.limit.return_value = mock_query
        mock_query.all.return_value = []
        mock_query.count.return_value = 0
        mock_db.query.return_value = mock_query

        result = service.query_logs(
            tenant_id="tenant-123",
            is_super_admin=False,
        )

        # Should have called filter with tenant_id
        mock_query.filter.assert_called()
        assert result.total == 0

    def test_super_admin_no_tenant_restriction(self, mock_db):
        """Super admin queries have no tenant restriction."""
        service = AuditQueryService(mock_db)

        mock_query = MagicMock()
        mock_query.filter.return_value = mock_query
        mock_query.order_by.return_value = mock_query
        mock_query.offset.return_value = mock_query
        mock_query.limit.return_value = mock_query
        mock_query.all.return_value = []
        mock_query.count.return_value = 0
        mock_db.query.return_value = mock_query

        result = service.query_logs(
            is_super_admin=True,
        )

        assert result.total == 0

    def test_no_tenant_access_returns_empty(self, mock_db):
        """No tenant access should return empty result."""
        service = AuditQueryService(mock_db)

        result = service.query_logs(
            tenant_id=None,
            accessible_tenants=None,
            is_super_admin=False,
        )

        assert result.items == []
        assert result.total == 0

    def test_agency_user_with_multiple_tenants(self, mock_db):
        """Agency user can query across allowed tenants."""
        service = AuditQueryService(mock_db)

        mock_query = MagicMock()
        mock_query.filter.return_value = mock_query
        mock_query.order_by.return_value = mock_query
        mock_query.offset.return_value = mock_query
        mock_query.limit.return_value = mock_query
        mock_query.all.return_value = []
        mock_query.count.return_value = 0
        mock_db.query.return_value = mock_query

        result = service.query_logs(
            accessible_tenants={"tenant-1", "tenant-2", "tenant-3"},
            is_super_admin=False,
        )

        # Should use IN clause for multiple tenants
        mock_query.filter.assert_called()
        assert result.total == 0


# ============================================================================
# TEST SUITE: PAGINATION
# ============================================================================

class TestPagination:
    """Test pagination of audit log queries."""

    def test_max_page_size_enforced(self, mock_db):
        """Page size is capped at MAX_PAGE_SIZE."""
        service = AuditQueryService(mock_db)

        mock_query = MagicMock()
        mock_query.filter.return_value = mock_query
        mock_query.order_by.return_value = mock_query
        mock_query.offset.return_value = mock_query
        mock_query.limit.return_value = mock_query
        mock_query.all.return_value = []
        mock_query.count.return_value = 0
        mock_db.query.return_value = mock_query

        result = service.query_logs(
            tenant_id="t-1",
            is_super_admin=False,
            limit=9999,
        )

        assert result.limit == AuditQueryService.MAX_PAGE_SIZE

    def test_has_more_is_true_when_more_results(self):
        """has_more is True when there are more results beyond current page."""
        result = AuditQueryResult(items=[], total=100, limit=50, offset=0)
        assert result.has_more is True

    def test_has_more_is_false_when_no_more(self):
        """has_more is False when on last page."""
        result = AuditQueryResult(items=[], total=50, limit=50, offset=0)
        assert result.has_more is False

    def test_has_more_with_offset(self):
        """has_more accounts for offset."""
        result = AuditQueryResult(items=[], total=100, limit=50, offset=50)
        assert result.has_more is False

        result = AuditQueryResult(items=[], total=100, limit=50, offset=25)
        assert result.has_more is True


# ============================================================================
# TEST SUITE: FILTERS
# ============================================================================

class TestFilters:
    """Test query filters."""

    def test_event_type_filter(self, mock_db):
        """Can filter by event_type."""
        service = AuditQueryService(mock_db)

        mock_query = MagicMock()
        mock_query.filter.return_value = mock_query
        mock_query.order_by.return_value = mock_query
        mock_query.offset.return_value = mock_query
        mock_query.limit.return_value = mock_query
        mock_query.all.return_value = []
        mock_query.count.return_value = 0
        mock_db.query.return_value = mock_query

        service.query_logs(
            tenant_id="t-1",
            is_super_admin=False,
            event_type="auth.login_success",
        )

        # Filter should be called multiple times (tenant + event_type)
        assert mock_query.filter.call_count >= 2

    def test_dashboard_id_filter(self, mock_db):
        """Can filter by dashboard_id."""
        service = AuditQueryService(mock_db)

        mock_query = MagicMock()
        mock_query.filter.return_value = mock_query
        mock_query.order_by.return_value = mock_query
        mock_query.offset.return_value = mock_query
        mock_query.limit.return_value = mock_query
        mock_query.all.return_value = []
        mock_query.count.return_value = 0
        mock_db.query.return_value = mock_query

        service.query_logs(
            tenant_id="t-1",
            is_super_admin=False,
            dashboard_id="overview",
        )

        assert mock_query.filter.call_count >= 2

    def test_date_range_filter(self, mock_db):
        """Can filter by date range."""
        service = AuditQueryService(mock_db)

        mock_query = MagicMock()
        mock_query.filter.return_value = mock_query
        mock_query.order_by.return_value = mock_query
        mock_query.offset.return_value = mock_query
        mock_query.limit.return_value = mock_query
        mock_query.all.return_value = []
        mock_query.count.return_value = 0
        mock_db.query.return_value = mock_query

        now = datetime.now(timezone.utc)
        service.query_logs(
            tenant_id="t-1",
            is_super_admin=False,
            start_date=now - timedelta(days=7),
            end_date=now,
        )

        # tenant + start_date + end_date = at least 3 filter calls
        assert mock_query.filter.call_count >= 3

    def test_success_filter(self, mock_db):
        """Can filter by success/failure."""
        service = AuditQueryService(mock_db)

        mock_query = MagicMock()
        mock_query.filter.return_value = mock_query
        mock_query.order_by.return_value = mock_query
        mock_query.offset.return_value = mock_query
        mock_query.limit.return_value = mock_query
        mock_query.all.return_value = []
        mock_query.count.return_value = 0
        mock_db.query.return_value = mock_query

        service.query_logs(
            tenant_id="t-1",
            is_super_admin=False,
            success=False,
        )

        assert mock_query.filter.call_count >= 2


# ============================================================================
# TEST SUITE: CORRELATION ID QUERIES
# ============================================================================

class TestCorrelationIdQueries:
    """Test correlation ID-based queries."""

    def test_get_by_correlation_id(self, mock_db):
        """Can retrieve all events for a correlation ID."""
        service = AuditQueryService(mock_db)

        mock_query = MagicMock()
        mock_query.filter.return_value = mock_query
        mock_query.order_by.return_value = mock_query
        mock_query.all.return_value = []
        mock_db.query.return_value = mock_query

        result = service.get_by_correlation_id(
            correlation_id="corr-123",
            tenant_id="t-1",
        )

        assert isinstance(result, list)

    def test_super_admin_correlation_no_tenant_filter(self, mock_db):
        """Super admin correlation query has no tenant filter."""
        service = AuditQueryService(mock_db)

        mock_query = MagicMock()
        mock_query.filter.return_value = mock_query
        mock_query.order_by.return_value = mock_query
        mock_query.all.return_value = []
        mock_db.query.return_value = mock_query

        service.get_by_correlation_id(
            correlation_id="corr-123",
            is_super_admin=True,
        )

        # Should only filter by correlation_id, not tenant
        assert mock_query.filter.call_count == 1


# ============================================================================
# TEST SUITE: COUNT BY EVENT TYPE
# ============================================================================

class TestCountByEventType:
    """Test event type count aggregation."""

    def test_count_by_event_type(self, mock_db):
        """Counts are grouped by event_type for a tenant."""
        service = AuditQueryService(mock_db)

        mock_query = MagicMock()
        mock_query.filter.return_value = mock_query
        mock_query.group_by.return_value = mock_query
        mock_query.all.return_value = [
            ("auth.login_success", 10),
            ("auth.login_failed", 3),
        ]
        mock_db.query.return_value = mock_query

        result = service.count_by_event_type(tenant_id="t-1")

        assert result == {
            "auth.login_success": 10,
            "auth.login_failed": 3,
        }
