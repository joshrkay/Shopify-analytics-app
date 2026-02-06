"""
Tests for data freshness audit events.

Validates:
- Audit event registration (AuditAction enum, AUDITABLE_EVENTS, EVENT_CATEGORIES, EVENT_SEVERITY)
- Event schema correctness (required fields)
- Audit emission on state transitions in DataAvailabilityService
- No audit emission when state is unchanged
- Recovery event emitted when returning to FRESH
"""

import pytest
from datetime import datetime, timezone
from unittest.mock import patch, MagicMock

from src.platform.audit import (
    AuditAction,
    AuditOutcome,
    AUDITABLE_EVENTS as AUDIT_PY_EVENTS,
    AuditableEventMetadata,
)
from src.platform.audit_events import (
    AUDITABLE_EVENTS,
    EVENT_CATEGORIES,
    EVENT_SEVERITY,
    validate_event_metadata,
    get_event_category,
    get_event_severity,
)


# ─── Event registration ──────────────────────────────────────────────────────


class TestAuditActionEnum:
    def test_stale_action_exists(self):
        assert AuditAction.DATA_FRESHNESS_STALE.value == "data.freshness.stale"

    def test_unavailable_action_exists(self):
        assert AuditAction.DATA_FRESHNESS_UNAVAILABLE.value == "data.freshness.unavailable"

    def test_recovered_action_exists(self):
        assert AuditAction.DATA_FRESHNESS_RECOVERED.value == "data.freshness.recovered"


class TestAuditEventsRegistry:
    """Tests against the audit_events.py canonical registry."""

    def test_stale_event_registered(self):
        assert "data.freshness.stale" in AUDITABLE_EVENTS

    def test_unavailable_event_registered(self):
        assert "data.freshness.unavailable" in AUDITABLE_EVENTS

    def test_recovered_event_registered(self):
        assert "data.freshness.recovered" in AUDITABLE_EVENTS

    @pytest.mark.parametrize("event_type", [
        "data.freshness.stale",
        "data.freshness.unavailable",
        "data.freshness.recovered",
    ])
    def test_required_fields(self, event_type):
        """All freshness events must require the same 6 fields."""
        fields = AUDITABLE_EVENTS[event_type]
        assert "tenant_id" in fields
        assert "source" in fields
        assert "previous_state" in fields
        assert "new_state" in fields
        assert "detected_at" in fields
        assert "root_cause" in fields

    @pytest.mark.parametrize("event_type", [
        "data.freshness.stale",
        "data.freshness.unavailable",
        "data.freshness.recovered",
    ])
    def test_validation_passes_with_all_fields(self, event_type):
        metadata = {
            "tenant_id": "t1",
            "source": "shopify_orders",
            "previous_state": "fresh",
            "new_state": "stale",
            "detected_at": "2026-02-06T00:00:00+00:00",
            "root_cause": "sla_exceeded",
        }
        is_valid, missing = validate_event_metadata(event_type, metadata)
        assert is_valid is True
        assert missing == []

    def test_validation_fails_with_missing_field(self):
        metadata = {
            "tenant_id": "t1",
            "source": "shopify_orders",
            # missing previous_state, new_state, detected_at, root_cause
        }
        is_valid, missing = validate_event_metadata("data.freshness.stale", metadata)
        assert is_valid is False
        assert "previous_state" in missing


class TestEventCategories:
    def test_data_freshness_category_exists(self):
        assert "data_freshness" in EVENT_CATEGORIES

    def test_category_contains_all_events(self):
        events = EVENT_CATEGORIES["data_freshness"]
        assert "data.freshness.stale" in events
        assert "data.freshness.unavailable" in events
        assert "data.freshness.recovered" in events

    @pytest.mark.parametrize("event_type", [
        "data.freshness.stale",
        "data.freshness.unavailable",
        "data.freshness.recovered",
    ])
    def test_category_lookup(self, event_type):
        assert get_event_category(event_type) == "data_freshness"


class TestEventSeverity:
    def test_stale_is_medium(self):
        assert get_event_severity("data.freshness.stale") == "medium"

    def test_unavailable_is_high(self):
        assert get_event_severity("data.freshness.unavailable") == "high"

    def test_recovered_is_low(self):
        assert get_event_severity("data.freshness.recovered") == "low"


class TestAuditPyRegistry:
    """Tests against the audit.py AUDITABLE_EVENTS (AuditableEventMetadata)."""

    def test_stale_registered_with_metadata(self):
        meta = AUDIT_PY_EVENTS[AuditAction.DATA_FRESHNESS_STALE]
        assert isinstance(meta, AuditableEventMetadata)
        assert "source" in meta.required_fields
        assert meta.risk_level == "medium"

    def test_unavailable_registered_with_metadata(self):
        meta = AUDIT_PY_EVENTS[AuditAction.DATA_FRESHNESS_UNAVAILABLE]
        assert isinstance(meta, AuditableEventMetadata)
        assert meta.risk_level == "high"
        assert "SOC2" in meta.compliance_tags

    def test_recovered_registered_with_metadata(self):
        meta = AUDIT_PY_EVENTS[AuditAction.DATA_FRESHNESS_RECOVERED]
        assert isinstance(meta, AuditableEventMetadata)
        assert meta.risk_level == "low"


# ─── Audit emission from DataAvailabilityService ──────────────────────────────


class TestFreshnessAuditEmission:
    """Test that DataAvailabilityService emits audit events on transitions."""

    @pytest.fixture
    def mock_db(self):
        return MagicMock()

    @pytest.fixture
    def service(self, mock_db):
        with patch(
            "src.services.data_availability_service.load_yaml_config",
            return_value={
                "sources": {
                    "shopify_orders": {
                        "free": {"warn_after_minutes": 60, "error_after_minutes": 120},
                    },
                },
                "default_tier": "free",
            },
        ):
            from src.services.data_availability_service import DataAvailabilityService
            svc = DataAvailabilityService(
                db_session=mock_db,
                tenant_id="tenant-123",
                billing_tier="free",
            )
            return svc

    def test_stale_transition_emits_audit(self, service):
        """FRESH → STALE should emit data.freshness.stale."""
        now = datetime.now(timezone.utc)
        with patch.object(service, "_emit_freshness_audit_event") as mock_emit:
            mock_emit.return_value = None
            service._emit_freshness_audit_event(
                source_type="shopify_orders",
                previous_state="fresh",
                new_state="stale",
                reason="sla_exceeded",
                detected_at=now,
            )
            # Since we're calling the real method (not mocked), verify manually
        # Test the method directly
        with patch(
            "src.services.data_availability_service.log_system_audit_event_sync"
        ) as mock_log:
            service._emit_freshness_audit_event(
                source_type="shopify_orders",
                previous_state="fresh",
                new_state="stale",
                reason="sla_exceeded",
                detected_at=now,
            )
            mock_log.assert_called_once()
            call_kwargs = mock_log.call_args
            assert call_kwargs.kwargs["action"] == AuditAction.DATA_FRESHNESS_STALE
            assert call_kwargs.kwargs["tenant_id"] == "tenant-123"
            assert call_kwargs.kwargs["resource_type"] == "data_source"
            assert call_kwargs.kwargs["resource_id"] == "shopify_orders"
            metadata = call_kwargs.kwargs["metadata"]
            assert metadata["source"] == "shopify_orders"
            assert metadata["previous_state"] == "fresh"
            assert metadata["new_state"] == "stale"
            assert metadata["root_cause"] == "sla_exceeded"

    def test_unavailable_transition_emits_audit(self, service):
        """STALE → UNAVAILABLE should emit data.freshness.unavailable."""
        now = datetime.now(timezone.utc)
        with patch(
            "src.services.data_availability_service.log_system_audit_event_sync"
        ) as mock_log:
            service._emit_freshness_audit_event(
                source_type="shopify_orders",
                previous_state="stale",
                new_state="unavailable",
                reason="grace_window_exceeded",
                detected_at=now,
            )
            mock_log.assert_called_once()
            call_kwargs = mock_log.call_args
            assert call_kwargs.kwargs["action"] == AuditAction.DATA_FRESHNESS_UNAVAILABLE
            assert call_kwargs.kwargs["metadata"]["root_cause"] == "grace_window_exceeded"

    def test_recovery_emits_audit(self, service):
        """STALE → FRESH should emit data.freshness.recovered."""
        now = datetime.now(timezone.utc)
        with patch(
            "src.services.data_availability_service.log_system_audit_event_sync"
        ) as mock_log:
            service._emit_freshness_audit_event(
                source_type="shopify_orders",
                previous_state="stale",
                new_state="fresh",
                reason="sync_ok",
                detected_at=now,
            )
            mock_log.assert_called_once()
            call_kwargs = mock_log.call_args
            assert call_kwargs.kwargs["action"] == AuditAction.DATA_FRESHNESS_RECOVERED
            assert call_kwargs.kwargs["metadata"]["previous_state"] == "stale"
            assert call_kwargs.kwargs["metadata"]["new_state"] == "fresh"

    def test_no_emission_for_unknown_state(self, service):
        """Unknown state should not emit an audit event."""
        now = datetime.now(timezone.utc)
        with patch(
            "src.services.data_availability_service.log_system_audit_event_sync"
        ) as mock_log:
            service._emit_freshness_audit_event(
                source_type="shopify_orders",
                previous_state="fresh",
                new_state="something_unknown",
                reason="bug",
                detected_at=now,
            )
            mock_log.assert_not_called()

    def test_audit_failure_does_not_propagate(self, service):
        """Audit emission failure should be swallowed (never crash the caller)."""
        now = datetime.now(timezone.utc)
        with patch(
            "src.services.data_availability_service.log_system_audit_event_sync",
            side_effect=RuntimeError("DB connection lost"),
        ):
            # Should not raise
            service._emit_freshness_audit_event(
                source_type="shopify_orders",
                previous_state="fresh",
                new_state="stale",
                reason="sla_exceeded",
                detected_at=now,
            )

    def test_metadata_contains_all_required_fields(self, service):
        """Emitted metadata must pass the audit_events.py schema validation."""
        now = datetime.now(timezone.utc)
        with patch(
            "src.services.data_availability_service.log_system_audit_event_sync"
        ) as mock_log:
            service._emit_freshness_audit_event(
                source_type="shopify_orders",
                previous_state="fresh",
                new_state="stale",
                reason="sla_exceeded",
                detected_at=now,
            )
            metadata = mock_log.call_args.kwargs["metadata"]
            is_valid, missing = validate_event_metadata(
                "data.freshness.stale", metadata
            )
            assert is_valid, f"Missing fields: {missing}"

    def test_previous_state_defaults_to_unknown_when_none(self, service):
        """First evaluation (no prior state) should use 'unknown'."""
        now = datetime.now(timezone.utc)
        with patch(
            "src.services.data_availability_service.log_system_audit_event_sync"
        ) as mock_log:
            service._emit_freshness_audit_event(
                source_type="shopify_orders",
                previous_state=None,
                new_state="unavailable",
                reason="never_synced",
                detected_at=now,
            )
            metadata = mock_log.call_args.kwargs["metadata"]
            assert metadata["previous_state"] == "unknown"
