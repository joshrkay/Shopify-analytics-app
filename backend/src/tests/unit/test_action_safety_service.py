"""
Unit tests for ActionSafetyService (Story 8.6).

Tests cover:
- Rate limiting per tenant
- Cooldown window enforcement
- Safety event logging
- Combined safety checks

Story 8.6 - Safety, Limits & Guardrails
"""

import pytest
import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import Mock, patch

from src.services.action_safety_service import (
    ActionSafetyService,
    SafetyCheckResult,
    RateLimitStatus,
    AIRateLimit,
    AICooldown,
    AISafetyEvent,
    DEFAULT_RATE_LIMITS,
    DEFAULT_COOLDOWNS,
    MAX_RECOMMENDATIONS_PER_RUN,
)


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def tenant_id():
    """Test tenant ID."""
    return "test-tenant-123"


@pytest.fixture
def mock_db_session():
    """Create a mock database session."""
    session = Mock()
    session.query = Mock(return_value=Mock())
    session.add = Mock()
    session.flush = Mock()
    session.commit = Mock()
    return session


@pytest.fixture
def safety_service_free(mock_db_session, tenant_id):
    """Create safety service for free tier."""
    return ActionSafetyService(
        db_session=mock_db_session,
        tenant_id=tenant_id,
        billing_tier="free",
    )


@pytest.fixture
def safety_service_growth(mock_db_session, tenant_id):
    """Create safety service for growth tier."""
    return ActionSafetyService(
        db_session=mock_db_session,
        tenant_id=tenant_id,
        billing_tier="growth",
    )


@pytest.fixture
def safety_service_enterprise(mock_db_session, tenant_id):
    """Create safety service for enterprise tier."""
    return ActionSafetyService(
        db_session=mock_db_session,
        tenant_id=tenant_id,
        billing_tier="enterprise",
    )


# =============================================================================
# Configuration Tests
# =============================================================================


class TestSafetyConfiguration:
    """Tests for safety configuration constants."""

    def test_free_tier_has_no_actions(self):
        """Free tier should have 0 action_execution limit."""
        assert DEFAULT_RATE_LIMITS["free"]["action_execution"] == 0

    def test_growth_tier_has_actions(self):
        """Growth tier should have positive action_execution limit."""
        assert DEFAULT_RATE_LIMITS["growth"]["action_execution"] == 50

    def test_enterprise_tier_is_unlimited(self):
        """Enterprise tier should have unlimited (-1) action_execution."""
        assert DEFAULT_RATE_LIMITS["enterprise"]["action_execution"] == -1

    def test_cooldowns_are_positive(self):
        """All cooldown values should be positive integers."""
        for action_type, seconds in DEFAULT_COOLDOWNS.items():
            assert seconds > 0, f"Cooldown for {action_type} should be positive"

    def test_max_recommendations_is_reasonable(self):
        """Max recommendations per run should be a reasonable number."""
        assert 10 <= MAX_RECOMMENDATIONS_PER_RUN <= 100


# =============================================================================
# Initialization Tests
# =============================================================================


class TestActionSafetyServiceInit:
    """Tests for ActionSafetyService initialization."""

    def test_requires_tenant_id(self, mock_db_session):
        """Should raise ValueError if tenant_id is empty."""
        with pytest.raises(ValueError, match="tenant_id is required"):
            ActionSafetyService(mock_db_session, "")

    def test_requires_tenant_id_none(self, mock_db_session):
        """Should raise ValueError if tenant_id is None."""
        with pytest.raises(ValueError, match="tenant_id is required"):
            ActionSafetyService(mock_db_session, None)

    def test_stores_tenant_id(self, mock_db_session, tenant_id):
        """Should store tenant_id correctly."""
        service = ActionSafetyService(mock_db_session, tenant_id)
        assert service.tenant_id == tenant_id

    def test_default_billing_tier_is_free(self, mock_db_session, tenant_id):
        """Default billing tier should be free."""
        service = ActionSafetyService(mock_db_session, tenant_id)
        assert service.billing_tier == "free"

    def test_stores_billing_tier(self, mock_db_session, tenant_id):
        """Should store billing tier correctly."""
        service = ActionSafetyService(mock_db_session, tenant_id, billing_tier="growth")
        assert service.billing_tier == "growth"


# =============================================================================
# Rate Limiting Tests
# =============================================================================


class TestRateLimiting:
    """Tests for rate limiting functionality."""

    def test_free_tier_blocks_action_execution(self, safety_service_free):
        """Free tier should block action execution."""
        # Mock query to return no existing rate limit
        mock_query = Mock()
        mock_query.filter.return_value.first.return_value = None
        safety_service_free.db.query.return_value = mock_query

        result = safety_service_free.check_rate_limit("action_execution")

        assert result.allowed is False
        assert "not available" in result.reason.lower()

    def test_enterprise_tier_always_allowed(self, safety_service_enterprise):
        """Enterprise tier should always allow (unlimited)."""
        result = safety_service_enterprise.check_rate_limit("action_execution")

        assert result.allowed is True
        assert result.reason is None

    def test_growth_tier_allowed_when_under_limit(self, safety_service_growth):
        """Growth tier should allow when under limit."""
        # Mock existing rate limit with low count
        mock_rate_limit = AIRateLimit(
            tenant_id=safety_service_growth.tenant_id,
            operation_type="action_execution",
            window_start=datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0),
            count=10,  # Well under 50 limit
            limit_value=50,
        )
        mock_query = Mock()
        mock_query.filter.return_value.first.return_value = mock_rate_limit
        safety_service_growth.db.query.return_value = mock_query

        result = safety_service_growth.check_rate_limit("action_execution")

        assert result.allowed is True

    def test_growth_tier_blocked_when_at_limit(self, safety_service_growth):
        """Growth tier should block when at limit."""
        # Mock existing rate limit at limit
        mock_rate_limit = AIRateLimit(
            tenant_id=safety_service_growth.tenant_id,
            operation_type="action_execution",
            window_start=datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0),
            count=50,  # At the 50 limit
            limit_value=50,
        )
        mock_query = Mock()
        mock_query.filter.return_value.first.return_value = mock_rate_limit
        safety_service_growth.db.query.return_value = mock_query

        result = safety_service_growth.check_rate_limit("action_execution")

        assert result.allowed is False
        assert "Rate limit exceeded" in result.reason
        assert result.retry_after_seconds is not None

    def test_consume_rate_limit_increments_count(self, safety_service_growth):
        """consume_rate_limit should increment the count."""
        # Mock existing rate limit
        mock_rate_limit = AIRateLimit(
            tenant_id=safety_service_growth.tenant_id,
            operation_type="action_execution",
            window_start=datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0),
            count=10,
            limit_value=50,
        )
        mock_query = Mock()
        mock_query.filter.return_value.first.return_value = mock_rate_limit
        safety_service_growth.db.query.return_value = mock_query

        safety_service_growth.consume_rate_limit("action_execution")

        assert mock_rate_limit.count == 11
        safety_service_growth.db.flush.assert_called()

    def test_consume_rate_limit_noop_for_unlimited(self, safety_service_enterprise):
        """consume_rate_limit should be no-op for unlimited tier."""
        # Should not query database
        safety_service_enterprise.consume_rate_limit("action_execution")
        safety_service_enterprise.db.query.assert_not_called()


# =============================================================================
# Cooldown Tests
# =============================================================================


class TestCooldowns:
    """Tests for cooldown functionality."""

    def test_no_cooldown_when_none_exists(self, safety_service_growth):
        """Should allow action when no cooldown exists."""
        # Mock no existing cooldown
        mock_query = Mock()
        mock_query.filter.return_value.first.return_value = None
        safety_service_growth.db.query.return_value = mock_query

        result = safety_service_growth.check_cooldown(
            platform="meta",
            entity_type="campaign",
            entity_id="campaign_123",
            action_type="pause_campaign",
        )

        assert result.allowed is True

    def test_cooldown_blocks_when_active(self, safety_service_growth):
        """Should block action when cooldown is active."""
        # Mock existing active cooldown
        mock_cooldown = AICooldown(
            tenant_id=safety_service_growth.tenant_id,
            platform="meta",
            entity_type="campaign",
            entity_id="campaign_123",
            action_type="pause_campaign",
            last_action_at=datetime.now(timezone.utc) - timedelta(minutes=30),
            cooldown_until=datetime.now(timezone.utc) + timedelta(minutes=30),  # Active
        )
        mock_query = Mock()
        mock_query.filter.return_value.first.return_value = mock_cooldown
        safety_service_growth.db.query.return_value = mock_query

        result = safety_service_growth.check_cooldown(
            platform="meta",
            entity_type="campaign",
            entity_id="campaign_123",
            action_type="pause_campaign",
        )

        assert result.allowed is False
        assert "cooldown" in result.reason.lower()
        assert result.retry_after_seconds > 0

    def test_cooldown_allows_when_expired(self, safety_service_growth):
        """Should allow action when cooldown has expired."""
        # Mock expired cooldown
        mock_cooldown = AICooldown(
            tenant_id=safety_service_growth.tenant_id,
            platform="meta",
            entity_type="campaign",
            entity_id="campaign_123",
            action_type="pause_campaign",
            last_action_at=datetime.now(timezone.utc) - timedelta(hours=5),
            cooldown_until=datetime.now(timezone.utc) - timedelta(hours=1),  # Expired
        )
        mock_query = Mock()
        mock_query.filter.return_value.first.return_value = mock_cooldown
        safety_service_growth.db.query.return_value = mock_query

        result = safety_service_growth.check_cooldown(
            platform="meta",
            entity_type="campaign",
            entity_id="campaign_123",
            action_type="pause_campaign",
        )

        assert result.allowed is True

    def test_record_action_creates_cooldown(self, safety_service_growth):
        """record_action should create or update cooldown."""
        # Mock no existing cooldown
        mock_query = Mock()
        mock_query.filter.return_value.first.return_value = None
        safety_service_growth.db.query.return_value = mock_query

        safety_service_growth.record_action(
            platform="meta",
            entity_type="campaign",
            entity_id="campaign_123",
            action_type="pause_campaign",
        )

        # Should have added a new cooldown
        safety_service_growth.db.add.assert_called_once()
        added_cooldown = safety_service_growth.db.add.call_args[0][0]
        assert isinstance(added_cooldown, AICooldown)
        assert added_cooldown.platform == "meta"
        assert added_cooldown.entity_id == "campaign_123"

    def test_record_action_updates_existing_cooldown(self, safety_service_growth):
        """record_action should update existing cooldown."""
        # Mock existing cooldown
        original_time = datetime.now(timezone.utc) - timedelta(hours=5)
        mock_cooldown = AICooldown(
            tenant_id=safety_service_growth.tenant_id,
            platform="meta",
            entity_type="campaign",
            entity_id="campaign_123",
            action_type="pause_campaign",
            last_action_at=original_time,
            cooldown_until=original_time + timedelta(hours=4),
        )
        mock_query = Mock()
        mock_query.filter.return_value.first.return_value = mock_cooldown
        safety_service_growth.db.query.return_value = mock_query

        safety_service_growth.record_action(
            platform="meta",
            entity_type="campaign",
            entity_id="campaign_123",
            action_type="pause_campaign",
        )

        # Should have updated the existing cooldown
        assert mock_cooldown.last_action_at > original_time
        safety_service_growth.db.add.assert_not_called()


# =============================================================================
# Combined Safety Check Tests
# =============================================================================


class TestCombinedSafetyChecks:
    """Tests for combined safety checks."""

    def test_check_action_safety_checks_rate_limit_first(self, safety_service_growth):
        """check_action_safety should check rate limit first."""
        # Mock rate limit exceeded
        mock_rate_limit = AIRateLimit(
            tenant_id=safety_service_growth.tenant_id,
            operation_type="action_execution",
            window_start=datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0),
            count=50,
            limit_value=50,
        )

        def mock_query_side_effect(model):
            mock = Mock()
            if model == AIRateLimit:
                mock.filter.return_value.first.return_value = mock_rate_limit
            else:
                mock.filter.return_value.first.return_value = None
            return mock

        safety_service_growth.db.query.side_effect = mock_query_side_effect

        result = safety_service_growth.check_action_safety(
            platform="meta",
            entity_type="campaign",
            entity_id="campaign_123",
            action_type="pause_campaign",
        )

        assert result.allowed is False
        assert "rate limit" in result.reason.lower()

    def test_check_action_safety_checks_cooldown_after_rate_limit(self, safety_service_growth):
        """check_action_safety should check cooldown after rate limit passes."""
        # Mock rate limit OK but cooldown active
        mock_rate_limit = AIRateLimit(
            tenant_id=safety_service_growth.tenant_id,
            operation_type="action_execution",
            window_start=datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0),
            count=10,
            limit_value=50,
        )
        mock_cooldown = AICooldown(
            tenant_id=safety_service_growth.tenant_id,
            platform="meta",
            entity_type="campaign",
            entity_id="campaign_123",
            action_type="pause_campaign",
            last_action_at=datetime.now(timezone.utc) - timedelta(minutes=30),
            cooldown_until=datetime.now(timezone.utc) + timedelta(minutes=30),
        )

        def mock_query_side_effect(model):
            mock = Mock()
            if model == AIRateLimit:
                mock.filter.return_value.first.return_value = mock_rate_limit
            elif model == AICooldown:
                mock.filter.return_value.first.return_value = mock_cooldown
            else:
                mock.filter.return_value.first.return_value = None
            return mock

        safety_service_growth.db.query.side_effect = mock_query_side_effect

        result = safety_service_growth.check_action_safety(
            platform="meta",
            entity_type="campaign",
            entity_id="campaign_123",
            action_type="pause_campaign",
        )

        assert result.allowed is False
        assert "cooldown" in result.reason.lower()

    def test_check_action_safety_allows_when_all_pass(self, safety_service_growth):
        """check_action_safety should allow when all checks pass."""
        # Mock everything OK
        mock_rate_limit = AIRateLimit(
            tenant_id=safety_service_growth.tenant_id,
            operation_type="action_execution",
            window_start=datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0),
            count=10,
            limit_value=50,
        )

        def mock_query_side_effect(model):
            mock = Mock()
            if model == AIRateLimit:
                mock.filter.return_value.first.return_value = mock_rate_limit
            else:
                mock.filter.return_value.first.return_value = None
            return mock

        safety_service_growth.db.query.side_effect = mock_query_side_effect

        result = safety_service_growth.check_action_safety(
            platform="meta",
            entity_type="campaign",
            entity_id="campaign_123",
            action_type="pause_campaign",
        )

        assert result.allowed is True


# =============================================================================
# Safety Event Logging Tests
# =============================================================================


class TestSafetyEventLogging:
    """Tests for safety event logging."""

    def test_log_action_blocked_creates_event(self, safety_service_growth):
        """log_action_blocked should create a safety event."""
        safety_service_growth.log_action_blocked(
            action_id="action-123",
            reason="Rate limit exceeded",
            blocked_by="rate_limit",
        )

        safety_service_growth.db.add.assert_called()
        added_event = safety_service_growth.db.add.call_args[0][0]
        assert isinstance(added_event, AISafetyEvent)
        assert added_event.event_type == "action_blocked"
        assert added_event.action_id == "action-123"

    def test_log_action_suppressed_creates_event(self, safety_service_growth):
        """log_action_suppressed should create a safety event."""
        safety_service_growth.log_action_suppressed(
            reason="Max recommendations reached",
            event_metadata={"count": 25},
        )

        safety_service_growth.db.add.assert_called()
        added_event = safety_service_growth.db.add.call_args[0][0]
        assert isinstance(added_event, AISafetyEvent)
        assert added_event.event_type == "action_suppressed"

    def test_safety_event_includes_correlation_id(self, safety_service_growth):
        """Safety events should include correlation_id when provided."""
        safety_service_growth.log_action_blocked(
            action_id="action-123",
            reason="Test",
            blocked_by="test",
            correlation_id="corr-456",
        )

        added_event = safety_service_growth.db.add.call_args[0][0]
        assert added_event.correlation_id == "corr-456"


# =============================================================================
# Record Action Execution Tests
# =============================================================================


class TestRecordActionExecution:
    """Tests for recording action execution."""

    def test_record_action_execution_updates_both(self, safety_service_growth):
        """record_action_execution should update rate limit and cooldown."""
        # Mock existing rate limit
        mock_rate_limit = AIRateLimit(
            tenant_id=safety_service_growth.tenant_id,
            operation_type="action_execution",
            window_start=datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0),
            count=10,
            limit_value=50,
        )

        def mock_query_side_effect(model):
            mock = Mock()
            if model == AIRateLimit:
                mock.filter.return_value.first.return_value = mock_rate_limit
            else:
                mock.filter.return_value.first.return_value = None
            return mock

        safety_service_growth.db.query.side_effect = mock_query_side_effect

        safety_service_growth.record_action_execution(
            platform="meta",
            entity_type="campaign",
            entity_id="campaign_123",
            action_type="pause_campaign",
        )

        # Rate limit should be incremented
        assert mock_rate_limit.count == 11
        # Cooldown should be added
        safety_service_growth.db.add.assert_called()


# =============================================================================
# Rate Limit Status Tests
# =============================================================================


class TestRateLimitStatus:
    """Tests for getting rate limit status."""

    def test_get_status_returns_correct_values(self, safety_service_growth):
        """get_rate_limit_status should return correct values."""
        mock_rate_limit = AIRateLimit(
            tenant_id=safety_service_growth.tenant_id,
            operation_type="action_execution",
            window_start=datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0),
            count=30,
            limit_value=50,
        )
        mock_query = Mock()
        mock_query.filter.return_value.first.return_value = mock_rate_limit
        safety_service_growth.db.query.return_value = mock_query

        status = safety_service_growth.get_rate_limit_status("action_execution")

        assert status.count == 30
        assert status.limit == 50
        assert status.remaining == 20
        assert status.is_limited is False

    def test_get_status_unlimited_for_enterprise(self, safety_service_enterprise):
        """get_rate_limit_status should show unlimited for enterprise."""
        status = safety_service_enterprise.get_rate_limit_status("action_execution")

        assert status.limit == -1
        assert status.remaining == -1
        assert status.is_limited is False
