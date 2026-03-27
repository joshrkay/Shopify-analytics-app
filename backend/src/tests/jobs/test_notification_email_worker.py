"""Unit tests for notification email worker Clerk lookup and failure handling."""

from unittest.mock import MagicMock, patch

import httpx
import pytest

from src.jobs.notification_email_worker import NotificationEmailWorker, validate_worker_environment
from src.models.notification import Notification, NotificationEventType


class TestGetUserEmail:
    def test_returns_primary_verified_email(self, monkeypatch):
        monkeypatch.setenv("CLERK_SECRET_KEY", "sk_test_123")
        worker = NotificationEmailWorker(db_session=MagicMock(), email_sender=MagicMock())

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "primary_email_address_id": "email_primary",
            "email_addresses": [
                {
                    "id": "email_primary",
                    "email_address": "primary@example.com",
                    "verification": {"status": "verified"},
                },
                {
                    "id": "email_secondary",
                    "email_address": "secondary@example.com",
                    "verification": {"status": "verified"},
                },
            ],
        }

        with patch("src.jobs.notification_email_worker.httpx.Client") as mock_client_cls:
            mock_client = mock_client_cls.return_value.__enter__.return_value
            mock_client.get.return_value = mock_response

            email = worker._get_user_email("user_123")

        assert email == "primary@example.com"

    def test_returns_none_when_user_not_found(self, monkeypatch):
        monkeypatch.setenv("CLERK_SECRET_KEY", "sk_test_123")
        worker = NotificationEmailWorker(db_session=MagicMock(), email_sender=MagicMock())

        mock_response = MagicMock()
        mock_response.status_code = 404

        with patch("src.jobs.notification_email_worker.httpx.Client") as mock_client_cls:
            mock_client = mock_client_cls.return_value.__enter__.return_value
            mock_client.get.return_value = mock_response

            email = worker._get_user_email("missing_user")

        assert email is None

    def test_returns_none_when_clerk_api_fails(self, monkeypatch):
        monkeypatch.setenv("CLERK_SECRET_KEY", "sk_test_123")
        worker = NotificationEmailWorker(db_session=MagicMock(), email_sender=MagicMock())

        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_response.raise_for_status.side_effect = httpx.HTTPStatusError(
            "server error",
            request=MagicMock(),
            response=MagicMock(),
        )

        with patch("src.jobs.notification_email_worker.httpx.Client") as mock_client_cls:
            mock_client = mock_client_cls.return_value.__enter__.return_value
            mock_client.get.return_value = mock_response

            email = worker._get_user_email("user_123")

        assert email is None


class TestEmailDeliveryPolicy:
    @pytest.mark.asyncio
    async def test_missing_email_marks_delivery_failed_by_default(self, monkeypatch):
        monkeypatch.setenv("CLERK_SECRET_KEY", "sk_test_123")
        monkeypatch.delenv("NOTIFICATION_MISSING_EMAIL_POLICY", raising=False)

        worker = NotificationEmailWorker(db_session=MagicMock(), email_sender=MagicMock())
        notification = Notification.create(
            tenant_id="tenant-1",
            event_type=NotificationEventType.ACTION_FAILED,
            title="Action failed",
            message="Action execution failed.",
            user_id="user_123",
            entity_id="entity-1",
        )
        notification.mark_email_queued()

        with patch.object(worker, "_get_user_email", return_value=None):
            success = await worker.process_notification(notification)

        assert success is False
        assert notification.email_sent_at is None
        assert notification.email_failed_at is not None
        assert worker.stats["failed"] == 1


class TestWorkerEnvironmentValidation:
    def test_validate_worker_environment_requires_clerk_secret(self, monkeypatch):
        monkeypatch.delenv("CLERK_SECRET_KEY", raising=False)

        with pytest.raises(RuntimeError, match="CLERK_SECRET_KEY is required"):
            validate_worker_environment()

    def test_validate_worker_environment_passes_when_configured(self, monkeypatch):
        monkeypatch.setenv("CLERK_SECRET_KEY", "sk_test_123")

        validate_worker_environment()
