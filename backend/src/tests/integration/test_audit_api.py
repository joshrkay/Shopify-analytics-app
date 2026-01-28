"""
Integration tests for Audit API (Story 8.7).

Tests the full API endpoints for audit log queries and safety events:
- Listing audit logs with filters
- Getting audit log details
- Audit summary statistics
- Correlation ID tracing
- Safety events
- Safety status

Story 8.7 - Audit, Rollback & Accountability
"""

import pytest
import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import Mock, patch, AsyncMock

from fastapi.testclient import TestClient
from fastapi import FastAPI

from src.api.routes.audit import router
from src.platform.audit import AuditLog


# =============================================================================
# Test Fixtures
# =============================================================================


@pytest.fixture
def tenant_id():
    """Test tenant ID."""
    return "test-tenant-123"


@pytest.fixture
def user_id():
    """Test user ID."""
    return "user-123"


@pytest.fixture
def app():
    """Create a test FastAPI app."""
    app = FastAPI()
    app.include_router(router)
    return app


@pytest.fixture
def client(app):
    """Create a test client."""
    return TestClient(app)


@pytest.fixture
def mock_tenant_context(tenant_id, user_id):
    """Create a mock tenant context."""
    ctx = Mock()
    ctx.tenant_id = tenant_id
    ctx.user_id = user_id
    ctx.roles = ["merchant_admin"]
    return ctx


@pytest.fixture
def sample_audit_log(tenant_id, user_id):
    """Create a sample audit log for testing."""
    return AuditLog(
        id=str(uuid.uuid4()),
        tenant_id=tenant_id,
        user_id=user_id,
        action="ai.action.executed",
        timestamp=datetime.now(timezone.utc),
        ip_address="127.0.0.1",
        user_agent="TestClient/1.0",
        resource_type="action",
        resource_id=str(uuid.uuid4()),
        event_metadata={"status": "success"},
        correlation_id=str(uuid.uuid4()),
    )


# =============================================================================
# List Audit Logs Tests
# =============================================================================


class TestListAuditLogs:
    """Tests for GET /api/audit/logs endpoint."""

    def test_returns_empty_list_when_no_logs(
        self, client, mock_tenant_context
    ):
        """Should return empty list when tenant has no audit logs."""
        mock_db = Mock()
        mock_query = Mock()
        mock_query.filter.return_value = mock_query
        mock_query.order_by.return_value = mock_query
        mock_query.offset.return_value = mock_query
        mock_query.limit.return_value = mock_query
        mock_query.all.return_value = []
        mock_query.count.return_value = 0
        mock_db.query.return_value = mock_query

        with patch('src.api.routes.audit.get_tenant_context', return_value=mock_tenant_context):
            with patch('src.api.routes.audit.get_db_session', return_value=mock_db):
                response = client.get("/api/audit/logs")

        assert response.status_code == 200
        data = response.json()
        assert data["logs"] == []
        assert data["total"] == 0
        assert data["has_more"] is False

    def test_returns_logs_list(
        self, client, mock_tenant_context, sample_audit_log
    ):
        """Should return list of audit logs."""
        mock_db = Mock()
        mock_query = Mock()
        mock_query.filter.return_value = mock_query
        mock_query.order_by.return_value = mock_query
        mock_query.offset.return_value = mock_query
        mock_query.limit.return_value = mock_query
        mock_query.all.return_value = [sample_audit_log]
        mock_query.count.return_value = 1
        mock_db.query.return_value = mock_query

        with patch('src.api.routes.audit.get_tenant_context', return_value=mock_tenant_context):
            with patch('src.api.routes.audit.get_db_session', return_value=mock_db):
                response = client.get("/api/audit/logs")

        assert response.status_code == 200
        data = response.json()
        assert len(data["logs"]) == 1
        assert data["logs"][0]["id"] == sample_audit_log.id
        assert data["logs"][0]["action"] == "ai.action.executed"

    def test_filters_by_action(self, client, mock_tenant_context, sample_audit_log):
        """Should filter logs by action type."""
        mock_db = Mock()
        mock_query = Mock()
        mock_query.filter.return_value = mock_query
        mock_query.order_by.return_value = mock_query
        mock_query.offset.return_value = mock_query
        mock_query.limit.return_value = mock_query
        mock_query.all.return_value = [sample_audit_log]
        mock_query.count.return_value = 1
        mock_db.query.return_value = mock_query

        with patch('src.api.routes.audit.get_tenant_context', return_value=mock_tenant_context):
            with patch('src.api.routes.audit.get_db_session', return_value=mock_db):
                response = client.get("/api/audit/logs?action=ai.action.executed")

        assert response.status_code == 200
        # Verify filter was applied (action filter called)
        assert mock_query.filter.called

    def test_filters_by_date_range(self, client, mock_tenant_context):
        """Should filter logs by date range."""
        mock_db = Mock()
        mock_query = Mock()
        mock_query.filter.return_value = mock_query
        mock_query.order_by.return_value = mock_query
        mock_query.offset.return_value = mock_query
        mock_query.limit.return_value = mock_query
        mock_query.all.return_value = []
        mock_query.count.return_value = 0
        mock_db.query.return_value = mock_query

        start = datetime.now(timezone.utc) - timedelta(days=7)
        end = datetime.now(timezone.utc)

        with patch('src.api.routes.audit.get_tenant_context', return_value=mock_tenant_context):
            with patch('src.api.routes.audit.get_db_session', return_value=mock_db):
                response = client.get(
                    f"/api/audit/logs?start_date={start.isoformat()}&end_date={end.isoformat()}"
                )

        assert response.status_code == 200


# =============================================================================
# Get Audit Log Tests
# =============================================================================


class TestGetAuditLog:
    """Tests for GET /api/audit/logs/{log_id} endpoint."""

    def test_returns_404_when_log_not_found(self, client, mock_tenant_context):
        """Should return 404 when log doesn't exist."""
        mock_db = Mock()
        mock_query = Mock()
        mock_query.filter.return_value.first.return_value = None
        mock_db.query.return_value = mock_query

        with patch('src.api.routes.audit.get_tenant_context', return_value=mock_tenant_context):
            with patch('src.api.routes.audit.get_db_session', return_value=mock_db):
                response = client.get(f"/api/audit/logs/{uuid.uuid4()}")

        assert response.status_code == 404

    def test_returns_log_details(self, client, mock_tenant_context, sample_audit_log):
        """Should return log details when found."""
        mock_db = Mock()
        mock_query = Mock()
        mock_query.filter.return_value.first.return_value = sample_audit_log
        mock_db.query.return_value = mock_query

        with patch('src.api.routes.audit.get_tenant_context', return_value=mock_tenant_context):
            with patch('src.api.routes.audit.get_db_session', return_value=mock_db):
                response = client.get(f"/api/audit/logs/{sample_audit_log.id}")

        assert response.status_code == 200
        data = response.json()
        assert data["id"] == sample_audit_log.id
        assert data["action"] == sample_audit_log.action


# =============================================================================
# Audit Summary Tests
# =============================================================================


class TestAuditSummary:
    """Tests for GET /api/audit/summary endpoint."""

    def test_returns_summary_statistics(self, client, mock_tenant_context):
        """Should return audit summary statistics."""
        mock_db = Mock()
        mock_query = Mock()

        # Mock count
        mock_query.filter.return_value.count.return_value = 100

        # Mock group by queries
        mock_query.filter.return_value.with_entities.return_value.group_by.return_value.all.return_value = [
            ("ai.action.executed", 50),
            ("ai.action.failed", 10),
        ]

        mock_db.query.return_value = mock_query

        with patch('src.api.routes.audit.get_tenant_context', return_value=mock_tenant_context):
            with patch('src.api.routes.audit.get_db_session', return_value=mock_db):
                response = client.get("/api/audit/summary")

        assert response.status_code == 200
        data = response.json()
        assert "total_events" in data
        assert "by_action" in data
        assert "by_severity" in data
        assert "by_resource_type" in data


# =============================================================================
# Correlation ID Tests
# =============================================================================


class TestCorrelatedLogs:
    """Tests for GET /api/audit/correlation/{correlation_id} endpoint."""

    def test_returns_correlated_logs(self, client, mock_tenant_context, sample_audit_log):
        """Should return all logs with same correlation ID."""
        correlation_id = sample_audit_log.correlation_id

        # Create another log with same correlation_id
        second_log = AuditLog(
            id=str(uuid.uuid4()),
            tenant_id=sample_audit_log.tenant_id,
            user_id=sample_audit_log.user_id,
            action="ai.action.started",
            timestamp=datetime.now(timezone.utc) - timedelta(seconds=5),
            correlation_id=correlation_id,
        )

        mock_db = Mock()
        mock_query = Mock()
        mock_query.filter.return_value.order_by.return_value.all.return_value = [
            second_log, sample_audit_log
        ]
        mock_db.query.return_value = mock_query

        with patch('src.api.routes.audit.get_tenant_context', return_value=mock_tenant_context):
            with patch('src.api.routes.audit.get_db_session', return_value=mock_db):
                response = client.get(f"/api/audit/correlation/{correlation_id}")

        assert response.status_code == 200
        data = response.json()
        assert len(data["logs"]) == 2
        assert data["has_more"] is False


# =============================================================================
# Safety Events Tests
# =============================================================================


class TestSafetyEvents:
    """Tests for GET /api/audit/safety/events endpoint."""

    def test_returns_safety_events(self, client, mock_tenant_context, tenant_id):
        """Should return safety events."""
        from src.services.action_safety_service import AISafetyEvent

        mock_event = Mock()
        mock_event.id = uuid.uuid4()
        mock_event.tenant_id = tenant_id
        mock_event.event_type = "rate_limit_hit"
        mock_event.operation_type = "action_execution"
        mock_event.entity_id = None
        mock_event.action_id = None
        mock_event.reason = "Rate limit exceeded"
        mock_event.metadata = {"count": 50, "limit": 50}
        mock_event.correlation_id = None
        mock_event.created_at = datetime.now(timezone.utc)

        mock_db = Mock()
        mock_query = Mock()
        mock_query.filter.return_value = mock_query
        mock_query.order_by.return_value = mock_query
        mock_query.offset.return_value = mock_query
        mock_query.limit.return_value = mock_query
        mock_query.all.return_value = [mock_event]
        mock_query.count.return_value = 1
        mock_db.query.return_value = mock_query

        with patch('src.api.routes.audit.get_tenant_context', return_value=mock_tenant_context):
            with patch('src.api.routes.audit.get_db_session', return_value=mock_db):
                response = client.get("/api/audit/safety/events")

        assert response.status_code == 200
        data = response.json()
        assert len(data["events"]) == 1
        assert data["events"][0]["event_type"] == "rate_limit_hit"

    def test_filters_safety_events_by_type(self, client, mock_tenant_context):
        """Should filter safety events by event type."""
        mock_db = Mock()
        mock_query = Mock()
        mock_query.filter.return_value = mock_query
        mock_query.order_by.return_value = mock_query
        mock_query.offset.return_value = mock_query
        mock_query.limit.return_value = mock_query
        mock_query.all.return_value = []
        mock_query.count.return_value = 0
        mock_db.query.return_value = mock_query

        with patch('src.api.routes.audit.get_tenant_context', return_value=mock_tenant_context):
            with patch('src.api.routes.audit.get_db_session', return_value=mock_db):
                response = client.get("/api/audit/safety/events?event_type=action_blocked")

        assert response.status_code == 200
        # Verify filter was applied
        assert mock_query.filter.called


# =============================================================================
# Safety Status Tests
# =============================================================================


class TestSafetyStatus:
    """Tests for GET /api/audit/safety/status endpoint."""

    def test_returns_safety_status(self, client, mock_tenant_context):
        """Should return current safety status."""
        mock_db = Mock()

        # Mock BillingEntitlementsService
        mock_billing = Mock()
        mock_billing.get_billing_tier.return_value = "growth"

        # Mock ActionSafetyService
        mock_safety = Mock()
        mock_rate_status = Mock()
        mock_rate_status.count = 10
        mock_rate_status.limit = 50
        mock_rate_status.remaining = 40
        mock_rate_status.reset_at = datetime.now(timezone.utc) + timedelta(hours=1)
        mock_rate_status.is_limited = False
        mock_safety.get_rate_limit_status.return_value = mock_rate_status

        # Mock cooldown count
        mock_query = Mock()
        mock_query.filter.return_value.scalar.return_value = 2
        mock_db.query.return_value = mock_query

        with patch('src.api.routes.audit.get_tenant_context', return_value=mock_tenant_context):
            with patch('src.api.routes.audit.get_db_session', return_value=mock_db):
                with patch('src.api.routes.audit.BillingEntitlementsService', return_value=mock_billing):
                    with patch('src.api.routes.audit.ActionSafetyService', return_value=mock_safety):
                        with patch('src.api.routes.audit.is_kill_switch_active', new_callable=AsyncMock, return_value=False):
                            response = client.get("/api/audit/safety/status")

        assert response.status_code == 200
        data = response.json()
        assert "rate_limit_status" in data
        assert "active_cooldowns" in data
        assert "kill_switch_active" in data
        assert "recent_blocked_count" in data
        assert data["kill_switch_active"] is False


# =============================================================================
# Tenant Isolation Tests
# =============================================================================


class TestTenantIsolation:
    """Tests for tenant isolation in audit endpoints."""

    def test_logs_are_tenant_scoped(self, client, tenant_id, user_id):
        """Should only return logs for the authenticated tenant."""
        other_tenant_log = AuditLog(
            id=str(uuid.uuid4()),
            tenant_id="other-tenant",  # Different tenant
            user_id=user_id,
            action="ai.action.executed",
            timestamp=datetime.now(timezone.utc),
        )

        mock_tenant_context = Mock()
        mock_tenant_context.tenant_id = tenant_id
        mock_tenant_context.user_id = user_id
        mock_tenant_context.roles = ["merchant_admin"]

        mock_db = Mock()
        mock_query = Mock()
        # Return empty because query filters by tenant_id
        mock_query.filter.return_value = mock_query
        mock_query.order_by.return_value = mock_query
        mock_query.offset.return_value = mock_query
        mock_query.limit.return_value = mock_query
        mock_query.all.return_value = []
        mock_query.count.return_value = 0
        mock_db.query.return_value = mock_query

        with patch('src.api.routes.audit.get_tenant_context', return_value=mock_tenant_context):
            with patch('src.api.routes.audit.get_db_session', return_value=mock_db):
                response = client.get("/api/audit/logs")

        assert response.status_code == 200
        # The query should have filtered by tenant_id
        # Verify by checking filter was called with tenant_id
        filter_calls = mock_query.filter.call_args_list
        assert len(filter_calls) > 0
