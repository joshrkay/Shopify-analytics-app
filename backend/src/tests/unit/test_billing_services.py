"""
Comprehensive tests for BillingService, BillingEntitlementsService, and BillingRoleSync.

Tests cover:
- BillingService: init validation, store/plan lookup, subscription lifecycle
  (activate, cancel, freeze), subscription info, Shopify sync, tier logic
- BillingEntitlementsService: init validation, tier resolution, feature entitlements,
  agency access, role validation, dashboard/store limits, feature matrix
- BillingRoleSync: downgrade/upgrade role changes, subscription cancellation
"""

import uuid
import pytest
from datetime import datetime, timezone, timedelta
from unittest.mock import MagicMock, patch, PropertyMock

from src.services.billing_service import (
    BillingService,
    CheckoutResult,
    SubscriptionInfo,
    BillingServiceError,
    PlanNotFoundError,
    StoreNotFoundError,
    SubscriptionError,
    FREE_PLAN_ID,
    PAYMENT_GRACE_PERIOD_DAYS,
)
from src.services.billing_entitlements import (
    BillingEntitlementsService,
    BillingFeature,
    BILLING_TIER_FEATURES,
    BillingRoleSync,
    EntitlementCheckResult,
    RoleValidationResult,
)
from src.models.subscription import SubscriptionStatus


# ---------------------------------------------------------------------------
# Helpers / Fixtures
# ---------------------------------------------------------------------------

TENANT_ID = "tenant-test-001"
STORE_ID = "store-001"
PLAN_FREE_ID = "plan_free"
PLAN_GROWTH_ID = "plan_growth"
PLAN_PRO_ID = "plan_pro"
PLAN_ENTERPRISE_ID = "plan_enterprise"
SHOPIFY_SUB_ID = "gid://shopify/AppSubscription/12345"


def _make_plan(
    plan_id: str = PLAN_GROWTH_ID,
    name: str = "growth",
    display_name: str = "Growth",
    price_monthly_cents: int = 2900,
    is_active: bool = True,
):
    plan = MagicMock()
    plan.id = plan_id
    plan.name = name
    plan.display_name = display_name
    plan.price_monthly_cents = price_monthly_cents
    plan.is_active = is_active
    return plan


def _make_subscription(
    sub_id: str | None = None,
    tenant_id: str = TENANT_ID,
    store_id: str = STORE_ID,
    plan_id: str = PLAN_GROWTH_ID,
    status: str = SubscriptionStatus.ACTIVE.value,
    shopify_subscription_id: str = SHOPIFY_SUB_ID,
    current_period_end: datetime | None = None,
    cancelled_at: datetime | None = None,
    grace_period_ends_on: datetime | None = None,
    trial_end: datetime | None = None,
    extra_metadata: dict | None = None,
):
    sub = MagicMock()
    sub.id = sub_id or str(uuid.uuid4())
    sub.tenant_id = tenant_id
    sub.store_id = store_id
    sub.plan_id = plan_id
    sub.status = status
    sub.shopify_subscription_id = shopify_subscription_id
    sub.current_period_end = current_period_end
    sub.cancelled_at = cancelled_at
    sub.grace_period_ends_on = grace_period_ends_on
    sub.trial_end = trial_end
    sub.extra_metadata = extra_metadata
    return sub


def _make_store(
    store_id: str = STORE_ID,
    tenant_id: str = TENANT_ID,
    shop_domain: str = "test-shop.myshopify.com",
    status: str = "active",
    access_token_encrypted: str = "enc_tok_abc",
    currency: str = "USD",
):
    store = MagicMock()
    store.id = store_id
    store.tenant_id = tenant_id
    store.shop_domain = shop_domain
    store.status = status
    store.access_token_encrypted = access_token_encrypted
    store.currency = currency
    return store


def _mock_query_chain(db_session, result):
    """Configure db_session.query(...).filter(...).first() to return *result*."""
    query = MagicMock()
    db_session.query.return_value = query
    query.filter.return_value = query
    query.order_by.return_value = query
    query.first.return_value = result
    return query


# ---------------------------------------------------------------------------
# BillingService Tests
# ---------------------------------------------------------------------------


class TestBillingServiceInit:
    """Tests for BillingService.__init__ validation."""

    def test_init_with_valid_tenant_id(self):
        db = MagicMock()
        svc = BillingService(db, TENANT_ID)
        assert svc.tenant_id == TENANT_ID
        assert svc.db is db

    @pytest.mark.parametrize("bad_id", [None, "", 0, False])
    def test_init_empty_tenant_id_raises(self, bad_id):
        with pytest.raises(ValueError, match="tenant_id is required"):
            BillingService(MagicMock(), bad_id)


class TestBillingServiceGetStore:
    """Tests for BillingService._get_store."""

    def test_get_store_found(self):
        db = MagicMock()
        store = _make_store()
        _mock_query_chain(db, store)
        svc = BillingService(db, TENANT_ID)
        assert svc._get_store() is store

    def test_get_store_not_found_raises(self):
        db = MagicMock()
        _mock_query_chain(db, None)
        svc = BillingService(db, TENANT_ID)
        with pytest.raises(StoreNotFoundError, match="No active store found"):
            svc._get_store()


class TestBillingServiceGetPlan:
    """Tests for BillingService._get_plan."""

    def test_get_plan_found(self):
        db = MagicMock()
        plan = _make_plan()
        _mock_query_chain(db, plan)
        svc = BillingService(db, TENANT_ID)
        assert svc._get_plan(PLAN_GROWTH_ID) is plan

    def test_get_plan_not_found_raises(self):
        db = MagicMock()
        _mock_query_chain(db, None)
        svc = BillingService(db, TENANT_ID)
        with pytest.raises(PlanNotFoundError, match="Plan not found or inactive"):
            svc._get_plan("plan_nonexistent")


class TestBillingServiceGetActiveSubscription:
    """Tests for BillingService._get_active_subscription."""

    @pytest.mark.parametrize(
        "status",
        [
            SubscriptionStatus.ACTIVE.value,
            SubscriptionStatus.PENDING.value,
            SubscriptionStatus.FROZEN.value,
        ],
    )
    def test_returns_subscription_for_active_statuses(self, status):
        db = MagicMock()
        sub = _make_subscription(status=status)
        query = MagicMock()
        db.query.return_value = query
        query.filter.return_value = query
        query.first.return_value = sub
        svc = BillingService(db, TENANT_ID)
        assert svc._get_active_subscription() is sub

    def test_returns_none_when_no_subscription(self):
        db = MagicMock()
        _mock_query_chain(db, None)
        svc = BillingService(db, TENANT_ID)
        assert svc._get_active_subscription() is None


class TestBillingServiceActivateSubscription:
    """Tests for BillingService.activate_subscription."""

    def test_happy_path(self):
        db = MagicMock()
        sub = _make_subscription(status=SubscriptionStatus.PENDING.value)
        _mock_query_chain(db, sub)

        svc = BillingService(db, TENANT_ID)
        period_end = datetime.now(timezone.utc) + timedelta(days=30)
        result = svc.activate_subscription(SHOPIFY_SUB_ID, current_period_end=period_end)

        assert result is sub
        assert sub.status == SubscriptionStatus.ACTIVE.value
        assert sub.current_period_end == period_end
        db.add.assert_called_once()  # billing event added
        db.commit.assert_called_once()

    def test_not_found_returns_none(self):
        db = MagicMock()
        _mock_query_chain(db, None)
        svc = BillingService(db, TENANT_ID)
        assert svc.activate_subscription(SHOPIFY_SUB_ID) is None
        db.commit.assert_not_called()


class TestBillingServiceCancelSubscription:
    """Tests for BillingService.cancel_subscription."""

    def test_happy_path(self):
        db = MagicMock()
        sub = _make_subscription(status=SubscriptionStatus.ACTIVE.value)
        _mock_query_chain(db, sub)

        svc = BillingService(db, TENANT_ID)
        cancelled_at = datetime.now(timezone.utc)
        result = svc.cancel_subscription(SHOPIFY_SUB_ID, cancelled_at=cancelled_at)

        assert result is sub
        assert sub.status == SubscriptionStatus.CANCELLED.value
        assert sub.cancelled_at == cancelled_at
        db.add.assert_called_once()
        db.commit.assert_called_once()

    def test_cancel_defaults_cancelled_at_to_now(self):
        db = MagicMock()
        sub = _make_subscription(status=SubscriptionStatus.ACTIVE.value)
        _mock_query_chain(db, sub)

        svc = BillingService(db, TENANT_ID)
        result = svc.cancel_subscription(SHOPIFY_SUB_ID)

        assert result is sub
        assert sub.cancelled_at is not None
        assert isinstance(sub.cancelled_at, datetime)

    def test_not_found_returns_none(self):
        db = MagicMock()
        _mock_query_chain(db, None)
        svc = BillingService(db, TENANT_ID)
        assert svc.cancel_subscription(SHOPIFY_SUB_ID) is None
        db.commit.assert_not_called()


class TestBillingServiceFreezeSubscription:
    """Tests for BillingService.freeze_subscription."""

    def test_sets_frozen_status_and_grace_period(self):
        db = MagicMock()
        sub = _make_subscription(status=SubscriptionStatus.ACTIVE.value)
        _mock_query_chain(db, sub)

        svc = BillingService(db, TENANT_ID)
        result = svc.freeze_subscription(SHOPIFY_SUB_ID, reason="payment_failed")

        assert result is sub
        assert sub.status == SubscriptionStatus.FROZEN.value
        assert sub.grace_period_ends_on is not None
        # Grace period should be roughly PAYMENT_GRACE_PERIOD_DAYS from now
        expected_end = datetime.now(timezone.utc) + timedelta(days=PAYMENT_GRACE_PERIOD_DAYS)
        delta = abs((sub.grace_period_ends_on - expected_end).total_seconds())
        assert delta < 5  # within 5 seconds
        db.commit.assert_called_once()

    def test_not_found_returns_none(self):
        db = MagicMock()
        _mock_query_chain(db, None)
        svc = BillingService(db, TENANT_ID)
        assert svc.freeze_subscription(SHOPIFY_SUB_ID) is None
        db.commit.assert_not_called()


class TestBillingServiceGetSubscriptionInfo:
    """Tests for BillingService.get_subscription_info."""

    def _setup_service(self, active_sub, fallback_sub, plan, free_plan=None):
        """
        Set up a BillingService with controlled query returns.

        The method calls _get_active_subscription first (statuses: active/pending/frozen),
        then falls back to cancelled/declined/expired, then free plan.
        """
        db = MagicMock()
        query_mock = MagicMock()
        db.query.return_value = query_mock
        query_mock.filter.return_value = query_mock
        query_mock.order_by.return_value = query_mock

        # We need to handle multiple calls to db.query(...).filter(...).first()
        # 1st call: _get_active_subscription
        # 2nd call: fallback (cancelled/declined/expired) OR plan lookup
        # 3rd call (if needed): plan lookup
        # 4th call (if needed): free plan lookup
        side_effects = []
        if active_sub is not None:
            side_effects.append(active_sub)   # active sub found
            side_effects.append(plan)          # plan lookup
        elif fallback_sub is not None:
            side_effects.append(None)          # no active sub
            side_effects.append(fallback_sub)  # fallback sub
            side_effects.append(plan)          # plan lookup
        else:
            side_effects.append(None)          # no active sub
            side_effects.append(None)          # no fallback sub
            side_effects.append(free_plan)     # free plan lookup

        query_mock.first.side_effect = side_effects
        return BillingService(db, TENANT_ID)

    def test_no_subscription_returns_free_plan_default(self):
        free_plan = _make_plan(
            plan_id=FREE_PLAN_ID, name="free", display_name="Free",
            price_monthly_cents=0,
        )
        svc = self._setup_service(
            active_sub=None, fallback_sub=None, plan=None, free_plan=free_plan,
        )
        info = svc.get_subscription_info()

        assert info.plan_id == FREE_PLAN_ID
        assert info.plan_name == "Free"
        assert info.status == "none"
        assert info.is_active is False
        assert info.can_access_features is True  # free tier always accessible
        assert info.subscription_id is None

    def test_active_subscription_returns_correct_info(self):
        period_end = datetime.now(timezone.utc) + timedelta(days=30)
        sub = _make_subscription(
            status=SubscriptionStatus.ACTIVE.value,
            current_period_end=period_end,
        )
        plan = _make_plan()
        svc = self._setup_service(active_sub=sub, fallback_sub=None, plan=plan)
        info = svc.get_subscription_info()

        assert info.subscription_id == sub.id
        assert info.plan_id == sub.plan_id
        assert info.plan_name == plan.display_name
        assert info.status == SubscriptionStatus.ACTIVE.value
        assert info.is_active is True
        assert info.can_access_features is True
        assert info.current_period_end == period_end

    @pytest.mark.parametrize(
        "status, expected_reason",
        [
            (SubscriptionStatus.CANCELLED.value, "Subscription cancelled"),
            (SubscriptionStatus.DECLINED.value, "Subscription declined"),
            (SubscriptionStatus.EXPIRED.value, "Trial expired"),
        ],
    )
    def test_cancelled_declined_expired_denies_access(self, status, expected_reason):
        sub = _make_subscription(status=status)
        plan = _make_plan()
        svc = self._setup_service(active_sub=None, fallback_sub=sub, plan=plan)
        info = svc.get_subscription_info()

        assert info.can_access_features is False
        assert expected_reason in info.downgraded_reason

    def test_frozen_expired_grace_period_denies_access(self):
        sub = _make_subscription(
            status=SubscriptionStatus.FROZEN.value,
            grace_period_ends_on=datetime.now(timezone.utc) - timedelta(hours=1),
        )
        plan = _make_plan()
        svc = self._setup_service(active_sub=sub, fallback_sub=None, plan=plan)
        info = svc.get_subscription_info()

        assert info.can_access_features is False
        assert "grace period expired" in info.downgraded_reason

    def test_frozen_within_grace_period_allows_access(self):
        sub = _make_subscription(
            status=SubscriptionStatus.FROZEN.value,
            grace_period_ends_on=datetime.now(timezone.utc) + timedelta(days=2),
        )
        plan = _make_plan()
        svc = self._setup_service(active_sub=sub, fallback_sub=None, plan=plan)
        info = svc.get_subscription_info()

        assert info.can_access_features is True
        assert "grace period" in info.downgraded_reason


class TestBillingServiceSyncWithShopify:
    """Tests for BillingService.sync_with_shopify."""

    def test_updates_status_when_different(self):
        db = MagicMock()
        sub = _make_subscription(status=SubscriptionStatus.ACTIVE.value)
        _mock_query_chain(db, sub)

        svc = BillingService(db, TENANT_ID)
        result = svc.sync_with_shopify(SHOPIFY_SUB_ID, "FROZEN")

        assert result is sub
        assert sub.status == SubscriptionStatus.FROZEN.value
        db.add.assert_called_once()  # billing event
        db.commit.assert_called_once()

    def test_no_change_when_same_status(self):
        db = MagicMock()
        sub = _make_subscription(status=SubscriptionStatus.ACTIVE.value)
        _mock_query_chain(db, sub)

        svc = BillingService(db, TENANT_ID)
        result = svc.sync_with_shopify(SHOPIFY_SUB_ID, "ACTIVE")

        assert result is sub
        assert sub.status == SubscriptionStatus.ACTIVE.value
        db.commit.assert_not_called()

    def test_unknown_shopify_status_ignored(self):
        db = MagicMock()
        sub = _make_subscription(status=SubscriptionStatus.ACTIVE.value)
        _mock_query_chain(db, sub)

        svc = BillingService(db, TENANT_ID)
        result = svc.sync_with_shopify(SHOPIFY_SUB_ID, "SOME_WEIRD_STATUS")

        assert result is sub
        assert sub.status == SubscriptionStatus.ACTIVE.value
        db.commit.assert_not_called()

    def test_not_found_returns_none(self):
        db = MagicMock()
        _mock_query_chain(db, None)
        svc = BillingService(db, TENANT_ID)
        assert svc.sync_with_shopify(SHOPIFY_SUB_ID, "ACTIVE") is None


class TestBillingServiceGetPlanTier:
    """Tests for BillingService.get_plan_tier."""

    @pytest.mark.parametrize(
        "price_cents, expected_tier",
        [
            (0, 0),       # free
            (2900, 1),    # growth ($29)
            (9900, 2),    # pro ($99)
            (29900, 3),   # enterprise ($299)
        ],
    )
    def test_tier_mapping(self, price_cents, expected_tier):
        db = MagicMock()
        plan = _make_plan(price_monthly_cents=price_cents)
        _mock_query_chain(db, plan)

        svc = BillingService(db, TENANT_ID)
        assert svc.get_plan_tier("any_plan_id") == expected_tier

    def test_boundary_3000_is_tier_1(self):
        db = MagicMock()
        plan = _make_plan(price_monthly_cents=3000)
        _mock_query_chain(db, plan)
        svc = BillingService(db, TENANT_ID)
        assert svc.get_plan_tier("x") == 1

    def test_boundary_10000_is_tier_2(self):
        db = MagicMock()
        plan = _make_plan(price_monthly_cents=10000)
        _mock_query_chain(db, plan)
        svc = BillingService(db, TENANT_ID)
        assert svc.get_plan_tier("x") == 2


class TestBillingServiceCanUpgradeTo:
    """Tests for BillingService.can_upgrade_to."""

    def test_no_active_subscription_can_upgrade(self):
        db = MagicMock()
        query = MagicMock()
        db.query.return_value = query
        query.filter.return_value = query

        # First call: _get_active_subscription -> None
        # Subsequent calls: _get_plan for target
        query.first.side_effect = [
            None,  # no active sub
        ]

        svc = BillingService(db, TENANT_ID)
        assert svc.can_upgrade_to(PLAN_GROWTH_ID) is True

    def test_can_upgrade_to_higher_tier(self):
        db = MagicMock()
        query = MagicMock()
        db.query.return_value = query
        query.filter.return_value = query

        current_plan = _make_plan(plan_id="plan_free", price_monthly_cents=0)
        target_plan = _make_plan(plan_id=PLAN_GROWTH_ID, price_monthly_cents=2900)
        sub = _make_subscription(plan_id="plan_free")

        # _get_active_subscription, _get_plan(current), _get_plan(target)
        query.first.side_effect = [sub, current_plan, target_plan]

        svc = BillingService(db, TENANT_ID)
        assert svc.can_upgrade_to(PLAN_GROWTH_ID) is True

    def test_cannot_upgrade_to_same_or_lower_tier(self):
        db = MagicMock()
        query = MagicMock()
        db.query.return_value = query
        query.filter.return_value = query

        current_plan = _make_plan(plan_id=PLAN_GROWTH_ID, price_monthly_cents=2900)
        target_plan = _make_plan(plan_id="plan_free", price_monthly_cents=0)
        sub = _make_subscription(plan_id=PLAN_GROWTH_ID)

        query.first.side_effect = [sub, current_plan, target_plan]

        svc = BillingService(db, TENANT_ID)
        assert svc.can_upgrade_to("plan_free") is False


class TestBillingServiceCanDowngradeTo:
    """Tests for BillingService.can_downgrade_to."""

    def test_no_active_subscription_cannot_downgrade(self):
        db = MagicMock()
        query = MagicMock()
        db.query.return_value = query
        query.filter.return_value = query
        query.first.return_value = None

        svc = BillingService(db, TENANT_ID)
        assert svc.can_downgrade_to(PLAN_FREE_ID) is False

    def test_can_downgrade_to_lower_tier(self):
        db = MagicMock()
        query = MagicMock()
        db.query.return_value = query
        query.filter.return_value = query

        current_plan = _make_plan(plan_id=PLAN_GROWTH_ID, price_monthly_cents=2900)
        target_plan = _make_plan(plan_id=PLAN_FREE_ID, price_monthly_cents=0)
        sub = _make_subscription(plan_id=PLAN_GROWTH_ID)

        query.first.side_effect = [sub, current_plan, target_plan]

        svc = BillingService(db, TENANT_ID)
        assert svc.can_downgrade_to(PLAN_FREE_ID) is True

    def test_cannot_downgrade_to_same_or_higher_tier(self):
        db = MagicMock()
        query = MagicMock()
        db.query.return_value = query
        query.filter.return_value = query

        current_plan = _make_plan(plan_id=PLAN_FREE_ID, price_monthly_cents=0)
        target_plan = _make_plan(plan_id=PLAN_GROWTH_ID, price_monthly_cents=2900)
        sub = _make_subscription(plan_id=PLAN_FREE_ID)

        query.first.side_effect = [sub, current_plan, target_plan]

        svc = BillingService(db, TENANT_ID)
        assert svc.can_downgrade_to(PLAN_GROWTH_ID) is False


# ---------------------------------------------------------------------------
# BillingEntitlementsService Tests
# ---------------------------------------------------------------------------


class TestBillingEntitlementsServiceInit:
    """Tests for BillingEntitlementsService.__init__."""

    def test_init_with_valid_tenant_id(self):
        db = MagicMock()
        svc = BillingEntitlementsService(db, TENANT_ID)
        assert svc.tenant_id == TENANT_ID
        assert svc.db is db
        assert svc._subscription is None
        assert svc._plan is None

    @pytest.mark.parametrize("bad_id", [None, "", 0, False])
    def test_init_empty_tenant_id_raises(self, bad_id):
        with pytest.raises(ValueError, match="tenant_id is required"):
            BillingEntitlementsService(MagicMock(), bad_id)


class TestBillingEntitlementsServiceGetBillingTier:
    """Tests for BillingEntitlementsService.get_billing_tier."""

    def test_no_plan_returns_free(self):
        db = MagicMock()
        _mock_query_chain(db, None)
        svc = BillingEntitlementsService(db, TENANT_ID)
        assert svc.get_billing_tier() == "free"

    @pytest.mark.parametrize(
        "plan_name, expected_tier",
        [
            ("growth", "growth"),
            ("starter", "growth"),
            ("professional", "growth"),
            ("enterprise", "enterprise"),
            ("pro", "enterprise"),
            ("business", "enterprise"),
            ("free", "free"),
            ("unknown_plan", "free"),
        ],
    )
    def test_plan_name_to_tier_mapping(self, plan_name, expected_tier):
        db = MagicMock()
        sub = _make_subscription(status=SubscriptionStatus.ACTIVE.value)
        plan = _make_plan(name=plan_name)

        query = MagicMock()
        db.query.return_value = query
        query.filter.return_value = query
        # first call: subscription, second call: plan
        query.first.side_effect = [sub, plan]

        svc = BillingEntitlementsService(db, TENANT_ID)
        assert svc.get_billing_tier() == expected_tier


class TestBillingEntitlementsServiceCheckFeatureEntitlement:
    """Tests for BillingEntitlementsService.check_feature_entitlement."""

    def _make_service_with_tier(self, tier: str):
        """Create a service that returns a specific billing tier."""
        svc = BillingEntitlementsService(MagicMock(), TENANT_ID)
        svc.get_billing_tier = MagicMock(return_value=tier)
        return svc

    def test_feature_enabled_returns_entitled(self):
        svc = self._make_service_with_tier("growth")
        result = svc.check_feature_entitlement(BillingFeature.ADVANCED_DASHBOARDS)

        assert result.is_entitled is True
        assert result.current_tier == "growth"

    def test_feature_not_enabled_returns_not_entitled_with_required_tier(self):
        svc = self._make_service_with_tier("free")
        result = svc.check_feature_entitlement(BillingFeature.ADVANCED_DASHBOARDS)

        assert result.is_entitled is False
        assert result.required_tier is not None  # should suggest growth or enterprise
        assert result.current_tier == "free"

    def test_free_tier_ai_insights_entitled(self):
        svc = self._make_service_with_tier("free")
        result = svc.check_feature_entitlement(BillingFeature.AI_INSIGHTS)
        assert result.is_entitled is True

    def test_free_tier_data_export_not_entitled(self):
        svc = self._make_service_with_tier("free")
        result = svc.check_feature_entitlement(BillingFeature.DATA_EXPORT)
        assert result.is_entitled is False

    def test_enterprise_custom_prompts_entitled(self):
        svc = self._make_service_with_tier("enterprise")
        result = svc.check_feature_entitlement(BillingFeature.CUSTOM_PROMPTS)
        assert result.is_entitled is True

    def test_growth_custom_prompts_not_entitled(self):
        svc = self._make_service_with_tier("growth")
        result = svc.check_feature_entitlement(BillingFeature.CUSTOM_PROMPTS)
        assert result.is_entitled is False


class TestBillingEntitlementsServiceCheckAgencyAccess:
    """Tests for BillingEntitlementsService.check_agency_access_entitlement."""

    def _make_service_with_tier(self, tier: str):
        svc = BillingEntitlementsService(MagicMock(), TENANT_ID)
        svc.get_billing_tier = MagicMock(return_value=tier)
        return svc

    def test_free_tier_denied(self):
        svc = self._make_service_with_tier("free")
        result = svc.check_agency_access_entitlement()
        assert result.is_entitled is False

    def test_growth_tier_allowed(self):
        svc = self._make_service_with_tier("growth")
        result = svc.check_agency_access_entitlement()
        assert result.is_entitled is True

    def test_enterprise_tier_allowed(self):
        svc = self._make_service_with_tier("enterprise")
        result = svc.check_agency_access_entitlement()
        assert result.is_entitled is True


class TestBillingEntitlementsServiceValidateRole:
    """Tests for validate_role_for_billing and validate_roles_for_billing."""

    def _make_service_with_tier(self, tier: str):
        svc = BillingEntitlementsService(MagicMock(), TENANT_ID)
        svc.get_billing_tier = MagicMock(return_value=tier)
        return svc

    def test_validate_role_allowed(self):
        svc = self._make_service_with_tier("free")
        result = svc.validate_role_for_billing("merchant_admin")
        assert result.is_valid is True
        assert result.revoked_roles == []

    def test_validate_role_not_allowed(self):
        svc = self._make_service_with_tier("free")
        result = svc.validate_role_for_billing("agency_admin")
        assert result.is_valid is False
        assert "agency_admin" in result.revoked_roles

    def test_validate_roles_all_allowed(self):
        svc = self._make_service_with_tier("enterprise")
        result = svc.validate_roles_for_billing(["merchant_admin", "agency_admin"])
        assert result.is_valid is True
        assert result.revoked_roles == []
        assert set(result.allowed_roles) == {"merchant_admin", "agency_admin"}

    def test_validate_roles_some_revoked(self):
        svc = self._make_service_with_tier("free")
        result = svc.validate_roles_for_billing(["merchant_admin", "agency_admin"])
        assert result.is_valid is False
        assert "agency_admin" in result.revoked_roles
        assert "merchant_admin" in result.allowed_roles


class TestBillingEntitlementsServiceDashboardShares:
    """Tests for get_max_dashboard_shares per tier."""

    @pytest.mark.parametrize(
        "tier, expected",
        [
            ("free", 0),
            ("growth", 5),
            ("enterprise", 999),
        ],
    )
    def test_max_dashboard_shares(self, tier, expected):
        svc = BillingEntitlementsService(MagicMock(), TENANT_ID)
        svc.get_billing_tier = MagicMock(return_value=tier)
        assert svc.get_max_dashboard_shares() == expected


class TestBillingEntitlementsServiceAgencyStores:
    """Tests for get_max_agency_stores and can_add_agency_store per tier."""

    @pytest.mark.parametrize(
        "tier, expected",
        [
            ("free", 0),
            ("growth", 5),
            ("enterprise", 999),
        ],
    )
    def test_max_agency_stores(self, tier, expected):
        svc = BillingEntitlementsService(MagicMock(), TENANT_ID)
        svc.get_billing_tier = MagicMock(return_value=tier)
        assert svc.get_max_agency_stores() == expected

    def test_can_add_agency_store_within_limit(self):
        svc = BillingEntitlementsService(MagicMock(), TENANT_ID)
        svc.get_billing_tier = MagicMock(return_value="growth")
        assert svc.can_add_agency_store(current_store_count=3) is True

    def test_cannot_add_agency_store_at_limit(self):
        svc = BillingEntitlementsService(MagicMock(), TENANT_ID)
        svc.get_billing_tier = MagicMock(return_value="growth")
        assert svc.can_add_agency_store(current_store_count=5) is False

    def test_cannot_add_agency_store_over_limit(self):
        svc = BillingEntitlementsService(MagicMock(), TENANT_ID)
        svc.get_billing_tier = MagicMock(return_value="growth")
        assert svc.can_add_agency_store(current_store_count=6) is False

    def test_free_tier_cannot_add_any_store(self):
        svc = BillingEntitlementsService(MagicMock(), TENANT_ID)
        svc.get_billing_tier = MagicMock(return_value="free")
        assert svc.can_add_agency_store(current_store_count=0) is False


class TestBillingTierFeaturesMatrix:
    """Tests for BILLING_TIER_FEATURES matrix correctness."""

    def test_all_tiers_present(self):
        assert "free" in BILLING_TIER_FEATURES
        assert "growth" in BILLING_TIER_FEATURES
        assert "enterprise" in BILLING_TIER_FEATURES

    def test_free_tier_agency_access_disabled(self):
        assert BILLING_TIER_FEATURES["free"][BillingFeature.AGENCY_ACCESS] is False

    def test_growth_tier_agency_access_enabled(self):
        assert BILLING_TIER_FEATURES["growth"][BillingFeature.AGENCY_ACCESS] is True

    def test_enterprise_tier_all_features_enabled(self):
        for feature in [
            BillingFeature.AGENCY_ACCESS,
            BillingFeature.MULTI_TENANT,
            BillingFeature.ADVANCED_DASHBOARDS,
            BillingFeature.EXPLORE_MODE,
            BillingFeature.DATA_EXPORT,
            BillingFeature.AI_INSIGHTS,
            BillingFeature.AI_RECOMMENDATIONS,
            BillingFeature.AI_ACTIONS,
            BillingFeature.CUSTOM_REPORTS,
            BillingFeature.LLM_ROUTING,
            BillingFeature.CUSTOM_PROMPTS,
            BillingFeature.COHORT_ANALYSIS,
            BillingFeature.BUDGET_PACING,
            BillingFeature.ALERTS,
        ]:
            assert BILLING_TIER_FEATURES["enterprise"][feature] is True, (
                f"Enterprise tier should enable {feature}"
            )

    def test_free_tier_has_limited_ai_insights(self):
        assert BILLING_TIER_FEATURES["free"][BillingFeature.AI_INSIGHTS] is True

    def test_free_tier_no_data_export(self):
        assert BILLING_TIER_FEATURES["free"][BillingFeature.DATA_EXPORT] is False

    def test_growth_tier_no_custom_prompts(self):
        assert BILLING_TIER_FEATURES["growth"][BillingFeature.CUSTOM_PROMPTS] is False

    def test_growth_tier_no_data_export(self):
        assert BILLING_TIER_FEATURES["growth"][BillingFeature.DATA_EXPORT] is False

    def test_free_tier_dashboard_limits(self):
        assert BILLING_TIER_FEATURES["free"]["max_dashboard_access"] == 3
        assert BILLING_TIER_FEATURES["free"]["max_dashboard_shares"] == 0
        assert BILLING_TIER_FEATURES["free"]["max_users"] == 2

    def test_growth_tier_limits(self):
        assert BILLING_TIER_FEATURES["growth"]["max_dashboard_access"] == 10
        assert BILLING_TIER_FEATURES["growth"]["max_dashboard_shares"] == 5
        assert BILLING_TIER_FEATURES["growth"]["max_agency_stores"] == 5

    def test_enterprise_tier_limits(self):
        assert BILLING_TIER_FEATURES["enterprise"]["max_dashboard_access"] == 999
        assert BILLING_TIER_FEATURES["enterprise"]["max_dashboard_shares"] == 999
        assert BILLING_TIER_FEATURES["enterprise"]["max_agency_stores"] == 999


# ---------------------------------------------------------------------------
# BillingRoleSync Tests
# ---------------------------------------------------------------------------


class TestBillingRoleSyncOnDowngrade:
    """Tests for BillingRoleSync.on_billing_downgrade."""

    def test_enterprise_to_free_revokes_agency_roles(self):
        sync = BillingRoleSync(MagicMock())
        result = sync.on_billing_downgrade(
            tenant_id=TENANT_ID,
            user_id="user-1",
            old_tier="enterprise",
            new_tier="free",
            current_roles=["agency_admin", "agency_viewer", "merchant_admin"],
        )

        # agency_admin and owner and admin are enterprise-only
        assert "agency_admin" in result["revoked_roles"]
        # merchant_admin should remain
        assert "merchant_admin" in result["remaining_roles"]
        assert result["old_tier"] == "enterprise"
        assert result["new_tier"] == "free"
        assert "timestamp" in result

    def test_same_tier_returns_empty_revoked(self):
        sync = BillingRoleSync(MagicMock())
        result = sync.on_billing_downgrade(
            tenant_id=TENANT_ID,
            user_id="user-1",
            old_tier="growth",
            new_tier="growth",
            current_roles=["merchant_admin"],
        )

        assert result["revoked_roles"] == []
        assert "merchant_admin" in result["remaining_roles"]

    def test_growth_to_free_revokes_agency_viewer(self):
        sync = BillingRoleSync(MagicMock())
        result = sync.on_billing_downgrade(
            tenant_id=TENANT_ID,
            user_id="user-1",
            old_tier="growth",
            new_tier="free",
            current_roles=["agency_viewer", "merchant_admin", "owner"],
        )

        assert "agency_viewer" in result["revoked_roles"]
        assert "owner" in result["revoked_roles"]
        assert "merchant_admin" in result["remaining_roles"]


class TestBillingRoleSyncOnUpgrade:
    """Tests for BillingRoleSync.on_billing_upgrade."""

    def test_free_to_growth_enables_new_roles(self):
        sync = BillingRoleSync(MagicMock())
        result = sync.on_billing_upgrade(
            tenant_id=TENANT_ID,
            user_id="user-1",
            old_tier="free",
            new_tier="growth",
        )

        # growth adds agency_viewer and owner compared to free
        new_roles = set(result["new_roles_available"])
        assert "agency_viewer" in new_roles
        assert "owner" in new_roles
        assert result["old_tier"] == "free"
        assert result["new_tier"] == "growth"
        assert "timestamp" in result

    def test_same_tier_returns_empty_new_roles(self):
        sync = BillingRoleSync(MagicMock())
        result = sync.on_billing_upgrade(
            tenant_id=TENANT_ID,
            user_id="user-1",
            old_tier="enterprise",
            new_tier="enterprise",
        )

        assert result["new_roles_available"] == []

    def test_growth_to_enterprise_adds_agency_admin_and_admin(self):
        sync = BillingRoleSync(MagicMock())
        result = sync.on_billing_upgrade(
            tenant_id=TENANT_ID,
            user_id="user-1",
            old_tier="growth",
            new_tier="enterprise",
        )

        new_roles = set(result["new_roles_available"])
        assert "agency_admin" in new_roles
        assert "admin" in new_roles


class TestBillingRoleSyncOnSubscriptionCancelled:
    """Tests for BillingRoleSync.on_subscription_cancelled."""

    def test_delegates_to_downgrade_with_free_target(self):
        sync = BillingRoleSync(MagicMock())
        result = sync.on_subscription_cancelled(
            tenant_id=TENANT_ID,
            user_id="user-1",
            cancelled_tier="enterprise",
            current_roles=["agency_admin", "merchant_admin"],
        )

        # Should behave like downgrade to free
        assert result["new_tier"] == "free"
        assert "agency_admin" in result["revoked_roles"]
        assert "merchant_admin" in result["remaining_roles"]

    def test_cancelled_from_growth(self):
        sync = BillingRoleSync(MagicMock())
        result = sync.on_subscription_cancelled(
            tenant_id=TENANT_ID,
            user_id="user-1",
            cancelled_tier="growth",
            current_roles=["agency_viewer", "editor"],
        )

        assert result["new_tier"] == "free"
        assert "agency_viewer" in result["revoked_roles"]
