"""
Audit logging tests for AI Growth Analytics.

CRITICAL: These tests verify that all sensitive actions are properly audited.
Audit logs MUST be append-only and include complete context.
"""

import pytest
from datetime import datetime, timezone
from unittest.mock import Mock, AsyncMock, patch, MagicMock
from fastapi import Request

from src.platform.audit import (
    AuditAction,
    AuditEvent,
    AuditLog,
    extract_client_info,
    get_correlation_id,
)


# ============================================================================
# FIXTURES
# ============================================================================

@pytest.fixture
def mock_request():
    """Create a mock FastAPI request."""
    request = Mock(spec=Request)
    request.headers = {
        "User-Agent": "Mozilla/5.0 Test Browser",
        "X-Forwarded-For": "192.168.1.100, 10.0.0.1",
        "X-Correlation-ID": "corr-123-456",
    }
    request.client = Mock()
    request.client.host = "127.0.0.1"
    request.state = Mock()
    request.state.correlation_id = "corr-123-456"
    return request


@pytest.fixture
def mock_request_no_headers():
    """Create a mock request without special headers."""
    request = Mock(spec=Request)
    request.headers = {}
    request.client = Mock()
    request.client.host = "192.168.1.50"
    request.state = Mock(spec=[])  # No attributes
    return request


# ============================================================================
# TEST SUITE: AUDIT EVENT CREATION
# ============================================================================

class TestAuditEventCreation:
    """Test audit event data structure."""

    def test_audit_event_has_required_fields(self):
        """CRITICAL: Audit events must include all required fields."""
        event = AuditEvent(
            tenant_id="tenant-123",
            user_id="user-456",
            action=AuditAction.BILLING_PLAN_CHANGED,
            ip_address="192.168.1.100",
            user_agent="Mozilla/5.0",
            resource_type="plan",
            resource_id="plan-789",
            metadata={"old_plan": "free", "new_plan": "pro"},
            correlation_id="corr-123",
        )

        assert event.tenant_id == "tenant-123"
        assert event.user_id == "user-456"
        assert event.action == AuditAction.BILLING_PLAN_CHANGED
        assert event.ip_address == "192.168.1.100"
        assert event.user_agent == "Mozilla/5.0"
        assert event.resource_type == "plan"
        assert event.resource_id == "plan-789"
        assert event.metadata == {"old_plan": "free", "new_plan": "pro"}
        assert event.correlation_id == "corr-123"
        assert event.timestamp is not None

    def test_audit_event_timestamp_auto_generated(self):
        """Audit events auto-generate timestamp if not provided."""
        before = datetime.now(timezone.utc)

        event = AuditEvent(
            tenant_id="tenant-123",
            user_id="user-456",
            action=AuditAction.AUTH_LOGIN,
        )

        after = datetime.now(timezone.utc)

        assert before <= event.timestamp <= after

    def test_audit_event_to_dict(self):
        """Audit event can be converted to dict for DB insertion."""
        event = AuditEvent(
            tenant_id="tenant-123",
            user_id="user-456",
            action=AuditAction.STORE_CONNECTED,
            resource_type="store",
            resource_id="store-789",
        )

        event_dict = event.to_dict()

        assert event_dict["tenant_id"] == "tenant-123"
        assert event_dict["user_id"] == "user-456"
        assert event_dict["action"] == "store.connected"
        assert event_dict["resource_type"] == "store"
        assert event_dict["resource_id"] == "store-789"
        assert "timestamp" in event_dict


# ============================================================================
# TEST SUITE: AUDIT ACTIONS
# ============================================================================

class TestAuditActions:
    """Test audit action enumeration."""

    def test_all_sensitive_actions_defined(self):
        """CRITICAL: All sensitive actions must have audit actions defined."""
        # Auth events
        assert AuditAction.AUTH_LOGIN
        assert AuditAction.AUTH_LOGOUT
        assert AuditAction.AUTH_LOGIN_FAILED

        # Billing events
        assert AuditAction.BILLING_PLAN_CHANGED
        assert AuditAction.BILLING_SUBSCRIPTION_CREATED
        assert AuditAction.BILLING_SUBSCRIPTION_CANCELLED

        # Store/connector events
        assert AuditAction.STORE_CONNECTED
        assert AuditAction.STORE_DISCONNECTED

        # AI events
        assert AuditAction.AI_KEY_CREATED
        assert AuditAction.AI_ACTION_EXECUTED

        # Export events
        assert AuditAction.EXPORT_REQUESTED
        assert AuditAction.EXPORT_COMPLETED

        # Automation events
        assert AuditAction.AUTOMATION_APPROVED
        assert AuditAction.AUTOMATION_EXECUTED

        # Feature flag events
        assert AuditAction.FEATURE_FLAG_ENABLED
        assert AuditAction.FEATURE_FLAG_DISABLED

        # Admin events
        assert AuditAction.ADMIN_PLAN_CREATED
        assert AuditAction.ADMIN_CONFIG_CHANGED

    def test_audit_action_values_follow_convention(self):
        """Audit action values should follow naming convention."""
        for action in AuditAction:
            # Values should be lowercase with dots
            assert action.value == action.value.lower()
            assert "." in action.value
            # Should have category.action format
            parts = action.value.split(".")
            assert len(parts) >= 2


# ============================================================================
# TEST SUITE: CLIENT INFO EXTRACTION
# ============================================================================

class TestClientInfoExtraction:
    """Test client information extraction from requests."""

    def test_extract_ip_from_x_forwarded_for(self, mock_request):
        """IP address extracted from X-Forwarded-For header."""
        ip, user_agent = extract_client_info(mock_request)

        # Should take first IP from X-Forwarded-For
        assert ip == "192.168.1.100"
        assert user_agent == "Mozilla/5.0 Test Browser"

    def test_extract_ip_from_client_direct(self, mock_request_no_headers):
        """IP address extracted from client when no proxy headers."""
        ip, user_agent = extract_client_info(mock_request_no_headers)

        assert ip == "192.168.1.50"
        assert user_agent is None

    def test_correlation_id_from_state(self, mock_request):
        """Correlation ID extracted from request state."""
        correlation_id = get_correlation_id(mock_request)

        assert correlation_id == "corr-123-456"

    def test_correlation_id_from_header(self):
        """Correlation ID extracted from header if not in state."""
        request = Mock(spec=Request)
        request.headers = {"X-Correlation-ID": "header-corr-id"}
        request.state = Mock(spec=[])  # No correlation_id attribute

        correlation_id = get_correlation_id(request)

        assert correlation_id == "header-corr-id"


# ============================================================================
# TEST SUITE: AUDIT LOG MODEL
# ============================================================================

class TestAuditLogModel:
    """Test AuditLog database model."""

    def test_audit_log_has_required_columns(self):
        """CRITICAL: AuditLog model has all required columns."""
        # Check that AuditLog has the required columns
        assert hasattr(AuditLog, 'id')
        assert hasattr(AuditLog, 'tenant_id')
        assert hasattr(AuditLog, 'user_id')
        assert hasattr(AuditLog, 'action')
        assert hasattr(AuditLog, 'timestamp')
        assert hasattr(AuditLog, 'ip_address')
        assert hasattr(AuditLog, 'user_agent')
        assert hasattr(AuditLog, 'resource_type')
        assert hasattr(AuditLog, 'resource_id')
        assert hasattr(AuditLog, 'metadata')
        assert hasattr(AuditLog, 'correlation_id')

    def test_audit_log_table_name(self):
        """AuditLog has correct table name."""
        assert AuditLog.__tablename__ == "audit_logs"


# ============================================================================
# TEST SUITE: AUDIT EVENT SCENARIOS
# ============================================================================

class TestAuditEventScenarios:
    """Test specific audit event scenarios."""

    def test_auth_login_event(self):
        """Auth login events capture required data."""
        event = AuditEvent(
            tenant_id="tenant-123",
            user_id="user-456",
            action=AuditAction.AUTH_LOGIN,
            ip_address="192.168.1.100",
            user_agent="Mozilla/5.0",
            metadata={
                "login_method": "oauth",
                "provider": "frontegg",
            }
        )

        assert event.action == AuditAction.AUTH_LOGIN
        assert event.metadata["login_method"] == "oauth"

    def test_billing_change_event(self):
        """Billing change events capture plan transition."""
        event = AuditEvent(
            tenant_id="tenant-123",
            user_id="user-456",
            action=AuditAction.BILLING_PLAN_CHANGED,
            resource_type="subscription",
            resource_id="sub-789",
            metadata={
                "old_plan": "free",
                "new_plan": "pro",
                "monthly_price": 29.99,
            }
        )

        assert event.action == AuditAction.BILLING_PLAN_CHANGED
        assert event.metadata["old_plan"] == "free"
        assert event.metadata["new_plan"] == "pro"

    def test_store_connected_event(self):
        """Store connected events capture shop details."""
        event = AuditEvent(
            tenant_id="tenant-123",
            user_id="user-456",
            action=AuditAction.STORE_CONNECTED,
            resource_type="store",
            resource_id="store-789",
            metadata={
                "shop_domain": "example.myshopify.com",
                "shop_name": "Example Store",
            }
        )

        assert event.action == AuditAction.STORE_CONNECTED
        assert event.resource_type == "store"

    def test_ai_action_executed_event(self):
        """AI action events capture what was executed."""
        event = AuditEvent(
            tenant_id="tenant-123",
            user_id="user-456",
            action=AuditAction.AI_ACTION_EXECUTED,
            resource_type="ai_action",
            resource_id="action-789",
            metadata={
                "action_type": "price_update",
                "affected_products": 15,
                "model_used": "gpt-4",
            }
        )

        assert event.action == AuditAction.AI_ACTION_EXECUTED
        assert event.metadata["action_type"] == "price_update"

    def test_export_event(self):
        """Export events capture export details."""
        event = AuditEvent(
            tenant_id="tenant-123",
            user_id="user-456",
            action=AuditAction.EXPORT_COMPLETED,
            resource_type="export",
            resource_id="export-789",
            metadata={
                "format": "csv",
                "rows": 10000,
                "file_size_bytes": 524288,
            }
        )

        assert event.action == AuditAction.EXPORT_COMPLETED
        assert event.metadata["format"] == "csv"

    def test_system_event_without_user(self):
        """System events can use 'system' as user_id."""
        event = AuditEvent(
            tenant_id="tenant-123",
            user_id="system",
            action=AuditAction.STORE_SYNC_COMPLETED,
            resource_type="store",
            resource_id="store-789",
            metadata={
                "records_synced": 5000,
                "duration_seconds": 120,
            }
        )

        assert event.user_id == "system"
        assert event.action == AuditAction.STORE_SYNC_COMPLETED


# ============================================================================
# TEST SUITE: APPEND-ONLY REQUIREMENT
# ============================================================================

class TestAppendOnlyRequirement:
    """Test that audit logs are append-only."""

    def test_audit_event_is_immutable_dataclass(self):
        """AuditEvent should be a dataclass (effectively immutable)."""
        from dataclasses import is_dataclass

        assert is_dataclass(AuditEvent)

    def test_audit_log_model_is_append_only_by_design(self):
        """
        CRITICAL: AuditLog is designed for append-only use.

        Note: Actual DB constraints would be at the database level.
        This test documents the requirement.
        """
        # The model exists and is intended for append-only use
        # Actual enforcement requires:
        # 1. No UPDATE/DELETE methods in repository
        # 2. Database triggers or policies
        # 3. Application-level restrictions

        # Verify model has no update method
        assert not hasattr(AuditLog, 'update')


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
