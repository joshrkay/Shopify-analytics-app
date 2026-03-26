"""Unit tests for actions route serialization helpers."""

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, Mock, patch

import pytest

from src.api.routes.actions import _job_to_response, execute_action
from src.models.ai_action import AIAction, ActionStatus, ActionType, ActionTargetEntityType
from src.models.action_job import ActionJob, ActionJobStatus


def test_job_to_response_maps_action_result_counts():
    """_job_to_response should map ActionJob action result fields."""
    job = ActionJob(
        job_id=str(uuid.uuid4()),
        tenant_id="tenant-1",
        status=ActionJobStatus.SUCCEEDED,
        action_ids=[str(uuid.uuid4()), str(uuid.uuid4())],
        actions_succeeded=2,
        actions_failed=0,
        created_at=datetime.now(timezone.utc),
    )

    response = _job_to_response(job)

    assert response.action_count == 2
    assert response.succeeded_count == 2
    assert response.failed_count == 0


@pytest.mark.asyncio
async def test_execute_action_response_serializes_job_id():
    """execute_action should return the action's job_id in success responses."""
    tenant_ctx = Mock(tenant_id="tenant-1", user_id="user-1")
    action = AIAction(
        id=str(uuid.uuid4()),
        tenant_id="tenant-1",
        recommendation_id=str(uuid.uuid4()),
        action_type=ActionType.PAUSE_CAMPAIGN,
        platform="meta",
        target_entity_id="campaign_123",
        target_entity_type=ActionTargetEntityType.CAMPAIGN,
        action_params={"status": "paused"},
        status=ActionStatus.APPROVED,
        content_hash="test-hash",
        job_id=str(uuid.uuid4()),
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )

    mock_db = Mock()
    mock_query = Mock()
    mock_query.filter.return_value.first.return_value = action
    mock_db.query.return_value = mock_query

    result = Mock()
    result.status = Mock(value="success")

    with patch("src.api.routes.actions.get_tenant_context", return_value=tenant_ctx):
        with patch(
            "src.api.routes.actions.ActionExecutionService.execute_action",
            new=AsyncMock(return_value=result),
        ):
            response = await execute_action(
                request=Mock(),
                action_id=action.id,
                db_session=mock_db,
                _rate_limit=None,
            )

    assert response.status == "ok"
    assert response.job_id == action.job_id
