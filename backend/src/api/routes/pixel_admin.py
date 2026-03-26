"""
Pixel Admin API — authenticated endpoints for managing Web Pixel registration.

POST   /api/pixel/admin/register   — Register a Web Pixel on the merchant's store
GET    /api/pixel/admin/status     — Check pixel registration status
DELETE /api/pixel/admin/unregister — Remove the Web Pixel from the merchant's store
"""

import logging

from fastapi import APIRouter, HTTPException, Request, Depends, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from src.database.session import get_db_session
from src.platform.tenant_context import get_tenant_context

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/pixel/admin", tags=["pixel-admin"])


class PixelRegistrationResponse(BaseModel):
    success: bool
    pixel_id: str | None = None
    shopify_pixel_gid: str | None = None
    message: str | None = None


class PixelAdminStatusResponse(BaseModel):
    registered: bool
    pixel_id: str | None = None
    shopify_pixel_gid: str | None = None
    shop_domain: str | None = None
    status: str | None = None


@router.post("/register", response_model=PixelRegistrationResponse)
async def register_pixel(
    request: Request,
    db: Session = Depends(get_db_session),
):
    """
    Register a Web Pixel on the authenticated merchant's Shopify store.

    Creates the pixel via Shopify GraphQL Admin API and records the
    registration in pixel_registrations for audit tracking.
    """
    tenant_ctx = get_tenant_context(request)
    tenant_id = tenant_ctx.tenant_id

    from src.models.store import ShopifyStore
    from src.models.pixel_registration import PixelRegistration
    from src.services.shopify_pixel_manager import ShopifyPixelManager

    # Find the merchant's active store
    store = db.query(ShopifyStore).filter(
        ShopifyStore.tenant_id == tenant_id,
        ShopifyStore.status == "active",
    ).first()

    if not store:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No active Shopify store found for this tenant",
        )

    if not store.access_token:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Store access token not available. Re-authorize the app.",
        )

    # Check for existing active registration
    existing = db.query(PixelRegistration).filter(
        PixelRegistration.tenant_id == tenant_id,
        PixelRegistration.shop_domain == store.shop_domain,
        PixelRegistration.status == "active",
    ).first()

    if existing:
        return PixelRegistrationResponse(
            success=True,
            pixel_id=existing.pixel_id,
            shopify_pixel_gid=existing.shopify_pixel_gid,
            message="Pixel already registered",
        )

    # Register pixel via Shopify GraphQL API
    manager = ShopifyPixelManager(store.shop_domain, store.access_token)
    result = await manager.create_web_pixel()

    if not result.get("success"):
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Failed to register pixel with Shopify: {result.get('errors') or result.get('error')}",
        )

    # Record the registration
    pixel_gid = result.get("pixel_id")
    registration = PixelRegistration(
        tenant_id=tenant_id,
        shop_domain=store.shop_domain,
        pixel_id=pixel_gid,
        shopify_pixel_gid=pixel_gid,
        status="active",
    )
    db.add(registration)
    db.commit()

    logger.info("Pixel registered", extra={
        "tenant_id": tenant_id,
        "shop_domain": store.shop_domain,
        "pixel_gid": pixel_gid,
    })

    return PixelRegistrationResponse(
        success=True,
        pixel_id=pixel_gid,
        shopify_pixel_gid=pixel_gid,
        message="Pixel registered successfully",
    )


@router.get("/status", response_model=PixelAdminStatusResponse)
async def get_pixel_admin_status(
    request: Request,
    db: Session = Depends(get_db_session),
):
    """Check the pixel registration status for the authenticated merchant."""
    tenant_ctx = get_tenant_context(request)
    tenant_id = tenant_ctx.tenant_id

    from src.models.pixel_registration import PixelRegistration

    registration = db.query(PixelRegistration).filter(
        PixelRegistration.tenant_id == tenant_id,
        PixelRegistration.status == "active",
    ).first()

    if not registration:
        return PixelAdminStatusResponse(registered=False)

    return PixelAdminStatusResponse(
        registered=True,
        pixel_id=registration.pixel_id,
        shopify_pixel_gid=registration.shopify_pixel_gid,
        shop_domain=registration.shop_domain,
        status=registration.status,
    )


@router.delete("/unregister", response_model=PixelRegistrationResponse)
async def unregister_pixel(
    request: Request,
    db: Session = Depends(get_db_session),
):
    """
    Remove the Web Pixel from the merchant's Shopify store.

    Calls Shopify's webPixelDelete mutation and marks the registration as deleted.
    """
    tenant_ctx = get_tenant_context(request)
    tenant_id = tenant_ctx.tenant_id

    from src.models.store import ShopifyStore
    from src.models.pixel_registration import PixelRegistration
    from src.services.shopify_pixel_manager import ShopifyPixelManager

    registration = db.query(PixelRegistration).filter(
        PixelRegistration.tenant_id == tenant_id,
        PixelRegistration.status == "active",
    ).first()

    if not registration:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No active pixel registration found",
        )

    # Get store for access token
    store = db.query(ShopifyStore).filter(
        ShopifyStore.tenant_id == tenant_id,
        ShopifyStore.shop_domain == registration.shop_domain,
    ).first()

    if store and store.access_token and registration.shopify_pixel_gid:
        manager = ShopifyPixelManager(store.shop_domain, store.access_token)
        deleted = await manager.delete_web_pixel(registration.shopify_pixel_gid)
        if not deleted:
            logger.warning("Shopify pixel deletion returned errors", extra={
                "tenant_id": tenant_id,
                "pixel_gid": registration.shopify_pixel_gid,
            })

    registration.status = "deleted"
    db.commit()

    logger.info("Pixel unregistered", extra={
        "tenant_id": tenant_id,
        "shop_domain": registration.shop_domain,
    })

    return PixelRegistrationResponse(
        success=True,
        message="Pixel unregistered successfully",
    )
