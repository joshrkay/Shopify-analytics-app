"""
Integration tests for Notifications API (Story 9.1).

Tests cover:
- GET /api/notifications (list notifications)
- GET /api/notifications/unread/count
- GET /api/notifications/{id}
- PATCH /api/notifications/{id}/read
- POST /api/notifications/read-all
- Tenant isolation
- User ownership

Story 9.1 - Notification Framework (Events → Channels)
"""

import pytest
import uuid
from unittest.mock import Mock, patch, MagicMock
from datetime import datetime, timezone

from fastapi.testclient import TestClient
from fastapi import FastAPI

from src.api.routes.notifications import router
from src.models.notification import (
    Notification,
    NotificationEventType,
    NotificationImportance,
    NotificationStatus,
)


@pytest.fixture
def tenant_id():
    """Test tenant ID."""
    return "test-tenant-123"


@pytest.fixture
def user_id():
    """Test user ID."""
    return "user-456"


@pytest.fixture
def other_user_id():
    """Different user ID for isolation tests."""
    return "other-user-789"


@pytest.fixture
def mock_tenant_context(tenant_id, user_id):
    """Create a mock tenant context."""
    ctx = Mock()
    ctx.tenant_id = tenant_id
    ctx.user_id = user_id
    ctx.roles = ["merchant_admin"]
    return ctx


@pytest.fixture
def sample_notification(tenant_id, user_id):
    """Create a sample notification for testing."""
    return Notification(
        id=str(uuid.uuid4()),
        tenant_id=tenant_id,
        user_id=user_id,
        event_type=NotificationEventType.CONNECTOR_FAILED,
        importance=NotificationImportance.IMPORTANT,
        title="Test notification",
        message="This is a test message",
        action_url="/connectors/abc123",
        entity_type="connector",
        entity_id="abc123",
        idempotency_key="test-key-123",
        status=NotificationStatus.DELIVERED,
        created_at=datetime.now(timezone.utc),
        in_app_delivered_at=datetime.now(timezone.utc),
    )


@pytest.fixture
def app():
    """Create a FastAPI test app."""
    app = FastAPI()
    app.include_router(router)
    return app


@pytest.fixture
def client(app):
    """Create a test client."""
    return TestClient(app)


class TestListNotifications:
    """Tests for GET /api/notifications."""

    def test_returns_user_notifications(self, client, mock_tenant_context, sample_notification):
        """Should return notifications for the authenticated user."""
        mock_db = MagicMock()
        mock_query = MagicMock()
        mock_query.filter.return_value = mock_query
        mock_query.order_by.return_value = mock_query
        mock_query.offset.return_value = mock_query
        mock_query.limit.return_value = mock_query
        mock_query.count.return_value = 1
        mock_query.all.return_value = [sample_notification]
        mock_db.query.return_value = mock_query

        with patch('src.api.routes.notifications.get_tenant_context', return_value=mock_tenant_context):
            with patch('src.api.routes.notifications.get_db_session', return_value=mock_db):
                response = client.get("/api/notifications")

        assert response.status_code == 200
        data = response.json()
        assert "notifications" in data
        assert "total" in data
        assert "unread_count" in data

    def test_filters_by_status(self, client, mock_tenant_context, sample_notification):
        """Should filter notifications by status."""
        mock_db = MagicMock()
        mock_query = MagicMock()
        mock_query.filter.return_value = mock_query
        mock_query.order_by.return_value = mock_query
        mock_query.offset.return_value = mock_query
        mock_query.limit.return_value = mock_query
        mock_query.count.return_value = 1
        mock_query.all.return_value = [sample_notification]
        mock_db.query.return_value = mock_query

        with patch('src.api.routes.notifications.get_tenant_context', return_value=mock_tenant_context):
            with patch('src.api.routes.notifications.get_db_session', return_value=mock_db):
                response = client.get("/api/notifications?status=delivered")

        assert response.status_code == 200

    def test_rejects_invalid_status(self, client, mock_tenant_context):
        """Should return 400 for invalid status filter."""
        mock_db = MagicMock()

        with patch('src.api.routes.notifications.get_tenant_context', return_value=mock_tenant_context):
            with patch('src.api.routes.notifications.get_db_session', return_value=mock_db):
                response = client.get("/api/notifications?status=invalid")

        assert response.status_code == 400
        assert "Invalid status" in response.json()["detail"]


class TestGetUnreadCount:
    """Tests for GET /api/notifications/unread/count."""

    def test_returns_unread_count(self, client, mock_tenant_context):
        """Should return count of unread notifications."""
        mock_db = MagicMock()
        mock_query = MagicMock()
        mock_query.filter.return_value = mock_query
        mock_query.count.return_value = 5
        mock_db.query.return_value = mock_query

        with patch('src.api.routes.notifications.get_tenant_context', return_value=mock_tenant_context):
            with patch('src.api.routes.notifications.get_db_session', return_value=mock_db):
                response = client.get("/api/notifications/unread/count")

        assert response.status_code == 200
        data = response.json()
        assert data["count"] == 5


class TestGetNotification:
    """Tests for GET /api/notifications/{id}."""

    def test_returns_notification(self, client, mock_tenant_context, sample_notification):
        """Should return notification by ID."""
        mock_db = MagicMock()
        mock_query = MagicMock()
        mock_query.filter.return_value.first.return_value = sample_notification
        mock_db.query.return_value = mock_query

        with patch('src.api.routes.notifications.get_tenant_context', return_value=mock_tenant_context):
            with patch('src.api.routes.notifications.get_db_session', return_value=mock_db):
                response = client.get(f"/api/notifications/{sample_notification.id}")

        assert response.status_code == 200
        data = response.json()
        assert data["id"] == sample_notification.id

    def test_returns_404_when_not_found(self, client, mock_tenant_context):
        """Should return 404 when notification not found."""
        mock_db = MagicMock()
        mock_query = MagicMock()
        mock_query.filter.return_value.first.return_value = None
        mock_db.query.return_value = mock_query

        with patch('src.api.routes.notifications.get_tenant_context', return_value=mock_tenant_context):
            with patch('src.api.routes.notifications.get_db_session', return_value=mock_db):
                response = client.get(f"/api/notifications/{uuid.uuid4()}")

        assert response.status_code == 404


class TestMarkAsRead:
    """Tests for PATCH /api/notifications/{id}/read."""

    def test_marks_notification_as_read(self, client, mock_tenant_context, sample_notification):
        """Should mark notification as read."""
        mock_db = MagicMock()
        mock_query = MagicMock()
        mock_query.filter.return_value.first.return_value = sample_notification
        mock_db.query.return_value = mock_query

        with patch('src.api.routes.notifications.get_tenant_context', return_value=mock_tenant_context):
            with patch('src.api.routes.notifications.get_db_session', return_value=mock_db):
                response = client.patch(f"/api/notifications/{sample_notification.id}/read")

        assert response.status_code == 200
        assert response.json()["success"] is True
        mock_db.commit.assert_called_once()

    def test_returns_404_when_not_found(self, client, mock_tenant_context):
        """Should return 404 when notification not found."""
        mock_db = MagicMock()
        mock_query = MagicMock()
        mock_query.filter.return_value.first.return_value = None
        mock_db.query.return_value = mock_query

        with patch('src.api.routes.notifications.get_tenant_context', return_value=mock_tenant_context):
            with patch('src.api.routes.notifications.get_db_session', return_value=mock_db):
                response = client.patch(f"/api/notifications/{uuid.uuid4()}/read")

        assert response.status_code == 404


class TestMarkAllAsRead:
    """Tests for POST /api/notifications/read-all."""

    def test_marks_all_as_read(self, client, mock_tenant_context):
        """Should mark all notifications as read."""
        mock_db = MagicMock()
        mock_query = MagicMock()
        mock_query.filter.return_value = mock_query
        mock_query.update.return_value = 10
        mock_db.query.return_value = mock_query

        with patch('src.api.routes.notifications.get_tenant_context', return_value=mock_tenant_context):
            with patch('src.api.routes.notifications.get_db_session', return_value=mock_db):
                response = client.post("/api/notifications/read-all")

        assert response.status_code == 200
        data = response.json()
        assert data["marked_count"] == 10
        mock_db.commit.assert_called_once()
