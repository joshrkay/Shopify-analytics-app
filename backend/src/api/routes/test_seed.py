"""
Test seed/teardown endpoints for E2E testing.

These endpoints are ONLY available when ENV=test.
They allow E2E tests to seed and clean up test data
in the database without direct SQL access.

SECURITY: Guarded by ENV=test check. Never available in production.
"""

import os
import logging
from typing import Optional
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/test", tags=["test"])


def _require_test_env():
    """Ensure we're running in test environment."""
    if os.getenv("ENV") != "test":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Test endpoints are only available in test environment (ENV=test)",
        )


# --- Request/Response Schemas ---

class TenantSeed(BaseModel):
    id: str
    name: str
    clerk_org_id: Optional[str] = None
    status: Optional[str] = "active"


class PlanSeed(BaseModel):
    id: str
    name: str
    display_name: str
    price_monthly_cents: int
    features: list[str] = []


class SubscriptionSeed(BaseModel):
    tenant_id: str
    plan_id: str
    status: Optional[str] = "active"


class StoreSeed(BaseModel):
    tenant_id: str
    shop_domain: str
    access_token: Optional[str] = "test-access-token"
    status: Optional[str] = "active"


class DashboardSeed(BaseModel):
    tenant_id: str
    name: str
    status: Optional[str] = "draft"
    reports: Optional[list[dict]] = None


class ConnectionSeed(BaseModel):
    tenant_id: str
    platform: str
    status: Optional[str] = "active"
    last_synced_at: Optional[str] = None


class InsightSeed(BaseModel):
    tenant_id: str
    title: str
    severity: Optional[str] = "medium"
    status: Optional[str] = "active"


class OrderSeed(BaseModel):
    tenant_id: str
    order_name: str
    financial_status: Optional[str] = "paid"
    revenue_gross: Optional[int] = 0


class SeedRequest(BaseModel):
    tenants: Optional[list[TenantSeed]] = None
    plans: Optional[list[PlanSeed]] = None
    subscriptions: Optional[list[SubscriptionSeed]] = None
    stores: Optional[list[StoreSeed]] = None
    dashboards: Optional[list[DashboardSeed]] = None
    connections: Optional[list[ConnectionSeed]] = None
    insights: Optional[list[InsightSeed]] = None
    orders: Optional[list[OrderSeed]] = None


class TeardownRequest(BaseModel):
    tenant_id: str


class QueryRequest(BaseModel):
    table: str
    tenant_id: str
    filters: Optional[dict[str, str]] = None


# --- Endpoints ---

@router.post("/seed")
async def seed_test_data(request: SeedRequest):
    """
    Seed test data into the database.

    Creates entities using SQLAlchemy models to ensure data integrity.
    Returns IDs of all created entities.
    """
    _require_test_env()

    from src.database.session import get_db_session_sync

    created_ids: dict[str, list[str]] = {}

    try:
        db = next(get_db_session_sync())
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Database unavailable: {str(e)}",
        )

    try:
        # Seed plans
        if request.plans:
            from src.models.plan import Plan
            plan_ids = []
            for p in request.plans:
                existing = db.query(Plan).filter(Plan.id == p.id).first()
                if not existing:
                    plan = Plan(
                        id=p.id,
                        name=p.name,
                        display_name=p.display_name,
                        price_monthly_cents=p.price_monthly_cents,
                        is_active=True,
                    )
                    db.add(plan)
                    plan_ids.append(p.id)
            created_ids["plans"] = plan_ids

        # Seed tenants
        if request.tenants:
            from src.models.tenant import Tenant
            tenant_ids = []
            for t in request.tenants:
                existing = db.query(Tenant).filter(Tenant.id == t.id).first()
                if not existing:
                    tenant = Tenant(
                        id=t.id,
                        name=t.name,
                        clerk_org_id=t.clerk_org_id or t.id,
                    )
                    db.add(tenant)
                    tenant_ids.append(t.id)
            created_ids["tenants"] = tenant_ids

        # Seed subscriptions
        if request.subscriptions:
            from src.models.subscription import Subscription
            sub_ids = []
            for s in request.subscriptions:
                import uuid
                sub_id = str(uuid.uuid4())
                subscription = Subscription(
                    id=sub_id,
                    tenant_id=s.tenant_id,
                    plan_id=s.plan_id,
                    status=s.status or "active",
                )
                db.add(subscription)
                sub_ids.append(sub_id)
            created_ids["subscriptions"] = sub_ids

        # Seed stores
        if request.stores:
            from src.models.store import ShopifyStore
            store_ids = []
            for s in request.stores:
                import uuid
                store_id = str(uuid.uuid4())
                store = ShopifyStore(
                    id=store_id,
                    tenant_id=s.tenant_id,
                    shop_domain=s.shop_domain,
                    access_token=s.access_token,
                    status=s.status or "active",
                )
                db.add(store)
                store_ids.append(store_id)
            created_ids["stores"] = store_ids

        # Seed dashboards
        if request.dashboards:
            from src.models.custom_dashboard import CustomDashboard
            dashboard_ids = []
            for d in request.dashboards:
                import uuid
                dash_id = str(uuid.uuid4())
                dashboard = CustomDashboard(
                    id=dash_id,
                    tenant_id=d.tenant_id,
                    name=d.name,
                    status=d.status or "draft",
                )
                db.add(dashboard)
                dashboard_ids.append(dash_id)
            created_ids["dashboards"] = dashboard_ids

        # Seed connections
        if request.connections:
            from src.models.airbyte_connection import AirbyteConnection
            conn_ids = []
            for c in request.connections:
                import uuid
                conn_id = str(uuid.uuid4())
                conn = AirbyteConnection(
                    id=conn_id,
                    tenant_id=c.tenant_id,
                    platform=c.platform,
                    status=c.status or "active",
                )
                db.add(conn)
                conn_ids.append(conn_id)
            created_ids["connections"] = conn_ids

        # Seed insights
        if request.insights:
            from src.models.ai_insight import AIInsight
            insight_ids = []
            for i in request.insights:
                import uuid
                insight_id = str(uuid.uuid4())
                insight = AIInsight(
                    id=insight_id,
                    tenant_id=i.tenant_id,
                    title=i.title,
                    severity=i.severity or "medium",
                    status=i.status or "active",
                )
                db.add(insight)
                insight_ids.append(insight_id)
            created_ids["insights"] = insight_ids

        db.commit()
        logger.info("E2E test data seeded", extra={"created_ids": created_ids})

        return {"status": "ok", "created_ids": created_ids}

    except Exception as e:
        db.rollback()
        logger.error("E2E seed failed", extra={"error": str(e)})
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Seed failed: {str(e)}",
        )
    finally:
        db.close()


@router.post("/teardown")
async def teardown_test_data(request: TeardownRequest):
    """
    Remove all test data for a specific tenant.

    Deletes all records associated with the given tenant_id.
    """
    _require_test_env()

    from src.database.session import get_db_session_sync
    from sqlalchemy import text

    try:
        db = next(get_db_session_sync())
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Database unavailable: {str(e)}",
        )

    try:
        tenant_id = request.tenant_id

        # Delete in dependency order (children first)
        tables_to_clean = [
            "audit_logs",
            "notification_preferences",
            "notifications",
            "alert_rules",
            "ai_insights",
            "ai_recommendations",
            "ai_actions",
            "action_proposals",
            "action_jobs",
            "action_execution_logs",
            "insight_jobs",
            "recommendation_jobs",
            "dashboard_shares",
            "dashboard_versions",
            "dashboard_metric_bindings",
            "custom_reports",
            "custom_dashboards",
            "airbyte_connections",
            "connector_credentials",
            "shopify_stores",
            "subscriptions",
            "user_tenant_roles",
            "tenants",
        ]

        for table in tables_to_clean:
            try:
                db.execute(
                    text(f"DELETE FROM {table} WHERE tenant_id = :tid"),
                    {"tid": tenant_id},
                )
            except Exception:
                # Table may not exist or may not have tenant_id column
                pass

        db.commit()
        logger.info("E2E test data torn down", extra={"tenant_id": tenant_id})

        return {"status": "ok", "tenant_id": tenant_id}

    except Exception as e:
        db.rollback()
        logger.error("E2E teardown failed", extra={"error": str(e)})
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Teardown failed: {str(e)}",
        )
    finally:
        db.close()


@router.post("/query")
async def query_test_data(request: QueryRequest):
    """
    Query data from the test database (for E2E assertions).

    Returns rows matching the given table, tenant_id, and optional filters.
    Limited to 100 rows for safety.
    """
    _require_test_env()

    from src.database.session import get_db_session_sync
    from sqlalchemy import text

    # Whitelist of queryable tables (prevent SQL injection via table name)
    ALLOWED_TABLES = {
        "tenants", "plans", "subscriptions", "shopify_stores",
        "custom_dashboards", "custom_reports", "airbyte_connections",
        "ai_insights", "ai_recommendations", "ai_actions",
        "action_proposals", "alert_rules", "notifications",
        "user_tenant_roles", "audit_logs",
    }

    if request.table not in ALLOWED_TABLES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Table '{request.table}' not in allowed list: {sorted(ALLOWED_TABLES)}",
        )

    try:
        db = next(get_db_session_sync())
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Database unavailable: {str(e)}",
        )

    try:
        query = f"SELECT * FROM {request.table} WHERE tenant_id = :tid"
        params = {"tid": request.tenant_id}

        if request.filters:
            for key, value in request.filters.items():
                # Only allow alphanumeric column names
                if not key.isalnum():
                    continue
                query += f" AND {key} = :filter_{key}"
                params[f"filter_{key}"] = value

        query += " LIMIT 100"

        result = db.execute(text(query), params)
        columns = result.keys()
        rows = [dict(zip(columns, row)) for row in result.fetchall()]

        # Serialize datetime objects
        for row in rows:
            for key, value in row.items():
                if isinstance(value, datetime):
                    row[key] = value.isoformat()

        return {"rows": rows, "count": len(rows)}

    except Exception as e:
        logger.error("E2E query failed", extra={"error": str(e)})
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Query failed: {str(e)}",
        )
    finally:
        db.close()
