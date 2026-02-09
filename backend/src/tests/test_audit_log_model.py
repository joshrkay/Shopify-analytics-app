"""Tests for canonical audit log model behavior."""

from datetime import datetime, timezone

from src.platform.audit import AuditEvent, AuditOutcome


def test_audit_event_redacts_pii():
    event = AuditEvent(
        tenant_id="tenant-1",
        action="auth.login_success",
        user_id="user-1",
        metadata={
            "email": "user@example.com",
            "token": "secret-token",
        },
    )

    payload = event.to_dict()

    assert payload["event_metadata"]["email"] == "***@example.com"
    assert payload["event_metadata"]["token"] == "[REDACTED]"


def test_audit_event_sets_event_type_and_success():
    now = datetime.now(timezone.utc)
    event = AuditEvent(
        tenant_id="tenant-1",
        action="dashboard.viewed",
        user_id="user-1",
        timestamp=now,
        outcome=AuditOutcome.SUCCESS,
    )

    payload = event.to_dict()

    assert payload["event_type"] == "dashboard.viewed"
    assert payload["created_at"] == now
    assert payload["success"] is True
