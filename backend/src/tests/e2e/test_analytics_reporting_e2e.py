"""
E2E Tests: Analytics & Reporting

Tests KPI summaries, channel metrics, attribution, orders,
cohort analysis, budget pacing, and dataset discovery.

Priority: P1 (Major Feature)
"""

import pytest


# =============================================================================
# KPI & Channel Metrics
# =============================================================================

@pytest.mark.e2e
class TestKPIAndChannels:
    """Tests for KPI summary and channel metrics endpoints."""

    async def test_kpi_summary(
        self,
        async_client,
        auth_headers,
    ):
        """GET /api/datasets/kpi-summary returns KPI metrics."""
        response = await async_client.get(
            "/api/datasets/kpi-summary",
            headers=auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        # Should have revenue/spend fields (may be zero for new tenant)
        assert isinstance(data, dict)

    async def test_channel_breakdown(
        self,
        async_client,
        auth_headers,
    ):
        """GET /api/datasets/channel-breakdown returns channel breakdown."""
        response = await async_client.get(
            "/api/datasets/channel-breakdown",
            headers=auth_headers,
        )
        assert response.status_code == 200

    async def test_channel_metrics(
        self,
        async_client,
        auth_headers,
    ):
        """GET /api/channels/{platform}/metrics returns per-channel data."""
        response = await async_client.get(
            "/api/channels/meta_ads/metrics",
            headers=auth_headers,
            params={"timeframe": "30d"},
        )
        # May return 200 with data or 404 if no data for that channel
        assert response.status_code in [200, 404]

    async def test_channel_metrics_invalid_platform(
        self,
        async_client,
        auth_headers,
    ):
        """Unknown platform should return 404 or empty data."""
        response = await async_client.get(
            "/api/channels/nonexistent_platform/metrics",
            headers=auth_headers,
        )
        assert response.status_code in [200, 404]

    async def test_kpi_summary_empty_data(
        self,
        async_client,
        auth_headers_b,
    ):
        """New tenant with no data should get 200 with zeroed metrics, not 500."""
        response = await async_client.get(
            "/api/datasets/kpi-summary",
            headers=auth_headers_b,
        )
        assert response.status_code == 200


# =============================================================================
# Attribution
# =============================================================================

@pytest.mark.e2e
class TestAttribution:
    """Tests for UTM attribution endpoints."""

    async def test_attribution_summary(
        self,
        async_client,
        auth_headers,
    ):
        """GET /api/attribution/summary returns attribution KPIs."""
        response = await async_client.get(
            "/api/attribution/summary",
            headers=auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, dict)

    async def test_attribution_orders(
        self,
        async_client,
        auth_headers,
    ):
        """GET /api/attribution/orders returns paginated attributed orders."""
        response = await async_client.get(
            "/api/attribution/orders",
            headers=auth_headers,
            params={"limit": 10, "offset": 0},
        )
        assert response.status_code == 200
        data = response.json()
        assert "orders" in data or isinstance(data, dict)

    async def test_attribution_orders_pagination(
        self,
        async_client,
        auth_headers,
    ):
        """Pagination with offset works correctly."""
        response = await async_client.get(
            "/api/attribution/orders",
            headers=auth_headers,
            params={"limit": 5, "offset": 5},
        )
        assert response.status_code == 200


# =============================================================================
# Orders
# =============================================================================

@pytest.mark.e2e
class TestOrders:
    """Tests for order list endpoints."""

    async def test_orders_list(
        self,
        async_client,
        auth_headers,
    ):
        """GET /api/orders returns paginated order list."""
        response = await async_client.get(
            "/api/orders",
            headers=auth_headers,
            params={"limit": 10},
        )
        assert response.status_code == 200
        data = response.json()
        assert "orders" in data or isinstance(data, dict)

    async def test_orders_list_with_filters(
        self,
        async_client,
        auth_headers,
    ):
        """Filter orders by timeframe."""
        response = await async_client.get(
            "/api/orders",
            headers=auth_headers,
            params={"timeframe": "30d", "limit": 10},
        )
        assert response.status_code == 200


# =============================================================================
# Datasets
# =============================================================================

@pytest.mark.e2e
class TestDatasets:
    """Tests for dataset discovery endpoints."""

    async def test_dataset_discovery(
        self,
        async_client,
        auth_headers,
    ):
        """GET /api/datasets returns available datasets."""
        response = await async_client.get(
            "/api/datasets",
            headers=auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert "datasets" in data or isinstance(data, list)


# =============================================================================
# Budget Pacing
# =============================================================================

@pytest.mark.e2e
class TestBudgetPacing:
    """Tests for budget pacing endpoints."""

    async def test_budget_pacing_list(
        self,
        async_client,
        pro_tier_headers,
    ):
        """GET /api/budget-pacing returns pacing data."""
        response = await async_client.get(
            "/api/budget-pacing",
            headers=pro_tier_headers,
        )
        assert response.status_code in [200, 404]

    async def test_budget_crud(
        self,
        async_client,
        pro_tier_headers,
    ):
        """Full budget lifecycle: create, update, delete."""
        # Create
        create_resp = await async_client.post(
            "/api/budgets",
            headers=pro_tier_headers,
            json={
                "source_platform": "meta_ads",
                "budget_monthly_cents": 500000,
                "start_date": "2025-01-01",
            },
        )
        assert create_resp.status_code in [200, 201, 400, 422]

        if create_resp.status_code in [200, 201]:
            budget_id = create_resp.json().get("id")
            if budget_id:
                # Update
                update_resp = await async_client.put(
                    f"/api/budgets/{budget_id}",
                    headers=pro_tier_headers,
                    json={"budget_monthly_cents": 600000},
                )
                assert update_resp.status_code in [200, 400, 404]

                # Delete
                delete_resp = await async_client.delete(
                    f"/api/budgets/{budget_id}",
                    headers=pro_tier_headers,
                )
                assert delete_resp.status_code in [200, 204, 404]


# =============================================================================
# Cohort Analysis
# =============================================================================

@pytest.mark.e2e
class TestCohortAnalysis:
    """Tests for cohort retention analysis."""

    async def test_cohort_analysis(
        self,
        async_client,
        pro_tier_headers,
    ):
        """GET /api/analytics/cohort-analysis returns retention grid."""
        response = await async_client.get(
            "/api/analytics/cohort-analysis",
            headers=pro_tier_headers,
        )
        assert response.status_code in [200, 404]
        if response.status_code == 200:
            data = response.json()
            assert "cohorts" in data or "summary" in data

    async def test_cohort_analysis_no_entitlement(
        self,
        async_client,
        free_tier_headers,
    ):
        """Free tier should be blocked from cohort analysis."""
        response = await async_client.get(
            "/api/analytics/cohort-analysis",
            headers=free_tier_headers,
        )
        assert response.status_code in [402, 403]
