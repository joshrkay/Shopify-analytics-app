"""
Integration tests for Actions API (Story 8.5).

Tests the full API endpoints for action execution, including:
- Listing actions
- Getting action details
- Executing actions
- Rolling back actions
- Viewing execution logs
- Job management

Story 8.5 - Action Execution (Scoped & Reversible)
"""

import pytest
import uuid
from datetime import datetime, timezone
from unittest.mock import Mock, patch, AsyncMock

from fastapi.testclient import TestClient
from fastapi import FastAPI

from src.api.routes.actions import router
from src.models.ai_action import AIAction, ActionStatus, ActionType, ActionTargetEntityType
from src.models.action_execution_log import ActionExecutionLog, ActionLogEventType
from src.models.action_job import ActionJob, ActionJobStatus


# =============================================================================
# Test Fixtures
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
def app():
    """Create a test FastAPI app."""
    app = FastAPI()
    app.include_router(router)
    return app


@pytest.fixture
def client(app):
    """Create a test client."""
    return TestClient(app)


@pytest.fixture
def mock_tenant_context(tenant_id, user_id):
    """Create a mock tenant context."""
    ctx = Mock()
    ctx.tenant_id = tenant_id
    ctx.user_id = user_id
    ctx.roles = ["merchant_admin"]
    return ctx


@pytest.fixture
def sample_action(tenant_id):
    """Create a sample action for testing."""
    return AIAction(
        id=str(uuid.uuid4()),
        tenant_id=tenant_id,
        recommendation_id=str(uuid.uuid4()),
        action_type=ActionType.PAUSE_CAMPAIGN,
        platform="meta",
        target_entity_id="campaign_123",
        target_entity_type=ActionTargetEntityType.CAMPAIGN,
        action_params={"status": "paused"},
        status=ActionStatus.APPROVED,
        content_hash="test-hash",
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )


@pytest.fixture
def sample_job(tenant_id):
    """Create a sample job for testing."""
    return ActionJob(
        job_id=str(uuid.uuid4()),
        tenant_id=tenant_id,
        status=ActionJobStatus.SUCCEEDED,
        action_ids=[str(uuid.uuid4())],
        succeeded_count=1,
        failed_count=0,
        created_at=datetime.now(timezone.utc),
    )


@pytest.fixture
def sample_log(tenant_id, sample_action):
    """Create a sample execution log for testing."""
    return ActionExecutionLog(
        id=str(uuid.uuid4()),
        tenant_id=tenant_id,
        action_id=sample_action.id,
        event_type=ActionLogEventType.EXECUTION_SUCCEEDED,
        event_timestamp=datetime.now(timezone.utc),
        triggered_by="system",
    )


# =============================================================================
# Helper to mock dependencies
# =============================================================================


def setup_mocks(
    mock_tenant_context,
    mock_db_session,
    mock_entitlement,
    actions=None,
    jobs=None,
    logs=None,
):
    """Set up common mocks for API tests."""
    # Mock tenant context
    with patch('src.api.routes.actions.get_tenant_context') as mock_get_ctx:
        mock_get_ctx.return_value = mock_tenant_context

        # Mock database session
        with patch('src.api.routes.actions.get_db_session') as mock_get_db:
            mock_get_db.return_value = mock_db_session

            # Mock entitlement check
            with patch('src.api.routes.actions.BillingEntitlementsService') as mock_billing:
                mock_result = Mock()
                mock_result.is_entitled = mock_entitlement
                mock_result.current_tier = "pro"
                mock_result.required_tier = "pro"
                mock_result.details = {"monthly_limit": 100}
                mock_billing.return_value.check_feature_entitlement.return_value = mock_result

                yield


# =============================================================================
# List Actions Tests
# =============================================================================


class TestListActions:
    """Tests for GET /api/actions endpoint."""

    def test_returns_empty_list_when_no_actions(
        self, client, mock_tenant_context
    ):
        """Should return empty list when tenant has no actions."""
        mock_db = Mock()
        mock_query = Mock()
        mock_query.filter.return_value = mock_query
        mock_query.order_by.return_value = mock_query
        mock_query.offset.return_value = mock_query
        mock_query.limit.return_value = mock_query
        mock_query.all.return_value = []
        mock_query.count.return_value = 0
        mock_db.query.return_value = mock_query

        with patch('src.api.routes.actions.get_tenant_context', return_value=mock_tenant_context):
            with patch('src.api.routes.actions.get_db_session', return_value=mock_db):
                with patch('src.api.routes.actions.BillingEntitlementsService') as mock_billing:
                    mock_result = Mock(is_entitled=True)
                    mock_billing.return_value.check_feature_entitlement.return_value = mock_result

                    response = client.get("/api/actions")

        # With all mocks set up, check response structure
        assert response.status_code == 200
        data = response.json()
        assert "actions" in data
        assert "total" in data
        assert "has_more" in data


# =============================================================================
# Get Action Tests
# =============================================================================


class TestGetAction:
    """Tests for GET /api/actions/{action_id} endpoint."""

    def test_returns_404_when_action_not_found(
        self, client, mock_tenant_context
    ):
        """Should return 404 when action doesn't exist."""
        mock_db = Mock()
        mock_query = Mock()
        mock_query.filter.return_value.first.return_value = None
        mock_db.query.return_value = mock_query

        with patch('src.api.routes.actions.get_tenant_context', return_value=mock_tenant_context):
            with patch('src.api.routes.actions.get_db_session', return_value=mock_db):
                with patch('src.api.routes.actions.BillingEntitlementsService') as mock_billing:
                    mock_result = Mock(is_entitled=True)
                    mock_billing.return_value.check_feature_entitlement.return_value = mock_result

                    response = client.get(f"/api/actions/{uuid.uuid4()}")

        assert response.status_code == 404

    def test_returns_action_details(
        self, client, mock_tenant_context, sample_action
    ):
        """Should return action details when found."""
        mock_db = Mock()
        mock_query = Mock()
        mock_query.filter.return_value.first.return_value = sample_action
        mock_db.query.return_value = mock_query

        with patch('src.api.routes.actions.get_tenant_context', return_value=mock_tenant_context):
            with patch('src.api.routes.actions.get_db_session', return_value=mock_db):
                with patch('src.api.routes.actions.BillingEntitlementsService') as mock_billing:
                    mock_result = Mock(is_entitled=True)
                    mock_billing.return_value.check_feature_entitlement.return_value = mock_result

                    response = client.get(f"/api/actions/{sample_action.id}")

        assert response.status_code == 200
        data = response.json()
        assert data["action_id"] == sample_action.id
        assert data["action_type"] == "pause_campaign"
        assert data["platform"] == "meta"


# =============================================================================
# Permission Tests
# =============================================================================


class TestActionPermissions:
    """Tests for action permission checks."""

    def test_returns_402_when_not_entitled(self, client, mock_tenant_context):
        """Should return 402 when tenant is not entitled to AI actions."""
        mock_db = Mock()

        with patch('src.api.routes.actions.get_tenant_context', return_value=mock_tenant_context):
            with patch('src.api.routes.actions.get_db_session', return_value=mock_db):
                with patch('src.api.routes.actions.BillingEntitlementsService') as mock_billing:
                    mock_result = Mock()
                    mock_result.is_entitled = False
                    mock_result.current_tier = "free"
                    mock_result.required_tier = "pro"
                    mock_billing.return_value.check_feature_entitlement.return_value = mock_result

                    response = client.get("/api/actions")

        assert response.status_code == 402

    def test_returns_403_for_viewer_role_on_execute(self, client, tenant_id, user_id):
        """Should return 403 when viewer tries to execute action."""
        viewer_context = Mock()
        viewer_context.tenant_id = tenant_id
        viewer_context.user_id = user_id
        viewer_context.roles = ["merchant_viewer"]  # Viewer cannot execute

        with patch('src.api.routes.actions.get_tenant_context', return_value=viewer_context):
            with patch('src.api.routes.actions.can_execute_actions', return_value=False):
                response = client.post(f"/api/actions/{uuid.uuid4()}/execute")

        assert response.status_code == 403

    def test_returns_403_for_viewer_role_on_rollback(self, client, tenant_id, user_id):
        """Should return 403 when viewer tries to rollback action."""
        viewer_context = Mock()
        viewer_context.tenant_id = tenant_id
        viewer_context.user_id = user_id
        viewer_context.roles = ["merchant_viewer"]  # Viewer cannot rollback

        with patch('src.api.routes.actions.get_tenant_context', return_value=viewer_context):
            with patch('src.api.routes.actions.can_rollback_actions', return_value=False):
                response = client.post(f"/api/actions/{uuid.uuid4()}/rollback")

        assert response.status_code == 403


# =============================================================================
# Execute Action Tests
# =============================================================================


class TestExecuteAction:
    """Tests for POST /api/actions/{action_id}/execute endpoint."""

    def test_returns_400_when_action_cannot_be_executed(
        self, client, mock_tenant_context, sample_action
    ):
        """Should return 400 when action is in non-executable status."""
        # Set action to a non-executable status
        sample_action.status = ActionStatus.SUCCEEDED

        mock_db = Mock()
        mock_query = Mock()
        mock_query.filter.return_value.first.return_value = sample_action
        mock_db.query.return_value = mock_query

        with patch('src.api.routes.actions.get_tenant_context', return_value=mock_tenant_context):
            with patch('src.api.routes.actions.get_db_session', return_value=mock_db):
                with patch('src.api.routes.actions.BillingEntitlementsService') as mock_billing:
                    mock_result = Mock(is_entitled=True)
                    mock_billing.return_value.check_feature_entitlement.return_value = mock_result
                    with patch('src.api.routes.actions.can_execute_actions', return_value=True):

                        response = client.post(f"/api/actions/{sample_action.id}/execute")

        assert response.status_code == 400
        assert "cannot be executed" in response.json()["detail"].lower()


# =============================================================================
# Rollback Action Tests
# =============================================================================


class TestRollbackAction:
    """Tests for POST /api/actions/{action_id}/rollback endpoint."""

    def test_returns_400_when_action_cannot_be_rolled_back(
        self, client, mock_tenant_context, sample_action
    ):
        """Should return 400 when action cannot be rolled back."""
        # Action in APPROVED status cannot be rolled back
        sample_action.status = ActionStatus.APPROVED

        mock_db = Mock()
        mock_query = Mock()
        mock_query.filter.return_value.first.return_value = sample_action
        mock_db.query.return_value = mock_query

        with patch('src.api.routes.actions.get_tenant_context', return_value=mock_tenant_context):
            with patch('src.api.routes.actions.get_db_session', return_value=mock_db):
                with patch('src.api.routes.actions.BillingEntitlementsService') as mock_billing:
                    mock_result = Mock(is_entitled=True)
                    mock_billing.return_value.check_feature_entitlement.return_value = mock_result
                    with patch('src.api.routes.actions.can_rollback_actions', return_value=True):

                        response = client.post(f"/api/actions/{sample_action.id}/rollback")

        assert response.status_code == 400
        assert "cannot be rolled back" in response.json()["detail"].lower()


# =============================================================================
# Execution Logs Tests
# =============================================================================


class TestGetActionLogs:
    """Tests for GET /api/actions/{action_id}/logs endpoint."""

    def test_returns_logs_for_action(
        self, client, mock_tenant_context, sample_action, sample_log
    ):
        """Should return execution logs for an action."""
        mock_db = Mock()
        mock_action_query = Mock()
        mock_action_query.filter.return_value.first.return_value = sample_action

        mock_log_query = Mock()
        mock_log_query.filter.return_value.order_by.return_value.all.return_value = [sample_log]

        def query_side_effect(model):
            if model == AIAction:
                return mock_action_query
            return mock_log_query

        mock_db.query.side_effect = query_side_effect

        with patch('src.api.routes.actions.get_tenant_context', return_value=mock_tenant_context):
            with patch('src.api.routes.actions.get_db_session', return_value=mock_db):
                with patch('src.api.routes.actions.BillingEntitlementsService') as mock_billing:
                    mock_result = Mock(is_entitled=True)
                    mock_billing.return_value.check_feature_entitlement.return_value = mock_result
                    with patch('src.api.routes.actions.can_view_action_audit', return_value=True):

                        response = client.get(f"/api/actions/{sample_action.id}/logs")

        assert response.status_code == 200
        data = response.json()
        assert data["action_id"] == sample_action.id
        assert "entries" in data
        assert len(data["entries"]) == 1


# =============================================================================
# Job Listing Tests
# =============================================================================


class TestListJobs:
    """Tests for GET /api/actions/jobs endpoint."""

    def test_returns_jobs_list(
        self, client, mock_tenant_context, sample_job
    ):
        """Should return list of action jobs."""
        mock_db = Mock()
        mock_query = Mock()
        mock_query.filter.return_value = mock_query
        mock_query.order_by.return_value = mock_query
        mock_query.offset.return_value = mock_query
        mock_query.limit.return_value = mock_query
        mock_query.all.return_value = [sample_job]
        mock_query.count.return_value = 1
        mock_db.query.return_value = mock_query

        with patch('src.api.routes.actions.get_tenant_context', return_value=mock_tenant_context):
            with patch('src.api.routes.actions.get_db_session', return_value=mock_db):
                with patch('src.api.routes.actions.BillingEntitlementsService') as mock_billing:
                    mock_result = Mock(is_entitled=True)
                    mock_billing.return_value.check_feature_entitlement.return_value = mock_result
                    with patch('src.api.routes.actions.can_view_actions', return_value=True):

                        response = client.get("/api/actions/jobs")

        assert response.status_code == 200
        data = response.json()
        assert "jobs" in data
        assert "total" in data


# =============================================================================
# Stats Endpoint Tests
# =============================================================================


class TestGetStats:
    """Tests for GET /api/actions/stats endpoint."""

    def test_returns_action_statistics(self, client, mock_tenant_context):
        """Should return action statistics."""
        mock_db = Mock()
        mock_query = Mock()
        # Return empty status counts
        mock_query.filter.return_value.group_by.return_value.all.return_value = []
        # Return 0 for monthly count
        mock_scalar_query = Mock()
        mock_scalar_query.filter.return_value.scalar.return_value = 0

        def query_side_effect(*args, **kwargs):
            return mock_query

        mock_db.query.side_effect = query_side_effect

        with patch('src.api.routes.actions.get_tenant_context', return_value=mock_tenant_context):
            with patch('src.api.routes.actions.get_db_session', return_value=mock_db):
                with patch('src.api.routes.actions.BillingEntitlementsService') as mock_billing:
                    mock_result = Mock(is_entitled=True, details={"monthly_limit": 100})
                    mock_billing.return_value.check_feature_entitlement.return_value = mock_result
                    with patch('src.api.routes.actions.can_view_actions', return_value=True):

                        response = client.get("/api/actions/stats")

        assert response.status_code == 200
        data = response.json()
        assert "total_actions" in data
        assert "succeeded" in data
        assert "failed" in data
        assert "actions_this_month" in data
