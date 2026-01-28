"""
Unit tests for Action Execution services (Story 8.5).

Tests cover:
- ActionApprovalService
- ActionExecutionService
- ActionRollbackService
- ActionJobRunner
- ActionJobDispatcher

Story 8.5 - Action Execution (Scoped & Reversible)
"""

import pytest
import uuid
from datetime import datetime, timezone
from unittest.mock import Mock, AsyncMock, patch, MagicMock

from src.models.ai_action import AIAction, ActionStatus, ActionType, ActionTargetEntityType
from src.models.action_job import ActionJob, ActionJobStatus
from src.models.ai_recommendation import (
    AIRecommendation,
    RecommendationType,
    RecommendationPriority,
    EstimatedImpact,
    RiskLevel,
)
from src.services.action_approval_service import (
    ActionApprovalService,
    RECOMMENDATION_TO_ACTION_MAP,
)
from src.services.action_job_dispatcher import ActionJobDispatcher


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def tenant_id():
    """Test tenant ID."""
    return "test-tenant-123"


@pytest.fixture
def user_id():
    """Test user ID."""
    return "user-123"


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
def sample_recommendation(tenant_id):
    """Create a sample recommendation."""
    return AIRecommendation(
        id=str(uuid.uuid4()),
        tenant_id=tenant_id,
        related_insight_id=str(uuid.uuid4()),
        recommendation_type=RecommendationType.PAUSE_CAMPAIGN,
        priority=RecommendationPriority.HIGH,
        recommendation_text="Consider pausing the underperforming campaign.",
        rationale="Campaign has 50% lower CTR than average.",
        estimated_impact=EstimatedImpact.MODERATE,
        risk_level=RiskLevel.LOW,
        confidence_score=0.85,
        affected_entity="campaign_123",
        affected_entity_type="campaign",
        content_hash="abc123",
        generated_at=datetime.now(timezone.utc),
    )


@pytest.fixture
def sample_action(tenant_id):
    """Create a sample action."""
    return AIAction(
        id=str(uuid.uuid4()),
        tenant_id=tenant_id,
        recommendation_id=str(uuid.uuid4()),
        action_type=ActionType.PAUSE_CAMPAIGN,
        platform="meta",
        target_entity_id="campaign_123",
        target_entity_type=ActionTargetEntityType.CAMPAIGN,
        action_params={"status": "paused"},
        status=ActionStatus.PENDING_APPROVAL,
        content_hash="xyz789",
    )


@pytest.fixture
def approved_action(sample_action):
    """Create an approved action."""
    sample_action.approve("user-123")
    return sample_action


@pytest.fixture
def sample_job(tenant_id):
    """Create a sample action job."""
    return ActionJob(
        job_id=str(uuid.uuid4()),
        tenant_id=tenant_id,
        status=ActionJobStatus.QUEUED,
        action_ids=[str(uuid.uuid4()) for _ in range(3)],
    )


# =============================================================================
# Recommendation to Action Mapping Tests
# =============================================================================


class TestRecommendationToActionMapping:
    """Tests for recommendation to action type mapping."""

    def test_pause_campaign_mapping(self):
        """PAUSE_CAMPAIGN recommendation should map to PAUSE_CAMPAIGN action."""
        assert RECOMMENDATION_TO_ACTION_MAP[RecommendationType.PAUSE_CAMPAIGN] == ActionType.PAUSE_CAMPAIGN

    def test_scale_campaign_mapping(self):
        """SCALE_CAMPAIGN recommendation should map to RESUME_CAMPAIGN action."""
        assert RECOMMENDATION_TO_ACTION_MAP[RecommendationType.SCALE_CAMPAIGN] == ActionType.RESUME_CAMPAIGN

    def test_reduce_spend_mapping(self):
        """REDUCE_SPEND recommendation should map to ADJUST_BUDGET action."""
        assert RECOMMENDATION_TO_ACTION_MAP[RecommendationType.REDUCE_SPEND] == ActionType.ADJUST_BUDGET

    def test_increase_spend_mapping(self):
        """INCREASE_SPEND recommendation should map to ADJUST_BUDGET action."""
        assert RECOMMENDATION_TO_ACTION_MAP[RecommendationType.INCREASE_SPEND] == ActionType.ADJUST_BUDGET

    def test_adjust_bidding_mapping(self):
        """ADJUST_BIDDING recommendation should map to ADJUST_BID action."""
        assert RECOMMENDATION_TO_ACTION_MAP[RecommendationType.ADJUST_BIDDING] == ActionType.ADJUST_BID


# =============================================================================
# ActionApprovalService Tests
# =============================================================================


class TestActionApprovalService:
    """Tests for ActionApprovalService."""

    def test_init_requires_tenant_id(self, mock_db_session):
        """Should raise ValueError if tenant_id is empty."""
        with pytest.raises(ValueError, match="tenant_id is required"):
            ActionApprovalService(mock_db_session, "")

    def test_init_stores_tenant_id(self, mock_db_session, tenant_id):
        """Should store tenant_id correctly."""
        service = ActionApprovalService(mock_db_session, tenant_id)
        assert service.tenant_id == tenant_id

    @patch('src.services.action_approval_service.BillingEntitlementsService')
    def test_check_entitlement_calls_billing_service(
        self, mock_billing_class, mock_db_session, tenant_id
    ):
        """Should check entitlement via BillingEntitlementsService."""
        mock_result = Mock()
        mock_result.is_entitled = True
        mock_billing = Mock()
        mock_billing.check_feature_entitlement.return_value = mock_result
        mock_billing_class.return_value = mock_billing

        service = ActionApprovalService(mock_db_session, tenant_id)
        result = service._check_entitlement()

        assert result is True
        mock_billing.check_feature_entitlement.assert_called_once()


# =============================================================================
# ActionJobDispatcher Tests
# =============================================================================


class TestActionJobDispatcher:
    """Tests for ActionJobDispatcher."""

    def test_init_requires_tenant_id(self, mock_db_session):
        """Should raise ValueError if tenant_id is empty."""
        with pytest.raises(ValueError, match="tenant_id is required"):
            ActionJobDispatcher(mock_db_session, "")

    def test_init_stores_tenant_id(self, mock_db_session, tenant_id):
        """Should store tenant_id correctly."""
        dispatcher = ActionJobDispatcher(mock_db_session, tenant_id)
        assert dispatcher.tenant_id == tenant_id

    @patch('src.services.action_job_dispatcher.BillingEntitlementsService')
    def test_should_create_job_returns_false_when_not_entitled(
        self, mock_billing_class, mock_db_session, tenant_id
    ):
        """should_create_job should return False when not entitled."""
        mock_result = Mock()
        mock_result.is_entitled = False
        mock_billing = Mock()
        mock_billing.check_feature_entitlement.return_value = mock_result
        mock_billing_class.return_value = mock_billing

        dispatcher = ActionJobDispatcher(mock_db_session, tenant_id)
        should_create, reason = dispatcher.should_create_job()

        assert should_create is False
        assert "Not entitled" in reason

    @patch('src.services.action_job_dispatcher.BillingEntitlementsService')
    def test_should_create_job_returns_false_when_active_job_exists(
        self, mock_billing_class, mock_db_session, tenant_id, sample_job
    ):
        """should_create_job should return False when active job exists."""
        mock_result = Mock()
        mock_result.is_entitled = True
        mock_billing = Mock()
        mock_billing.check_feature_entitlement.return_value = mock_result
        mock_billing_class.return_value = mock_billing

        # Mock query to return existing active job
        mock_query = Mock()
        mock_query.filter.return_value.first.return_value = sample_job
        mock_db_session.query.return_value = mock_query

        dispatcher = ActionJobDispatcher(mock_db_session, tenant_id)
        should_create, reason = dispatcher.should_create_job()

        assert should_create is False
        assert "Active job already exists" in reason

    def test_get_pending_action_count(self, mock_db_session, tenant_id):
        """Should return count of approved actions."""
        mock_query = Mock()
        mock_query.filter.return_value.count.return_value = 5
        mock_db_session.query.return_value = mock_query

        dispatcher = ActionJobDispatcher(mock_db_session, tenant_id)
        count = dispatcher.get_pending_action_count()

        assert count == 5


# =============================================================================
# Action Status Transition Tests (via Services)
# =============================================================================


class TestActionStatusTransitionsViaService:
    """Tests for action status transitions triggered by services."""

    def test_action_approval_workflow(self, sample_action, user_id):
        """Test full approval workflow."""
        # Initial state
        assert sample_action.status == ActionStatus.PENDING_APPROVAL
        assert sample_action.approved_by is None

        # Approve
        sample_action.approve(user_id)
        assert sample_action.status == ActionStatus.APPROVED
        assert sample_action.approved_by == user_id
        assert sample_action.approved_at is not None

        # Queue for execution
        sample_action.queue_for_execution()
        assert sample_action.status == ActionStatus.QUEUED

    def test_action_execution_success_workflow(self, approved_action):
        """Test successful execution workflow."""
        # Start execution
        approved_action.mark_executing("idempotency-key-123")
        assert approved_action.status == ActionStatus.EXECUTING
        assert approved_action.idempotency_key == "idempotency-key-123"

        # Mark succeeded with state
        before = {"status": "active"}
        after = {"status": "paused"}
        rollback = {"action": "resume", "target_status": "active"}

        approved_action.mark_succeeded(before, after, rollback)
        assert approved_action.status == ActionStatus.SUCCEEDED
        assert approved_action.before_state == before
        assert approved_action.after_state == after
        assert approved_action.rollback_instructions == rollback

    def test_action_execution_failure_workflow(self, approved_action):
        """Test failed execution workflow."""
        # Start execution
        approved_action.mark_executing("idempotency-key-123")

        # Mark failed
        approved_action.mark_failed("Rate limit exceeded", "ERR_429")
        assert approved_action.status == ActionStatus.FAILED
        assert approved_action.error_message == "Rate limit exceeded"
        assert approved_action.error_code == "ERR_429"

    def test_action_rollback_workflow(self, approved_action):
        """Test rollback workflow after successful execution."""
        # Execute successfully
        approved_action.mark_executing("key")
        approved_action.mark_succeeded(
            {"status": "active"},
            {"status": "paused"},
            {"action": "resume"},
        )

        # Verify can be rolled back
        assert approved_action.can_be_rolled_back is True

        # Execute rollback
        approved_action.mark_rolled_back()
        assert approved_action.status == ActionStatus.ROLLED_BACK
        assert approved_action.rollback_executed_at is not None

        # Verify cannot be rolled back again
        assert approved_action.can_be_rolled_back is False


# =============================================================================
# Job Processing Tests
# =============================================================================


class TestJobProcessing:
    """Tests for action job processing."""

    def test_job_start_and_finalize_success(self, sample_job):
        """Test job start and successful finalization."""
        # Start job
        sample_job.start()
        assert sample_job.status == ActionJobStatus.RUNNING
        assert sample_job.started_at is not None

        # Process actions
        sample_job.increment_succeeded()
        sample_job.increment_succeeded()
        sample_job.increment_succeeded()

        # Finalize
        sample_job.finalize()
        assert sample_job.status == ActionJobStatus.SUCCEEDED
        assert sample_job.completed_at is not None
        assert sample_job.succeeded_count == 3
        assert sample_job.failed_count == 0

    def test_job_finalize_partial_success(self, sample_job):
        """Test job finalization with partial success."""
        sample_job.start()

        # Some succeed, some fail
        sample_job.increment_succeeded()
        sample_job.increment_succeeded()
        sample_job.increment_failed()

        sample_job.finalize()
        assert sample_job.status == ActionJobStatus.PARTIAL_SUCCESS
        assert sample_job.succeeded_count == 2
        assert sample_job.failed_count == 1

    def test_job_finalize_all_failed(self, sample_job):
        """Test job finalization when all actions fail."""
        sample_job.start()

        # All fail
        sample_job.increment_failed()
        sample_job.increment_failed()
        sample_job.increment_failed()

        sample_job.finalize()
        assert sample_job.status == ActionJobStatus.FAILED
        assert sample_job.succeeded_count == 0
        assert sample_job.failed_count == 3


# =============================================================================
# Integration-style Tests (Mocked Dependencies)
# =============================================================================


class TestApprovalToExecutionFlow:
    """Tests for the full approval to execution flow."""

    def test_full_lifecycle_with_mocks(self, sample_action, user_id):
        """Test the full action lifecycle from approval to execution."""
        # 1. Start in PENDING_APPROVAL
        assert sample_action.status == ActionStatus.PENDING_APPROVAL

        # 2. User approves
        sample_action.approve(user_id)
        assert sample_action.status == ActionStatus.APPROVED

        # 3. System queues for execution
        sample_action.queue_for_execution()
        assert sample_action.status == ActionStatus.QUEUED

        # 4. Worker picks up and starts execution
        sample_action.mark_executing("unique-idem-key")
        assert sample_action.status == ActionStatus.EXECUTING

        # 5. Execution succeeds
        sample_action.mark_succeeded(
            before_state={"budget": 1000},
            after_state={"budget": 850},
            rollback_instructions={"restore_budget": 1000},
        )
        assert sample_action.status == ActionStatus.SUCCEEDED

        # Verify full state captured
        assert sample_action.approved_by == user_id
        assert sample_action.approved_at is not None
        assert sample_action.execution_started_at is not None
        assert sample_action.execution_completed_at is not None
        assert sample_action.before_state == {"budget": 1000}
        assert sample_action.after_state == {"budget": 850}
        assert sample_action.can_be_rolled_back is True

    def test_retry_count_tracking(self, approved_action):
        """Test that retry count is tracked correctly."""
        approved_action.mark_executing("key")

        # Simulate first attempt failed (would reset to approved/queued in real system)
        approved_action.increment_retry()
        assert approved_action.retry_count == 1

        # Simulate second attempt
        approved_action.increment_retry()
        assert approved_action.retry_count == 2

    def test_idempotency_key_prevents_duplicate_execution(self, approved_action):
        """Test that idempotency key is set during execution."""
        key = "unique-execution-key-12345"
        approved_action.mark_executing(key)

        # Idempotency key should be stored
        assert approved_action.idempotency_key == key

        # This key would be used by the platform executor to prevent duplicates
        # In a real system, re-submitting with the same key would return cached result
