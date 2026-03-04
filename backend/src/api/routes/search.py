"""
Global Search API — search across dashboards, pages, and entities.

Provides:
  GET /api/search?q=<query> — search with min 2 char query

Tenant isolation: WHERE tenant_id = :tenant_id on every query.
"""

import logging
from typing import List

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel
from sqlalchemy import text

from src.platform.tenant_context import get_tenant_context

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/search", tags=["search"])


def _get_db(request: Request):
    get_tenant_context(request)
    from src.database.session import SessionLocal
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


class SearchResult(BaseModel):
    type: str
    title: str
    path: str


class SearchResponse(BaseModel):
    results: List[SearchResult]


# Static pages for client-side matching
STATIC_PAGES = [
    SearchResult(type="page", title="Home", path="/home"),
    SearchResult(type="page", title="Attribution", path="/attribution"),
    SearchResult(type="page", title="Orders", path="/orders"),
    SearchResult(type="page", title="Cohort Analysis", path="/cohort-analysis"),
    SearchResult(type="page", title="Budget Pacing", path="/budget-pacing"),
    SearchResult(type="page", title="Alerts", path="/alerts"),
    SearchResult(type="page", title="Builder", path="/dashboards"),
    SearchResult(type="page", title="Insights", path="/insights"),
    SearchResult(type="page", title="Sources", path="/data-sources"),
    SearchResult(type="page", title="Settings", path="/settings"),
    SearchResult(type="page", title="What's New", path="/whats-new"),
]


@router.get("", response_model=SearchResponse)
async def global_search(
    request: Request,
    q: str = Query(..., min_length=2, max_length=100),
    db=Depends(_get_db),
):
    """Search across pages and custom dashboards."""
    tenant_ctx = get_tenant_context(request)
    results: List[SearchResult] = []
    query_lower = q.lower()

    # Static page matches
    for page in STATIC_PAGES:
        if query_lower in page.title.lower():
            results.append(page)

    # Search custom dashboards
    try:
        rows = db.execute(text("""
            SELECT id, title
            FROM custom_dashboards
            WHERE tenant_id = :tenant_id
              AND title ILIKE :query
            LIMIT 5
        """), {
            "tenant_id": tenant_ctx.tenant_id,
            "query": f"%{q}%",
        }).fetchall()

        for row in rows:
            results.append(SearchResult(
                type="dashboard",
                title=row.title,
                path=f"/dashboards/{row.id}",
            ))
    except Exception as exc:
        logger.warning("Dashboard search failed: %s", exc)

    return SearchResponse(results=results)
