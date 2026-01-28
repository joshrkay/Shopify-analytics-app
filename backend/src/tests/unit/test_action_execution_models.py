"""
Unit tests for Action Execution models (Story 8.5).

Tests cover:
- AIAction model creation and validation
- ActionExecutionLog model creation
- ActionJob model creation
- Status transitions and validation

Story 8.5 - Action Execution (Scoped & Reversible)
"""

import pytest
import uuid
from datetime import datetime, timezone, timedelta

from src.models.ai_action import (
    AIAction,
    ActionStatus,
    ActionType,
    ActionTargetEntityType,
    Platform,
)
from src.models.action_execution_log import (
    ActionExecutionLog,
    ActionLogEventType,
)
from src.models.action_job import (
    ActionJob,
    ActionJobStatus,
)


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def tenant_id():
    """Test tenant ID."""
    return "test-tenant-123"


@pytest.fixture
def recommendation_id():
    """Test recommendation ID."""
    return str(uuid.uuid4())


@pytest.fixture
def sample_action(tenant_id, recommendation_id):
    """Create a sample action."""
    return AIAction(
        id=str(uuid.uuid4()),
        tenant_id=tenant_id,
        recommendation_id=recommendation_id,
        action_type=ActionType.PAUSE_CAMPAIGN,
        platform="meta",
        target_entity_id="campaign_123",
        target_entity_type=ActionTargetEntityType.CAMPAIGN,
        action_params={"status": "paused"},
        status=ActionStatus.PENDING_APPROVAL,
        content_hash="abc123def456",
    )


@pytest.fixture
def sample_job(tenant_id):
    """Create a sample action job."""
    action_ids = [str(uuid.uuid4()) for _ in range(3)]
    return ActionJob(
        job_id=str(uuid.uuid4()),
        tenant_id=tenant_id,
        status=ActionJobStatus.QUEUED,
        action_ids=action_ids,
    )


# =============================================================================
# AIAction Model Tests
# =============================================================================


class TestAIActionModel:
    """Tests for AIAction model."""

    def test_creates_with_required_fields(self, tenant_id, recommendation_id):
        """Should create AIAction with required fields."""
        action = AIAction(
            tenant_id=tenant_id,
            recommendation_id=recommendation_id,
            action_type=ActionType.ADJUST_BUDGET,
            platform="google",
            target_entity_id="campaign_456",
            target_entity_type=ActionTargetEntityType.CAMPAIGN,
            action_params={"new_budget": 1000, "currency": "USD"},
            content_hash="xyz789",
        )

        assert action.tenant_id == tenant_id
        assert action.action_type == ActionType.ADJUST_BUDGET
        assert action.platform == "google"
        assert action.status == ActionStatus.PENDING_APPROVAL

    def test_is_pending_approval_returns_true_initially(self, sample_action):
        """is_pending_approval should return True for new actions."""
        assert sample_action.status == ActionStatus.PENDING_APPROVAL
        assert sample_action.is_pending_approval is True

    def test_is_approved_returns_true_after_approval(self, sample_action):
        """is_approved should return True after approval."""
        sample_action.approve("user-123")
        assert sample_action.is_approved is True

    def test_is_terminal_for_all_terminal_statuses(self, sample_action):
        """is_terminal should return True for all terminal statuses."""
        terminal_statuses = [
            ActionStatus.SUCCEEDED,
            ActionStatus.FAILED,
            ActionStatus.PARTIALLY_EXECUTED,
            ActionStatus.ROLLED_BACK,
            ActionStatus.ROLLBACK_FAILED,
        ]

        # Set up action in executing state first
        sample_action.approve("user-123")
        sample_action.mark_executing("idempotency-key")

        for status in terminal_statuses:
            # Reset to executing for each test
            sample_action.status = ActionStatus.EXECUTING

            if status == ActionStatus.SUCCEEDED:
                sample_action.mark_succeeded({}, {})
            elif status == ActionStatus.FAILED:
                sample_action.mark_failed("error", "ERR001")
            elif status == ActionStatus.PARTIALLY_EXECUTED:
                sample_action.mark_partially_executed("partial", {}, {})

            assert sample_action.is_terminal is True, f"Failed for {status}"

    def test_can_be_executed_for_approved_and_queued(self, sample_action):
        """can_be_executed should return True for APPROVED and QUEUED."""
        sample_action.approve("user-123")
        assert sample_action.can_be_executed is True

        sample_action.queue_for_execution()
        assert sample_action.can_be_executed is True

    def test_can_be_executed_false_for_other_statuses(self, sample_action):
        """can_be_executed should return False for non-executable statuses."""
        assert sample_action.can_be_executed is False  # PENDING_APPROVAL

        sample_action.approve("user-123")
        sample_action.mark_executing("key")
        assert sample_action.can_be_executed is False  # EXECUTING

    def test_can_be_rolled_back_only_for_succeeded_with_instructions(self, sample_action):
        """can_be_rolled_back should only return True for succeeded with rollback instructions."""
        sample_action.approve("user-123")
        sample_action.mark_executing("key")
        sample_action.mark_succeeded(
            before_state={"status": "active"},
            after_state={"status": "paused"},
            rollback_instructions={"action": "resume"},
        )

        assert sample_action.can_be_rolled_back is True

    def test_can_be_rolled_back_false_without_instructions(self, sample_action):
        """can_be_rolled_back should return False without rollback instructions."""
        sample_action.approve("user-123")
        sample_action.mark_executing("key")
        sample_action.mark_succeeded(
            before_state={"status": "active"},
            after_state={"status": "paused"},
            rollback_instructions=None,
        )

        assert sample_action.can_be_rolled_back is False


class TestAIActionStatusTransitions:
    """Tests for AIAction status transition methods."""

    def test_approve_sets_approved_status(self, sample_action):
        """approve() should set status to APPROVED."""
        user_id = "user-123"
        sample_action.approve(user_id)

        assert sample_action.status == ActionStatus.APPROVED
        assert sample_action.approved_by == user_id
        assert sample_action.approved_at is not None

    def test_approve_raises_if_not_pending_approval(self, sample_action):
        """approve() should raise ValueError if not in PENDING_APPROVAL status."""
        sample_action.approve("user-123")

        with pytest.raises(ValueError, match="Cannot approve action"):
            sample_action.approve("user-456")

    def test_queue_for_execution_requires_approved_status(self, sample_action):
        """queue_for_execution() should require APPROVED status."""
        with pytest.raises(ValueError, match="Cannot queue action"):
            sample_action.queue_for_execution()

        sample_action.approve("user-123")
        sample_action.queue_for_execution()
        assert sample_action.status == ActionStatus.QUEUED

    def test_mark_executing_sets_idempotency_key(self, sample_action):
        """mark_executing() should set idempotency key and timestamp."""
        sample_action.approve("user-123")
        sample_action.mark_executing("unique-key-123")

        assert sample_action.status == ActionStatus.EXECUTING
        assert sample_action.idempotency_key == "unique-key-123"
        assert sample_action.execution_started_at is not None

    def test_mark_succeeded_requires_state_snapshots(self, sample_action):
        """mark_succeeded() should store before/after state."""
        sample_action.approve("user-123")
        sample_action.mark_executing("key")

        before = {"budget": 1000}
        after = {"budget": 850}
        rollback = {"restore_budget": 1000}

        sample_action.mark_succeeded(before, after, rollback)

        assert sample_action.status == ActionStatus.SUCCEEDED
        assert sample_action.before_state == before
        assert sample_action.after_state == after
        assert sample_action.rollback_instructions == rollback
        assert sample_action.execution_completed_at is not None

    def test_mark_failed_stores_error_details(self, sample_action):
        """mark_failed() should store error message and code."""
        sample_action.approve("user-123")
        sample_action.mark_executing("key")

        sample_action.mark_failed("API rate limit exceeded", "RATE_LIMIT")

        assert sample_action.status == ActionStatus.FAILED
        assert sample_action.error_message == "API rate limit exceeded"
        assert sample_action.error_code == "RATE_LIMIT"
        assert sample_action.execution_completed_at is not None

    def test_mark_rolled_back_requires_succeeded_status(self, sample_action):
        """mark_rolled_back() should require SUCCEEDED status."""
        sample_action.approve("user-123")
        sample_action.mark_executing("key")
        sample_action.mark_succeeded({}, {}, {"action": "restore"})

        sample_action.mark_rolled_back()

        assert sample_action.status == ActionStatus.ROLLED_BACK
        assert sample_action.rollback_executed_at is not None

    def test_mark_rollback_failed_stores_error(self, sample_action):
        """mark_rollback_failed() should store error message."""
        sample_action.approve("user-123")
        sample_action.mark_executing("key")
        sample_action.mark_succeeded({}, {}, {"action": "restore"})

        sample_action.mark_rollback_failed("Platform rejected rollback")

        assert sample_action.status == ActionStatus.ROLLBACK_FAILED
        assert sample_action.error_message == "Platform rejected rollback"

    def test_increment_retry_increases_count(self, sample_action):
        """increment_retry() should increase retry count."""
        assert sample_action.retry_count == 0

        sample_action.increment_retry()
        assert sample_action.retry_count == 1

        sample_action.increment_retry()
        assert sample_action.retry_count == 2


# =============================================================================
# ActionExecutionLog Model Tests
# =============================================================================


class TestActionExecutionLogModel:
    """Tests for ActionExecutionLog model."""

    def test_log_created_factory_method(self, tenant_id):
        """log_created should create a log entry for action creation."""
        action_id = str(uuid.uuid4())

        log = ActionExecutionLog.log_created(
            tenant_id=tenant_id,
            action_id=action_id,
            triggered_by="system",
        )

        assert log.tenant_id == tenant_id
        assert log.action_id == action_id
        assert log.event_type == ActionLogEventType.CREATED
        assert log.triggered_by == "system"

    def test_log_approved_includes_user_id(self, tenant_id):
        """log_approved should include user ID in triggered_by."""
        action_id = str(uuid.uuid4())
        user_id = "user-123"

        log = ActionExecutionLog.log_approved(
            tenant_id=tenant_id,
            action_id=action_id,
            user_id=user_id,
        )

        assert log.event_type == ActionLogEventType.APPROVED
        assert log.triggered_by == f"user:{user_id}"

    def test_log_execution_started_includes_job_id(self, tenant_id):
        """log_execution_started should include job ID in triggered_by."""
        action_id = str(uuid.uuid4())
        job_id = str(uuid.uuid4())

        log = ActionExecutionLog.log_execution_started(
            tenant_id=tenant_id,
            action_id=action_id,
            job_id=job_id,
        )

        assert log.event_type == ActionLogEventType.EXECUTION_STARTED
        assert log.triggered_by == f"worker:{job_id}"

    def test_log_state_captured_for_before_and_after(self, tenant_id):
        """log_state_captured should work for both before and after states."""
        action_id = str(uuid.uuid4())
        state = {"budget": 1000}

        before_log = ActionExecutionLog.log_state_captured(
            tenant_id=tenant_id,
            action_id=action_id,
            state_snapshot=state,
            is_before=True,
        )

        after_log = ActionExecutionLog.log_state_captured(
            tenant_id=tenant_id,
            action_id=action_id,
            state_snapshot=state,
            is_before=False,
        )

        assert before_log.event_type == ActionLogEventType.BEFORE_STATE_CAPTURED
        assert after_log.event_type == ActionLogEventType.AFTER_STATE_CAPTURED
        assert before_log.state_snapshot == state

    def test_log_api_request_stores_payload(self, tenant_id):
        """log_api_request should store request payload."""
        action_id = str(uuid.uuid4())
        payload = {"campaign_id": "123", "status": "paused"}

        log = ActionExecutionLog.log_api_request(
            tenant_id=tenant_id,
            action_id=action_id,
            request_payload=payload,
        )

        assert log.event_type == ActionLogEventType.API_REQUEST_SENT
        assert log.request_payload == payload

    def test_log_api_response_stores_response_and_status(self, tenant_id):
        """log_api_response should store response and HTTP status."""
        action_id = str(uuid.uuid4())
        response = {"success": True, "id": "123"}

        log = ActionExecutionLog.log_api_response(
            tenant_id=tenant_id,
            action_id=action_id,
            response_payload=response,
            http_status_code=200,
        )

        assert log.event_type == ActionLogEventType.API_RESPONSE_RECEIVED
        assert log.response_payload == response
        assert log.http_status_code == 200

    def test_log_execution_failed_stores_error_details(self, tenant_id):
        """log_execution_failed should store error details."""
        action_id = str(uuid.uuid4())
        error_details = {"code": "ERR001", "message": "Rate limit exceeded"}

        log = ActionExecutionLog.log_execution_failed(
            tenant_id=tenant_id,
            action_id=action_id,
            error_details=error_details,
            http_status_code=429,
        )

        assert log.event_type == ActionLogEventType.EXECUTION_FAILED
        assert log.error_details == error_details
        assert log.http_status_code == 429

    def test_log_rollback_succeeded(self, tenant_id):
        """log_rollback_succeeded should create proper entry."""
        action_id = str(uuid.uuid4())
        state = {"status": "active"}

        log = ActionExecutionLog.log_rollback_succeeded(
            tenant_id=tenant_id,
            action_id=action_id,
            state_snapshot=state,
        )

        assert log.event_type == ActionLogEventType.ROLLBACK_SUCCEEDED
        assert log.state_snapshot == state


# =============================================================================
# ActionJob Model Tests
# =============================================================================


class TestActionJobModel:
    """Tests for ActionJob model."""

    def test_creates_with_required_fields(self, tenant_id):
        """Should create ActionJob with required fields."""
        action_ids = [str(uuid.uuid4())]

        job = ActionJob(
            tenant_id=tenant_id,
            status=ActionJobStatus.QUEUED,
            action_ids=action_ids,
        )

        assert job.tenant_id == tenant_id
        assert job.status == ActionJobStatus.QUEUED
        assert job.action_ids == action_ids

    def test_is_running_returns_true_for_running_status(self, sample_job):
        """is_running should return True for RUNNING status."""
        sample_job.status = ActionJobStatus.RUNNING
        assert sample_job.is_running is True

    def test_is_running_returns_false_for_other_statuses(self, sample_job):
        """is_running should return False for non-RUNNING statuses."""
        assert sample_job.is_running is False  # QUEUED

    def test_is_completed_for_all_completed_statuses(self, sample_job):
        """is_completed should return True for all completed statuses."""
        completed_statuses = [
            ActionJobStatus.SUCCEEDED,
            ActionJobStatus.FAILED,
            ActionJobStatus.PARTIAL_SUCCESS,
        ]

        for status in completed_statuses:
            sample_job.status = status
            assert sample_job.is_completed is True, f"Failed for {status}"

    def test_is_completed_false_for_active_statuses(self, sample_job):
        """is_completed should return False for active statuses."""
        sample_job.status = ActionJobStatus.QUEUED
        assert sample_job.is_completed is False

        sample_job.status = ActionJobStatus.RUNNING
        assert sample_job.is_completed is False

    def test_start_sets_running_status_and_timestamp(self, sample_job):
        """start() should set status to RUNNING and record timestamp."""
        sample_job.start()

        assert sample_job.status == ActionJobStatus.RUNNING
        assert sample_job.started_at is not None

    def test_start_raises_if_not_queued(self, sample_job):
        """start() should raise if not in QUEUED status."""
        sample_job.status = ActionJobStatus.RUNNING

        with pytest.raises(ValueError, match="Cannot start job"):
            sample_job.start()

    def test_finalize_determines_status_from_counts(self, sample_job):
        """finalize() should determine status based on succeeded/failed counts."""
        sample_job.start()

        # All succeeded
        sample_job.succeeded_count = 3
        sample_job.failed_count = 0
        sample_job.finalize()
        assert sample_job.status == ActionJobStatus.SUCCEEDED

    def test_finalize_sets_failed_when_all_failed(self, sample_job):
        """finalize() should set FAILED when all actions failed."""
        sample_job.start()
        sample_job.succeeded_count = 0
        sample_job.failed_count = 3
        sample_job.finalize()

        assert sample_job.status == ActionJobStatus.FAILED

    def test_finalize_sets_partial_success_when_mixed(self, sample_job):
        """finalize() should set PARTIAL_SUCCESS when some succeeded and some failed."""
        sample_job.start()
        sample_job.succeeded_count = 2
        sample_job.failed_count = 1
        sample_job.finalize()

        assert sample_job.status == ActionJobStatus.PARTIAL_SUCCESS

    def test_finalize_sets_completed_at(self, sample_job):
        """finalize() should set completed_at timestamp."""
        sample_job.start()
        sample_job.succeeded_count = 3
        sample_job.finalize()

        assert sample_job.completed_at is not None

    def test_increment_succeeded(self, sample_job):
        """increment_succeeded() should increase succeeded count."""
        sample_job.start()

        sample_job.increment_succeeded()
        assert sample_job.succeeded_count == 1

        sample_job.increment_succeeded()
        assert sample_job.succeeded_count == 2

    def test_increment_failed(self, sample_job):
        """increment_failed() should increase failed count."""
        sample_job.start()

        sample_job.increment_failed()
        assert sample_job.failed_count == 1

        sample_job.increment_failed()
        assert sample_job.failed_count == 2


# =============================================================================
# Enum Tests
# =============================================================================


class TestActionTypeEnum:
    """Tests for ActionType enum."""

    def test_all_action_types_have_string_values(self):
        """All action types should have snake_case string values."""
        for action_type in ActionType:
            assert isinstance(action_type.value, str)
            assert action_type.value.islower()

    def test_core_action_types_exist(self):
        """Core action types should be defined."""
        assert ActionType.PAUSE_CAMPAIGN.value == "pause_campaign"
        assert ActionType.RESUME_CAMPAIGN.value == "resume_campaign"
        assert ActionType.ADJUST_BUDGET.value == "adjust_budget"
        assert ActionType.ADJUST_BID.value == "adjust_bid"


class TestActionStatusEnum:
    """Tests for ActionStatus enum."""

    def test_pending_approval_is_initial_status(self):
        """PENDING_APPROVAL should be the initial status for new actions."""
        assert ActionStatus.PENDING_APPROVAL.value == "pending_approval"

    def test_all_lifecycle_statuses_are_defined(self):
        """All lifecycle statuses should be defined."""
        lifecycle = [
            ActionStatus.PENDING_APPROVAL,
            ActionStatus.APPROVED,
            ActionStatus.QUEUED,
            ActionStatus.EXECUTING,
            ActionStatus.SUCCEEDED,
            ActionStatus.FAILED,
            ActionStatus.PARTIALLY_EXECUTED,
            ActionStatus.ROLLED_BACK,
            ActionStatus.ROLLBACK_FAILED,
        ]
        for status in lifecycle:
            assert status in ActionStatus


class TestActionJobStatusEnum:
    """Tests for ActionJobStatus enum."""

    def test_all_job_statuses_are_defined(self):
        """All job statuses should be defined."""
        assert ActionJobStatus.QUEUED.value == "queued"
        assert ActionJobStatus.RUNNING.value == "running"
        assert ActionJobStatus.SUCCEEDED.value == "succeeded"
        assert ActionJobStatus.FAILED.value == "failed"
        assert ActionJobStatus.PARTIAL_SUCCESS.value == "partial_success"


class TestActionLogEventTypeEnum:
    """Tests for ActionLogEventType enum."""

    def test_lifecycle_events_are_defined(self):
        """Lifecycle events should be defined."""
        assert ActionLogEventType.CREATED.value == "created"
        assert ActionLogEventType.APPROVED.value == "approved"
        assert ActionLogEventType.QUEUED.value == "queued"
        assert ActionLogEventType.CANCELLED.value == "cancelled"

    def test_execution_events_are_defined(self):
        """Execution events should be defined."""
        assert ActionLogEventType.EXECUTION_STARTED.value == "execution_started"
        assert ActionLogEventType.BEFORE_STATE_CAPTURED.value == "before_state_captured"
        assert ActionLogEventType.API_REQUEST_SENT.value == "api_request_sent"
        assert ActionLogEventType.API_RESPONSE_RECEIVED.value == "api_response_received"
        assert ActionLogEventType.AFTER_STATE_CAPTURED.value == "after_state_captured"
        assert ActionLogEventType.EXECUTION_SUCCEEDED.value == "execution_succeeded"
        assert ActionLogEventType.EXECUTION_FAILED.value == "execution_failed"

    def test_rollback_events_are_defined(self):
        """Rollback events should be defined."""
        assert ActionLogEventType.ROLLBACK_STARTED.value == "rollback_started"
        assert ActionLogEventType.ROLLBACK_SUCCEEDED.value == "rollback_succeeded"
        assert ActionLogEventType.ROLLBACK_FAILED.value == "rollback_failed"
