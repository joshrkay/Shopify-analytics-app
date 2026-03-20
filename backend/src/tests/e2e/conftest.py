"""
E2E Test Configuration and Fixtures.

Provides:
- Test database setup with PostgreSQL
- Mock service instances (Shopify, Airbyte, OpenRouter, Clerk)
- Test client with dependency overrides
- Test data providers
"""

import os
import uuid
import hashlib
import pytest
from datetime import datetime, timezone, timedelta
from typing import Generator, AsyncGenerator, Dict, List
from unittest.mock import patch

from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from fastapi.testclient import TestClient
from httpx import AsyncClient

# Set test environment before importing app modules
os.environ["ENV"] = "test"
os.environ["SHOPIFY_API_SECRET"] = "test-webhook-secret-for-hmac"
os.environ["SHOPIFY_BILLING_TEST_MODE"] = "true"
os.environ.setdefault("CLERK_SECRET_KEY", "test-clerk-secret-key")
os.environ.setdefault("CLERK_PUBLISHABLE_KEY", "test-clerk-publishable-key")
os.environ.setdefault("ENCRYPTION_KEY", "dGVzdC1lbmNyeXB0aW9uLWtleS0zMi1ieXRlcw==")
os.environ.setdefault("AIRBYTE_API_TOKEN", "test-airbyte-token")
os.environ.setdefault("AIRBYTE_WORKSPACE_ID", "test-workspace-id")
os.environ.setdefault("OPENROUTER_API_KEY", "test-openrouter-key")

# Import mocks
from .mocks import (
    MockShopifyServer,
    ShopifyWebhookSimulator,
    MockAirbyteServer,
    MockOpenRouterServer,
    MockClerkServer,  # Backwards compatibility alias
)

# Import helpers
from .helpers import (
    generate_test_orders,
)

# Test constants
TEST_WEBHOOK_SECRET = "test-webhook-secret-for-hmac"


# =============================================================================
# Database Configuration
# =============================================================================

def _get_test_database_url() -> str:
    """Get PostgreSQL database URL for E2E tests."""
    database_url = os.getenv("DATABASE_URL")

    if not database_url:
        database_url = "postgresql://postgres:test@localhost:5432/shopify_analytics_test"

    # Handle Render's postgres:// URL format
    if database_url.startswith("postgres://"):
        database_url = database_url.replace("postgres://", "postgresql://", 1)

    return database_url


def _get_async_database_url() -> str:
    """Get async PostgreSQL URL."""
    url = _get_test_database_url()
    return url.replace("postgresql://", "postgresql+asyncpg://")


# =============================================================================
# Database Fixtures
# =============================================================================

@pytest.fixture(scope="session")
def db_engine():
    """Create PostgreSQL database engine for E2E tests."""
    database_url = _get_test_database_url()

    try:
        engine = create_engine(database_url, pool_pre_ping=True)
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
    except Exception as e:
        pytest.skip(
            f"PostgreSQL required for E2E tests. "
            f"Set DATABASE_URL or run: docker run -d --name test-pg "
            f"-e POSTGRES_PASSWORD=test -p 5432:5432 postgres:15. "
            f"Error: {e}"
        )

    # Import and create all tables
    from src.db_base import Base

    Base.metadata.create_all(bind=engine)

    yield engine

    # Cleanup
    Base.metadata.drop_all(bind=engine)


@pytest.fixture(scope="function")
def db_session(db_engine) -> Generator[Session, None, None]:
    """Create database session with transaction rollback for test isolation."""
    connection = db_engine.connect()
    transaction = connection.begin()

    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=connection)
    session = SessionLocal()

    nested = connection.begin_nested()

    @event.listens_for(session, "after_transaction_end")
    def restart_savepoint(session, transaction):
        nonlocal nested
        if transaction.nested and not transaction._parent.nested:
            nested = connection.begin_nested()

    yield session

    session.close()
    transaction.rollback()
    connection.close()


@pytest.fixture(scope="session")
def async_db_engine():
    """Create async PostgreSQL engine for E2E tests."""
    database_url = _get_async_database_url()

    try:
        engine = create_async_engine(database_url, pool_pre_ping=True)
    except Exception as e:
        pytest.skip(f"Async PostgreSQL connection failed: {e}")

    yield engine


@pytest.fixture
async def async_db_session(async_db_engine) -> AsyncGenerator[AsyncSession, None]:
    """Create async database session."""
    async_session_maker = async_sessionmaker(
        async_db_engine,
        class_=AsyncSession,
        expire_on_commit=False
    )

    async with async_session_maker() as session:
        yield session


# =============================================================================
# Mock Service Fixtures
# =============================================================================

@pytest.fixture(scope="session")
def mock_clerk() -> MockClerkServer:
    """Create mock Clerk auth server (session-scoped for key consistency)."""
    return MockClerkServer()


# Backwards compatibility alias
@pytest.fixture(scope="session")
def mock_frontegg(mock_clerk) -> MockClerkServer:
    """Backwards compatibility alias for mock_clerk fixture."""
    return mock_clerk


@pytest.fixture
def mock_shopify() -> MockShopifyServer:
    """Create mock Shopify API server."""
    return MockShopifyServer(api_secret=TEST_WEBHOOK_SECRET)


@pytest.fixture
def mock_airbyte() -> MockAirbyteServer:
    """Create mock Airbyte API server."""
    return MockAirbyteServer(sync_delay_seconds=0.1)


@pytest.fixture
def mock_openrouter() -> MockOpenRouterServer:
    """Create mock OpenRouter LLM server."""
    return MockOpenRouterServer()


@pytest.fixture
def webhook_simulator(client) -> ShopifyWebhookSimulator:
    """Create webhook simulator for sending signed webhooks via test client."""
    return ShopifyWebhookSimulator(
        api_secret=TEST_WEBHOOK_SECRET,
        test_client=client
    )


# =============================================================================
# Test Identity Fixtures
# =============================================================================

@pytest.fixture
def test_tenant_id() -> str:
    """Generate unique tenant ID."""
    return f"e2e-tenant-{uuid.uuid4().hex[:8]}"


@pytest.fixture
def test_tenant_id_b() -> str:
    """Second tenant ID for isolation tests."""
    return f"e2e-tenant-b-{uuid.uuid4().hex[:8]}"


@pytest.fixture
def test_shop_domain(test_tenant_id) -> str:
    """Test shop domain."""
    return f"{test_tenant_id}.myshopify.com"


@pytest.fixture
def test_shop_domain_b(test_tenant_id_b) -> str:
    """Second shop domain."""
    return f"{test_tenant_id_b}.myshopify.com"


# =============================================================================
# Auth Token Fixtures
# =============================================================================

@pytest.fixture
def test_token(mock_frontegg, test_tenant_id) -> str:
    """Create test JWT token for primary tenant."""
    return mock_frontegg.create_test_token(
        tenant_id=test_tenant_id,
        entitlements=["AI_INSIGHTS", "AI_RECOMMENDATIONS", "AI_ACTIONS"],
    )


@pytest.fixture
def test_token_b(mock_frontegg, test_tenant_id_b) -> str:
    """Create test JWT token for second tenant."""
    return mock_frontegg.create_test_token(
        tenant_id=test_tenant_id_b,
        entitlements=["AI_INSIGHTS"],
    )


@pytest.fixture
def free_tier_token(mock_frontegg, test_tenant_id) -> str:
    """Create token for free tier user (no AI entitlements)."""
    return mock_frontegg.create_free_tier_token(test_tenant_id)


@pytest.fixture
def admin_token(mock_frontegg, test_tenant_id) -> str:
    """Create admin token."""
    return mock_frontegg.create_admin_token(test_tenant_id)


# =============================================================================
# FastAPI Test Client Fixtures
# =============================================================================

class MockJWKSClient:
    """Mock JWKS client that uses the mock Clerk server's keys."""

    def __init__(self, mock_clerk_server):
        self._mock = mock_clerk_server
        self.client_id = os.getenv("CLERK_PUBLISHABLE_KEY", "test-clerk-publishable-key")

    def get_signing_key(self, token):
        """Return mock signing key using the mock server's public key."""
        class MockSigningKey:
            def __init__(self, public_key):
                self.key = public_key
        return MockSigningKey(self._mock._public_key)


@pytest.fixture
def test_app(db_session, mock_clerk, mock_shopify, mock_airbyte, mock_openrouter):
    """
    Create FastAPI test application with all dependencies mocked.
    """
    from main import app
    from src.api.routes.webhooks_shopify import get_db_session
    from src.platform.tenant_context import TenantContextMiddleware

    original_overrides = app.dependency_overrides.copy()

    # Override database session
    def override_get_db_session():
        yield db_session

    app.dependency_overrides[get_db_session] = override_get_db_session

    # Store mock references for access in tests
    app.state.mock_clerk = mock_clerk
    app.state.mock_frontegg = mock_clerk  # Backwards compatibility
    app.state.mock_shopify = mock_shopify
    app.state.mock_airbyte = mock_airbyte
    app.state.mock_openrouter = mock_openrouter

    # Create mock JWKS client that uses mock_clerk's keys
    mock_jwks_client = MockJWKSClient(mock_clerk)

    # Patch the TenantContextMiddleware to use our mock JWKS client
    with patch.object(TenantContextMiddleware, '_get_jwks_client', return_value=mock_jwks_client):
        yield app

    app.dependency_overrides = original_overrides


@pytest.fixture
def client(test_app) -> TestClient:
    """Create synchronous test client."""
    return TestClient(test_app)


@pytest.fixture
async def async_client(test_app) -> AsyncGenerator[AsyncClient, None]:
    """Create async test client using ASGITransport (httpx 0.23.0+ pattern)."""
    import httpx
    transport = httpx.ASGITransport(app=test_app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


# =============================================================================
# Test Data Fixtures
# =============================================================================

@pytest.fixture
def test_orders() -> list:
    """Generate standard test orders."""
    return generate_test_orders(count=10)


@pytest.fixture
def test_orders_with_refunds() -> list:
    """Generate orders including refunds and cancellations."""
    from .helpers import generate_test_order

    orders = [
        generate_test_order(total_price=100.0, financial_status="paid"),
        generate_test_order(total_price=150.0, financial_status="paid"),
        generate_test_order(total_price=200.0, financial_status="refunded", refunds=[{"amount": "200.00"}]),
        generate_test_order(total_price=75.0, financial_status="partially_refunded", refunds=[{"amount": "25.00"}]),
        generate_test_order(total_price=50.0, financial_status="paid", cancelled_at=datetime.now(timezone.utc).isoformat()),
    ]
    return orders


@pytest.fixture
def declining_revenue_orders() -> list:
    """Generate orders showing declining revenue pattern."""
    from .helpers import generate_declining_revenue_pattern
    return generate_declining_revenue_pattern(days=14, start_revenue=10000.0, decline_rate=0.2)


# =============================================================================
# Database Entity Fixtures
# =============================================================================

@pytest.fixture
def test_plan_free(db_session):
    """Create free plan."""
    from src.models.plan import Plan

    plan = Plan(
        id="plan_free_e2e",
        name="free",
        display_name="Free",
        description="Free tier",
        price_monthly_cents=0,
        price_yearly_cents=0,
        is_active=True
    )
    db_session.add(plan)
    db_session.flush()
    return plan


@pytest.fixture
def test_plan_pro(db_session):
    """Create pro plan with AI features."""
    from src.models.plan import Plan

    plan = Plan(
        id="plan_pro_e2e",
        name="pro",
        display_name="Pro",
        description="Pro tier with AI features",
        price_monthly_cents=7900,
        price_yearly_cents=79000,
        is_active=True
    )
    db_session.add(plan)
    db_session.flush()
    return plan


@pytest.fixture
def test_store(db_session, test_tenant_id, test_shop_domain):
    """Create test Shopify store."""
    from src.models.store import ShopifyStore

    store = ShopifyStore(
        id=str(uuid.uuid4()),
        tenant_id=test_tenant_id,
        shop_domain=test_shop_domain,
        shop_id=str(hash(test_shop_domain) % 10**12),
        access_token_encrypted="encrypted-test-token",
        scopes="read_products,write_products,read_orders",
        currency="USD",
        timezone="America/New_York",
        status="active"
    )
    db_session.add(store)
    db_session.flush()
    return store


@pytest.fixture
def test_airbyte_connection(db_session, test_tenant_id):
    """Create test Airbyte connection."""
    from src.models.airbyte_connection import (
        TenantAirbyteConnection,
        ConnectionStatus,
        ConnectionType,
    )

    connection = TenantAirbyteConnection(
        id=str(uuid.uuid4()),
        tenant_id=test_tenant_id,
        airbyte_connection_id=f"airbyte-e2e-{uuid.uuid4().hex[:12]}",
        connection_name="E2E Test Shopify Connection",
        connection_type=ConnectionType.SOURCE,
        source_type="shopify",
        status=ConnectionStatus.ACTIVE,
        is_enabled=True,
        configuration={"shop": "test-store.myshopify.com"}
    )
    db_session.add(connection)
    db_session.flush()
    return connection


# =============================================================================
# Utility Fixtures
# =============================================================================

@pytest.fixture
def auth_headers(test_token) -> Dict[str, str]:
    """Standard auth headers for API requests."""
    return {"Authorization": f"Bearer {test_token}"}


@pytest.fixture
def auth_headers_b(test_token_b) -> Dict[str, str]:
    """Auth headers for second tenant."""
    return {"Authorization": f"Bearer {test_token_b}"}


@pytest.fixture
def webhook_secret() -> str:
    """Webhook secret for HMAC signing."""
    return TEST_WEBHOOK_SECRET


# =============================================================================
# Markers
# =============================================================================

@pytest.fixture
def free_tier_headers(free_tier_token) -> Dict[str, str]:
    """Auth headers for free tier user."""
    return {"Authorization": f"Bearer {free_tier_token}"}


@pytest.fixture
def admin_headers(admin_token) -> Dict[str, str]:
    """Auth headers for admin user."""
    return {"Authorization": f"Bearer {admin_token}"}


@pytest.fixture
def viewer_token(mock_frontegg, test_tenant_id) -> str:
    """Create token with viewer role only."""
    return mock_frontegg.create_test_token(
        tenant_id=test_tenant_id,
        roles=["viewer"],
        entitlements=[],
    )


@pytest.fixture
def viewer_headers(viewer_token) -> Dict[str, str]:
    """Auth headers for viewer user."""
    return {"Authorization": f"Bearer {viewer_token}"}


@pytest.fixture
def pro_tier_token(mock_frontegg, test_tenant_id) -> str:
    """Create token with full pro entitlements."""
    return mock_frontegg.create_test_token(
        tenant_id=test_tenant_id,
        roles=["admin", "user"],
        entitlements=[
            "AI_INSIGHTS", "AI_RECOMMENDATIONS", "AI_ACTIONS",
            "CUSTOM_REPORTS", "ADVANCED_ANALYTICS",
            "COHORT_ANALYSIS", "BUDGET_PACING", "ALERTS",
        ],
    )


@pytest.fixture
def pro_tier_headers(pro_tier_token) -> Dict[str, str]:
    """Auth headers for pro tier user."""
    return {"Authorization": f"Bearer {pro_tier_token}"}


@pytest.fixture
def agency_token(mock_frontegg, test_tenant_id, test_tenant_id_b) -> str:
    """Create agency token with multi-tenant access."""
    return mock_frontegg.create_agency_token(
        primary_tenant_id=test_tenant_id,
        allowed_tenants=[test_tenant_id, test_tenant_id_b],
    )


@pytest.fixture
def agency_headers(agency_token) -> Dict[str, str]:
    """Auth headers for agency user."""
    return {"Authorization": f"Bearer {agency_token}"}


@pytest.fixture
def test_user_id(test_token) -> str:
    """Extract user_id from the test token."""
    import jwt as pyjwt
    claims = pyjwt.decode(test_token, options={"verify_signature": False})
    return claims["sub"]


# =============================================================================
# Database Entity Fixtures — Subscriptions & Billing
# =============================================================================

@pytest.fixture
def test_subscription(db_session, test_tenant_id, test_plan_pro, test_store):
    """Create active pro subscription."""
    from src.models.subscription import Subscription

    now = datetime.now(timezone.utc)
    sub = Subscription(
        id=str(uuid.uuid4()),
        tenant_id=test_tenant_id,
        store_id=test_store.id,
        plan_id=test_plan_pro.id,
        status="active",
        shopify_subscription_id=f"gid://shopify/AppSubscription/{uuid.uuid4().hex[:12]}",
        current_period_start=now - timedelta(days=15),
        current_period_end=now + timedelta(days=15),
    )
    db_session.add(sub)
    db_session.flush()
    return sub


# =============================================================================
# Database Entity Fixtures — AI Features
# =============================================================================

def _content_hash(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


@pytest.fixture
def test_insights(db_session, test_tenant_id) -> list:
    """Seed 5 AI insight records."""
    from src.models.ai_insight import AIInsight

    now = datetime.now(timezone.utc)
    insights = []
    types = ["spend_anomaly", "roas_change", "revenue_vs_spend_divergence", "channel_mix_shift", "cac_anomaly"]
    severities = ["critical", "warning", "info", "warning", "critical"]

    for i, (itype, sev) in enumerate(zip(types, severities)):
        insight = AIInsight(
            id=str(uuid.uuid4()),
            tenant_id=test_tenant_id,
            insight_type=itype,
            severity=sev,
            summary=f"E2E test insight {i}: {itype} detected",
            why_it_matters=f"This matters because of test reason {i}",
            supporting_metrics=[{"metric": "spend", "current": 100 + i * 10, "change_pct": -5.0 * i}],
            confidence_score=0.85 + i * 0.02,
            period_type="weekly",
            period_start=now - timedelta(days=7),
            period_end=now,
            comparison_type="week_over_week",
            content_hash=_content_hash(f"insight-{i}-{test_tenant_id}"),
            generated_at=now - timedelta(hours=i),
            is_read=0,
            is_dismissed=0,
        )
        db_session.add(insight)
        insights.append(insight)

    db_session.flush()
    return insights


@pytest.fixture
def test_recommendations(db_session, test_tenant_id, test_insights) -> list:
    """Seed 3 AI recommendation records."""
    from src.models.ai_recommendation import AIRecommendation

    now = datetime.now(timezone.utc)
    recs = []
    rec_types = ["reduce_spend", "increase_spend", "reallocate_budget"]
    priorities = ["high", "medium", "low"]

    for i, (rtype, prio) in enumerate(zip(rec_types, priorities)):
        rec = AIRecommendation(
            id=str(uuid.uuid4()),
            tenant_id=test_tenant_id,
            related_insight_id=test_insights[i].id,
            recommendation_type=rtype,
            priority=prio,
            recommendation_text=f"E2E recommendation {i}: {rtype}",
            rationale=f"Based on test insight {i}",
            estimated_impact="moderate",
            risk_level="low",
            confidence_score=0.80 + i * 0.05,
            content_hash=_content_hash(f"rec-{i}-{test_tenant_id}"),
            generated_at=now - timedelta(hours=i),
            is_accepted=0,
            is_dismissed=0,
        )
        db_session.add(rec)
        recs.append(rec)

    db_session.flush()
    return recs


@pytest.fixture
def test_action_proposals(db_session, test_tenant_id, test_recommendations) -> list:
    """Seed 2 action proposals (1 pending, 1 approved)."""
    from src.models.action_proposal import ActionProposal

    now = datetime.now(timezone.utc)
    proposals = []

    for i, status in enumerate(["proposed", "approved"]):
        proposal = ActionProposal(
            id=str(uuid.uuid4()),
            tenant_id=test_tenant_id,
            source_recommendation_id=test_recommendations[i].id,
            action_type="reduce_budget" if i == 0 else "increase_budget",
            status=status,
            target_platform="meta",
            target_entity_type="campaign",
            target_entity_id=f"camp_{uuid.uuid4().hex[:8]}",
            target_entity_name=f"E2E Test Campaign {i}",
            proposed_change={"field": "daily_budget", "from": 100, "to": 80 if i == 0 else 120},
            current_value={"daily_budget": 100},
            expected_effect=f"Expected to {'save' if i == 0 else 'increase'} spend by 20%",
            risk_disclaimer="Test risk disclaimer",
            risk_level="low",
            confidence_score=0.85,
            expires_at=now + timedelta(days=7),
            content_hash=_content_hash(f"proposal-{i}-{test_tenant_id}"),
            generated_at=now,
        )
        db_session.add(proposal)
        proposals.append(proposal)

    db_session.flush()
    return proposals


@pytest.fixture
def test_actions(db_session, test_tenant_id, test_recommendations) -> list:
    """Seed 2 AI action records."""
    from src.models.ai_action import AIAction

    now = datetime.now(timezone.utc)
    actions = []

    for i, status in enumerate(["approved", "succeeded"]):
        action = AIAction(
            id=str(uuid.uuid4()),
            tenant_id=test_tenant_id,
            recommendation_id=test_recommendations[i].id,
            action_type="adjust_budget" if i == 0 else "pause_campaign",
            platform="meta",
            target_entity_id=f"camp_{uuid.uuid4().hex[:8]}",
            target_entity_type="campaign",
            action_params={"field": "daily_budget", "value": 80},
            status=status,
            content_hash=_content_hash(f"action-{i}-{test_tenant_id}"),
            created_at=now - timedelta(hours=i),
        )
        db_session.add(action)
        actions.append(action)

    db_session.flush()
    return actions


# =============================================================================
# Database Entity Fixtures — Dashboards
# =============================================================================

@pytest.fixture
def test_dashboard(db_session, test_tenant_id, test_user_id):
    """Create a custom dashboard with 2 reports."""
    from src.models.custom_dashboard import CustomDashboard
    from src.models.custom_report import CustomReport

    dashboard = CustomDashboard(
        id=str(uuid.uuid4()),
        tenant_id=test_tenant_id,
        name="E2E Test Dashboard",
        description="Dashboard for E2E testing",
        status="draft",
        layout_json={"cols": 12, "rowHeight": 30},
        created_by=test_user_id,
    )
    db_session.add(dashboard)
    db_session.flush()

    reports = []
    for i in range(2):
        report = CustomReport(
            id=str(uuid.uuid4()),
            tenant_id=test_tenant_id,
            dashboard_id=dashboard.id,
            name=f"E2E Report {i}",
            chart_type="line" if i == 0 else "bar",
            dataset_name="kpi_summary",
            config_json={"metric": "revenue", "dimension": "date"},
            position_json={"x": i * 6, "y": 0, "w": 6, "h": 4},
            created_by=test_user_id,
            sort_order=i,
        )
        db_session.add(report)
        reports.append(report)

    db_session.flush()
    dashboard._test_reports = reports
    return dashboard


# =============================================================================
# Database Entity Fixtures — Alerts
# =============================================================================

@pytest.fixture
def test_alert_rules(db_session, test_tenant_id) -> list:
    """Seed 3 alert rules."""
    from src.models.alert_rule import AlertRule

    rules = []
    configs = [
        ("Revenue Drop Alert", "total_revenue", "lt", 1000.0, "daily", "critical"),
        ("High Spend Alert", "total_spend", "gt", 5000.0, "daily", "warning"),
        ("Low ROAS Alert", "roas", "lt", 1.5, "weekly", "warning"),
    ]

    for name, metric, op, threshold, period, severity in configs:
        rule = AlertRule(
            id=str(uuid.uuid4()),
            tenant_id=test_tenant_id,
            name=name,
            metric_name=metric,
            comparison_operator=op,
            threshold_value=threshold,
            evaluation_period=period,
            severity=severity,
            enabled=True,
        )
        db_session.add(rule)
        rules.append(rule)

    db_session.flush()
    return rules


# =============================================================================
# Database Entity Fixtures — Notifications
# =============================================================================

@pytest.fixture
def test_notifications(db_session, test_tenant_id, test_user_id) -> list:
    """Seed 5 notification records."""
    from src.models.notification import Notification

    now = datetime.now(timezone.utc)
    notifications = []
    event_types = [
        "insight_generated", "recommendation_created", "action_requires_approval",
        "sync_completed", "alert_triggered",
    ]

    for i, etype in enumerate(event_types):
        notif = Notification(
            id=str(uuid.uuid4()),
            tenant_id=test_tenant_id,
            user_id=test_user_id,
            event_type=etype,
            importance="important" if i < 2 else "routine",
            title=f"E2E Notification {i}",
            message=f"Test notification message for {etype}",
            idempotency_key=f"e2e-notif-{uuid.uuid4().hex[:12]}",
            status="delivered" if i < 3 else "pending",
            created_at=now - timedelta(hours=i),
        )
        db_session.add(notif)
        notifications.append(notif)

    db_session.flush()
    return notifications


# =============================================================================
# Database Entity Fixtures — Audit Logs
# =============================================================================

@pytest.fixture
def test_audit_logs(db_session, test_tenant_id, test_user_id) -> list:
    """Seed 10 audit log records."""
    from src.models.audit_log import GAAuditLog

    now = datetime.now(timezone.utc)
    correlation = str(uuid.uuid4())
    logs = []
    event_types = [
        "auth.login_success", "dashboard.created", "dashboard.viewed",
        "dashboard.updated", "dashboard.published", "insight.generated",
        "recommendation.accepted", "action.executed", "billing.checkout",
        "team.member_invited",
    ]

    for i, etype in enumerate(event_types):
        log = GAAuditLog(
            id=str(uuid.uuid4()),
            event_type=etype,
            user_id=test_user_id,
            tenant_id=test_tenant_id,
            access_surface="external_app",
            success=True,
            event_metadata={"detail": f"E2E test event {i}"},
            correlation_id=correlation if i < 3 else str(uuid.uuid4()),
            created_at=now - timedelta(hours=i),
        )
        db_session.add(log)
        logs.append(log)

    db_session.flush()
    return logs


# =============================================================================
# Database Entity Fixtures — Store for Tenant B
# =============================================================================

@pytest.fixture
def test_store_b(db_session, test_tenant_id_b, test_shop_domain_b):
    """Create second test Shopify store for tenant B."""
    from src.models.store import ShopifyStore

    store = ShopifyStore(
        id=str(uuid.uuid4()),
        tenant_id=test_tenant_id_b,
        shop_domain=test_shop_domain_b,
        shop_id=str(hash(test_shop_domain_b) % 10**12),
        access_token_encrypted="encrypted-test-token-b",
        scopes="read_products,write_products,read_orders",
        currency="USD",
        timezone="America/New_York",
        status="active",
    )
    db_session.add(store)
    db_session.flush()
    return store


# =============================================================================
# Markers
# =============================================================================

def pytest_configure(config):
    """Register custom markers."""
    config.addinivalue_line("markers", "e2e: mark test as end-to-end test")
    config.addinivalue_line("markers", "security: mark test as security-focused")
    config.addinivalue_line("markers", "slow: mark test as slow-running")
    config.addinivalue_line("markers", "ai_features: mark test as testing AI features")
    config.addinivalue_line("markers", "billing: mark test as billing-focused")
    config.addinivalue_line("markers", "rbac: mark test as RBAC-focused")
