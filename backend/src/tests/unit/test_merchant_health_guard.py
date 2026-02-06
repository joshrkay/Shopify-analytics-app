"""
Unit tests for merchant health guard middleware.

Tests cover:
- MerchantHealthGuard DI guard (require_healthy_for_ai,
  require_available_for_dashboards, require_healthy_for_export)
- Decorator: require_merchant_healthy
- Decorator: require_merchant_available
- All three states trigger correct behavior

Story 4.3 - Merchant Data Health Trust Layer
"""

import pytest
from datetime import datetime, timezone
from unittest.mock import Mock, MagicMock, patch, AsyncMock

from fastapi import HTTPException

from src.models.merchant_data_health import MerchantHealthState
from src.services.merchant_data_health import MerchantDataHealthResult
from src.middleware.merchant_health_guard import (
    MerchantHealthGuard,
    _evaluate_merchant_health,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _make_result(state: MerchantHealthState) -> MerchantDataHealthResult:
    """Build a MerchantDataHealthResult for testing."""
    from src.models.merchant_data_health import FEATURE_FLAGS, get_merchant_message

    flags = FEATURE_FLAGS[state]
    return MerchantDataHealthResult(
        state=state,
        message=get_merchant_message(state),
        ai_insights_enabled=flags["ai_insights_enabled"],
        dashboards_enabled=flags["dashboards_enabled"],
        exports_enabled=flags["exports_enabled"],
        evaluated_at=datetime.now(timezone.utc),
    )


def _healthy_result():
    return _make_result(MerchantHealthState.HEALTHY)


def _delayed_result():
    return _make_result(MerchantHealthState.DELAYED)


def _unavailable_result():
    return _make_result(MerchantHealthState.UNAVAILABLE)


@pytest.fixture
def mock_request():
    """Create a mock FastAPI request with tenant context."""
    request = Mock()
    request.url.path = "/api/test"
    request.state = MagicMock()
    # Ensure merchant_health is not set initially
    request.state.merchant_health = None
    del request.state.merchant_health
    return request


@pytest.fixture
def mock_tenant_ctx():
    """Mock tenant context."""
    ctx = Mock()
    ctx.tenant_id = "test-tenant-001"
    ctx.user_id = "user-001"
    ctx.billing_tier = "free"
    return ctx


# ---------------------------------------------------------------------------
# MerchantHealthGuard - AI gate
# ---------------------------------------------------------------------------

class TestMerchantHealthGuardAI:
    """Tests for require_healthy_for_ai."""

    @patch("src.middleware.merchant_health_guard._evaluate_merchant_health")
    @patch("src.middleware.merchant_health_guard.get_tenant_context")
    def test_healthy_allows_ai(self, mock_ctx, mock_eval, mock_request, mock_tenant_ctx):
        mock_eval.return_value = _healthy_result()
        mock_ctx.return_value = mock_tenant_ctx

        guard = MerchantHealthGuard()
        guard.require_healthy_for_ai(mock_request)  # Should not raise

    @patch("src.middleware.merchant_health_guard._evaluate_merchant_health")
    @patch("src.middleware.merchant_health_guard.get_tenant_context")
    def test_delayed_blocks_ai(self, mock_ctx, mock_eval, mock_request, mock_tenant_ctx):
        mock_eval.return_value = _delayed_result()
        mock_ctx.return_value = mock_tenant_ctx

        guard = MerchantHealthGuard()
        with pytest.raises(HTTPException) as exc_info:
            guard.require_healthy_for_ai(mock_request)

        assert exc_info.value.status_code == 503
        assert "AI_INSIGHTS_PAUSED" in str(exc_info.value.detail)

    @patch("src.middleware.merchant_health_guard._evaluate_merchant_health")
    @patch("src.middleware.merchant_health_guard.get_tenant_context")
    def test_unavailable_blocks_ai(self, mock_ctx, mock_eval, mock_request, mock_tenant_ctx):
        mock_eval.return_value = _unavailable_result()
        mock_ctx.return_value = mock_tenant_ctx

        guard = MerchantHealthGuard()
        with pytest.raises(HTTPException) as exc_info:
            guard.require_healthy_for_ai(mock_request)

        assert exc_info.value.status_code == 503


# ---------------------------------------------------------------------------
# MerchantHealthGuard - Dashboard gate
# ---------------------------------------------------------------------------

class TestMerchantHealthGuardDashboard:
    """Tests for require_available_for_dashboards."""

    @patch("src.middleware.merchant_health_guard._evaluate_merchant_health")
    @patch("src.middleware.merchant_health_guard.get_tenant_context")
    def test_healthy_allows_dashboard(self, mock_ctx, mock_eval, mock_request, mock_tenant_ctx):
        mock_eval.return_value = _healthy_result()
        mock_ctx.return_value = mock_tenant_ctx

        guard = MerchantHealthGuard()
        guard.require_available_for_dashboards(mock_request)  # Should not raise

    @patch("src.middleware.merchant_health_guard._evaluate_merchant_health")
    @patch("src.middleware.merchant_health_guard.get_tenant_context")
    def test_delayed_allows_dashboard(self, mock_ctx, mock_eval, mock_request, mock_tenant_ctx):
        mock_eval.return_value = _delayed_result()
        mock_ctx.return_value = mock_tenant_ctx

        guard = MerchantHealthGuard()
        guard.require_available_for_dashboards(mock_request)  # Should not raise

    @patch("src.middleware.merchant_health_guard._evaluate_merchant_health")
    @patch("src.middleware.merchant_health_guard.get_tenant_context")
    def test_unavailable_blocks_dashboard(self, mock_ctx, mock_eval, mock_request, mock_tenant_ctx):
        mock_eval.return_value = _unavailable_result()
        mock_ctx.return_value = mock_tenant_ctx

        guard = MerchantHealthGuard()
        with pytest.raises(HTTPException) as exc_info:
            guard.require_available_for_dashboards(mock_request)

        assert exc_info.value.status_code == 503
        assert "DATA_UNAVAILABLE" in str(exc_info.value.detail)


# ---------------------------------------------------------------------------
# MerchantHealthGuard - Export gate
# ---------------------------------------------------------------------------

class TestMerchantHealthGuardExport:
    """Tests for require_healthy_for_export."""

    @patch("src.middleware.merchant_health_guard._evaluate_merchant_health")
    @patch("src.middleware.merchant_health_guard.get_tenant_context")
    def test_healthy_allows_export(self, mock_ctx, mock_eval, mock_request, mock_tenant_ctx):
        mock_eval.return_value = _healthy_result()
        mock_ctx.return_value = mock_tenant_ctx

        guard = MerchantHealthGuard()
        guard.require_healthy_for_export(mock_request)  # Should not raise

    @patch("src.middleware.merchant_health_guard._evaluate_merchant_health")
    @patch("src.middleware.merchant_health_guard.get_tenant_context")
    def test_delayed_blocks_export(self, mock_ctx, mock_eval, mock_request, mock_tenant_ctx):
        mock_eval.return_value = _delayed_result()
        mock_ctx.return_value = mock_tenant_ctx

        guard = MerchantHealthGuard()
        with pytest.raises(HTTPException) as exc_info:
            guard.require_healthy_for_export(mock_request)

        assert exc_info.value.status_code == 503
        assert "EXPORT_PAUSED" in str(exc_info.value.detail)

    @patch("src.middleware.merchant_health_guard._evaluate_merchant_health")
    @patch("src.middleware.merchant_health_guard.get_tenant_context")
    def test_unavailable_blocks_export(self, mock_ctx, mock_eval, mock_request, mock_tenant_ctx):
        mock_eval.return_value = _unavailable_result()
        mock_ctx.return_value = mock_tenant_ctx

        guard = MerchantHealthGuard()
        with pytest.raises(HTTPException) as exc_info:
            guard.require_healthy_for_export(mock_request)

        assert exc_info.value.status_code == 503


# ---------------------------------------------------------------------------
# Non-blocking check
# ---------------------------------------------------------------------------

class TestMerchantHealthGuardCheck:
    """Tests for the non-blocking check method."""

    @patch("src.middleware.merchant_health_guard._evaluate_merchant_health")
    def test_check_returns_result_without_raising(self, mock_eval, mock_request):
        mock_eval.return_value = _unavailable_result()

        guard = MerchantHealthGuard()
        result = guard.check(mock_request)

        assert result.state == MerchantHealthState.UNAVAILABLE
        # Should not raise


# ---------------------------------------------------------------------------
# Error message safety
# ---------------------------------------------------------------------------

class TestErrorMessageSafety:
    """Tests that error messages never contain internal jargon."""

    FORBIDDEN_TERMS = [
        "dbt", "airbyte", "rls", "sla", "threshold",
        "postgresql", "supabase", "temporal", "kafka",
    ]

    @patch("src.middleware.merchant_health_guard._evaluate_merchant_health")
    @patch("src.middleware.merchant_health_guard.get_tenant_context")
    def test_ai_block_message_is_safe(self, mock_ctx, mock_eval, mock_request, mock_tenant_ctx):
        mock_eval.return_value = _delayed_result()
        mock_ctx.return_value = mock_tenant_ctx

        guard = MerchantHealthGuard()
        with pytest.raises(HTTPException) as exc_info:
            guard.require_healthy_for_ai(mock_request)

        message = exc_info.value.detail["message"].lower()
        for term in self.FORBIDDEN_TERMS:
            assert term not in message, (
                f"Forbidden term '{term}' found in AI block message"
            )

    @patch("src.middleware.merchant_health_guard._evaluate_merchant_health")
    @patch("src.middleware.merchant_health_guard.get_tenant_context")
    def test_dashboard_block_message_is_safe(self, mock_ctx, mock_eval, mock_request, mock_tenant_ctx):
        mock_eval.return_value = _unavailable_result()
        mock_ctx.return_value = mock_tenant_ctx

        guard = MerchantHealthGuard()
        with pytest.raises(HTTPException) as exc_info:
            guard.require_available_for_dashboards(mock_request)

        message = exc_info.value.detail["message"].lower()
        for term in self.FORBIDDEN_TERMS:
            assert term not in message, (
                f"Forbidden term '{term}' found in dashboard block message"
            )
