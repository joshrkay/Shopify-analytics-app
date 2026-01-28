"""
Unit tests for NotificationService (Story 9.1).

Tests cover:
- Notification creation
- Idempotency (duplicate prevention)
- Channel routing
- Email queueing
- Preference checking

Story 9.1 - Notification Framework (Events → Channels)
"""

import pytest
from unittest.mock import Mock, patch, MagicMock
from datetime import datetime, timezone
from sqlalchemy.exc import IntegrityError

from src.models.notification import (
    Notification,
    NotificationEventType,
    NotificationImportance,
    NotificationStatus,
)
from src.models.notification_preference import NotificationPreference
from src.services.notification_service import NotificationService


@pytest.fixture
def tenant_id():
    """Test tenant ID."""
    return "test-tenant-123"


@pytest.fixture
def user_id():
    """Test user ID."""
    return "user-456"


@pytest.fixture
def mock_db_session():
    """Create a mock database session."""
    session = Mock()
    session.query = Mock(return_value=Mock())
    session.add = Mock()
    session.flush = Mock()
    session.commit = Mock()
    session.rollback = Mock()
    return session


@pytest.fixture
def notification_service(mock_db_session, tenant_id):
    """Create a notification service instance."""
    return NotificationService(mock_db_session, tenant_id)


class TestNotificationServiceInit:
    """Tests for NotificationService initialization."""

    def test_requires_tenant_id(self, mock_db_session):
        """Should raise ValueError if tenant_id is empty."""
        with pytest.raises(ValueError, match="tenant_id is required"):
            NotificationService(mock_db_session, "")

        with pytest.raises(ValueError, match="tenant_id is required"):
            NotificationService(mock_db_session, None)

    def test_initializes_with_valid_tenant_id(self, mock_db_session, tenant_id):
        """Should initialize successfully with valid tenant_id."""
        service = NotificationService(mock_db_session, tenant_id)
        assert service.tenant_id == tenant_id
        assert service.db == mock_db_session


class TestNotificationCreation:
    """Tests for notification creation."""

    def test_notify_creates_notification(self, notification_service, user_id):
        """Should create notification with correct fields."""
        notification = notification_service.notify(
            event_type=NotificationEventType.CONNECTOR_FAILED,
            title="Sync failed",
            message="Your connector failed to sync",
            user_id=user_id,
            entity_type="connector",
            entity_id="conn-123",
            action_url="/connectors/conn-123",
        )

        assert notification is not None
        assert notification.event_type == NotificationEventType.CONNECTOR_FAILED
        assert notification.title == "Sync failed"
        assert notification.user_id == user_id
        assert notification.importance == NotificationImportance.IMPORTANT

    def test_notify_marks_as_delivered(self, notification_service, user_id):
        """Should mark notification as delivered immediately."""
        notification = notification_service.notify(
            event_type=NotificationEventType.CONNECTOR_FAILED,
            title="Test",
            message="Test message",
            user_id=user_id,
        )

        assert notification.status == NotificationStatus.DELIVERED
        assert notification.in_app_delivered_at is not None

    def test_notify_queues_email_for_important_events(self, notification_service, user_id):
        """Should queue email for important events."""
        notification = notification_service.notify(
            event_type=NotificationEventType.CONNECTOR_FAILED,
            title="Test",
            message="Test message",
            user_id=user_id,
        )

        assert notification.email_queued_at is not None

    def test_notify_does_not_queue_email_for_routine_events(self, notification_service, user_id):
        """Should not queue email for routine events."""
        notification = notification_service.notify(
            event_type=NotificationEventType.ACTION_EXECUTED,
            title="Test",
            message="Test message",
            user_id=user_id,
        )

        assert notification.email_queued_at is None

    def test_notify_handles_duplicate_idempotency_key(self, mock_db_session, tenant_id, user_id):
        """Should return None for duplicate idempotency key."""
        mock_db_session.flush.side_effect = [IntegrityError(None, None, None), None]

        service = NotificationService(mock_db_session, tenant_id)
        result = service.notify(
            event_type=NotificationEventType.CONNECTOR_FAILED,
            title="Test",
            message="Test message",
            user_id=user_id,
        )

        assert result is None
        mock_db_session.rollback.assert_called_once()


class TestHelperMethods:
    """Tests for helper notification methods."""

    def test_notify_connector_failed(self, notification_service):
        """Should create connector failed notification."""
        notifications = notification_service.notify_connector_failed(
            connector_id="conn-123",
            connector_name="Shopify",
            error_message="Connection timeout",
        )

        assert len(notifications) == 1
        assert notifications[0].event_type == NotificationEventType.CONNECTOR_FAILED
        assert "Shopify" in notifications[0].title
        assert notifications[0].entity_type == "connector"
        assert notifications[0].entity_id == "conn-123"

    def test_notify_connector_failed_multiple_users(self, notification_service):
        """Should create notifications for multiple users."""
        user_ids = ["user-1", "user-2", "user-3"]

        notifications = notification_service.notify_connector_failed(
            connector_id="conn-123",
            connector_name="Shopify",
            error_message="Connection timeout",
            user_ids=user_ids,
        )

        assert len(notifications) == 3

    def test_notify_action_requires_approval(self, notification_service):
        """Should create approval required notification."""
        notifications = notification_service.notify_action_requires_approval(
            action_id="action-123",
            action_type="pause_campaign",
            description="Pause campaign X",
            user_ids=["user-1"],
        )

        assert len(notifications) == 1
        assert notifications[0].event_type == NotificationEventType.ACTION_REQUIRES_APPROVAL
        assert notifications[0].entity_type == "action"

    def test_notify_action_executed(self, notification_service, user_id):
        """Should create action executed notification."""
        notification = notification_service.notify_action_executed(
            action_id="action-123",
            action_type="pause_campaign",
            user_id=user_id,
        )

        assert notification.event_type == NotificationEventType.ACTION_EXECUTED
        assert notification.importance == NotificationImportance.ROUTINE

    def test_notify_action_failed(self, notification_service, user_id):
        """Should create action failed notification."""
        notification = notification_service.notify_action_failed(
            action_id="action-123",
            action_type="pause_campaign",
            error_message="API error",
            user_id=user_id,
        )

        assert notification.event_type == NotificationEventType.ACTION_FAILED
        assert notification.importance == NotificationImportance.IMPORTANT

    def test_notify_incident_declared(self, notification_service):
        """Should create incident notification."""
        notifications = notification_service.notify_incident_declared(
            incident_id="inc-123",
            severity="critical",
            title="Data quality issue",
            description="Row count dropped 90%",
        )

        assert len(notifications) == 1
        assert notifications[0].event_type == NotificationEventType.INCIDENT_DECLARED


class TestPreferenceChecking:
    """Tests for preference checking."""

    def test_should_send_email_default_true(self, mock_db_session, tenant_id, user_id):
        """Should default to sending email if no preference set."""
        mock_query = MagicMock()
        mock_query.filter.return_value.first.return_value = None
        mock_db_session.query.return_value = mock_query

        service = NotificationService(mock_db_session, tenant_id)
        result = service._should_send_email(NotificationEventType.CONNECTOR_FAILED, user_id)

        assert result is True

    def test_should_send_email_respects_user_preference(self, mock_db_session, tenant_id, user_id):
        """Should respect user-specific preference."""
        mock_pref = Mock()
        mock_pref.email_enabled = False

        mock_query = MagicMock()
        mock_query.filter.return_value.first.return_value = mock_pref
        mock_db_session.query.return_value = mock_query

        service = NotificationService(mock_db_session, tenant_id)
        result = service._should_send_email(NotificationEventType.CONNECTOR_FAILED, user_id)

        assert result is False


class TestNotificationQueries:
    """Tests for notification query methods."""

    def test_get_notifications(self, mock_db_session, tenant_id, user_id):
        """Should query notifications with filters."""
        mock_notifications = [Mock(), Mock()]
        mock_query = MagicMock()
        mock_query.filter.return_value = mock_query
        mock_query.order_by.return_value = mock_query
        mock_query.offset.return_value = mock_query
        mock_query.limit.return_value = mock_query
        mock_query.count.return_value = 10
        mock_query.all.return_value = mock_notifications
        mock_db_session.query.return_value = mock_query

        service = NotificationService(mock_db_session, tenant_id)
        notifications, total = service.get_notifications(user_id=user_id, limit=50)

        assert notifications == mock_notifications
        assert total == 10

    def test_get_unread_count(self, mock_db_session, tenant_id, user_id):
        """Should return unread count for user."""
        mock_query = MagicMock()
        mock_query.filter.return_value = mock_query
        mock_query.count.return_value = 5
        mock_db_session.query.return_value = mock_query

        service = NotificationService(mock_db_session, tenant_id)
        count = service.get_unread_count(user_id)

        assert count == 5

    def test_mark_as_read(self, mock_db_session, tenant_id, user_id):
        """Should mark notification as read."""
        mock_notification = Mock()
        mock_notification.mark_read = Mock()

        mock_query = MagicMock()
        mock_query.filter.return_value.first.return_value = mock_notification
        mock_db_session.query.return_value = mock_query

        service = NotificationService(mock_db_session, tenant_id)
        result = service.mark_as_read("notif-123", user_id)

        assert result is True
        mock_notification.mark_read.assert_called_once()

    def test_mark_as_read_not_found(self, mock_db_session, tenant_id, user_id):
        """Should return False if notification not found."""
        mock_query = MagicMock()
        mock_query.filter.return_value.first.return_value = None
        mock_db_session.query.return_value = mock_query

        service = NotificationService(mock_db_session, tenant_id)
        result = service.mark_as_read("notif-123", user_id)

        assert result is False

    def test_mark_all_as_read(self, mock_db_session, tenant_id, user_id):
        """Should mark all notifications as read."""
        mock_query = MagicMock()
        mock_query.filter.return_value = mock_query
        mock_query.update.return_value = 5
        mock_db_session.query.return_value = mock_query

        service = NotificationService(mock_db_session, tenant_id)
        count = service.mark_all_as_read(user_id)

        assert count == 5
