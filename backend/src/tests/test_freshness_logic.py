"""
Tests for FreshnessService — data freshness tracking and AI staleness gate.

Validates:
- Per-source freshness classification (fresh / stale / critical / never_synced)
- Dashboard summary aggregation and scoring
- AI freshness gate blocks when data is stale
- AI freshness gate allows when data is fresh
- Edge cases: no sources, disabled sources, mixed freshness
"""

import uuid
import pytest
from datetime import datetime, timezone, timedelta
from unittest.mock import MagicMock, patch

from src.services.freshness_service import (
    FreshnessService,
    FreshnessGateResult,
    SourceFreshness,
)


# =============================================================================
# Helpers
# =============================================================================

def _make_connection(
    tenant_id,
    source_type="shopify",
    last_sync_at=None,
    last_sync_status="success",
    sync_frequency_minutes="60",
    is_enabled=True,
    status=None,
    connection_name=None,
):
    """Create a mock TenantAirbyteConnection."""
    from src.models.airbyte_connection import ConnectionStatus

    conn = MagicMock()
    conn.id = str(uuid.uuid4())
    conn.tenant_id = tenant_id
    conn.source_type = source_type
    conn.connection_name = connection_name or f"Test {source_type} connection"
    conn.last_sync_at = last_sync_at
    conn.last_sync_status = last_sync_status
    conn.sync_frequency_minutes = sync_frequency_minutes
    conn.is_enabled = is_enabled
    conn.status = status or ConnectionStatus.ACTIVE
    return conn


# =============================================================================
# Test: Initialization
# =============================================================================

class TestFreshnessServiceInit:

    def test_requires_tenant_id(self):
        with pytest.raises(ValueError, match="tenant_id is required"):
            FreshnessService(db_session=MagicMock(), tenant_id="")

    def test_requires_non_none_tenant_id(self):
        with pytest.raises(ValueError):
            FreshnessService(db_session=MagicMock(), tenant_id=None)

    def test_default_ai_threshold(self):
        svc = FreshnessService(db_session=MagicMock(), tenant_id="t-1")
        assert svc.ai_block_threshold_minutes == 1440

    def test_custom_ai_threshold(self):
        svc = FreshnessService(
            db_session=MagicMock(), tenant_id="t-1",
            ai_block_threshold_minutes=720,
        )
        assert svc.ai_block_threshold_minutes == 720


# =============================================================================
# Test: Freshness Classification
# =============================================================================

class TestFreshnessClassification:

    def _make_service(self):
        return FreshnessService(db_session=MagicMock(), tenant_id="t-1")

    def test_never_synced(self):
        svc = self._make_service()
        assert svc._classify_freshness(None, 60) == "never_synced"

    def test_fresh_within_threshold(self):
        svc = self._make_service()
        ts = datetime.now(timezone.utc) - timedelta(minutes=30)
        assert svc._classify_freshness(ts, 60) == "fresh"

    def test_fresh_at_effective_threshold(self):
        svc = self._make_service()
        # effective_threshold = max(60, 120) = 120
        ts = datetime.now(timezone.utc) - timedelta(minutes=119)
        assert svc._classify_freshness(ts, 60) == "fresh"

    def test_stale_beyond_freshness_threshold(self):
        svc = self._make_service()
        ts = datetime.now(timezone.utc) - timedelta(minutes=180)
        assert svc._classify_freshness(ts, 60) == "stale"

    def test_critical_beyond_24h(self):
        svc = self._make_service()
        ts = datetime.now(timezone.utc) - timedelta(hours=25)
        assert svc._classify_freshness(ts, 60) == "critical"

    def test_high_frequency_uses_larger_threshold(self):
        """Sync frequency of 360 min → effective threshold is 360, not 120."""
        svc = self._make_service()
        ts = datetime.now(timezone.utc) - timedelta(minutes=300)
        assert svc._classify_freshness(ts, 360) == "fresh"

    def test_timezone_naive_treated_as_utc(self):
        svc = self._make_service()
        ts = datetime.utcnow() - timedelta(minutes=30)
        assert svc._classify_freshness(ts, 60) == "fresh"


# =============================================================================
# Test: Source Freshness Building
# =============================================================================

class TestBuildSourceFreshness:

    def test_healthy_source(self):
        svc = FreshnessService(db_session=MagicMock(), tenant_id="t-1")
        conn = _make_connection(
            "t-1",
            last_sync_at=datetime.now(timezone.utc) - timedelta(minutes=10),
        )
        sf = svc._build_source_freshness(conn)

        assert sf.freshness_status == "fresh"
        assert sf.is_healthy is True
        assert sf.is_stale is False
        assert sf.warning_message is None

    def test_stale_source_warning(self):
        svc = FreshnessService(db_session=MagicMock(), tenant_id="t-1")
        conn = _make_connection(
            "t-1",
            last_sync_at=datetime.now(timezone.utc) - timedelta(hours=3),
        )
        sf = svc._build_source_freshness(conn)

        assert sf.freshness_status == "stale"
        assert sf.is_stale is True
        assert sf.is_healthy is False
        assert "stale" in sf.warning_message.lower()

    def test_critical_source_warning(self):
        svc = FreshnessService(db_session=MagicMock(), tenant_id="t-1")
        conn = _make_connection(
            "t-1",
            last_sync_at=datetime.now(timezone.utc) - timedelta(hours=25),
        )
        sf = svc._build_source_freshness(conn)

        assert sf.freshness_status == "critical"
        assert sf.is_stale is True
        assert "critically stale" in sf.warning_message.lower()

    def test_never_synced_warning(self):
        svc = FreshnessService(db_session=MagicMock(), tenant_id="t-1")
        conn = _make_connection("t-1", last_sync_at=None)
        sf = svc._build_source_freshness(conn)

        assert sf.freshness_status == "never_synced"
        assert sf.is_stale is True
        assert "never been synced" in sf.warning_message.lower()

    def test_failed_last_sync_not_healthy(self):
        svc = FreshnessService(db_session=MagicMock(), tenant_id="t-1")
        conn = _make_connection(
            "t-1",
            last_sync_at=datetime.now(timezone.utc) - timedelta(minutes=10),
            last_sync_status="failed",
        )
        sf = svc._build_source_freshness(conn)

        assert sf.freshness_status == "fresh"
        assert sf.is_healthy is False

    def test_invalid_sync_frequency_defaults_to_60(self):
        svc = FreshnessService(db_session=MagicMock(), tenant_id="t-1")
        conn = _make_connection(
            "t-1",
            last_sync_at=datetime.now(timezone.utc),
            sync_frequency_minutes="invalid",
        )
        sf = svc._build_source_freshness(conn)
        assert sf.sync_frequency_minutes == 60

    def test_minutes_since_sync_is_integer(self):
        svc = FreshnessService(db_session=MagicMock(), tenant_id="t-1")
        conn = _make_connection(
            "t-1",
            last_sync_at=datetime.now(timezone.utc) - timedelta(minutes=45, seconds=30),
        )
        sf = svc._build_source_freshness(conn)
        assert isinstance(sf.minutes_since_sync, int)


# =============================================================================
# Test: get_all_source_freshness
# =============================================================================

class TestGetAllSourceFreshness:

    def test_returns_all_enabled(self):
        svc = FreshnessService(db_session=MagicMock(), tenant_id="t-1")
        conns = [
            _make_connection(
                "t-1", source_type=st,
                last_sync_at=datetime.now(timezone.utc),
            )
            for st in ("shopify", "meta", "google")
        ]
        with patch.object(svc, "_get_connections", return_value=conns):
            result = svc.get_all_source_freshness()
        assert len(result) == 3


# =============================================================================
# Test: Dashboard Summary
# =============================================================================

class TestFreshnessSummary:

    def test_no_sources_gives_100_score(self):
        svc = FreshnessService(db_session=MagicMock(), tenant_id="t-1")
        with patch.object(svc, "_get_connections", return_value=[]):
            summary = svc.get_freshness_summary()

        assert summary.total_sources == 0
        assert summary.overall_freshness_score == 100.0
        assert summary.has_stale_data is False

    def test_all_fresh_gives_100_score(self):
        svc = FreshnessService(db_session=MagicMock(), tenant_id="t-1")
        conns = [
            _make_connection(
                "t-1", source_type=st,
                last_sync_at=datetime.now(timezone.utc) - timedelta(minutes=10),
            )
            for st in ("shopify", "meta")
        ]
        with patch.object(svc, "_get_connections", return_value=conns):
            summary = svc.get_freshness_summary()

        assert summary.fresh_sources == 2
        assert summary.overall_freshness_score == 100.0
        assert summary.has_stale_data is False

    def test_mixed_freshness_scoring(self):
        svc = FreshnessService(db_session=MagicMock(), tenant_id="t-1")
        fresh = _make_connection(
            "t-1", source_type="shopify",
            last_sync_at=datetime.now(timezone.utc) - timedelta(minutes=10),
        )
        stale = _make_connection(
            "t-1", source_type="meta",
            last_sync_at=datetime.now(timezone.utc) - timedelta(hours=5),
        )
        with patch.object(svc, "_get_connections", return_value=[fresh, stale]):
            summary = svc.get_freshness_summary()

        assert summary.fresh_sources == 1
        assert summary.stale_sources == 1
        assert summary.overall_freshness_score == 75.0
        assert summary.has_stale_data is True

    def test_critical_sources_score_zero(self):
        svc = FreshnessService(db_session=MagicMock(), tenant_id="t-1")
        critical = _make_connection(
            "t-1", source_type="shopify",
            last_sync_at=datetime.now(timezone.utc) - timedelta(hours=25),
        )
        with patch.object(svc, "_get_connections", return_value=[critical]):
            summary = svc.get_freshness_summary()

        assert summary.critical_sources == 1
        assert summary.overall_freshness_score == 0.0

    def test_never_synced_scores_25(self):
        svc = FreshnessService(db_session=MagicMock(), tenant_id="t-1")
        never = _make_connection("t-1", last_sync_at=None)
        with patch.object(svc, "_get_connections", return_value=[never]):
            summary = svc.get_freshness_summary()

        assert summary.never_synced_sources == 1
        assert summary.overall_freshness_score == 25.0

    def test_summary_includes_source_details(self):
        svc = FreshnessService(db_session=MagicMock(), tenant_id="t-1")
        conn = _make_connection(
            "t-1", last_sync_at=datetime.now(timezone.utc),
        )
        with patch.object(svc, "_get_connections", return_value=[conn]):
            summary = svc.get_freshness_summary()

        assert len(summary.sources) == 1
        assert isinstance(summary.sources[0], SourceFreshness)

    def test_summary_to_dict(self):
        svc = FreshnessService(db_session=MagicMock(), tenant_id="t-1")
        with patch.object(svc, "_get_connections", return_value=[]):
            summary = svc.get_freshness_summary()

        d = summary.to_dict()
        assert d["tenant_id"] == "t-1"
        assert d["overall_freshness_score"] == 100.0
        assert isinstance(d["sources"], list)


# =============================================================================
# Test: AI Freshness Gate
# =============================================================================

class TestAIFreshnessGate:

    def test_blocks_when_no_sources(self):
        svc = FreshnessService(db_session=MagicMock(), tenant_id="t-1")
        with patch.object(svc, "_get_connections", return_value=[]):
            gate = svc.check_freshness_gate()

        assert gate.is_allowed is False
        assert "No enabled data sources" in gate.reason

    def test_allows_when_all_fresh(self):
        svc = FreshnessService(db_session=MagicMock(), tenant_id="t-1")
        conns = [
            _make_connection(
                "t-1", source_type=st,
                last_sync_at=datetime.now(timezone.utc) - timedelta(minutes=10),
            )
            for st in ("shopify", "meta")
        ]
        with patch.object(svc, "_get_connections", return_value=conns):
            gate = svc.check_freshness_gate()

        assert gate.is_allowed is True
        assert gate.freshness_score == 100.0
        assert gate.stale_sources == []

    def test_blocks_when_critical(self):
        svc = FreshnessService(db_session=MagicMock(), tenant_id="t-1")
        fresh = _make_connection(
            "t-1", source_type="shopify",
            last_sync_at=datetime.now(timezone.utc) - timedelta(minutes=10),
        )
        critical = _make_connection(
            "t-1", source_type="meta",
            last_sync_at=datetime.now(timezone.utc) - timedelta(hours=25),
        )
        with patch.object(svc, "_get_connections", return_value=[fresh, critical]):
            with patch.object(svc, "_log_ai_gate_blocked"):
                gate = svc.check_freshness_gate()

        assert gate.is_allowed is False
        assert len(gate.stale_sources) == 1
        assert "meta" in gate.stale_sources[0]

    def test_blocks_when_never_synced(self):
        svc = FreshnessService(db_session=MagicMock(), tenant_id="t-1")
        never = _make_connection("t-1", source_type="shopify", last_sync_at=None)
        with patch.object(svc, "_get_connections", return_value=[never]):
            with patch.object(svc, "_log_ai_gate_blocked"):
                gate = svc.check_freshness_gate()

        assert gate.is_allowed is False
        assert "never synced" in gate.stale_sources[0]

    def test_allows_when_stale_but_below_ai_threshold(self):
        """3 hours stale is under the 24h AI block threshold."""
        svc = FreshnessService(db_session=MagicMock(), tenant_id="t-1")
        stale = _make_connection(
            "t-1", source_type="shopify",
            last_sync_at=datetime.now(timezone.utc) - timedelta(hours=3),
        )
        with patch.object(svc, "_get_connections", return_value=[stale]):
            gate = svc.check_freshness_gate()

        assert gate.is_allowed is True

    def test_required_sources_filter(self):
        """Gate only checks required_sources when specified."""
        svc = FreshnessService(db_session=MagicMock(), tenant_id="t-1")
        shopify_fresh = _make_connection(
            "t-1", source_type="shopify",
            last_sync_at=datetime.now(timezone.utc) - timedelta(minutes=10),
        )
        meta_critical = _make_connection(
            "t-1", source_type="meta",
            last_sync_at=datetime.now(timezone.utc) - timedelta(hours=25),
        )
        with patch.object(
            svc, "_get_connections",
            return_value=[shopify_fresh, meta_critical],
        ):
            gate = svc.check_freshness_gate(required_sources=["shopify"])

        assert gate.is_allowed is True

    def test_required_sources_missing_blocks(self):
        svc = FreshnessService(db_session=MagicMock(), tenant_id="t-1")
        shopify = _make_connection(
            "t-1", source_type="shopify",
            last_sync_at=datetime.now(timezone.utc),
        )
        with patch.object(svc, "_get_connections", return_value=[shopify]):
            gate = svc.check_freshness_gate(required_sources=["meta"])

        assert gate.is_allowed is False
        assert "Required sources not found" in gate.reason

    def test_custom_ai_threshold(self):
        svc = FreshnessService(
            db_session=MagicMock(), tenant_id="t-1",
            ai_block_threshold_minutes=60,
        )
        conn = _make_connection(
            "t-1", source_type="shopify",
            last_sync_at=datetime.now(timezone.utc) - timedelta(minutes=90),
        )
        with patch.object(svc, "_get_connections", return_value=[conn]):
            with patch.object(svc, "_log_ai_gate_blocked"):
                gate = svc.check_freshness_gate()

        assert gate.is_allowed is False

    def test_gate_audit_called_on_block(self):
        svc = FreshnessService(db_session=MagicMock(), tenant_id="t-1")
        critical = _make_connection(
            "t-1", source_type="shopify",
            last_sync_at=datetime.now(timezone.utc) - timedelta(hours=25),
        )
        with patch.object(svc, "_get_connections", return_value=[critical]):
            with patch.object(svc, "_log_ai_gate_blocked") as mock_audit:
                svc.check_freshness_gate()

        mock_audit.assert_called_once()
        assert len(mock_audit.call_args[0][0]) == 1

    def test_gate_score_with_mixed_states(self):
        """Gate score reflects fraction of fresh sources."""
        svc = FreshnessService(db_session=MagicMock(), tenant_id="t-1")
        fresh1 = _make_connection(
            "t-1", source_type="shopify",
            last_sync_at=datetime.now(timezone.utc) - timedelta(minutes=10),
        )
        fresh2 = _make_connection(
            "t-1", source_type="meta",
            last_sync_at=datetime.now(timezone.utc) - timedelta(minutes=10),
        )
        stale = _make_connection(
            "t-1", source_type="google",
            last_sync_at=datetime.now(timezone.utc) - timedelta(hours=5),
        )
        with patch.object(
            svc, "_get_connections",
            return_value=[fresh1, fresh2, stale],
        ):
            gate = svc.check_freshness_gate()

        assert gate.is_allowed is True
        assert gate.freshness_score == 66.7


# =============================================================================
# Test: Static Convenience Method
# =============================================================================

class TestStaticAIGate:

    def test_delegates_to_instance(self):
        db = MagicMock()
        with patch.object(
            FreshnessService, "check_freshness_gate",
            return_value=FreshnessGateResult(is_allowed=True),
        ) as mock_gate:
            result = FreshnessService.check_ai_freshness_gate(
                db_session=db,
                tenant_id="t-1",
                required_sources=["shopify"],
            )

        assert result.is_allowed is True
        mock_gate.assert_called_once_with(required_sources=["shopify"])


# =============================================================================
# Test: Data Class Serialization
# =============================================================================

class TestSerialization:

    def test_source_freshness_to_dict(self):
        ts = datetime(2025, 1, 1, 12, 0, tzinfo=timezone.utc)
        sf = SourceFreshness(
            connection_id="c-1",
            connection_name="Test",
            source_type="shopify",
            last_sync_at=ts,
            last_sync_status="success",
            sync_frequency_minutes=60,
            minutes_since_sync=30,
            freshness_status="fresh",
            is_stale=False,
            is_healthy=True,
        )
        d = sf.to_dict()
        assert d["connection_id"] == "c-1"
        assert d["last_sync_at"] == ts.isoformat()
        assert d["freshness_status"] == "fresh"

    def test_source_freshness_to_dict_null_sync(self):
        sf = SourceFreshness(
            connection_id="c-1",
            connection_name="Test",
            source_type="shopify",
            last_sync_at=None,
            last_sync_status=None,
            sync_frequency_minutes=60,
            minutes_since_sync=None,
            freshness_status="never_synced",
            is_stale=True,
            is_healthy=False,
        )
        d = sf.to_dict()
        assert d["last_sync_at"] is None
        assert d["minutes_since_sync"] is None

    def test_gate_result_to_dict(self):
        result = FreshnessGateResult(
            is_allowed=False,
            reason="test reason",
            stale_sources=["shopify"],
            freshness_score=50.0,
        )
        d = result.to_dict()
        assert d["is_allowed"] is False
        assert d["reason"] == "test reason"
        assert d["stale_sources"] == ["shopify"]


# =============================================================================
# Test: Audit Logging
# =============================================================================

class TestAuditLogging:

    @patch("src.services.freshness_service.logger")
    def test_audit_failure_does_not_crash(self, mock_logger):
        """Audit logging failure is caught and logged, not raised."""
        svc = FreshnessService(db_session=MagicMock(), tenant_id="t-1")

        with patch(
            "src.platform.audit.log_system_audit_event_sync",
            side_effect=Exception("audit DB down"),
        ):
            svc._log_ai_gate_blocked(["shopify (1500min stale)"])

        mock_logger.error.assert_called_once()

    def test_audit_called_with_correct_action(self):
        svc = FreshnessService(db_session=MagicMock(), tenant_id="t-1")

        with patch(
            "src.platform.audit.log_system_audit_event_sync",
        ) as mock_audit:
            svc._log_ai_gate_blocked(["shopify (critical)"])

        from src.platform.audit import AuditAction
        mock_audit.assert_called_once()
        call_kwargs = mock_audit.call_args.kwargs
        assert call_kwargs["action"] == AuditAction.AI_ACTION_BLOCKED
