"""
E2E Tests: Alert Rules CRUD and Execution History

Tests alert rule creation, listing, updating, toggling, deletion,
and execution history queries.

Priority: P2 (Lower Risk)
"""

import pytest
import uuid


@pytest.mark.e2e
class TestAlertRulesHappyPath:
    """Happy path tests for alert rule management."""

    async def test_create_alert_rule(
        self,
        async_client,
        pro_tier_headers,
    ):
        """POST /api/alerts/rules creates a new rule."""
        response = await async_client.post(
            "/api/alerts/rules",
            headers=pro_tier_headers,
            json={
                "name": "E2E Alert Rule",
                "metric_name": "total_revenue",
                "comparison_operator": "lt",
                "threshold_value": 500.0,
                "evaluation_period": "daily",
                "severity": "warning",
            },
        )
        assert response.status_code in [200, 201]
        data = response.json()
        assert data.get("name") == "E2E Alert Rule"

    async def test_list_alert_rules(
        self,
        async_client,
        pro_tier_headers,
        test_alert_rules,
    ):
        """GET /api/alerts/rules returns rule list."""
        response = await async_client.get(
            "/api/alerts/rules",
            headers=pro_tier_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert "rules" in data
        assert len(data["rules"]) >= 3

    async def test_update_alert_rule(
        self,
        async_client,
        pro_tier_headers,
        test_alert_rules,
    ):
        """PUT /api/alerts/rules/{id} updates a rule."""
        rule_id = test_alert_rules[0].id
        response = await async_client.put(
            f"/api/alerts/rules/{rule_id}",
            headers=pro_tier_headers,
            json={"name": "Updated E2E Rule"},
        )
        assert response.status_code == 200

    async def test_toggle_alert_rule(
        self,
        async_client,
        pro_tier_headers,
        test_alert_rules,
    ):
        """PATCH /api/alerts/rules/{id}/toggle disables/enables rule."""
        rule_id = test_alert_rules[0].id
        response = await async_client.patch(
            f"/api/alerts/rules/{rule_id}/toggle",
            headers=pro_tier_headers,
            json={"enabled": False},
        )
        assert response.status_code == 200
        data = response.json()
        assert data.get("enabled") is False

    async def test_delete_alert_rule(
        self,
        async_client,
        pro_tier_headers,
        db_session,
        test_tenant_id,
    ):
        """DELETE /api/alerts/rules/{id} removes a rule."""
        from src.models.alert_rule import AlertRule

        rule = AlertRule(
            id=str(uuid.uuid4()),
            tenant_id=test_tenant_id,
            name="Delete Target",
            metric_name="test_metric",
            comparison_operator="gt",
            threshold_value=100.0,
            evaluation_period="daily",
            severity="info",
            enabled=True,
        )
        db_session.add(rule)
        db_session.flush()

        response = await async_client.delete(
            f"/api/alerts/rules/{rule.id}",
            headers=pro_tier_headers,
        )
        assert response.status_code in [200, 204]

    async def test_alert_execution_history(
        self,
        async_client,
        pro_tier_headers,
    ):
        """GET /api/alerts/history returns execution history."""
        response = await async_client.get(
            "/api/alerts/history",
            headers=pro_tier_headers,
        )
        assert response.status_code == 200

    async def test_rule_specific_history(
        self,
        async_client,
        pro_tier_headers,
        test_alert_rules,
    ):
        """GET /api/alerts/rules/{id}/history returns rule-specific history."""
        rule_id = test_alert_rules[0].id
        response = await async_client.get(
            f"/api/alerts/rules/{rule_id}/history",
            headers=pro_tier_headers,
        )
        assert response.status_code == 200


@pytest.mark.e2e
class TestAlertRulesEdgeCases:
    """Edge cases for alert rules."""

    async def test_alert_rule_tenant_isolation(
        self,
        async_client,
        auth_headers_b,
        test_alert_rules,
    ):
        """Tenant B cannot see Tenant A's alert rules."""
        rule_id = test_alert_rules[0].id
        response = await async_client.get(
            f"/api/alerts/rules/{rule_id}/history",
            headers=auth_headers_b,
        )
        assert response.status_code in [403, 404]

    async def test_free_tier_cannot_create_alerts(
        self,
        async_client,
        free_tier_headers,
    ):
        """Free tier should be blocked from creating alerts."""
        response = await async_client.post(
            "/api/alerts/rules",
            headers=free_tier_headers,
            json={
                "name": "Should Fail",
                "metric_name": "revenue",
                "comparison_operator": "lt",
                "threshold_value": 100.0,
                "evaluation_period": "daily",
            },
        )
        assert response.status_code in [402, 403]
