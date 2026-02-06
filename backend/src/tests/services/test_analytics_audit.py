"""
Tests for Superset analytics audit event emitters (Story 5.1.7).

Validates:
- Each emit function creates audit log with correct action/metadata
- DENIED outcome for access_denied and cross_tenant_blocked
- All emitters swallow exceptions (never crash caller)
- AuditAction enum has all analytics entries

Story 5.1.7 - Audit Logging
"""

import logging
from unittest.mock import patch, MagicMock, ANY

import pytest

from src.platform.audit import AuditAction, AuditOutcome
from src.platform.audit_events import AUDITABLE_EVENTS
from src.services.audit_logger import (
    emit_dashboard_viewed,
    emit_explore_accessed,
    emit_access_denied,
    emit_cross_tenant_blocked,
    emit_token_generated,
    emit_token_refreshed,
)


# =============================================================================
# AUDIT ACTION ENUM
# =============================================================================


class TestAuditActionEntries:
    """Verify all analytics AuditAction entries exist."""

    def test_dashboard_viewed_action(self):
        assert AuditAction.ANALYTICS_DASHBOARD_VIEWED == "analytics.dashboard.viewed"

    def test_explore_accessed_action(self):
        assert AuditAction.ANALYTICS_EXPLORE_ACCESSED == "analytics.explore.accessed"

    def test_access_denied_action(self):
        assert AuditAction.ANALYTICS_ACCESS_DENIED == "analytics.access.denied"

    def test_cross_tenant_blocked_action(self):
        assert AuditAction.ANALYTICS_CROSS_TENANT_BLOCKED == "analytics.cross_tenant.blocked"

    def test_token_generated_action(self):
        assert AuditAction.ANALYTICS_TOKEN_GENERATED == "analytics.token.generated"

    def test_token_refreshed_action(self):
        assert AuditAction.ANALYTICS_TOKEN_REFRESHED == "analytics.token.refreshed"

    def test_token_expired_action(self):
        assert AuditAction.ANALYTICS_TOKEN_EXPIRED == "analytics.token.expired"


# =============================================================================
# AUDITABLE EVENTS REGISTRY
# =============================================================================


class TestAuditableEventsRegistry:
    """Verify analytics events are in the AUDITABLE_EVENTS registry."""

    def test_dashboard_viewed_in_registry(self):
        assert "analytics.dashboard.viewed" in AUDITABLE_EVENTS

    def test_explore_accessed_in_registry(self):
        assert "analytics.explore.accessed" in AUDITABLE_EVENTS

    def test_access_denied_in_registry(self):
        assert "analytics.access.denied" in AUDITABLE_EVENTS

    def test_cross_tenant_blocked_in_registry(self):
        assert "analytics.cross_tenant.blocked" in AUDITABLE_EVENTS

    def test_token_generated_in_registry(self):
        assert "analytics.token.generated" in AUDITABLE_EVENTS

    def test_token_refreshed_in_registry(self):
        assert "analytics.token.refreshed" in AUDITABLE_EVENTS

    def test_token_expired_in_registry(self):
        assert "analytics.token.expired" in AUDITABLE_EVENTS

    def test_dashboard_viewed_required_fields(self):
        fields = AUDITABLE_EVENTS["analytics.dashboard.viewed"]
        assert "user_id" in fields
        assert "tenant_id" in fields
        assert "dashboard_id" in fields

    def test_access_denied_required_fields(self):
        fields = AUDITABLE_EVENTS["analytics.access.denied"]
        assert "user_id" in fields
        assert "tenant_id" in fields
        assert "reason" in fields
        assert "path" in fields

    def test_cross_tenant_blocked_required_fields(self):
        fields = AUDITABLE_EVENTS["analytics.cross_tenant.blocked"]
        assert "user_id" in fields
        assert "tenant_id" in fields
        assert "attempted_tenant_id" in fields


# =============================================================================
# EMIT DASHBOARD VIEWED
# =============================================================================


class TestEmitDashboardViewed:
    """Test emit_dashboard_viewed emitter."""

    @patch("src.services.audit_logger.logging")
    def test_calls_log_system_audit(self, mock_logging):
        db = MagicMock()
        with patch(
            "src.platform.audit.log_system_audit_event_sync"
        ) as mock_log:
            emit_dashboard_viewed(
                db=db,
                tenant_id="tenant_abc",
                user_id="user_001",
                dashboard_id="dash_001",
            )
            mock_log.assert_called_once()
            call_kwargs = mock_log.call_args
            assert call_kwargs.kwargs["action"] == AuditAction.ANALYTICS_DASHBOARD_VIEWED
            assert call_kwargs.kwargs["outcome"] == AuditOutcome.SUCCESS
            assert call_kwargs.kwargs["tenant_id"] == "tenant_abc"

    def test_swallows_exceptions(self):
        """Audit emitter must never crash the caller."""
        db = MagicMock()
        with patch(
            "src.platform.audit.log_system_audit_event_sync",
            side_effect=Exception("DB down"),
        ):
            # Should not raise
            emit_dashboard_viewed(
                db=db,
                tenant_id="tenant_abc",
                user_id="user_001",
                dashboard_id="dash_001",
            )


# =============================================================================
# EMIT EXPLORE ACCESSED
# =============================================================================


class TestEmitExploreAccessed:
    """Test emit_explore_accessed emitter."""

    @patch("src.services.audit_logger.logging")
    def test_calls_log_system_audit(self, mock_logging):
        db = MagicMock()
        with patch(
            "src.platform.audit.log_system_audit_event_sync"
        ) as mock_log:
            emit_explore_accessed(
                db=db,
                tenant_id="tenant_abc",
                user_id="user_001",
                dataset_name="fact_orders",
            )
            mock_log.assert_called_once()
            call_kwargs = mock_log.call_args
            assert call_kwargs.kwargs["action"] == AuditAction.ANALYTICS_EXPLORE_ACCESSED

    def test_swallows_exceptions(self):
        db = MagicMock()
        with patch(
            "src.platform.audit.log_system_audit_event_sync",
            side_effect=RuntimeError("fail"),
        ):
            emit_explore_accessed(
                db=db,
                tenant_id="tenant_abc",
                user_id="user_001",
                dataset_name="fact_orders",
            )


# =============================================================================
# EMIT ACCESS DENIED
# =============================================================================


class TestEmitAccessDenied:
    """Test emit_access_denied emitter."""

    @patch("src.services.audit_logger.logging")
    def test_outcome_is_denied(self, mock_logging):
        db = MagicMock()
        with patch(
            "src.platform.audit.log_system_audit_event_sync"
        ) as mock_log:
            emit_access_denied(
                db=db,
                tenant_id="tenant_abc",
                user_id="user_001",
                reason="missing_token",
                path="/superset/dashboard/1/",
            )
            mock_log.assert_called_once()
            call_kwargs = mock_log.call_args
            assert call_kwargs.kwargs["action"] == AuditAction.ANALYTICS_ACCESS_DENIED
            assert call_kwargs.kwargs["outcome"] == AuditOutcome.DENIED

    def test_handles_unknown_tenant(self):
        """When tenant is unknown, should still log."""
        db = MagicMock()
        with patch(
            "src.platform.audit.log_system_audit_event_sync"
        ) as mock_log:
            emit_access_denied(
                db=db,
                tenant_id="",
                user_id="",
                reason="missing_token",
                path="/api/v1/chart/data",
            )
            mock_log.assert_called_once()
            call_kwargs = mock_log.call_args
            assert call_kwargs.kwargs["tenant_id"] == "unknown"

    def test_swallows_exceptions(self):
        db = MagicMock()
        with patch(
            "src.platform.audit.log_system_audit_event_sync",
            side_effect=Exception("DB down"),
        ):
            emit_access_denied(
                db=db,
                tenant_id="tenant_abc",
                user_id="user_001",
                reason="invalid_token",
                path="/api/v1/chart/data",
            )


# =============================================================================
# EMIT CROSS TENANT BLOCKED
# =============================================================================


class TestEmitCrossTenantBlocked:
    """Test emit_cross_tenant_blocked emitter."""

    @patch("src.services.audit_logger.logging")
    def test_outcome_is_denied(self, mock_logging):
        db = MagicMock()
        with patch(
            "src.platform.audit.log_system_audit_event_sync"
        ) as mock_log:
            emit_cross_tenant_blocked(
                db=db,
                tenant_id="tenant_abc",
                user_id="user_001",
                attempted_tenant_id="tenant_xyz",
            )
            mock_log.assert_called_once()
            call_kwargs = mock_log.call_args
            assert call_kwargs.kwargs["action"] == AuditAction.ANALYTICS_CROSS_TENANT_BLOCKED
            assert call_kwargs.kwargs["outcome"] == AuditOutcome.DENIED

    def test_metadata_includes_attempted_tenant(self):
        db = MagicMock()
        with patch(
            "src.platform.audit.log_system_audit_event_sync"
        ) as mock_log:
            emit_cross_tenant_blocked(
                db=db,
                tenant_id="tenant_abc",
                user_id="user_001",
                attempted_tenant_id="tenant_xyz",
            )
            metadata = mock_log.call_args.kwargs["metadata"]
            assert metadata["attempted_tenant_id"] == "tenant_xyz"

    def test_swallows_exceptions(self):
        db = MagicMock()
        with patch(
            "src.platform.audit.log_system_audit_event_sync",
            side_effect=Exception("DB down"),
        ):
            emit_cross_tenant_blocked(
                db=db,
                tenant_id="tenant_abc",
                user_id="user_001",
                attempted_tenant_id="tenant_xyz",
            )


# =============================================================================
# EMIT TOKEN GENERATED
# =============================================================================


class TestEmitTokenGenerated:
    """Test emit_token_generated emitter."""

    @patch("src.services.audit_logger.logging")
    def test_calls_log_system_audit(self, mock_logging):
        db = MagicMock()
        with patch(
            "src.platform.audit.log_system_audit_event_sync"
        ) as mock_log:
            emit_token_generated(
                db=db,
                tenant_id="tenant_abc",
                user_id="user_001",
                dashboard_id="dash_001",
            )
            mock_log.assert_called_once()
            call_kwargs = mock_log.call_args
            assert call_kwargs.kwargs["action"] == AuditAction.ANALYTICS_TOKEN_GENERATED
            assert call_kwargs.kwargs["outcome"] == AuditOutcome.SUCCESS

    def test_swallows_exceptions(self):
        db = MagicMock()
        with patch(
            "src.platform.audit.log_system_audit_event_sync",
            side_effect=Exception("DB down"),
        ):
            emit_token_generated(
                db=db,
                tenant_id="tenant_abc",
                user_id="user_001",
                dashboard_id="dash_001",
            )


# =============================================================================
# EMIT TOKEN REFRESHED
# =============================================================================


class TestEmitTokenRefreshed:
    """Test emit_token_refreshed emitter."""

    @patch("src.services.audit_logger.logging")
    def test_calls_log_system_audit(self, mock_logging):
        db = MagicMock()
        with patch(
            "src.platform.audit.log_system_audit_event_sync"
        ) as mock_log:
            emit_token_refreshed(
                db=db,
                tenant_id="tenant_abc",
                user_id="user_001",
                dashboard_id="dash_001",
            )
            mock_log.assert_called_once()
            call_kwargs = mock_log.call_args
            assert call_kwargs.kwargs["action"] == AuditAction.ANALYTICS_TOKEN_REFRESHED
            assert call_kwargs.kwargs["outcome"] == AuditOutcome.SUCCESS

    def test_swallows_exceptions(self):
        db = MagicMock()
        with patch(
            "src.platform.audit.log_system_audit_event_sync",
            side_effect=Exception("DB down"),
        ):
            emit_token_refreshed(
                db=db,
                tenant_id="tenant_abc",
                user_id="user_001",
                dashboard_id="dash_001",
            )


# =============================================================================
# CORRELATION ID SUPPORT
# =============================================================================


class TestCorrelationId:
    """All emitters should pass through correlation_id."""

    @patch("src.services.audit_logger.logging")
    def test_dashboard_viewed_correlation(self, mock_logging):
        db = MagicMock()
        with patch(
            "src.platform.audit.log_system_audit_event_sync"
        ) as mock_log:
            emit_dashboard_viewed(
                db=db,
                tenant_id="t",
                user_id="u",
                dashboard_id="d",
                correlation_id="corr-123",
            )
            assert mock_log.call_args.kwargs["correlation_id"] == "corr-123"

    @patch("src.services.audit_logger.logging")
    def test_access_denied_correlation(self, mock_logging):
        db = MagicMock()
        with patch(
            "src.platform.audit.log_system_audit_event_sync"
        ) as mock_log:
            emit_access_denied(
                db=db,
                tenant_id="t",
                user_id="u",
                reason="r",
                path="/p",
                correlation_id="corr-456",
            )
            assert mock_log.call_args.kwargs["correlation_id"] == "corr-456"
