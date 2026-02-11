"""
Unified Sources API route for listing all data source connections.

Returns Shopify and ad platform connections in a single unified list.
Each source maps to: id, platform key, display name, authType, status, lastSyncAt.

SECURITY: All routes require valid tenant context from JWT.

Story 2.1.1 — Unified Source domain model
"""

import logging
from typing import List

from fastapi import APIRouter, Request, Depends

from src.platform.tenant_context import get_tenant_context
from src.database.session import get_db_session
from src.services.airbyte_service import AirbyteService
from src.api.schemas.sources import (
    SourceSummary,
    SourceListResponse,
    normalize_connection_to_source,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/sources", tags=["sources"])


@router.get(
    "",
    response_model=SourceListResponse,
)
async def list_sources(
    request: Request,
    db_session=Depends(get_db_session),
):
    """
    List all data source connections for the authenticated tenant.

    Returns a unified list of Shopify and ad platform connections,
    each normalized to a common Source schema.

    SECURITY: Only returns connections belonging to the tenant.
    """
    tenant_ctx = get_tenant_context(request)
    service = AirbyteService(db_session, tenant_ctx.tenant_id)

    result = service.list_connections(connection_type="source")

    sources: List[SourceSummary] = [
        normalize_connection_to_source(conn)
        for conn in result.connections
        if conn.status != "deleted"
    ]

    logger.info(
        "Listed unified sources",
        extra={
            "tenant_id": tenant_ctx.tenant_id,
            "count": len(sources),
        },
    )

    return SourceListResponse(sources=sources, total=len(sources))
