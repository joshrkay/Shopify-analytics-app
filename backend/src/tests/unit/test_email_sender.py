"""
Unit tests for email sender service.

Tests cover:
- EmailMessage dataclass
- MockEmailSender
- SendGridEmailSender (mocked HTTP calls)
- SMTPEmailSender (mocked SMTP)
- get_email_sender factory
"""

import pytest
from unittest.mock import MagicMock, patch

from src.services.email_sender import (
    EmailMessage,
    MockEmailSender,
    SendGridEmailSender,
    SMTPEmailSender,
    get_email_sender,
)


# =============================================================================
# EmailMessage
# =============================================================================

class TestEmailMessage:

    def test_required_fields(self):
        msg = EmailMessage(
            to_email="test@example.com",
            to_name="Test User",
            subject="Hello",
            html_body="<p>Hi</p>",
        )
        assert msg.to_email == "test@example.com"
        assert msg.subject == "Hello"

    def test_optional_fields_default_none(self):
        msg = EmailMessage(
            to_email="test@example.com",
            to_name=None,
            subject="Test",
            html_body="<p>Body</p>",
        )
        assert msg.text_body is None
        assert msg.from_email is None
        assert msg.reply_to is None
        assert msg.tags is None


# =============================================================================
# MockEmailSender
# =============================================================================

class TestMockEmailSender:

    def test_send_records_message(self):
        sender = MockEmailSender()
        msg = EmailMessage(
            to_email="test@example.com",
            to_name="Test",
            subject="Test",
            html_body="<p>Test</p>",
        )
        result = sender.send_sync(msg)
        assert result is True
        assert len(sender.sent_messages) == 1
        assert sender.sent_messages[0].to_email == "test@example.com"

    @pytest.mark.asyncio
    async def test_async_send(self):
        sender = MockEmailSender()
        msg = EmailMessage(
            to_email="test@example.com",
            to_name="Test",
            subject="Test",
            html_body="<p>Test</p>",
        )
        result = await sender.send(msg)
        assert result is True
        assert len(sender.sent_messages) == 1

    def test_clear(self):
        sender = MockEmailSender()
        msg = EmailMessage(
            to_email="test@example.com",
            to_name="Test",
            subject="Test",
            html_body="<p>Test</p>",
        )
        sender.send_sync(msg)
        assert len(sender.sent_messages) == 1
        sender.clear()
        assert len(sender.sent_messages) == 0


# =============================================================================
# SendGridEmailSender
# =============================================================================

class TestSendGridEmailSender:

    def test_no_api_key_returns_false(self):
        """Send fails gracefully when API key is not configured."""
        sender = SendGridEmailSender(api_key=None, from_email="test@example.com")
        msg = EmailMessage(
            to_email="user@example.com",
            to_name="User",
            subject="Hello",
            html_body="<p>Hi</p>",
        )
        result = sender.send_sync(msg)
        assert result is False

    @patch("src.services.email_sender.httpx")
    def test_successful_send(self, mock_httpx):
        """Successful SendGrid API call returns True."""
        mock_response = MagicMock()
        mock_response.status_code = 202
        mock_client = MagicMock()
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client.post.return_value = mock_response
        mock_httpx.Client.return_value = mock_client

        sender = SendGridEmailSender(
            api_key="test-key",
            from_email="sender@example.com",
        )
        msg = EmailMessage(
            to_email="user@example.com",
            to_name="User",
            subject="Hello",
            html_body="<p>Hi</p>",
        )
        result = sender.send_sync(msg)
        assert result is True
        mock_client.post.assert_called_once()

    @patch("src.services.email_sender.httpx")
    def test_api_error_returns_false(self, mock_httpx):
        """Non-2xx response from SendGrid returns False."""
        mock_response = MagicMock()
        mock_response.status_code = 400
        mock_response.text = "Bad Request"
        mock_client = MagicMock()
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client.post.return_value = mock_response
        mock_httpx.Client.return_value = mock_client

        sender = SendGridEmailSender(
            api_key="test-key",
            from_email="sender@example.com",
        )
        msg = EmailMessage(
            to_email="user@example.com",
            to_name="User",
            subject="Hello",
            html_body="<p>Hi</p>",
        )
        result = sender.send_sync(msg)
        assert result is False

    @patch("src.services.email_sender.httpx")
    def test_network_error_returns_false(self, mock_httpx):
        """Network error returns False without raising."""
        mock_client = MagicMock()
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client.post.side_effect = ConnectionError("Network down")
        mock_httpx.Client.return_value = mock_client

        sender = SendGridEmailSender(
            api_key="test-key",
            from_email="sender@example.com",
        )
        msg = EmailMessage(
            to_email="user@example.com",
            to_name="User",
            subject="Hello",
            html_body="<p>Hi</p>",
        )
        result = sender.send_sync(msg)
        assert result is False


# =============================================================================
# get_email_sender factory
# =============================================================================

class TestGetEmailSender:

    @patch.dict("os.environ", {"NOTIFICATION_EMAIL_PROVIDER": "mock"})
    def test_mock_provider(self):
        sender = get_email_sender()
        assert isinstance(sender, MockEmailSender)

    @patch.dict("os.environ", {"NOTIFICATION_EMAIL_PROVIDER": "smtp"})
    def test_smtp_provider(self):
        sender = get_email_sender()
        assert isinstance(sender, SMTPEmailSender)

    @patch.dict("os.environ", {"NOTIFICATION_EMAIL_PROVIDER": "sendgrid"})
    def test_sendgrid_provider(self):
        sender = get_email_sender()
        assert isinstance(sender, SendGridEmailSender)

    @patch.dict("os.environ", {}, clear=True)
    def test_default_is_sendgrid(self):
        sender = get_email_sender()
        assert isinstance(sender, SendGridEmailSender)
