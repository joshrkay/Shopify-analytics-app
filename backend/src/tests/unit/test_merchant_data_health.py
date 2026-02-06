"""
Unit tests for merchant data health service and model.

Tests cover:
- MerchantHealthState enum values
- All 9 mapping combinations (3 availability x 3 quality)
- MerchantDataHealthService.evaluate() with mocked dependencies
- Feature flags per state
- Merchant-safe messaging (no internal jargon)

Story 4.3 - Merchant Data Health Trust Layer
"""

import pytest
from datetime import datetime, timezone
from unittest.mock import Mock, MagicMock, patch

from src.models.data_availability import AvailabilityState
from src.models.dq_models import DataQualityState
from src.models.merchant_data_health import (
    FEATURE_FLAGS,
    MERCHANT_MESSAGES,
    MerchantDataHealthResponse,
    MerchantHealthState,
    get_merchant_message,
)
from src.services.merchant_data_health import (
    MerchantDataHealthResult,
    MerchantDataHealthService,
)


# ---------------------------------------------------------------------------
# MerchantHealthState enum
# ---------------------------------------------------------------------------

class TestMerchantHealthState:
    """Tests for the MerchantHealthState enum."""

    def test_has_three_states(self):
        assert len(MerchantHealthState) == 3

    def test_healthy_value(self):
        assert MerchantHealthState.HEALTHY.value == "healthy"

    def test_delayed_value(self):
        assert MerchantHealthState.DELAYED.value == "delayed"

    def test_unavailable_value(self):
        assert MerchantHealthState.UNAVAILABLE.value == "unavailable"


# ---------------------------------------------------------------------------
# Merchant-safe messaging
# ---------------------------------------------------------------------------

class TestMerchantMessages:
    """Tests for merchant-safe messaging."""

    # Internal system names that must NEVER appear in merchant copy
    FORBIDDEN_TERMS = [
        "dbt", "airbyte", "rls", "sla", "threshold",
        "sync_failed", "grace_window", "backfill",
        "postgresql", "supabase", "temporal", "kafka",
        "error_code", "exception", "traceback",
    ]

    def test_all_states_have_messages(self):
        for state in MerchantHealthState:
            msg = get_merchant_message(state)
            assert isinstance(msg, str)
            assert len(msg) > 0

    def test_healthy_message(self):
        msg = get_merchant_message(MerchantHealthState.HEALTHY)
        assert msg == "Your data is up to date."

    def test_delayed_message(self):
        msg = get_merchant_message(MerchantHealthState.DELAYED)
        assert msg == "Some data is delayed. Reports may be incomplete."

    def test_unavailable_message(self):
        msg = get_merchant_message(MerchantHealthState.UNAVAILABLE)
        assert msg == "Your data is temporarily unavailable."

    def test_no_internal_jargon_in_messages(self):
        """Ensure no internal system terms leak into merchant messages."""
        for state in MerchantHealthState:
            msg = get_merchant_message(state).lower()
            for term in self.FORBIDDEN_TERMS:
                assert term not in msg, (
                    f"Forbidden term '{term}' found in {state.value} message"
                )


# ---------------------------------------------------------------------------
# Feature flags per state
# ---------------------------------------------------------------------------

class TestFeatureFlags:
    """Tests for feature flags per merchant health state."""

    def test_healthy_enables_all(self):
        flags = FEATURE_FLAGS[MerchantHealthState.HEALTHY]
        assert flags["ai_insights_enabled"] is True
        assert flags["dashboards_enabled"] is True
        assert flags["exports_enabled"] is True

    def test_delayed_disables_ai_and_exports(self):
        flags = FEATURE_FLAGS[MerchantHealthState.DELAYED]
        assert flags["ai_insights_enabled"] is False
        assert flags["dashboards_enabled"] is True
        assert flags["exports_enabled"] is False

    def test_unavailable_disables_all(self):
        flags = FEATURE_FLAGS[MerchantHealthState.UNAVAILABLE]
        assert flags["ai_insights_enabled"] is False
        assert flags["dashboards_enabled"] is False
        assert flags["exports_enabled"] is False


# ---------------------------------------------------------------------------
# State mapping logic (9 combinations)
# ---------------------------------------------------------------------------

class TestStateMappingLogic:
    """Tests for the _map_to_merchant_state static method."""

    @pytest.mark.parametrize(
        "availability,quality,expected",
        [
            # FRESH + PASS = HEALTHY
            ("fresh", "pass", MerchantHealthState.HEALTHY),
            # FRESH + WARN = DELAYED
            ("fresh", "warn", MerchantHealthState.DELAYED),
            # FRESH + FAIL = UNAVAILABLE
            ("fresh", "fail", MerchantHealthState.UNAVAILABLE),
            # STALE + PASS = DELAYED
            ("stale", "pass", MerchantHealthState.DELAYED),
            # STALE + WARN = DELAYED
            ("stale", "warn", MerchantHealthState.DELAYED),
            # STALE + FAIL = UNAVAILABLE
            ("stale", "fail", MerchantHealthState.UNAVAILABLE),
            # UNAVAILABLE + PASS = UNAVAILABLE
            ("unavailable", "pass", MerchantHealthState.UNAVAILABLE),
            # UNAVAILABLE + WARN = UNAVAILABLE
            ("unavailable", "warn", MerchantHealthState.UNAVAILABLE),
            # UNAVAILABLE + FAIL = UNAVAILABLE
            ("unavailable", "fail", MerchantHealthState.UNAVAILABLE),
        ],
    )
    def test_mapping(self, availability, quality, expected):
        result = MerchantDataHealthService._map_to_merchant_state(
            availability, quality,
        )
        assert result == expected

    def test_unavailable_always_wins_over_pass(self):
        """UNAVAILABLE availability should always produce UNAVAILABLE."""
        result = MerchantDataHealthService._map_to_merchant_state(
            "unavailable", "pass",
        )
        assert result == MerchantHealthState.UNAVAILABLE

    def test_fail_always_wins_over_fresh(self):
        """FAIL quality should always produce UNAVAILABLE."""
        result = MerchantDataHealthService._map_to_merchant_state(
            "fresh", "fail",
        )
        assert result == MerchantHealthState.UNAVAILABLE


# ---------------------------------------------------------------------------
# MerchantDataHealthService.evaluate()
# ---------------------------------------------------------------------------

class TestMerchantDataHealthServiceEvaluate:
    """Tests for the full evaluate() method with mocked deps."""

    def _make_service(self) -> MerchantDataHealthService:
        db = MagicMock()
        return MerchantDataHealthService(
            db_session=db,
            tenant_id="test-tenant-001",
            billing_tier="growth",
        )

    def test_requires_tenant_id(self):
        with pytest.raises(ValueError, match="tenant_id is required"):
            MerchantDataHealthService(
                db_session=MagicMock(),
                tenant_id="",
            )

    @patch.object(
        MerchantDataHealthService,
        "_get_availability_aggregate",
        return_value="fresh",
    )
    @patch.object(
        MerchantDataHealthService,
        "_get_quality_aggregate",
        return_value="pass",
    )
    def test_evaluate_healthy(self, mock_qual, mock_avail):
        service = self._make_service()
        result = service.evaluate()

        assert result.state == MerchantHealthState.HEALTHY
        assert result.ai_insights_enabled is True
        assert result.dashboards_enabled is True
        assert result.exports_enabled is True
        assert "up to date" in result.message.lower()
        assert isinstance(result.evaluated_at, datetime)

    @patch.object(
        MerchantDataHealthService,
        "_get_availability_aggregate",
        return_value="stale",
    )
    @patch.object(
        MerchantDataHealthService,
        "_get_quality_aggregate",
        return_value="pass",
    )
    def test_evaluate_delayed_from_stale(self, mock_qual, mock_avail):
        service = self._make_service()
        result = service.evaluate()

        assert result.state == MerchantHealthState.DELAYED
        assert result.ai_insights_enabled is False
        assert result.dashboards_enabled is True
        assert result.exports_enabled is False

    @patch.object(
        MerchantDataHealthService,
        "_get_availability_aggregate",
        return_value="fresh",
    )
    @patch.object(
        MerchantDataHealthService,
        "_get_quality_aggregate",
        return_value="warn",
    )
    def test_evaluate_delayed_from_warn(self, mock_qual, mock_avail):
        service = self._make_service()
        result = service.evaluate()

        assert result.state == MerchantHealthState.DELAYED

    @patch.object(
        MerchantDataHealthService,
        "_get_availability_aggregate",
        return_value="unavailable",
    )
    @patch.object(
        MerchantDataHealthService,
        "_get_quality_aggregate",
        return_value="pass",
    )
    def test_evaluate_unavailable_from_availability(self, mock_qual, mock_avail):
        service = self._make_service()
        result = service.evaluate()

        assert result.state == MerchantHealthState.UNAVAILABLE
        assert result.ai_insights_enabled is False
        assert result.dashboards_enabled is False
        assert result.exports_enabled is False

    @patch.object(
        MerchantDataHealthService,
        "_get_availability_aggregate",
        return_value="fresh",
    )
    @patch.object(
        MerchantDataHealthService,
        "_get_quality_aggregate",
        return_value="fail",
    )
    def test_evaluate_unavailable_from_quality(self, mock_qual, mock_avail):
        service = self._make_service()
        result = service.evaluate()

        assert result.state == MerchantHealthState.UNAVAILABLE


# ---------------------------------------------------------------------------
# Response model
# ---------------------------------------------------------------------------

class TestMerchantDataHealthResponse:
    """Tests for the Pydantic response model."""

    def test_valid_response(self):
        resp = MerchantDataHealthResponse(
            health_state="healthy",
            last_updated="2026-02-06T12:00:00Z",
            user_safe_message="Your data is up to date.",
            ai_insights_enabled=True,
            dashboards_enabled=True,
            exports_enabled=True,
        )
        assert resp.health_state == "healthy"
        assert resp.ai_insights_enabled is True
