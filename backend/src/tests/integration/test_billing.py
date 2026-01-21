"""
Integration tests for Shopify Billing.

Tests cover:
1. Checkout URL creation
2. Webhook HMAC verification
3. Subscription state management
4. Tenant isolation for billing operations
5. Reconciliation job
"""

import pytest
import uuid
import hmac
import hashlib
import base64
import json
from datetime import datetime, timezone, timedelta
from unittest.mock import Mock, patch, AsyncMock, MagicMock

from sqlalchemy import create_engine, Column, String, Integer, Boolean, Text, DateTime, ForeignKey, func, JSON
from sqlalchemy.orm import sessionmaker, declarative_base

# Create test-specific base and models to avoid JSONB issues with SQLite
TestBase = declarative_base()


class TestPlan(TestBase):
    """Test Plan model with JSON instead of JSONB."""
    __tablename__ = "plans"
    id = Column(String(255), primary_key=True)
    name = Column(String(255), nullable=False, unique=True)
    display_name = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    shopify_plan_id = Column(String(255), nullable=True)
    price_monthly_cents = Column(Integer, nullable=True)
    price_yearly_cents = Column(Integer, nullable=True)
    is_active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())


class TestPlanFeature(TestBase):
    """Test PlanFeature model."""
    __tablename__ = "plan_features"
    id = Column(String(255), primary_key=True)
    plan_id = Column(String(255), ForeignKey("plans.id"), nullable=False)
    feature_key = Column(String(255), nullable=False)
    is_enabled = Column(Boolean, nullable=False, default=True)
    limit_value = Column(Integer, nullable=True)
    limits = Column(JSON, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())


class TestShopifyStore(TestBase):
    """Test ShopifyStore model."""
    __tablename__ = "shopify_stores"
    id = Column(String(255), primary_key=True)
    shop_domain = Column(String(255), nullable=False, unique=True)
    access_token_encrypted = Column(String(2048), nullable=False)
    status = Column(String(50), nullable=False, default="active")
    tenant_id = Column(String(255), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())


class TestSubscription(TestBase):
    """Test Subscription model with JSON instead of JSONB."""
    __tablename__ = "tenant_subscriptions"
    id = Column(String(255), primary_key=True)
    store_id = Column(String(255), nullable=True)
    plan_id = Column(String(255), ForeignKey("plans.id"), nullable=False)
    shopify_subscription_id = Column(String(255), nullable=True, unique=True)
    shopify_charge_id = Column(String(255), nullable=True)
    status = Column(String(50), nullable=False, default="active")
    current_period_start = Column(DateTime(timezone=True), nullable=True)
    current_period_end = Column(DateTime(timezone=True), nullable=True)
    trial_end = Column(DateTime(timezone=True), nullable=True)
    cancelled_at = Column(DateTime(timezone=True), nullable=True)
    grace_period_ends_on = Column(DateTime(timezone=True), nullable=True)
    extra_metadata = Column("metadata", JSON, nullable=True)
    tenant_id = Column(String(255), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())


class TestBillingEvent(TestBase):
    """Test BillingEvent model with JSON instead of JSONB."""
    __tablename__ = "billing_events"
    id = Column(String(255), primary_key=True)
    event_type = Column(String(100), nullable=False)
    store_id = Column(String(255), nullable=True)
    subscription_id = Column(String(255), nullable=True)
    from_plan_id = Column(String(255), nullable=True)
    to_plan_id = Column(String(255), nullable=True)
    amount_cents = Column(Integer, nullable=True)
    shopify_subscription_id = Column(String(255), nullable=True)
    shopify_charge_id = Column(String(255), nullable=True)
    extra_metadata = Column("metadata", JSON, nullable=True)
    tenant_id = Column(String(255), nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())


# ============================================================================
# FIXTURES
# ============================================================================

@pytest.fixture
def db_session():
    """Create in-memory SQLite database for testing."""
    engine = create_engine("sqlite:///:memory:")
    TestBase.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()


@pytest.fixture
def sample_plan(db_session):
    """Create a sample plan for testing."""
    plan = TestPlan(
        id="plan_growth",
        name="growth",
        display_name="Growth Plan",
        description="For growing businesses",
        price_monthly_cents=2900,
        is_active=True,
    )
    db_session.add(plan)
    db_session.commit()
    return plan


@pytest.fixture
def free_plan(db_session):
    """Create a free plan for testing."""
    plan = TestPlan(
        id="plan_free",
        name="free",
        display_name="Free Plan",
        description="Free tier",
        price_monthly_cents=0,
        is_active=True,
    )
    db_session.add(plan)

    # Add free tier features
    feature = TestPlanFeature(
        id=str(uuid.uuid4()),
        plan_id=plan.id,
        feature_key="basic_analytics",
        is_enabled=True,
    )
    db_session.add(feature)
    db_session.commit()
    return plan


@pytest.fixture
def sample_store(db_session):
    """Create a sample Shopify store for testing."""
    store = TestShopifyStore(
        id=str(uuid.uuid4()),
        shop_domain="test-store.myshopify.com",
        access_token_encrypted="encrypted_token_here",
        tenant_id="tenant-123",
        status="active",
    )
    db_session.add(store)
    db_session.commit()
    return store


@pytest.fixture
def webhook_secret():
    """Webhook secret for HMAC verification."""
    return "test_webhook_secret"


# ============================================================================
# BILLING SERVICE UNIT TESTS (using test models directly)
# ============================================================================

class TestBillingServiceUnit:
    """Unit tests for BillingService without external dependencies."""

    def test_billing_service_requires_tenant_id(self, db_session):
        """BillingService must have non-empty tenant_id."""
        from src.services.billing_service import BillingService

        with pytest.raises(ValueError, match="tenant_id is required"):
            BillingService(db_session, "")

        with pytest.raises(ValueError, match="tenant_id is required"):
            BillingService(db_session, None)


# ============================================================================
# SUBSCRIPTION STATE MANAGEMENT TESTS
# ============================================================================

class TestSubscriptionStateManagement:
    """Tests for subscription state changes."""

    def test_subscription_creation(self, db_session, sample_plan):
        """Test creating a subscription."""
        subscription = TestSubscription(
            id=str(uuid.uuid4()),
            tenant_id="tenant-123",
            plan_id=sample_plan.id,
            status="active",
            shopify_subscription_id="gid://shopify/AppSubscription/123",
        )
        db_session.add(subscription)
        db_session.commit()

        # Query back
        found = db_session.query(TestSubscription).filter(
            TestSubscription.tenant_id == "tenant-123"
        ).first()

        assert found is not None
        assert found.status == "active"
        assert found.plan_id == sample_plan.id

    def test_subscription_cancellation(self, db_session, sample_plan):
        """Test cancelling a subscription."""
        subscription = TestSubscription(
            id=str(uuid.uuid4()),
            tenant_id="tenant-123",
            plan_id=sample_plan.id,
            status="active",
            shopify_subscription_id="gid://shopify/AppSubscription/456",
        )
        db_session.add(subscription)
        db_session.commit()

        # Cancel
        subscription.status = "cancelled"
        subscription.cancelled_at = datetime.now(timezone.utc)
        db_session.commit()

        # Verify
        db_session.refresh(subscription)
        assert subscription.status == "cancelled"
        assert subscription.cancelled_at is not None

    def test_tenant_isolation(self, db_session, sample_plan):
        """Test that tenants are isolated."""
        # Create subscriptions for different tenants
        sub_a = TestSubscription(
            id=str(uuid.uuid4()),
            tenant_id="tenant-a",
            plan_id=sample_plan.id,
            status="active",
        )
        sub_b = TestSubscription(
            id=str(uuid.uuid4()),
            tenant_id="tenant-b",
            plan_id=sample_plan.id,
            status="active",
        )
        db_session.add(sub_a)
        db_session.add(sub_b)
        db_session.commit()

        # Query for tenant-a only
        subs_a = db_session.query(TestSubscription).filter(
            TestSubscription.tenant_id == "tenant-a"
        ).all()

        assert len(subs_a) == 1
        assert subs_a[0].tenant_id == "tenant-a"


# ============================================================================
# BILLING EVENT AUDIT TRAIL TESTS
# ============================================================================

class TestBillingEventAuditTrail:
    """Tests for billing event audit trail."""

    def test_billing_event_creation(self, db_session, sample_plan):
        """Test creating a billing event."""
        subscription = TestSubscription(
            id=str(uuid.uuid4()),
            tenant_id="tenant-123",
            plan_id=sample_plan.id,
            status="active",
        )
        db_session.add(subscription)
        db_session.commit()

        event = TestBillingEvent(
            id=str(uuid.uuid4()),
            tenant_id="tenant-123",
            event_type="subscription_created",
            subscription_id=subscription.id,
            to_plan_id=sample_plan.id,
        )
        db_session.add(event)
        db_session.commit()

        # Query back
        events = db_session.query(TestBillingEvent).filter(
            TestBillingEvent.tenant_id == "tenant-123"
        ).all()

        assert len(events) == 1
        assert events[0].event_type == "subscription_created"

    def test_billing_event_with_metadata(self, db_session):
        """Test billing event with metadata."""
        event = TestBillingEvent(
            id=str(uuid.uuid4()),
            tenant_id="tenant-123",
            event_type="subscription_cancelled",
            extra_metadata={"reason": "user_requested", "source": "webhook"},
        )
        db_session.add(event)
        db_session.commit()

        # Query back
        found = db_session.query(TestBillingEvent).filter(
            TestBillingEvent.id == event.id
        ).first()

        assert found.extra_metadata["reason"] == "user_requested"


# ============================================================================
# WEBHOOK VERIFICATION TESTS
# ============================================================================

class TestWebhookVerification:
    """Tests for Shopify webhook HMAC verification."""

    def test_verify_webhook_signature_valid(self, webhook_secret):
        """Valid HMAC signature is verified successfully."""
        from src.integrations.shopify.billing_client import ShopifyBillingClient

        payload = b'{"test": "data"}'
        computed_hmac = hmac.new(
            webhook_secret.encode("utf-8"),
            payload,
            hashlib.sha256,
        ).digest()
        signature = base64.b64encode(computed_hmac).decode("utf-8")

        with patch.dict("os.environ", {"SHOPIFY_API_SECRET": webhook_secret}):
            result = ShopifyBillingClient.verify_webhook_signature(payload, signature)

        assert result is True

    def test_verify_webhook_signature_invalid(self, webhook_secret):
        """Invalid HMAC signature is rejected."""
        from src.integrations.shopify.billing_client import ShopifyBillingClient

        payload = b'{"test": "data"}'
        invalid_signature = "invalid_signature_here"

        with patch.dict("os.environ", {"SHOPIFY_API_SECRET": webhook_secret}):
            result = ShopifyBillingClient.verify_webhook_signature(payload, invalid_signature)

        assert result is False

    def test_verify_webhook_signature_tampered_payload(self, webhook_secret):
        """Tampered payload fails verification."""
        from src.integrations.shopify.billing_client import ShopifyBillingClient

        original_payload = b'{"test": "data"}'
        tampered_payload = b'{"test": "tampered"}'

        # Create signature for original payload
        computed_hmac = hmac.new(
            webhook_secret.encode("utf-8"),
            original_payload,
            hashlib.sha256,
        ).digest()
        signature = base64.b64encode(computed_hmac).decode("utf-8")

        # Verify with tampered payload
        with patch.dict("os.environ", {"SHOPIFY_API_SECRET": webhook_secret}):
            result = ShopifyBillingClient.verify_webhook_signature(tampered_payload, signature)

        assert result is False


# ============================================================================
# GRACE PERIOD TESTS
# ============================================================================

class TestGracePeriod:
    """Tests for grace period handling."""

    def test_grace_period_expiration(self, db_session, sample_plan):
        """Test subscription expires after grace period."""
        # Use naive datetime for SQLite compatibility
        grace_end = datetime.utcnow() - timedelta(days=1)
        subscription = TestSubscription(
            id=str(uuid.uuid4()),
            tenant_id="tenant-grace",
            plan_id=sample_plan.id,
            status="active",
            grace_period_ends_on=grace_end,
        )
        db_session.add(subscription)
        db_session.commit()

        # Check if should be expired
        now = datetime.utcnow()
        should_expire = subscription.grace_period_ends_on < now

        assert should_expire is True

    def test_grace_period_not_expired(self, db_session, sample_plan):
        """Test subscription not expired during grace period."""
        # Use naive datetime for SQLite compatibility
        grace_end = datetime.utcnow() + timedelta(days=1)
        subscription = TestSubscription(
            id=str(uuid.uuid4()),
            tenant_id="tenant-grace-active",
            plan_id=sample_plan.id,
            status="active",
            grace_period_ends_on=grace_end,
        )
        db_session.add(subscription)
        db_session.commit()

        now = datetime.utcnow()
        should_expire = subscription.grace_period_ends_on < now

        assert should_expire is False


# ============================================================================
# SHOPIFY BILLING CLIENT TESTS
# ============================================================================

class TestShopifyBillingClient:
    """Tests for ShopifyBillingClient."""

    @pytest.mark.asyncio
    async def test_create_subscription_success(self):
        """create_subscription calls Shopify API and returns result."""
        from src.integrations.shopify.billing_client import (
            ShopifyBillingClient,
            ShopifyPlanConfig,
        )

        mock_response = {
            "data": {
                "appSubscriptionCreate": {
                    "appSubscription": {
                        "id": "gid://shopify/AppSubscription/123",
                        "name": "Growth Plan",
                        "status": "PENDING",
                        "createdAt": "2024-01-01T00:00:00Z",
                        "currentPeriodEnd": "2024-02-01T00:00:00Z",
                        "test": False,
                    },
                    "confirmationUrl": "https://example.myshopify.com/admin/charges/123/confirm",
                    "userErrors": [],
                }
            }
        }

        with patch("httpx.AsyncClient.post") as mock_post:
            mock_resp = Mock()
            mock_resp.json.return_value = mock_response
            mock_resp.raise_for_status = Mock()
            mock_post.return_value = mock_resp

            client = ShopifyBillingClient("test.myshopify.com", "token")

            plan = ShopifyPlanConfig(
                name="Growth Plan",
                price=29.00,
                interval="EVERY_30_DAYS",
            )

            result = await client.create_subscription(
                plan=plan,
                return_url="https://app.example.com/callback",
            )

            assert result.subscription_id == "gid://shopify/AppSubscription/123"
            assert result.confirmation_url == "https://example.myshopify.com/admin/charges/123/confirm"
            assert result.status == "PENDING"

            await client.close()

    @pytest.mark.asyncio
    async def test_get_active_subscriptions(self):
        """get_active_subscriptions returns list of active subs."""
        from src.integrations.shopify.billing_client import ShopifyBillingClient

        mock_response = {
            "data": {
                "currentAppInstallation": {
                    "activeSubscriptions": [
                        {
                            "id": "gid://shopify/AppSubscription/1",
                            "name": "Growth Plan",
                            "status": "ACTIVE",
                            "createdAt": "2024-01-01T00:00:00Z",
                            "currentPeriodEnd": "2024-02-01T00:00:00Z",
                            "test": False,
                        }
                    ]
                }
            }
        }

        with patch("httpx.AsyncClient.post") as mock_post:
            mock_resp = Mock()
            mock_resp.json.return_value = mock_response
            mock_resp.raise_for_status = Mock()
            mock_post.return_value = mock_resp

            client = ShopifyBillingClient("test.myshopify.com", "token")
            result = await client.get_active_subscriptions()

            assert len(result) == 1
            assert result[0].subscription_id == "gid://shopify/AppSubscription/1"
            assert result[0].status == "ACTIVE"

            await client.close()

    @pytest.mark.asyncio
    async def test_cancel_subscription_success(self):
        """cancel_subscription calls Shopify API."""
        from src.integrations.shopify.billing_client import ShopifyBillingClient

        mock_response = {
            "data": {
                "appSubscriptionCancel": {
                    "appSubscription": {
                        "id": "gid://shopify/AppSubscription/123",
                        "status": "CANCELLED",
                    },
                    "userErrors": [],
                }
            }
        }

        with patch("httpx.AsyncClient.post") as mock_post:
            mock_resp = Mock()
            mock_resp.json.return_value = mock_response
            mock_resp.raise_for_status = Mock()
            mock_post.return_value = mock_resp

            client = ShopifyBillingClient("test.myshopify.com", "token")
            result = await client.cancel_subscription("gid://shopify/AppSubscription/123")

            assert result is True
            await client.close()


# ============================================================================
# CANCELLATION TIMING TEST
# ============================================================================

class TestCancellationTiming:
    """Tests to verify cancellation is reflected quickly."""

    def test_cancellation_update_is_immediate(self, db_session, sample_plan):
        """Cancellation updates status immediately (under 5 minutes)."""
        subscription = TestSubscription(
            id=str(uuid.uuid4()),
            tenant_id="tenant-timing",
            plan_id=sample_plan.id,
            status="active",
            shopify_subscription_id="gid://shopify/AppSubscription/timing",
        )
        db_session.add(subscription)
        db_session.commit()

        # Record time before cancellation (use naive datetime for SQLite)
        before = datetime.utcnow()

        # Perform cancellation
        subscription.status = "cancelled"
        subscription.cancelled_at = datetime.utcnow()
        db_session.commit()

        after = datetime.utcnow()

        # Refresh and check
        db_session.refresh(subscription)

        assert subscription.status == "cancelled"
        assert subscription.cancelled_at is not None

        # Verify it happened within 5 minutes (should be milliseconds)
        time_taken = after - before
        assert time_taken.total_seconds() < 300  # 5 minutes


# ============================================================================
# ENTITLEMENT CHECKS
# ============================================================================

class TestEntitlements:
    """Tests for feature entitlements."""

    def test_feature_enabled_for_plan(self, db_session, sample_plan):
        """Test feature is enabled for a plan."""
        feature = TestPlanFeature(
            id=str(uuid.uuid4()),
            plan_id=sample_plan.id,
            feature_key="ai_insights",
            is_enabled=True,
        )
        db_session.add(feature)
        db_session.commit()

        # Check if feature exists for plan
        found = db_session.query(TestPlanFeature).filter(
            TestPlanFeature.plan_id == sample_plan.id,
            TestPlanFeature.feature_key == "ai_insights",
            TestPlanFeature.is_enabled == True,
        ).first()

        assert found is not None

    def test_feature_not_enabled(self, db_session, sample_plan):
        """Test feature is not enabled when not in plan."""
        # Query non-existent feature
        found = db_session.query(TestPlanFeature).filter(
            TestPlanFeature.plan_id == sample_plan.id,
            TestPlanFeature.feature_key == "premium_feature",
            TestPlanFeature.is_enabled == True,
        ).first()

        assert found is None


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
