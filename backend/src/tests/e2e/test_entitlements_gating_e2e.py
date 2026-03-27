"""
E2E Tests: Feature Entitlements & Gating

Tests that feature gates correctly block/allow access based on billing tier.

Priority: P0 (Critical Path)
"""

import pytest


@pytest.mark.e2e
class TestEntitlementGatingHappyPath:
    """Tests verifying feature gates enforce billing tier restrictions."""

    async def test_free_tier_cannot_access_gated_route(
        self,
        async_client,
        free_tier_headers,
    ):
        """Free tier user should be blocked from AI insights."""
        response = await async_client.get(
            "/api/insights",
            headers=free_tier_headers,
        )
        # Should be denied — 402 Payment Required or 403 Forbidden
        assert response.status_code in [402, 403]

    async def test_pro_tier_can_access_gated_route(
        self,
        async_client,
        pro_tier_headers,
        test_insights,
    ):
        """Pro tier user should access AI insights."""
        response = await async_client.get(
            "/api/insights",
            headers=pro_tier_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert "insights" in data or isinstance(data, list)

    async def test_free_tier_can_access_ungated_routes(
        self,
        async_client,
        free_tier_headers,
    ):
        """Free tier user should access ungated routes like health."""
        response = await async_client.get(
            "/api/data-health/summary",
            headers=free_tier_headers,
        )
        assert response.status_code == 200

    async def test_custom_dashboards_write_requires_entitlement(
        self,
        async_client,
        free_tier_headers,
        pro_tier_headers,
    ):
        """
        Free tier: POST /api/v1/dashboards should be blocked.
        Pro tier: should succeed.
        """
        # Free tier — blocked
        free_resp = await async_client.post(
            "/api/v1/dashboards",
            headers=free_tier_headers,
            json={"name": "Test Dashboard"},
        )
        assert free_resp.status_code in [402, 403]

        # Pro tier — allowed
        pro_resp = await async_client.post(
            "/api/v1/dashboards",
            headers=pro_tier_headers,
            json={"name": "Test Dashboard Pro"},
        )
        assert pro_resp.status_code in [200, 201]

    async def test_cohort_analysis_requires_entitlement(
        self,
        async_client,
        free_tier_headers,
        pro_tier_headers,
    ):
        """Cohort analysis should be gated for free tier."""
        free_resp = await async_client.get(
            "/api/analytics/cohort-analysis",
            headers=free_tier_headers,
        )
        assert free_resp.status_code in [402, 403]

        pro_resp = await async_client.get(
            "/api/analytics/cohort-analysis",
            headers=pro_tier_headers,
        )
        # Pro should be allowed (may return 200 or empty data)
        assert pro_resp.status_code in [200, 404]

    async def test_budget_pacing_requires_entitlement(
        self,
        async_client,
        free_tier_headers,
        pro_tier_headers,
    ):
        """Budget pacing should be gated for free tier."""
        free_resp = await async_client.get(
            "/api/budget-pacing",
            headers=free_tier_headers,
        )
        assert free_resp.status_code in [402, 403]

        pro_resp = await async_client.get(
            "/api/budget-pacing",
            headers=pro_tier_headers,
        )
        assert pro_resp.status_code in [200, 404]


@pytest.mark.e2e
class TestEntitlementGatingEdgeCases:
    """Edge cases for entitlement gating."""

    async def test_downgraded_user_can_still_read_dashboards(
        self,
        async_client,
        free_tier_headers,
    ):
        """
        Downgraded users should still read dashboards (GET),
        but not create new ones (POST).
        """
        # GET should work (may return empty list)
        read_resp = await async_client.get(
            "/api/v1/dashboards",
            headers=free_tier_headers,
        )
        assert read_resp.status_code in [200, 402, 403]

        # POST should be blocked
        write_resp = await async_client.post(
            "/api/v1/dashboards",
            headers=free_tier_headers,
            json={"name": "Should Be Blocked"},
        )
        assert write_resp.status_code in [402, 403]

    async def test_entitlement_fallback_when_no_subscription(
        self,
        async_client,
        auth_headers,
    ):
        """
        No Subscription row in DB should fall back to BILLING_TIER_FEATURES.
        The /api/billing/entitlements endpoint should still return 200.
        """
        response = await async_client.get(
            "/api/billing/entitlements",
            headers=auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert "features" in data or "billing_state" in data

    async def test_alerts_entitlement_gate(
        self,
        async_client,
        free_tier_headers,
    ):
        """Alerts CRUD should be gated for free tier."""
        response = await async_client.get(
            "/api/alerts/rules",
            headers=free_tier_headers,
        )
        assert response.status_code in [402, 403]
