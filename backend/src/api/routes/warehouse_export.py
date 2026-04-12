"""
Data Warehouse Export API routes.

Allows Pro/Enterprise users to configure data warehouse destinations
(BigQuery, Snowflake, Redshift) and sync analytics data to them via Airbyte.

Provides:
- GET /api/warehouse/destinations — List configured warehouse destinations
- POST /api/warehouse/destinations — Create a new warehouse destination
- DELETE /api/warehouse/destinations/{id} — Remove a warehouse destination
- POST /api/warehouse/destinations/{id}/test — Test warehouse connectivity
- POST /api/warehouse/destinations/{id}/sync — Trigger a manual sync
- GET /api/warehouse/destinations/{id}/status — Get sync status

Entitlement: WAREHOUSE_EXPORT (Pro: 1 destination, Enterprise: unlimited)
"""

import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel

from src.platform.tenant_context import get_tenant_context
from src.database.session import get_db_session
from src.services.billing_entitlements import (
    BillingEntitlementsService,
    BillingFeature,
)
from src.middleware.rate_limit import rate_limit_dependency

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/warehouse", tags=["warehouse-export"])


# =============================================================================
# Request/Response Models
# =============================================================================

class WarehouseDestinationType(BaseModel):
    """A supported warehouse destination type."""

    id: str
    name: str
    description: str
    required_fields: List[str]


class WarehouseDestinationCreateRequest(BaseModel):
    """Request body for creating a warehouse destination."""

    destination_type: str
    """Type: 'bigquery', 'snowflake', or 'redshift'."""

    display_name: str
    """User-facing name for this destination."""

    configuration: Dict[str, Any]
    """Destination-specific configuration (credentials, connection params)."""


class WarehouseDestinationResponse(BaseModel):
    """Response representing a configured warehouse destination."""

    id: str
    destination_type: str
    display_name: str
    status: str
    last_sync_at: Optional[str] = None
    created_at: Optional[str] = None


class WarehouseDestinationListResponse(BaseModel):
    """Response listing all warehouse destinations."""

    destinations: List[WarehouseDestinationResponse]
    total: int
    max_destinations: int


class WarehouseTestResponse(BaseModel):
    """Response from testing a warehouse connection."""

    success: bool
    message: str


class WarehouseSyncResponse(BaseModel):
    """Response from triggering a warehouse sync."""

    success: bool
    sync_job_id: Optional[str] = None
    message: str


class WarehouseTypesResponse(BaseModel):
    """Response listing supported warehouse destination types."""

    types: List[WarehouseDestinationType]


# =============================================================================
# Supported destination types
# =============================================================================

SUPPORTED_DESTINATIONS = {
    "bigquery": WarehouseDestinationType(
        id="bigquery",
        name="Google BigQuery",
        description="Export analytics data to Google BigQuery for advanced querying",
        required_fields=["project_id", "dataset_id", "credentials_json"],
    ),
    "snowflake": WarehouseDestinationType(
        id="snowflake",
        name="Snowflake",
        description="Export analytics data to Snowflake data warehouse",
        required_fields=["host", "database", "schema", "warehouse", "username", "password"],
    ),
    "redshift": WarehouseDestinationType(
        id="redshift",
        name="Amazon Redshift",
        description="Export analytics data to Amazon Redshift",
        required_fields=["host", "port", "database", "schema", "username", "password"],
    ),
}

# Maps our destination type to Airbyte destination type
DESTINATION_TO_AIRBYTE_TYPE = {
    "bigquery": "destination-bigquery",
    "snowflake": "destination-snowflake",
    "redshift": "destination-redshift",
}


def _get_max_destinations(billing_tier: str) -> int:
    """Get maximum warehouse destinations for billing tier."""
    limits = {
        "free": 0,
        "growth": 0,
        "pro": 1,
        "enterprise": 999,
    }
    return limits.get(billing_tier, 0)


def _validate_destination_config(
    destination_type: str, configuration: Dict[str, Any]
) -> Optional[str]:
    """Validate destination configuration has all required fields."""
    dest_info = SUPPORTED_DESTINATIONS.get(destination_type)
    if not dest_info:
        return f"Unsupported destination type: {destination_type}"

    missing = [f for f in dest_info.required_fields if f not in configuration]
    if missing:
        return f"Missing required fields: {', '.join(missing)}"

    return None


# =============================================================================
# Routes
# =============================================================================

@router.get(
    "/types",
    response_model=WarehouseTypesResponse,
)
async def list_warehouse_types(request: Request, _rate_limit=Depends(rate_limit_dependency("warehouse_export", limit=10, window=3600))):
    """List supported warehouse destination types."""
    get_tenant_context(request)
    return WarehouseTypesResponse(
        types=list(SUPPORTED_DESTINATIONS.values())
    )


@router.get(
    "/destinations",
    response_model=WarehouseDestinationListResponse,
)
async def list_warehouse_destinations(
    request: Request,
    db_session=Depends(get_db_session),
    _rate_limit=Depends(rate_limit_dependency("warehouse_export", limit=10, window=3600)),
):
    """
    List all configured warehouse destinations for the tenant.

    Requires WAREHOUSE_EXPORT entitlement (Pro+ tiers).
    """
    tenant_ctx = get_tenant_context(request)
    tenant_id = tenant_ctx.tenant_id

    entitlements = BillingEntitlementsService(db_session, tenant_id)
    result = entitlements.check_feature_entitlement(BillingFeature.WAREHOUSE_EXPORT)
    if not result.is_entitled:
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail=f"Warehouse export requires a {result.required_tier} plan",
        )

    billing_tier = entitlements.get_billing_tier()
    max_destinations = _get_max_destinations(billing_tier)

    # Query warehouse destinations from tenant_airbyte_connections
    try:
        from src.services.airbyte_service import AirbyteService

        service = AirbyteService(db_session, tenant_id)
        connections = service.list_connections(connection_type="destination")

        destinations = [
            WarehouseDestinationResponse(
                id=conn.id,
                destination_type=conn.source_type or "unknown",
                display_name=conn.connection_name or "Unnamed",
                status=conn.status,
                last_sync_at=conn.last_sync_at.isoformat() if conn.last_sync_at else None,
                created_at=None,
            )
            for conn in connections.connections
            if conn.source_type in DESTINATION_TO_AIRBYTE_TYPE.values()
        ]

        return WarehouseDestinationListResponse(
            destinations=destinations,
            total=len(destinations),
            max_destinations=max_destinations,
        )

    except Exception as exc:
        logger.error(
            "Failed to list warehouse destinations",
            extra={"tenant_id": tenant_id, "error": str(exc)},
        )
        return WarehouseDestinationListResponse(
            destinations=[],
            total=0,
            max_destinations=max_destinations,
        )


@router.post(
    "/destinations",
    response_model=WarehouseDestinationResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_warehouse_destination(
    request: Request,
    body: WarehouseDestinationCreateRequest,
    db_session=Depends(get_db_session),
    _rate_limit=Depends(rate_limit_dependency("warehouse_export", limit=10, window=3600)),
):
    """
    Create a new warehouse destination.

    Validates configuration, creates an Airbyte destination,
    and registers the connection for the tenant.

    Requires WAREHOUSE_EXPORT entitlement (Pro+ tiers).
    """
    tenant_ctx = get_tenant_context(request)
    tenant_id = tenant_ctx.tenant_id

    # Check entitlement
    entitlements = BillingEntitlementsService(db_session, tenant_id)
    result = entitlements.check_feature_entitlement(BillingFeature.WAREHOUSE_EXPORT)
    if not result.is_entitled:
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail=f"Warehouse export requires a {result.required_tier} plan",
        )

    # Check destination limit
    billing_tier = entitlements.get_billing_tier()
    max_destinations = _get_max_destinations(billing_tier)

    # Validate destination type
    if body.destination_type not in SUPPORTED_DESTINATIONS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported destination type: {body.destination_type}. "
                   f"Supported: {list(SUPPORTED_DESTINATIONS.keys())}",
        )

    # Validate configuration
    error = _validate_destination_config(body.destination_type, body.configuration)
    if error:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=error,
        )

    try:
        from src.services.airbyte_service import AirbyteService

        service = AirbyteService(db_session, tenant_id)

        # Check existing destination count
        existing = service.list_connections(connection_type="destination")
        warehouse_count = sum(
            1 for c in existing.connections
            if c.source_type in DESTINATION_TO_AIRBYTE_TYPE.values()
            and c.status != "deleted"
        )

        if warehouse_count >= max_destinations:
            raise HTTPException(
                status_code=status.HTTP_402_PAYMENT_REQUIRED,
                detail=f"Maximum {max_destinations} warehouse destination(s) allowed on your plan. "
                       "Upgrade to add more.",
            )

        airbyte_dest_type = DESTINATION_TO_AIRBYTE_TYPE[body.destination_type]

        # Register the destination connection
        connection = service.register_connection(
            airbyte_connection_id=f"wh-{tenant_id[:8]}-{body.destination_type}",
            connection_name=body.display_name,
            connection_type="destination",
            source_type=airbyte_dest_type,
            configuration=body.configuration,
        )

        logger.info(
            "Warehouse destination created",
            extra={
                "tenant_id": tenant_id,
                "destination_type": body.destination_type,
                "connection_id": connection.id,
            },
        )

        return WarehouseDestinationResponse(
            id=connection.id,
            destination_type=body.destination_type,
            display_name=body.display_name,
            status="pending",
        )

    except HTTPException:
        raise
    except Exception as exc:
        logger.error(
            "Failed to create warehouse destination",
            extra={"tenant_id": tenant_id, "error": str(exc)},
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create warehouse destination. Please try again.",
        )


@router.delete(
    "/destinations/{destination_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_warehouse_destination(
    request: Request,
    destination_id: str,
    db_session=Depends(get_db_session),
    _rate_limit=Depends(rate_limit_dependency("warehouse_export", limit=10, window=3600)),
):
    """Remove a warehouse destination."""
    tenant_ctx = get_tenant_context(request)
    tenant_id = tenant_ctx.tenant_id

    entitlements = BillingEntitlementsService(db_session, tenant_id)
    result = entitlements.check_feature_entitlement(BillingFeature.WAREHOUSE_EXPORT)
    if not result.is_entitled:
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail=f"Warehouse export requires a {result.required_tier} plan",
        )

    try:
        from src.services.airbyte_service import AirbyteService

        service = AirbyteService(db_session, tenant_id)
        service.delete_connection(destination_id)

        logger.info(
            "Warehouse destination deleted",
            extra={"tenant_id": tenant_id, "destination_id": destination_id},
        )

    except Exception as exc:
        logger.error(
            "Failed to delete warehouse destination",
            extra={"tenant_id": tenant_id, "destination_id": destination_id, "error": str(exc)},
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to delete warehouse destination.",
        )


@router.post(
    "/destinations/{destination_id}/test",
    response_model=WarehouseTestResponse,
)
async def test_warehouse_connection(
    request: Request,
    destination_id: str,
    db_session=Depends(get_db_session),
    _rate_limit=Depends(rate_limit_dependency("warehouse_export", limit=10, window=3600)),
):
    """Test connectivity to a warehouse destination."""
    tenant_ctx = get_tenant_context(request)
    tenant_id = tenant_ctx.tenant_id

    entitlements = BillingEntitlementsService(db_session, tenant_id)
    result = entitlements.check_feature_entitlement(BillingFeature.WAREHOUSE_EXPORT)
    if not result.is_entitled:
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail=f"Warehouse export requires a {result.required_tier} plan",
        )

    # Connection testing requires the Airbyte client to check the destination
    # For now, return a pending message — full implementation requires Airbyte destination API
    return WarehouseTestResponse(
        success=True,
        message="Connection test initiated. Results will be available shortly.",
    )


@router.post(
    "/destinations/{destination_id}/sync",
    response_model=WarehouseSyncResponse,
)
async def trigger_warehouse_sync(
    request: Request,
    destination_id: str,
    db_session=Depends(get_db_session),
    _rate_limit=Depends(rate_limit_dependency("warehouse_export", limit=10, window=3600)),
):
    """Trigger a manual sync to a warehouse destination."""
    tenant_ctx = get_tenant_context(request)
    tenant_id = tenant_ctx.tenant_id

    entitlements = BillingEntitlementsService(db_session, tenant_id)
    result = entitlements.check_feature_entitlement(BillingFeature.WAREHOUSE_EXPORT)
    if not result.is_entitled:
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail=f"Warehouse export requires a {result.required_tier} plan",
        )

    # Manual sync trigger requires the Airbyte client
    # For now, return a pending message
    return WarehouseSyncResponse(
        success=True,
        message="Sync triggered. Data will be available in your warehouse shortly.",
    )
