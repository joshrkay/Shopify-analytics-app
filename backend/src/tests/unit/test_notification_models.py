"""
Unit tests for Notification models (Story 9.1).

Tests cover:
- Notification model creation and validation
- NotificationPreference model creation
- Status transitions
- Factory methods
- Importance mapping

Story 9.1 - Notification Framework (Events → Channels)
"""

import pytest
import uuid
from datetime import datetime, timezone, date

from src.models.notification import (
    Notification,
    NotificationEventType,
    NotificationImportance,
    NotificationStatus,
    EVENT_IMPORTANCE_MAP,
)
from src.models.notification_preference import NotificationPreference


@pytest.fixture
def tenant_id():
    """Test tenant ID."""
    return "test-tenant-123"


@pytest.fixture
def user_id():
    """Test user ID."""
    return "user-456"


@pytest.fixture
def sample_notification(tenant_id, user_id):
    """Create a sample notification."""
    return Notification(
        id=str(uuid.uuid4()),
        tenant_id=tenant_id,
        user_id=user_id,
        event_type=NotificationEventType.CONNECTOR_FAILED,
        importance=NotificationImportance.IMPORTANT,
        title="Test notification",
        message="This is a test notification message.",
        action_url="/connectors/abc123",
        entity_type="connector",
        entity_id="abc123",
        idempotency_key=f"{tenant_id}:connector_failed:abc123:{date.today().isoformat()}",
        status=NotificationStatus.PENDING,
    )


class TestNotificationModel:
    """Tests for Notification model."""

    def test_creates_with_required_fields(self, tenant_id, user_id):
        """Should create Notification with required fields."""
        notification = Notification(
            tenant_id=tenant_id,
            user_id=user_id,
            event_type=NotificationEventType.CONNECTOR_FAILED,
            importance=NotificationImportance.IMPORTANT,
            title="Data sync failed",
            message="Your connector failed to sync",
            idempotency_key="test-key",
        )

        assert notification.tenant_id == tenant_id
        assert notification.user_id == user_id
        assert notification.event_type == NotificationEventType.CONNECTOR_FAILED
        assert notification.importance == NotificationImportance.IMPORTANT
        assert notification.title == "Data sync failed"
        assert notification.status == NotificationStatus.PENDING

    def test_factory_creates_with_automatic_importance(self, tenant_id, user_id):
        """Should create notification with automatic importance based on event type."""
        notification = Notification.create(
            tenant_id=tenant_id,
            event_type=NotificationEventType.CONNECTOR_FAILED,
            title="Test",
            message="Test message",
            user_id=user_id,
        )

        assert notification.importance == NotificationImportance.IMPORTANT

        notification2 = Notification.create(
            tenant_id=tenant_id,
            event_type=NotificationEventType.ACTION_EXECUTED,
            title="Test",
            message="Test message",
            user_id=user_id,
        )

        assert notification2.importance == NotificationImportance.ROUTINE

    def test_factory_generates_idempotency_key(self, tenant_id):
        """Should generate idempotency key from tenant, event, entity, and date."""
        notification = Notification.create(
            tenant_id=tenant_id,
            event_type=NotificationEventType.CONNECTOR_FAILED,
            title="Test",
            message="Test message",
            entity_id="connector-123",
        )

        expected_key = f"{tenant_id}:connector_failed:connector-123:{date.today().isoformat()}"
        assert notification.idempotency_key == expected_key

    def test_factory_handles_none_entity_id(self, tenant_id):
        """Should handle None entity_id in idempotency key."""
        notification = Notification.create(
            tenant_id=tenant_id,
            event_type=NotificationEventType.INSIGHT_GENERATED,
            title="Test",
            message="Test message",
        )

        expected_key = f"{tenant_id}:insight_generated:none:{date.today().isoformat()}"
        assert notification.idempotency_key == expected_key


class TestNotificationStatus:
    """Tests for notification status transitions."""

    def test_is_pending(self, sample_notification):
        """Should correctly identify pending status."""
        sample_notification.status = NotificationStatus.PENDING
        assert sample_notification.is_pending is True
        assert sample_notification.is_delivered is False
        assert sample_notification.is_read is False

    def test_is_delivered(self, sample_notification):
        """Should correctly identify delivered status."""
        sample_notification.status = NotificationStatus.DELIVERED
        assert sample_notification.is_pending is False
        assert sample_notification.is_delivered is True
        assert sample_notification.is_read is False

    def test_is_read(self, sample_notification):
        """Should correctly identify read status."""
        sample_notification.status = NotificationStatus.READ
        assert sample_notification.is_pending is False
        assert sample_notification.is_delivered is False
        assert sample_notification.is_read is True

    def test_mark_delivered(self, sample_notification):
        """Should mark notification as delivered and set timestamp."""
        sample_notification.mark_delivered()

        assert sample_notification.status == NotificationStatus.DELIVERED
        assert sample_notification.in_app_delivered_at is not None

    def test_mark_read(self, sample_notification):
        """Should mark notification as read and set timestamp."""
        sample_notification.mark_read()

        assert sample_notification.status == NotificationStatus.READ
        assert sample_notification.read_at is not None

    def test_mark_read_idempotent(self, sample_notification):
        """Should not update timestamp if already read."""
        sample_notification.mark_read()
        first_read_at = sample_notification.read_at

        sample_notification.mark_read()
        assert sample_notification.read_at == first_read_at


class TestNotificationEmail:
    """Tests for notification email tracking."""

    def test_is_important(self, sample_notification):
        """Should correctly identify important notifications."""
        sample_notification.importance = NotificationImportance.IMPORTANT
        assert sample_notification.is_important is True

        sample_notification.importance = NotificationImportance.ROUTINE
        assert sample_notification.is_important is False

    def test_requires_email(self, sample_notification):
        """Should correctly identify if email is required."""
        sample_notification.importance = NotificationImportance.IMPORTANT
        sample_notification.email_sent_at = None
        sample_notification.email_failed_at = None

        assert sample_notification.requires_email is True

        sample_notification.email_sent_at = datetime.now(timezone.utc)
        assert sample_notification.requires_email is False

    def test_mark_email_queued(self, sample_notification):
        """Should mark email as queued."""
        sample_notification.mark_email_queued()
        assert sample_notification.email_queued_at is not None

    def test_mark_email_sent(self, sample_notification):
        """Should mark email as sent."""
        sample_notification.mark_email_sent()
        assert sample_notification.email_sent_at is not None

    def test_mark_email_failed(self, sample_notification):
        """Should mark email as failed with error."""
        sample_notification.mark_email_failed("SMTP error")

        assert sample_notification.email_failed_at is not None
        assert sample_notification.email_error == "SMTP error"

    def test_mark_email_failed_truncates_long_error(self, sample_notification):
        """Should truncate long error messages."""
        long_error = "x" * 1000
        sample_notification.mark_email_failed(long_error)

        assert len(sample_notification.email_error) == 500


class TestEventImportanceMapping:
    """Tests for event type to importance mapping."""

    def test_important_events(self):
        """Important events should map to IMPORTANT importance."""
        important_events = [
            NotificationEventType.CONNECTOR_FAILED,
            NotificationEventType.ACTION_REQUIRES_APPROVAL,
            NotificationEventType.INCIDENT_DECLARED,
            NotificationEventType.ACTION_FAILED,
        ]

        for event_type in important_events:
            assert EVENT_IMPORTANCE_MAP[event_type] == NotificationImportance.IMPORTANT

    def test_routine_events(self):
        """Routine events should map to ROUTINE importance."""
        routine_events = [
            NotificationEventType.ACTION_EXECUTED,
            NotificationEventType.INCIDENT_RESOLVED,
            NotificationEventType.SYNC_COMPLETED,
            NotificationEventType.INSIGHT_GENERATED,
            NotificationEventType.RECOMMENDATION_CREATED,
        ]

        for event_type in routine_events:
            assert EVENT_IMPORTANCE_MAP[event_type] == NotificationImportance.ROUTINE


class TestNotificationPreferenceModel:
    """Tests for NotificationPreference model."""

    def test_creates_with_required_fields(self, tenant_id, user_id):
        """Should create preference with required fields."""
        pref = NotificationPreference(
            tenant_id=tenant_id,
            user_id=user_id,
            event_type=NotificationEventType.CONNECTOR_FAILED,
            in_app_enabled=True,
            email_enabled=False,
        )

        assert pref.tenant_id == tenant_id
        assert pref.user_id == user_id
        assert pref.event_type == NotificationEventType.CONNECTOR_FAILED
        assert pref.in_app_enabled is True
        assert pref.email_enabled is False

    def test_defaults_to_enabled(self, tenant_id, user_id):
        """Should default to both channels enabled."""
        pref = NotificationPreference(
            tenant_id=tenant_id,
            user_id=user_id,
            event_type=NotificationEventType.CONNECTOR_FAILED,
        )

        assert pref.in_app_enabled is True
        assert pref.email_enabled is True

    def test_tenant_default_has_null_user_id(self, tenant_id):
        """Should allow NULL user_id for tenant defaults."""
        pref = NotificationPreference(
            tenant_id=tenant_id,
            user_id=None,
            event_type=NotificationEventType.CONNECTOR_FAILED,
        )

        assert pref.user_id is None
