"""
Billing API routes for managing Shopify subscriptions.

All routes require tenant context from JWT.
tenant_id is NEVER accepted from request body.
"""

import logging
from typing import Optional, List
from datetime import datetime

from fastapi import APIRouter, Request, HTTPException, status, Depends
from pydantic import BaseModel, Field

from src.platform.tenant_context import get_tenant_context
from src.services.billing_service import BillingService, BillingServiceError

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/billing", tags=["billing"])


# Request/Response Models

class CreateCheckoutRequest(BaseModel):
    """Request to create a checkout URL."""
    plan_id: str = Field(..., description="Plan ID to subscribe to")
    return_url: str = Field(..., description="URL to redirect after checkout")
    shop_domain: str = Field(..., description="Shopify shop domain")
    # Note: access_token should come from stored credentials, not request


class CreateCheckoutResponse(BaseModel):
    """Response with checkout URL."""
    checkout_url: str
    subscription_id: str
    plan_id: str


class SubscriptionResponse(BaseModel):
    """Subscription details response."""
    id: str
    tenant_id: str
    plan_id: str
    plan_name: str
    status: str
    shopify_subscription_id: Optional[str]
    current_period_end: Optional[datetime]
    cancelled_at: Optional[datetime]
    created_at: datetime


class PlanResponse(BaseModel):
    """Plan details response."""
    id: str
    name: str
    display_name: str
    description: Optional[str]
    price_monthly_cents: Optional[int]
    price_yearly_cents: Optional[int]
    is_active: bool


class EntitlementCheckResponse(BaseModel):
    """Entitlement check response."""
    feature_key: str
    has_access: bool
    plan_id: Optional[str]
    plan_name: Optional[str]


# Dependency to get database session
def get_db_session(request: Request):
    """Get database session from request state."""
    if hasattr(request.app.state, "db_session"):
        return request.app.state.db_session
    # For now, raise error - in production, use proper session management
    raise HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail="Database not configured"
    )


@router.get("/plans", response_model=List[PlanResponse])
async def list_plans(request: Request):
    """
    List all available subscription plans.

    Returns active plans that merchants can subscribe to.
    This endpoint does not require tenant context.
    """
    from src.models.plan import Plan

    try:
        db_session = get_db_session(request)
        plans = db_session.query(Plan).filter(Plan.is_active == True).all()

        return [
            PlanResponse(
                id=plan.id,
                name=plan.name,
                display_name=plan.display_name,
                description=plan.description,
                price_monthly_cents=plan.price_monthly_cents,
                price_yearly_cents=plan.price_yearly_cents,
                is_active=plan.is_active,
            )
            for plan in plans
        ]
    except Exception as e:
        logger.error("Failed to list plans", extra={"error": str(e)})
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve plans"
        )


@router.post("/checkout", response_model=CreateCheckoutResponse)
async def create_checkout(request: Request, checkout_request: CreateCheckoutRequest):
    """
    Create a Shopify checkout URL for subscription.

    Redirects the merchant to Shopify to approve the subscription charge.
    tenant_id is extracted from JWT, not from request body.
    """
    tenant_ctx = get_tenant_context(request)

    logger.info("Creating checkout URL", extra={
        "tenant_id": tenant_ctx.tenant_id,
        "plan_id": checkout_request.plan_id,
        "shop_domain": checkout_request.shop_domain,
    })

    try:
        db_session = get_db_session(request)

        # Get shop's access token from store record
        from src.models.store import ShopifyStore
        store = db_session.query(ShopifyStore).filter(
            ShopifyStore.tenant_id == tenant_ctx.tenant_id,
            ShopifyStore.shop_domain == checkout_request.shop_domain,
        ).first()

        if not store:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Store not found for this tenant"
            )

        # Decrypt access token (implementation depends on encryption method)
        access_token = store.access_token_encrypted  # TODO: Add decryption

        billing_service = BillingService(db_session, tenant_ctx.tenant_id)

        result = await billing_service.create_checkout_url(
            plan_id=checkout_request.plan_id,
            return_url=checkout_request.return_url,
            shop_domain=checkout_request.shop_domain,
            access_token=access_token,
        )

        return CreateCheckoutResponse(
            checkout_url=result.checkout_url,
            subscription_id=result.subscription_id,
            plan_id=result.plan_id,
        )

    except BillingServiceError as e:
        logger.warning("Checkout creation failed", extra={
            "tenant_id": tenant_ctx.tenant_id,
            "error": str(e),
        })
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Unexpected error creating checkout", extra={
            "tenant_id": tenant_ctx.tenant_id,
            "error": str(e),
        })
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create checkout"
        )


@router.get("/subscription", response_model=Optional[SubscriptionResponse])
async def get_current_subscription(request: Request):
    """
    Get the current active subscription for the tenant.

    Returns the active or trialing subscription, or null if none exists.
    """
    tenant_ctx = get_tenant_context(request)

    try:
        db_session = get_db_session(request)
        billing_service = BillingService(db_session, tenant_ctx.tenant_id)

        subscription = billing_service.get_subscription()

        if not subscription:
            return None

        return SubscriptionResponse(
            id=subscription.id,
            tenant_id=subscription.tenant_id,
            plan_id=subscription.plan_id,
            plan_name=subscription.plan_name,
            status=subscription.status,
            shopify_subscription_id=subscription.shopify_subscription_id,
            current_period_end=subscription.current_period_end,
            cancelled_at=subscription.cancelled_at,
            created_at=subscription.created_at,
        )

    except Exception as e:
        logger.error("Failed to get subscription", extra={
            "tenant_id": tenant_ctx.tenant_id,
            "error": str(e),
        })
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve subscription"
        )


@router.get("/subscriptions", response_model=List[SubscriptionResponse])
async def list_subscriptions(request: Request):
    """
    List all subscriptions for the tenant (including cancelled).

    Returns subscription history for the tenant.
    """
    tenant_ctx = get_tenant_context(request)

    try:
        db_session = get_db_session(request)
        billing_service = BillingService(db_session, tenant_ctx.tenant_id)

        subscriptions = billing_service.get_all_subscriptions()

        return [
            SubscriptionResponse(
                id=sub.id,
                tenant_id=sub.tenant_id,
                plan_id=sub.plan_id,
                plan_name=sub.plan_name,
                status=sub.status,
                shopify_subscription_id=sub.shopify_subscription_id,
                current_period_end=sub.current_period_end,
                cancelled_at=sub.cancelled_at,
                created_at=sub.created_at,
            )
            for sub in subscriptions
        ]

    except Exception as e:
        logger.error("Failed to list subscriptions", extra={
            "tenant_id": tenant_ctx.tenant_id,
            "error": str(e),
        })
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve subscriptions"
        )


@router.get("/entitlement/{feature_key}", response_model=EntitlementCheckResponse)
async def check_entitlement(request: Request, feature_key: str):
    """
    Check if the tenant has access to a specific feature.

    Used for feature gating based on subscription plan.
    """
    tenant_ctx = get_tenant_context(request)

    try:
        db_session = get_db_session(request)
        billing_service = BillingService(db_session, tenant_ctx.tenant_id)

        has_access = billing_service.check_entitlement(feature_key)
        subscription = billing_service.get_subscription()

        return EntitlementCheckResponse(
            feature_key=feature_key,
            has_access=has_access,
            plan_id=subscription.plan_id if subscription else None,
            plan_name=subscription.plan_name if subscription else None,
        )

    except Exception as e:
        logger.error("Failed to check entitlement", extra={
            "tenant_id": tenant_ctx.tenant_id,
            "feature_key": feature_key,
            "error": str(e),
        })
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to check entitlement"
        )
