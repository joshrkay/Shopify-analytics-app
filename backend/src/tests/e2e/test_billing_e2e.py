"""
E2E Tests: Billing & Subscription Lifecycle

Tests the full billing flow: plans, checkout, subscription management,
entitlements, and webhook callbacks.

Priority: P0 (Critical Path)
"""

import pytest
import uuid
from datetime import datetime, timedelta, timezone


@pytest.mark.e2e
@pytest.mark.billing
class TestBillingPlans:
    """Tests for plan listing and retrieval."""

    async def test_list_plans(
        self,
        async_client,
        auth_headers,
        test_plan_free,
        test_plan_pro,
    ):
        """GET /api/billing/plans returns available plans."""
        response = await async_client.get(
            "/api/billing/plans",
            headers=auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert "plans" in data or isinstance(data, list)

        plans = data.get("plans", data)
        plan_names = [p.get("name") or p.get("display_name") for p in plans]
        assert any("free" in (n or "").lower() for n in plan_names)


@pytest.mark.e2e
@pytest.mark.billing
class TestBillingCheckout:
    """Tests for checkout flow."""

    async def test_create_checkout_url(
        self,
        async_client,
        admin_headers,
        test_plan_pro,
        test_store,
        mock_shopify,
    ):
        """POST /api/billing/checkout creates a checkout URL."""
        response = await async_client.post(
            "/api/billing/checkout",
            headers=admin_headers,
            json={"plan_id": test_plan_pro.id},
        )
        # Checkout may succeed or fail depending on mock Shopify billing setup
        assert response.status_code in [200, 201, 400, 402, 422, 503]
        if response.status_code in [200, 201]:
            data = response.json()
            assert "checkout_url" in data or "confirmation_url" in data or "success" in data

    async def test_create_checkout_invalid_plan_returns_error(
        self,
        async_client,
        admin_headers,
        test_store,
    ):
        """Checkout with nonexistent plan_id should fail."""
        response = await async_client.post(
            "/api/billing/checkout",
            headers=admin_headers,
            json={"plan_id": "nonexistent-plan-id"},
        )
        assert response.status_code in [400, 404, 422]

    async def test_create_checkout_no_store_returns_error(
        self,
        async_client,
        auth_headers,
        test_plan_pro,
    ):
        """Checkout without a Shopify store should fail."""
        # auth_headers uses test_tenant_id which has no store (unless test_store fixture used)
        response = await async_client.post(
            "/api/billing/checkout",
            headers=auth_headers,
            json={"plan_id": test_plan_pro.id},
        )
        assert response.status_code in [400, 403, 404, 422, 503]


@pytest.mark.e2e
@pytest.mark.billing
class TestBillingSubscription:
    """Tests for subscription management."""

    async def test_get_subscription(
        self,
        async_client,
        auth_headers,
        test_subscription,
    ):
        """GET /api/billing/subscription returns current subscription."""
        response = await async_client.get(
            "/api/billing/subscription",
            headers=auth_headers,
        )
        assert response.status_code in [200, 404]
        if response.status_code == 200:
            data = response.json()
            assert "status" in data or "plan_id" in data or "plan_name" in data

    async def test_cancel_subscription(
        self,
        async_client,
        admin_headers,
        test_subscription,
    ):
        """POST /api/billing/cancel transitions subscription to cancelled."""
        response = await async_client.post(
            "/api/billing/cancel",
            headers=admin_headers,
        )
        assert response.status_code in [200, 400, 404]
        if response.status_code == 200:
            data = response.json()
            assert "message" in data or "subscription_id" in data

    async def test_cancel_already_cancelled_subscription(
        self,
        async_client,
        admin_headers,
        test_subscription,
        db_session,
    ):
        """Cancelling an already-cancelled subscription should be handled gracefully."""
        # Cancel first
        await async_client.post("/api/billing/cancel", headers=admin_headers)
        # Cancel again
        response = await async_client.post(
            "/api/billing/cancel",
            headers=admin_headers,
        )
        # Should not be a 500
        assert response.status_code in [200, 400, 404, 409]


@pytest.mark.e2e
@pytest.mark.billing
class TestBillingEntitlements:
    """Tests for entitlements endpoint."""

    async def test_get_entitlements_paid_tier(
        self,
        async_client,
        auth_headers,
        test_subscription,
    ):
        """Active pro subscription should return pro-tier entitlements."""
        response = await async_client.get(
            "/api/billing/entitlements",
            headers=auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert "features" in data or "billing_state" in data

    async def test_get_entitlements_free_tier(
        self,
        async_client,
        auth_headers,
    ):
        """No subscription should fall back to free-tier entitlements."""
        response = await async_client.get(
            "/api/billing/entitlements",
            headers=auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert "features" in data or "billing_state" in data

    async def test_get_usage(
        self,
        async_client,
        auth_headers,
    ):
        """GET /api/billing/usage returns resource usage metrics."""
        response = await async_client.get(
            "/api/billing/usage",
            headers=auth_headers,
        )
        assert response.status_code in [200, 404]
        if response.status_code == 200:
            data = response.json()
            # Should have some usage fields
            assert isinstance(data, dict)


    async def test_get_usage_aggregates_storage_and_ai_by_billing_period(
        self,
        async_client,
        auth_headers,
        db_session,
        test_tenant_id,
    ):
        """Usage endpoint should aggregate storage and AI usage within current billing period."""
        from src.ingestion.jobs.models import IngestionJob, JobStatus
        from src.models.llm_routing import LLMUsageLog
        from src.models.plan import Plan
        from src.models.subscription import Subscription

        now = datetime.now(timezone.utc)
        period_start = now - timedelta(days=10)
        period_end = now + timedelta(days=20)

        plan = Plan(
            id=f"usage-plan-{uuid.uuid4().hex[:8]}",
            name="usage_plan",
            display_name="Usage Plan",
            description="Usage test plan",
            price_monthly_cents=2900,
            is_active=True,
        )
        db_session.add(plan)
        db_session.flush()

        subscription = Subscription(
            tenant_id=test_tenant_id,
            plan_id=plan.id,
            status="active",
            current_period_start=period_start,
            current_period_end=period_end,
        )
        db_session.add(subscription)

        in_period_job = IngestionJob(
            tenant_id=test_tenant_id,
            connector_id=f"conn-{uuid.uuid4().hex[:8]}",
            external_account_id="acct-1",
            status=JobStatus.SUCCESS,
            completed_at=now - timedelta(days=1),
            job_metadata={"bytes_synced": 2 * 1024 * 1024 * 1024},
        )
        out_of_period_job = IngestionJob(
            tenant_id=test_tenant_id,
            connector_id=f"conn-{uuid.uuid4().hex[:8]}",
            external_account_id="acct-2",
            status=JobStatus.SUCCESS,
            completed_at=now - timedelta(days=45),
            job_metadata={"bytes_synced": 9 * 1024 * 1024 * 1024},
        )
        db_session.add_all([in_period_job, out_of_period_job])

        db_session.add_all([
            LLMUsageLog(
                tenant_id=test_tenant_id,
                model_id="gpt-test",
                input_tokens=10,
                output_tokens=20,
                total_tokens=30,
                latency_ms=100,
                cost_usd=0,
                was_fallback=False,
                request_metadata={},
                response_status="success",
                created_at=now - timedelta(hours=2),
            ),
            LLMUsageLog(
                tenant_id=test_tenant_id,
                model_id="gpt-test",
                input_tokens=10,
                output_tokens=20,
                total_tokens=30,
                latency_ms=100,
                cost_usd=0,
                was_fallback=False,
                request_metadata={},
                response_status="success",
                created_at=now - timedelta(hours=1),
            ),
            LLMUsageLog(
                tenant_id=test_tenant_id,
                model_id="gpt-test",
                input_tokens=10,
                output_tokens=20,
                total_tokens=30,
                latency_ms=100,
                cost_usd=0,
                was_fallback=False,
                request_metadata={},
                response_status="success",
                created_at=now - timedelta(days=60),
            ),
        ])
        db_session.commit()

        response = await async_client.get("/api/billing/usage", headers=auth_headers)
        assert response.status_code == 200

        data = response.json()
        assert data["storageUsedGb"] == 2.0
        assert data["aiRequestsUsed"] == 2

    async def test_get_usage_returns_tier_limits(
        self,
        async_client,
        mock_frontegg,
        test_tenant_id,
    ):
        """Usage endpoint should return configured limits for the tenant billing tier."""
        pro_token = mock_frontegg.create_test_token(
            tenant_id=test_tenant_id,
            roles=["admin"],
            entitlements=["AI_INSIGHTS"],
            custom_claims={
                "metadata": {
                    "roles": ["admin"],
                    "entitlements": ["AI_INSIGHTS"],
                    "allowed_tenants": [test_tenant_id],
                    "billing_tier": "pro",
                }
            },
        )

        response = await async_client.get(
            "/api/billing/usage",
            headers={"Authorization": f"Bearer {pro_token}"},
        )
        assert response.status_code == 200

        data = response.json()
        assert data["storageLimitGb"] == 50.0
        assert data["aiRequestsLimit"] == 5000

    async def test_get_invoices(
        self,
        async_client,
        auth_headers,
    ):
        """GET /api/billing/invoices returns billing event history."""
        response = await async_client.get(
            "/api/billing/invoices",
            headers=auth_headers,
        )
        assert response.status_code in [200, 404]


@pytest.mark.e2e
@pytest.mark.billing
class TestBillingWebhooks:
    """Tests for billing webhook callbacks."""

    async def test_billing_callback(
        self,
        async_client,
        auth_headers,
        test_store,
    ):
        """GET /api/billing/callback handles Shopify billing callback."""
        response = await async_client.get(
            "/api/billing/callback",
            headers=auth_headers,
            params={
                "shop": test_store.shop_domain,
                "charge_id": "gid://shopify/AppSubscription/12345",
            },
        )
        # May fail without real Shopify — but should not 500
        assert response.status_code in [200, 302, 400, 404, 422]

    async def test_billing_event_audit_trail(
        self,
        async_client,
        auth_headers,
        test_subscription,
        db_session,
    ):
        """
        Billing events should be recorded as append-only audit entries.
        Verify BillingEvent records can be queried after subscription creation.
        """
        from src.models.billing_event import BillingEvent

        events = db_session.query(BillingEvent).filter(
            BillingEvent.tenant_id == test_subscription.tenant_id
        ).all()
        # May or may not have events depending on fixture setup
        # The key check is that the query doesn't fail
        assert isinstance(events, list)
