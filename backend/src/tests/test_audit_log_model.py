"""
Tests for GA Audit Log Model, PII sanitization, and correlation ID generation.

CRITICAL: Verifies:
- Schema columns match GA requirements
- PII is automatically sanitized in metadata
- Correlation ID is generated for every event
- Event types are validated
- Append-only model design

Matches: models/audit_log.py
"""

import uuid
import pytest
from datetime import datetime, timezone
from dataclasses import is_dataclass

from src.models.audit_log import (
    GAAuditLog,
    GAAuditEvent,
    AuditEventType,
    AccessSurface,
    PIISanitizer,
    generate_correlation_id,
)


# ============================================================================
# FIXTURES
# ============================================================================

@pytest.fixture
def sample_event():
    """Create a sample GA audit event."""
    return GAAuditEvent(
        event_type=AuditEventType.AUTH_LOGIN_SUCCESS,
        tenant_id="tenant-123",
        user_id="user-456",
        access_surface=AccessSurface.EXTERNAL_APP,
        success=True,
        metadata={"ip_address": "192.168.1.1"},
    )


@pytest.fixture
def sample_event_with_pii():
    """Create a GA audit event with PII in metadata."""
    return GAAuditEvent(
        event_type=AuditEventType.AUTH_LOGIN_FAILED,
        tenant_id="tenant-123",
        user_id="user-456",
        success=False,
        metadata={
            "email": "user@example.com",
            "token": "secret-jwt-token",
            "reason": "invalid_credentials",
            "ip_address": "10.0.0.1",
        },
    )


# ============================================================================
# TEST SUITE: GAAuditLog MODEL SCHEMA
# ============================================================================

class TestGAAuditLogModel:
    """Test GA audit log database model schema requirements."""

    def test_has_all_required_columns(self):
        """CRITICAL: Model has all GA-required columns."""
        assert hasattr(GAAuditLog, "id")
        assert hasattr(GAAuditLog, "event_type")
        assert hasattr(GAAuditLog, "user_id")
        assert hasattr(GAAuditLog, "tenant_id")
        assert hasattr(GAAuditLog, "dashboard_id")
        assert hasattr(GAAuditLog, "access_surface")
        assert hasattr(GAAuditLog, "success")
        assert hasattr(GAAuditLog, "metadata")
        assert hasattr(GAAuditLog, "correlation_id")
        assert hasattr(GAAuditLog, "created_at")

    def test_table_name(self):
        """Model uses correct table name."""
        assert GAAuditLog.__tablename__ == "ga_audit_logs"

    def test_model_does_not_have_update_method(self):
        """Append-only: model should not have an update method."""
        assert not hasattr(GAAuditLog, "update")


# ============================================================================
# TEST SUITE: AUDIT EVENT TYPES
# ============================================================================

class TestAuditEventType:
    """Test GA-scope audit event type enum."""

    def test_auth_event_types_exist(self):
        """All auth event types are defined."""
        assert AuditEventType.AUTH_LOGIN_SUCCESS.value == "auth.login_success"
        assert AuditEventType.AUTH_LOGIN_FAILED.value == "auth.login_failed"
        assert AuditEventType.AUTH_JWT_ISSUED.value == "auth.jwt_issued"
        assert AuditEventType.AUTH_JWT_REFRESH.value == "auth.jwt_refresh"
        assert AuditEventType.AUTH_JWT_REVOKED.value == "auth.jwt_revoked"

    def test_dashboard_event_types_exist(self):
        """All dashboard event types are defined."""
        assert AuditEventType.DASHBOARD_VIEWED.value == "dashboard.viewed"
        assert AuditEventType.DASHBOARD_LOAD_FAILED.value == "dashboard.load_failed"
        assert AuditEventType.DASHBOARD_ACCESS_DENIED.value == "dashboard.access_denied"

    def test_all_event_types_follow_dot_notation(self):
        """All event types use category.action format."""
        for evt in AuditEventType:
            parts = evt.value.split(".")
            assert len(parts) == 2, f"{evt.value} should have category.action format"
            assert parts[0] in ("auth", "dashboard")

    def test_event_type_count_is_eight(self):
        """GA scope has exactly 8 event types."""
        assert len(AuditEventType) == 8


# ============================================================================
# TEST SUITE: ACCESS SURFACE
# ============================================================================

class TestAccessSurface:
    """Test access surface enum."""

    def test_has_shopify_embed(self):
        assert AccessSurface.SHOPIFY_EMBED.value == "shopify_embed"

    def test_has_external_app(self):
        assert AccessSurface.EXTERNAL_APP.value == "external_app"

    def test_only_two_values(self):
        assert len(AccessSurface) == 2


# ============================================================================
# TEST SUITE: GA AUDIT EVENT (DATACLASS)
# ============================================================================

class TestGAAuditEvent:
    """Test GA audit event data structure."""

    def test_is_dataclass(self):
        """GAAuditEvent should be a dataclass."""
        assert is_dataclass(GAAuditEvent)

    def test_required_fields_populated(self, sample_event):
        """Event has all required fields populated."""
        assert sample_event.event_type == AuditEventType.AUTH_LOGIN_SUCCESS
        assert sample_event.tenant_id == "tenant-123"
        assert sample_event.user_id == "user-456"
        assert sample_event.success is True

    def test_correlation_id_auto_generated(self):
        """Correlation ID is auto-generated if not provided."""
        event = GAAuditEvent(event_type=AuditEventType.AUTH_LOGIN_SUCCESS)
        assert event.correlation_id is not None
        assert len(event.correlation_id) == 36  # UUID format

    def test_created_at_auto_generated(self):
        """created_at is auto-generated if not provided."""
        before = datetime.now(timezone.utc)
        event = GAAuditEvent(event_type=AuditEventType.DASHBOARD_VIEWED)
        after = datetime.now(timezone.utc)
        assert before <= event.created_at <= after

    def test_to_dict_returns_all_fields(self, sample_event):
        """to_dict includes all required fields."""
        d = sample_event.to_dict()
        assert "event_type" in d
        assert "tenant_id" in d
        assert "user_id" in d
        assert "dashboard_id" in d
        assert "access_surface" in d
        assert "success" in d
        assert "metadata" in d
        assert "correlation_id" in d
        assert "created_at" in d

    def test_to_dict_event_type_is_string(self, sample_event):
        """Event type in dict is a string value, not the enum."""
        d = sample_event.to_dict()
        assert d["event_type"] == "auth.login_success"
        assert isinstance(d["event_type"], str)

    def test_to_dict_access_surface_is_string(self, sample_event):
        """Access surface in dict is a string value."""
        d = sample_event.to_dict()
        assert d["access_surface"] == "external_app"
        assert isinstance(d["access_surface"], str)

    def test_to_dict_sanitizes_pii(self, sample_event_with_pii):
        """CRITICAL: PII is sanitized when converting to dict."""
        d = sample_event_with_pii.to_dict()
        metadata = d["metadata"]

        assert metadata["email"] == "***@example.com"
        assert metadata["token"] == "[REDACTED]"
        assert metadata["reason"] == "invalid_credentials"  # Not PII
        assert metadata["ip_address"] == "10.0.0.1"  # Not PII

    def test_dashboard_event_with_dashboard_id(self):
        """Dashboard events can include dashboard_id."""
        event = GAAuditEvent(
            event_type=AuditEventType.DASHBOARD_VIEWED,
            tenant_id="tenant-123",
            user_id="user-456",
            dashboard_id="overview",
            access_surface=AccessSurface.SHOPIFY_EMBED,
        )
        d = event.to_dict()
        assert d["dashboard_id"] == "overview"
        assert d["access_surface"] == "shopify_embed"

    def test_failed_event_success_false(self):
        """Failed events have success=False."""
        event = GAAuditEvent(
            event_type=AuditEventType.AUTH_LOGIN_FAILED,
            success=False,
            metadata={"reason": "invalid_token"},
        )
        d = event.to_dict()
        assert d["success"] is False

    def test_nullable_fields_default_to_none(self):
        """Optional fields default to None."""
        event = GAAuditEvent(event_type=AuditEventType.AUTH_LOGIN_FAILED)
        assert event.user_id is None
        assert event.tenant_id is None
        assert event.dashboard_id is None


# ============================================================================
# TEST SUITE: PII SANITIZER
# ============================================================================

class TestPIISanitizer:
    """Test PII sanitization layer."""

    def test_sanitizes_email_to_domain_only(self):
        """Email is replaced with ***@domain.com."""
        data = {"email": "user@example.com", "name": "John"}
        result = PIISanitizer.sanitize(data)
        assert result["email"] == "***@example.com"
        assert result["name"] == "John"

    def test_sanitizes_phone_to_last_four(self):
        """Phone is replaced with ***1234."""
        data = {"phone": "555-123-4567"}
        result = PIISanitizer.sanitize(data)
        assert result["phone"] == "***4567"

    def test_sanitizes_phone_number_field(self):
        """phone_number field is also sanitized."""
        data = {"phone_number": "9876543210"}
        result = PIISanitizer.sanitize(data)
        assert result["phone_number"] == "***3210"

    def test_sanitizes_tokens_completely(self):
        """Tokens and secrets are replaced with [REDACTED]."""
        data = {
            "token": "secret-token-value",
            "access_token": "bearer-token-xyz",
            "refresh_token": "refresh-abc",
            "api_key": "key-456",
            "api_secret": "secret-789",
        }
        result = PIISanitizer.sanitize(data)
        for key in data:
            assert result[key] == "[REDACTED]"

    def test_sanitizes_password_and_credentials(self):
        """Password and credential fields are fully redacted."""
        data = {
            "password": "super-secret",
            "secret": "my-secret",
            "credential": "cred-123",
            "credentials": {"user": "a", "pass": "b"},
        }
        result = PIISanitizer.sanitize(data)
        assert result["password"] == "[REDACTED]"
        assert result["secret"] == "[REDACTED]"
        assert result["credential"] == "[REDACTED]"
        assert result["credentials"] == "[REDACTED]"

    def test_sanitizes_nested_dict(self):
        """PII in nested dicts is sanitized."""
        data = {
            "user": {
                "email": "nested@example.com",
                "role": "admin",
            },
        }
        result = PIISanitizer.sanitize(data)
        assert result["user"]["email"] == "***@example.com"
        assert result["user"]["role"] == "admin"

    def test_sanitizes_pii_in_lists(self):
        """PII in list items (dicts) is sanitized."""
        data = {
            "users": [
                {"email": "a@b.com", "name": "Alice"},
                {"email": "c@d.com", "name": "Bob"},
            ],
        }
        result = PIISanitizer.sanitize(data)
        assert result["users"][0]["email"] == "***@b.com"
        assert result["users"][0]["name"] == "Alice"
        assert result["users"][1]["email"] == "***@d.com"

    def test_preserves_non_pii_fields(self):
        """Non-PII fields are unchanged."""
        data = {
            "action": "login",
            "status": "success",
            "count": 42,
            "enabled": True,
        }
        result = PIISanitizer.sanitize(data)
        assert result == data

    def test_handles_empty_dict(self):
        """Empty dict returns empty dict."""
        assert PIISanitizer.sanitize({}) == {}

    def test_handles_non_dict_input(self):
        """Non-dict input is returned unchanged."""
        assert PIISanitizer.sanitize("not a dict") == "not a dict"
        assert PIISanitizer.sanitize(42) == 42
        assert PIISanitizer.sanitize(None) is None

    def test_handles_none_values_in_pii_fields(self):
        """None values in PII fields are redacted."""
        data = {"email": None, "phone": None}
        result = PIISanitizer.sanitize(data)
        assert result["email"] == "[REDACTED]"
        assert result["phone"] == "[REDACTED]"

    def test_case_insensitive_field_matching(self):
        """PII field matching is case-insensitive."""
        data = {
            "Email": "upper@test.com",
            "PHONE": "9999999999",
            "API_KEY": "key-xyz",
        }
        result = PIISanitizer.sanitize(data)
        assert result["Email"] == "***@test.com"
        assert result["PHONE"] == "***9999"
        assert result["API_KEY"] == "[REDACTED]"

    def test_detects_jwt_like_values(self):
        """Values that look like JWTs are redacted regardless of field name."""
        data = {
            "some_field": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.dozjgNryP4J3jVmNHl0w5N_XgL0n3I9PlFUP0THsR8U",
        }
        result = PIISanitizer.sanitize(data)
        assert result["some_field"] == "[REDACTED]"

    def test_detects_bearer_token_values(self):
        """Values starting with 'Bearer' are redacted."""
        data = {"auth_header": "Bearer some-token-value"}
        result = PIISanitizer.sanitize(data)
        assert result["auth_header"] == "[REDACTED]"

    def test_financial_fields_redacted(self):
        """Financial fields are fully redacted."""
        data = {
            "credit_card": "4111111111111111",
            "card_number": "5500000000000004",
            "cvv": "123",
            "bank_account": "123456789",
        }
        result = PIISanitizer.sanitize(data)
        for key in data:
            assert result[key] == "[REDACTED]"


# ============================================================================
# TEST SUITE: CORRELATION ID
# ============================================================================

class TestCorrelationID:
    """Test correlation ID generation."""

    def test_generates_uuid_format(self):
        """Correlation ID is a valid UUID v4."""
        cid = generate_correlation_id()
        assert len(cid) == 36
        # Should be valid UUID
        uuid.UUID(cid, version=4)

    def test_generates_unique_ids(self):
        """Each call generates a unique ID."""
        ids = {generate_correlation_id() for _ in range(100)}
        assert len(ids) == 100

    def test_event_correlation_id_is_uuid(self):
        """Event correlation_id is a valid UUID."""
        event = GAAuditEvent(event_type=AuditEventType.AUTH_LOGIN_SUCCESS)
        uuid.UUID(event.correlation_id, version=4)


# ============================================================================
# TEST SUITE: EVENT SCENARIOS
# ============================================================================

class TestEventScenarios:
    """Test specific audit event scenarios."""

    def test_auth_login_success_event(self):
        """Auth login success captures required data."""
        event = GAAuditEvent(
            event_type=AuditEventType.AUTH_LOGIN_SUCCESS,
            tenant_id="t-1",
            user_id="u-1",
            access_surface=AccessSurface.SHOPIFY_EMBED,
            success=True,
            metadata={"ip_address": "10.0.0.1", "user_agent": "Chrome"},
        )
        d = event.to_dict()
        assert d["event_type"] == "auth.login_success"
        assert d["success"] is True
        assert d["access_surface"] == "shopify_embed"

    def test_dashboard_access_denied_event(self):
        """Dashboard access denied captures reason."""
        event = GAAuditEvent(
            event_type=AuditEventType.DASHBOARD_ACCESS_DENIED,
            tenant_id="t-1",
            user_id="u-1",
            dashboard_id="sales",
            success=False,
            metadata={"reason": "plan_not_allowed"},
        )
        d = event.to_dict()
        assert d["event_type"] == "dashboard.access_denied"
        assert d["dashboard_id"] == "sales"
        assert d["success"] is False
        assert d["metadata"]["reason"] == "plan_not_allowed"

    def test_jwt_refresh_failed_event(self):
        """JWT refresh failure includes reason code."""
        event = GAAuditEvent(
            event_type=AuditEventType.AUTH_JWT_REFRESH,
            tenant_id="t-1",
            user_id="u-1",
            success=False,
            metadata={"reason": "token_expired"},
        )
        d = event.to_dict()
        assert d["event_type"] == "auth.jwt_refresh"
        assert d["success"] is False
        assert d["metadata"]["reason"] == "token_expired"

    def test_pre_auth_failure_nullable_fields(self):
        """Pre-auth failures can have null user_id and tenant_id."""
        event = GAAuditEvent(
            event_type=AuditEventType.AUTH_LOGIN_FAILED,
            tenant_id=None,
            user_id=None,
            success=False,
            metadata={"reason": "missing_token", "ip_address": "10.0.0.1"},
        )
        d = event.to_dict()
        assert d["user_id"] is None
        assert d["tenant_id"] is None
        assert d["success"] is False
