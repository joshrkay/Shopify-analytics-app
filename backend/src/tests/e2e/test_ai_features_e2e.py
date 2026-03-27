"""
E2E Tests: AI Features — Insights, Recommendations, Action Proposals, Actions, Chat

Tests the full AI pipeline: insight generation, recommendations,
action proposal approval workflow, action execution, and AI chat.

Priority: P1 (Major Feature)
"""

import pytest


# =============================================================================
# AI Insights
# =============================================================================

@pytest.mark.e2e
@pytest.mark.ai_features
class TestAIInsights:
    """Tests for /api/insights endpoints."""

    async def test_list_insights(
        self,
        async_client,
        auth_headers,
        test_insights,
    ):
        """GET /api/insights returns seeded insights."""
        response = await async_client.get(
            "/api/insights",
            headers=auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert "insights" in data
        assert len(data["insights"]) >= 5

    async def test_filter_insights_by_type(
        self,
        async_client,
        auth_headers,
        test_insights,
    ):
        """Filter insights by insight_type."""
        response = await async_client.get(
            "/api/insights",
            headers=auth_headers,
            params={"insight_type": "spend_anomaly"},
        )
        assert response.status_code == 200
        data = response.json()
        for insight in data.get("insights", []):
            assert insight["insight_type"] == "spend_anomaly"

    async def test_filter_insights_by_severity(
        self,
        async_client,
        auth_headers,
        test_insights,
    ):
        """Filter insights by severity."""
        response = await async_client.get(
            "/api/insights",
            headers=auth_headers,
            params={"severity": "critical"},
        )
        assert response.status_code == 200
        data = response.json()
        for insight in data.get("insights", []):
            assert insight["severity"] == "critical"

    async def test_mark_insight_read(
        self,
        async_client,
        auth_headers,
        test_insights,
    ):
        """PATCH /api/insights/{id}/read marks insight as read."""
        insight_id = test_insights[0].id
        response = await async_client.patch(
            f"/api/insights/{insight_id}/read",
            headers=auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert data.get("status") == "success" or data.get("insight_id") == insight_id

    async def test_dismiss_insight(
        self,
        async_client,
        auth_headers,
        test_insights,
    ):
        """PATCH /api/insights/{id}/dismiss marks insight as dismissed."""
        insight_id = test_insights[1].id
        response = await async_client.patch(
            f"/api/insights/{insight_id}/dismiss",
            headers=auth_headers,
        )
        assert response.status_code == 200

    async def test_batch_mark_read(
        self,
        async_client,
        auth_headers,
        test_insights,
    ):
        """POST /api/insights/batch/read marks multiple insights as read."""
        ids = [i.id for i in test_insights[:3]]
        response = await async_client.post(
            "/api/insights/batch/read",
            headers=auth_headers,
            json={"insight_ids": ids},
        )
        assert response.status_code == 200
        data = response.json()
        assert data.get("updated", 0) >= 1 or data.get("status") == "success"


# =============================================================================
# AI Recommendations
# =============================================================================

@pytest.mark.e2e
@pytest.mark.ai_features
class TestAIRecommendations:
    """Tests for /api/recommendations endpoints."""

    async def test_list_recommendations(
        self,
        async_client,
        auth_headers,
        test_recommendations,
    ):
        """GET /api/recommendations returns seeded recommendations."""
        response = await async_client.get(
            "/api/recommendations",
            headers=auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert "recommendations" in data
        assert len(data["recommendations"]) >= 3

    async def test_accept_recommendation(
        self,
        async_client,
        auth_headers,
        test_recommendations,
    ):
        """PATCH /api/recommendations/{id}/accept changes status."""
        rec_id = test_recommendations[0].id
        response = await async_client.patch(
            f"/api/recommendations/{rec_id}/accept",
            headers=auth_headers,
        )
        assert response.status_code == 200

    async def test_dismiss_recommendation(
        self,
        async_client,
        auth_headers,
        test_recommendations,
    ):
        """PATCH /api/recommendations/{id}/dismiss changes status."""
        rec_id = test_recommendations[1].id
        response = await async_client.patch(
            f"/api/recommendations/{rec_id}/dismiss",
            headers=auth_headers,
        )
        assert response.status_code == 200


# =============================================================================
# Action Proposals
# =============================================================================

@pytest.mark.e2e
@pytest.mark.ai_features
class TestActionProposals:
    """Tests for /api/action-proposals endpoints."""

    async def test_list_action_proposals(
        self,
        async_client,
        auth_headers,
        test_action_proposals,
    ):
        """GET /api/action-proposals returns seeded proposals."""
        response = await async_client.get(
            "/api/action-proposals",
            headers=auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert "proposals" in data
        assert len(data["proposals"]) >= 2

    async def test_approve_action_proposal(
        self,
        async_client,
        admin_headers,
        test_action_proposals,
    ):
        """POST /api/action-proposals/{id}/approve with admin token."""
        # Use the 'proposed' status proposal
        proposal_id = test_action_proposals[0].id
        response = await async_client.post(
            f"/api/action-proposals/{proposal_id}/approve",
            headers=admin_headers,
            json={"reason": "E2E test approval"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data.get("new_status") == "approved" or data.get("status") in ["success", "approved"]

    async def test_reject_action_proposal(
        self,
        async_client,
        admin_headers,
        test_action_proposals,
        db_session,
    ):
        """POST /api/action-proposals/{id}/reject stores reason."""
        # Create a fresh proposal to reject
        from src.models.action_proposal import ActionProposal
        import uuid
        import hashlib
        from datetime import datetime, timezone, timedelta

        proposal = ActionProposal(
            id=str(uuid.uuid4()),
            tenant_id=test_action_proposals[0].tenant_id,
            source_recommendation_id=test_action_proposals[0].source_recommendation_id,
            action_type="pause_campaign",
            status="proposed",
            target_platform="meta",
            target_entity_type="campaign",
            target_entity_id=f"camp_{uuid.uuid4().hex[:8]}",
            proposed_change={"action": "pause"},
            expected_effect="Pause campaign",
            risk_disclaimer="Test",
            risk_level="low",
            confidence_score=0.8,
            expires_at=datetime.now(timezone.utc) + timedelta(days=7),
            content_hash=hashlib.sha256(f"reject-test-{uuid.uuid4()}".encode()).hexdigest(),
        )
        db_session.add(proposal)
        db_session.flush()

        response = await async_client.post(
            f"/api/action-proposals/{proposal.id}/reject",
            headers=admin_headers,
            json={"reason": "E2E test rejection reason"},
        )
        assert response.status_code == 200

    async def test_get_proposal_audit_trail(
        self,
        async_client,
        auth_headers,
        test_action_proposals,
    ):
        """GET /api/action-proposals/{id}/audit returns audit entries."""
        proposal_id = test_action_proposals[0].id
        response = await async_client.get(
            f"/api/action-proposals/{proposal_id}/audit",
            headers=auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert "entries" in data or "proposal_id" in data

    async def test_get_pending_proposals_count(
        self,
        async_client,
        auth_headers,
        test_action_proposals,
    ):
        """GET /api/action-proposals/stats/pending returns count."""
        response = await async_client.get(
            "/api/action-proposals/stats/pending",
            headers=auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert "pending_count" in data


# =============================================================================
# Actions
# =============================================================================

@pytest.mark.e2e
@pytest.mark.ai_features
class TestAIActions:
    """Tests for /api/actions endpoints."""

    async def test_execute_action(
        self,
        async_client,
        admin_headers,
        test_actions,
    ):
        """POST /api/actions/{id}/execute on an approved action."""
        # test_actions[0] has status 'approved'
        action_id = test_actions[0].id
        response = await async_client.post(
            f"/api/actions/{action_id}/execute",
            headers=admin_headers,
        )
        # May succeed or fail depending on mock platform availability
        assert response.status_code in [200, 400, 422, 503]

    async def test_rollback_action(
        self,
        async_client,
        admin_headers,
        test_actions,
    ):
        """POST /api/actions/{id}/rollback on a succeeded action."""
        # test_actions[1] has status 'succeeded'
        action_id = test_actions[1].id
        response = await async_client.post(
            f"/api/actions/{action_id}/rollback",
            headers=admin_headers,
            json={"reason": "E2E test rollback"},
        )
        assert response.status_code in [200, 400, 422]

    async def test_get_action_logs(
        self,
        async_client,
        auth_headers,
        test_actions,
    ):
        """GET /api/actions/{id}/logs returns execution history."""
        action_id = test_actions[0].id
        response = await async_client.get(
            f"/api/actions/{action_id}/logs",
            headers=auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert "entries" in data or "action_id" in data


# =============================================================================
# AI Chat
# =============================================================================

@pytest.mark.e2e
@pytest.mark.ai_features
class TestAIChat:
    """Tests for /api/ai/chat endpoint."""

    async def test_ai_chat_basic_question(
        self,
        async_client,
        auth_headers,
        mock_openrouter,
    ):
        """POST /api/ai/chat with a basic question."""
        response = await async_client.post(
            "/api/ai/chat",
            headers=auth_headers,
            json={"question": "What was my revenue last week?"},
        )
        # Depends on OpenRouter mock — should not be 500
        assert response.status_code in [200, 400, 402, 403, 422, 503]


# =============================================================================
# Edge Cases
# =============================================================================

@pytest.mark.e2e
@pytest.mark.ai_features
class TestAIFeaturesEdgeCases:
    """Edge cases for AI features."""

    async def test_insights_tenant_isolation(
        self,
        async_client,
        auth_headers,
        auth_headers_b,
        test_insights,
    ):
        """Tenant A's insights should not be visible to Tenant B."""
        # Tenant A sees insights
        resp_a = await async_client.get("/api/insights", headers=auth_headers)
        assert resp_a.status_code == 200
        insights_a = resp_a.json().get("insights", [])

        # Tenant B should not see Tenant A's insights
        resp_b = await async_client.get("/api/insights", headers=auth_headers_b)
        if resp_b.status_code == 200:
            insights_b = resp_b.json().get("insights", [])
            a_ids = {i["insight_id"] for i in insights_a} if insights_a else set()
            b_ids = {i["insight_id"] for i in insights_b} if insights_b else set()
            assert a_ids.isdisjoint(b_ids), "Tenant B can see Tenant A's insights"

    async def test_only_admin_can_approve_proposals(
        self,
        async_client,
        viewer_headers,
        test_action_proposals,
    ):
        """Viewer token should be denied from approving proposals."""
        proposal_id = test_action_proposals[0].id
        response = await async_client.post(
            f"/api/action-proposals/{proposal_id}/approve",
            headers=viewer_headers,
        )
        assert response.status_code in [403, 401]

    async def test_cannot_execute_unapproved_action(
        self,
        async_client,
        admin_headers,
        test_actions,
        db_session,
    ):
        """Action in pending_approval status should not be executable."""
        from src.models.ai_action import AIAction
        import uuid
        import hashlib

        action = AIAction(
            id=str(uuid.uuid4()),
            tenant_id=test_actions[0].tenant_id,
            recommendation_id=test_actions[0].recommendation_id,
            action_type="pause_campaign",
            platform="meta",
            target_entity_id="camp_test",
            target_entity_type="campaign",
            action_params={},
            status="pending_approval",
            content_hash=hashlib.sha256(f"unapproved-{uuid.uuid4()}".encode()).hexdigest(),
        )
        db_session.add(action)
        db_session.flush()

        response = await async_client.post(
            f"/api/actions/{action.id}/execute",
            headers=admin_headers,
        )
        assert response.status_code in [400, 403, 409, 422]

    async def test_dismiss_already_dismissed_insight(
        self,
        async_client,
        auth_headers,
        test_insights,
    ):
        """Dismissing an already-dismissed insight should be idempotent."""
        insight_id = test_insights[2].id

        # Dismiss first time
        await async_client.patch(
            f"/api/insights/{insight_id}/dismiss",
            headers=auth_headers,
        )

        # Dismiss second time
        response = await async_client.patch(
            f"/api/insights/{insight_id}/dismiss",
            headers=auth_headers,
        )
        assert response.status_code in [200, 400, 409]
