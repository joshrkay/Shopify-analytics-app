"""
Billing API routes for subscription management.

All routes require JWT authentication with tenant context.
"""

import logging
from typing import Optional

from fastapi import APIRouter, Request, HTTPException, status, Depends, Query
from pydantic import BaseModel, ConfigDict, Field

from src.platform.tenant_context import get_tenant_context
from src.services.billing_service import (
    BillingService,
    BillingServiceError,
    PlanNotFoundError,
    StoreNotFoundError,
    SubscriptionError
)
from src.entitlements.policy import EntitlementPolicy, BillingState
from src.models.subscription import Subscription
from src.models.billing_event import BillingEvent
from src.services.billing_entitlements import BILLING_TIER_FEATURES, BillingFeature

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/billing", tags=["billing"])


# Request/Response models
class CreateCheckoutRequest(BaseModel):
    """Request to create a checkout URL."""
    plan_id: str = Field(..., description="Plan ID to subscribe to")
    return_url: Optional[str] = Field(None, description="URL to redirect after checkout")
    test_mode: Optional[bool] = Field(False, description="Create test charge (no real money)")


class CheckoutResponse(BaseModel):
    """Response with checkout URL."""
    checkout_url: str
    subscription_id: str
    shopify_subscription_id: Optional[str] = None
    success: bool


class SubscriptionResponse(BaseModel):
    """Current subscription information."""
    subscription_id: Optional[str]
    plan_id: str
    plan_name: str
    status: str
    is_active: bool
    current_period_end: Optional[str]
    trial_end: Optional[str]
    can_access_features: bool
    downgraded_reason: Optional[str] = None


class PlanResponse(BaseModel):
    """Plan information."""
    id: str
    name: str
    display_name: str
    description: Optional[str]
    price_monthly_cents: Optional[int]
    price_yearly_cents: Optional[int]
    is_active: bool


class PlansListResponse(BaseModel):
    """List of available plans."""
    plans: list[PlanResponse]


class CallbackResponse(BaseModel):
    """Response after billing callback."""
    success: bool
    subscription_id: Optional[str]
    status: str
    message: str


# Import shared database session dependency
from src.database.session import get_db_session  # noqa: E402


def get_billing_service(request: Request, db_session=Depends(get_db_session)) -> BillingService:
    """Get billing service with tenant context."""
    tenant_ctx = get_tenant_context(request)
    return BillingService(db_session, tenant_ctx.tenant_id)


@router.post("/checkout", response_model=CheckoutResponse)
async def create_checkout(
    request: Request,
    checkout_request: CreateCheckoutRequest,
    billing_service: BillingService = Depends(get_billing_service)
):
    """
    Create a Shopify Billing checkout URL.

    The merchant will be redirected to Shopify to approve the charge.
    After approval, they are redirected to the return_url with charge status.

    Returns:
        CheckoutResponse with confirmation URL for redirect
    """
    tenant_ctx = get_tenant_context(request)

    logger.info("Creating checkout URL", extra={
        "tenant_id": tenant_ctx.tenant_id,
        "plan_id": checkout_request.plan_id
    })

    try:
        result = await billing_service.create_checkout_url(
            plan_id=checkout_request.plan_id,
            return_url=checkout_request.return_url,
            test_mode=checkout_request.test_mode or False
        )

        return CheckoutResponse(
            checkout_url=result.checkout_url,
            subscription_id=result.subscription_id,
            shopify_subscription_id=result.shopify_subscription_id,
            success=result.success
        )

    except PlanNotFoundError as e:
        logger.warning("Plan not found", extra={
            "tenant_id": tenant_ctx.tenant_id,
            "plan_id": checkout_request.plan_id
        })
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e)
        )
    except StoreNotFoundError as e:
        logger.warning("Store not found", extra={
            "tenant_id": tenant_ctx.tenant_id
        })
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e)
        )
    except SubscriptionError as e:
        logger.error("Subscription error", extra={
            "tenant_id": tenant_ctx.tenant_id,
            "error": str(e)
        })
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except BillingServiceError as e:
        logger.error("Billing service error", extra={
            "tenant_id": tenant_ctx.tenant_id,
            "error": str(e)
        })
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create checkout"
        )


@router.get("/subscription", response_model=SubscriptionResponse)
async def get_subscription(
    request: Request,
    billing_service: BillingService = Depends(get_billing_service)
):
    """
    Get current subscription information.

    Returns subscription status, plan details, and access permissions.
    """
    tenant_ctx = get_tenant_context(request)

    logger.info("Getting subscription info", extra={
        "tenant_id": tenant_ctx.tenant_id
    })

    try:
        info = billing_service.get_subscription_info()

        return SubscriptionResponse(
            subscription_id=info.subscription_id,
            plan_id=info.plan_id,
            plan_name=info.plan_name,
            status=info.status,
            is_active=info.is_active,
            current_period_end=info.current_period_end.isoformat() if info.current_period_end else None,
            trial_end=info.trial_end.isoformat() if info.trial_end else None,
            can_access_features=info.can_access_features,
            downgraded_reason=info.downgraded_reason
        )
    except Exception as e:
        logger.error("Error getting subscription", extra={
            "tenant_id": tenant_ctx.tenant_id,
            "error": str(e)
        })
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get subscription information"
        )


@router.get("/callback")
async def billing_callback(
    request: Request,
    shop: str = Query(..., description="Shop domain"),
    charge_id: Optional[str] = Query(None, description="Shopify charge ID"),
    billing_service: BillingService = Depends(get_billing_service)
):
    """
    Handle callback from Shopify Billing after merchant approval/decline.

    This endpoint is called when the merchant returns from Shopify checkout.
    The charge_id parameter indicates the result of the charge.
    """
    tenant_ctx = get_tenant_context(request)

    logger.info("Billing callback received", extra={
        "tenant_id": tenant_ctx.tenant_id,
        "shop": shop,
        "charge_id": charge_id
    })

    # The actual subscription activation happens via webhooks
    # This callback just confirms the redirect happened

    info = billing_service.get_subscription_info()

    return CallbackResponse(
        success=info.is_active or info.status == "pending",
        subscription_id=info.subscription_id,
        status=info.status,
        message="Subscription processing. Status will be updated via webhook."
    )


@router.get("/plans", response_model=PlansListResponse)
async def list_plans(
    request: Request,
    db_session=Depends(get_db_session)
):
    """
    List all available subscription plans.

    Returns active plans that can be subscribed to.
    """
    from src.models.plan import Plan

    tenant_ctx = get_tenant_context(request)

    logger.info("Listing plans", extra={
        "tenant_id": tenant_ctx.tenant_id
    })

    plans = db_session.query(Plan).filter(Plan.is_active).all()

    return PlansListResponse(
        plans=[
            PlanResponse(
                id=plan.id,
                name=plan.name,
                display_name=plan.display_name,
                description=plan.description,
                price_monthly_cents=plan.price_monthly_cents,
                price_yearly_cents=plan.price_yearly_cents,
                is_active=plan.is_active
            )
            for plan in plans
        ]
    )


@router.post("/cancel")
async def cancel_subscription(
    request: Request,
    billing_service: BillingService = Depends(get_billing_service)
):
    """
    Request subscription cancellation.

    Note: Actual cancellation is processed by Shopify and confirmed via webhook.
    This endpoint initiates the cancellation request.
    """
    tenant_ctx = get_tenant_context(request)

    logger.info("Cancellation requested", extra={
        "tenant_id": tenant_ctx.tenant_id
    })

    info = billing_service.get_subscription_info()

    if not info.subscription_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No active subscription found"
        )

    # For Shopify apps, merchants cancel through Shopify admin
    # We just acknowledge the request
    return {
        "message": "To cancel your subscription, please visit your Shopify admin and manage app subscriptions.",
        "subscription_id": info.subscription_id,
        "current_plan": info.plan_name
    }


class FeatureEntitlementResponse(BaseModel):
    """Feature entitlement information."""
    feature: str
    is_entitled: bool
    billing_state: str
    plan_id: Optional[str]
    plan_name: Optional[str]
    reason: Optional[str] = None
    required_plan: Optional[str] = None
    grace_period_ends_on: Optional[str] = None


class EntitlementsResponse(BaseModel):
    """Complete entitlements information for UI."""
    billing_state: str
    plan_id: Optional[str]
    plan_name: Optional[str]
    features: dict[str, FeatureEntitlementResponse]
    grace_period_days_remaining: Optional[int] = None


@router.get("/entitlements", response_model=EntitlementsResponse)
async def get_entitlements(
    request: Request,
    billing_service: BillingService = Depends(get_billing_service),
    db_session=Depends(get_db_session)
):
    """
    Get current entitlements for the tenant.

    Returns billing state, plan info, and feature entitlements.
    Used by UI to determine what features to show/disable.
    """
    tenant_ctx = get_tenant_context(request)

    logger.info("Getting entitlements", extra={
        "tenant_id": tenant_ctx.tenant_id
    })

    try:
        # Get subscription info
        subscription_info = billing_service.get_subscription_info()
        
        # Get subscription object for policy evaluation
        subscription = db_session.query(Subscription).filter(
            Subscription.tenant_id == tenant_ctx.tenant_id
        ).order_by(Subscription.created_at.desc()).first()
        
        # Create policy and get billing state
        policy = EntitlementPolicy(db_session)
        billing_state = policy.get_billing_state(subscription)
        
        # Calculate grace period days remaining
        grace_period_days_remaining = None
        if billing_state == BillingState.GRACE_PERIOD and subscription and subscription.grace_period_ends_on:
            from datetime import datetime, timezone
            now = datetime.now(timezone.utc)
            delta = subscription.grace_period_ends_on - now
            if delta.total_seconds() > 0:
                grace_period_days_remaining = delta.days + (1 if delta.seconds > 0 else 0)
        
        # Get plan name
        plan_name = subscription_info.plan_name if subscription_info else None
        
        # Build feature entitlements (check common features)
        feature_keys = [
            BillingFeature.AGENCY_ACCESS,
            BillingFeature.ADVANCED_DASHBOARDS,
            BillingFeature.EXPLORE_MODE,
            BillingFeature.DATA_EXPORT,
            BillingFeature.AI_INSIGHTS,
            BillingFeature.AI_ACTIONS,
            BillingFeature.CUSTOM_REPORTS,
        ]

        features = {}
        if subscription is None:
            # No subscription row yet: fall back to static billing-tier matrix
            # so free-tier tenants still get expected baseline feature access.
            tier_features = BILLING_TIER_FEATURES.get(tenant_ctx.billing_tier or 'free', {})
            for feature_key in feature_keys:
                is_enabled = bool(tier_features.get(feature_key, False))
                features[feature_key] = FeatureEntitlementResponse(
                    feature=feature_key,
                    is_entitled=is_enabled,
                    billing_state=billing_state.value,
                    plan_id=subscription_info.plan_id,
                    plan_name=plan_name,
                    reason=None if is_enabled else f"Feature '{feature_key}' not available on {tenant_ctx.billing_tier or 'free'} tier",
                    required_plan='growth' if not is_enabled and feature_key == BillingFeature.CUSTOM_REPORTS else None,
                    grace_period_ends_on=None,
                )
        else:
            for feature_key in feature_keys:
                result = policy.check_feature_entitlement(
                    tenant_id=tenant_ctx.tenant_id,
                    feature=feature_key,
                    subscription=subscription,
                )
                features[feature_key] = FeatureEntitlementResponse(
                    feature=feature_key,
                    is_entitled=result.is_entitled,
                    billing_state=result.billing_state.value,
                    plan_id=result.plan_id,
                    plan_name=plan_name if result.plan_id == subscription_info.plan_id else None,
                    reason=result.reason,
                    required_plan=result.required_plan,
                    grace_period_ends_on=result.grace_period_ends_on.isoformat() if result.grace_period_ends_on else None,
                )
        
        return EntitlementsResponse(
            billing_state=billing_state.value,
            plan_id=subscription_info.plan_id,
            plan_name=plan_name,
            features=features,
            grace_period_days_remaining=grace_period_days_remaining,
        )
    except Exception as e:
        logger.error("Error getting entitlements", extra={
            "tenant_id": tenant_ctx.tenant_id,
            "error": str(e)
        }, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get entitlements"
        )


# =============================================================================
# Invoice, Payment Method, Usage, Plan Change, Cancel (frontend contract)
# =============================================================================


def _to_camel(s: str) -> str:
    """Convert snake_case to camelCase for frontend JSON serialization."""
    parts = s.split("_")
    return parts[0] + "".join(p.capitalize() for p in parts[1:])


class InvoiceResponse(BaseModel):
    """Invoice/billing event record."""
    model_config = ConfigDict(alias_generator=_to_camel, populate_by_name=True)

    id: str
    date: str
    amount: str
    status: str
    download_url: Optional[str] = None


class PaymentMethodResponse(BaseModel):
    """Payment method information."""
    model_config = ConfigDict(alias_generator=_to_camel, populate_by_name=True)

    id: str
    type: str
    last4: str
    brand: Optional[str] = None
    expiry_month: int
    expiry_year: int


class UsageMetricsResponse(BaseModel):
    """Current resource usage for the tenant."""
    model_config = ConfigDict(alias_generator=_to_camel, populate_by_name=True)

    data_sources_used: int
    team_members_used: int
    dashboards_used: int
    storage_used_gb: float
    storage_limit_gb: float
    ai_requests_used: int
    ai_requests_limit: int


class ChangePlanRequest(BaseModel):
    """Request to change subscription plan."""
    model_config = ConfigDict(populate_by_name=True)

    plan_id: str = Field(..., alias="planId")
    interval: str = Field("month")


@router.get("/invoices", response_model=list[InvoiceResponse])
async def get_invoices(
    request: Request,
    db_session=Depends(get_db_session),
):
    """
    Get billing event history as invoices.

    Returns charge and subscription events for the tenant, sorted by date descending.
    """
    tenant_ctx = get_tenant_context(request)

    events = (
        db_session.query(BillingEvent)
        .filter(
            BillingEvent.tenant_id == tenant_ctx.tenant_id,
            BillingEvent.event_type.in_([
                "charge_succeeded",
                "subscription_created",
                "subscription_renewed",
                "plan_changed",
            ]),
        )
        .order_by(BillingEvent.created_at.desc())
        .limit(100)
        .all()
    )

    return [
        InvoiceResponse(
            id=e.id,
            date=e.created_at.isoformat() if e.created_at else "",
            amount=f"${e.amount_cents / 100:.2f}" if e.amount_cents else "$0.00",
            status="paid" if e.event_type in ("charge_succeeded", "subscription_renewed") else "pending",
            download_url=None,
        )
        for e in events
    ]


@router.get("/payment-method", response_model=PaymentMethodResponse)
async def get_payment_method(request: Request):
    """
    Get payment method information.

    Shopify manages payment collection directly — merchants pay through
    their Shopify account. This endpoint returns a placeholder indicating
    payment is managed by Shopify.
    """
    get_tenant_context(request)  # validate auth

    return PaymentMethodResponse(
        id="shopify_managed",
        type="card",
        last4="****",
        brand="Managed by Shopify",
        expiry_month=0,
        expiry_year=0,
    )


@router.get("/usage", response_model=UsageMetricsResponse)
async def get_usage_metrics(
    request: Request,
    db_session=Depends(get_db_session),
):
    """
    Get current resource usage for the tenant.

    Queries actual counts from the database and derives limits from the
    tenant's billing tier.
    """
    tenant_ctx = get_tenant_context(request)

    from src.models.connector_credential import ConnectorCredential
    from src.models.user_tenant_roles import UserTenantRole
    from src.models.custom_dashboard import CustomDashboard

    data_sources = db_session.query(ConnectorCredential).filter(
        ConnectorCredential.tenant_id == tenant_ctx.tenant_id,
    ).count()

    team_members = db_session.query(UserTenantRole).filter(
        UserTenantRole.tenant_id == tenant_ctx.tenant_id,
    ).count()

    dashboards = db_session.query(CustomDashboard).filter(
        CustomDashboard.tenant_id == tenant_ctx.tenant_id,
    ).count()

    # Derive limits from billing tier
    tier = tenant_ctx.billing_tier or "free"
    tier_limits = {
        "free": {"storage_gb": 1.0, "ai_limit": 50},
        "growth": {"storage_gb": 10.0, "ai_limit": 500},
        "pro": {"storage_gb": 50.0, "ai_limit": 5000},
        "enterprise": {"storage_gb": 500.0, "ai_limit": 50000},
    }
    limits = tier_limits.get(tier, tier_limits["free"])

    return UsageMetricsResponse(
        data_sources_used=data_sources,
        team_members_used=team_members,
        dashboards_used=dashboards,
        storage_used_gb=0.0,  # Storage tracking not yet implemented
        storage_limit_gb=limits["storage_gb"],
        ai_requests_used=0,  # AI usage tracking not yet implemented
        ai_requests_limit=limits["ai_limit"],
    )


@router.put("/subscription")
async def change_plan(
    request: Request,
    body: ChangePlanRequest,
    billing_service: BillingService = Depends(get_billing_service),
):
    """
    Change subscription plan (upgrade or downgrade).

    Determines direction based on plan tier comparison and delegates to
    the appropriate billing service method.
    """
    tenant_ctx = get_tenant_context(request)

    logger.info("Plan change requested", extra={
        "tenant_id": tenant_ctx.tenant_id,
        "new_plan_id": body.plan_id,
    })

    try:
        if billing_service.can_upgrade_to(body.plan_id):
            await billing_service.upgrade_subscription(
                new_plan_id=body.plan_id,
            )
        elif billing_service.can_downgrade_to(body.plan_id):
            await billing_service.downgrade_subscription(
                new_plan_id=body.plan_id,
            )
        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cannot change to the requested plan",
            )

        info = billing_service.get_subscription_info()
        return SubscriptionResponse(
            subscription_id=info.subscription_id,
            plan_id=info.plan_id,
            plan_name=info.plan_name,
            status=info.status,
            is_active=info.is_active,
            current_period_end=info.current_period_end.isoformat() if info.current_period_end else None,
            trial_end=info.trial_end.isoformat() if info.trial_end else None,
            can_access_features=info.can_access_features,
        )

    except PlanNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except SubscriptionError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except BillingServiceError as e:
        logger.error("Plan change failed", extra={
            "tenant_id": tenant_ctx.tenant_id, "error": str(e)
        })
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to change plan",
        )


@router.delete("/subscription")
async def delete_subscription(
    request: Request,
    billing_service: BillingService = Depends(get_billing_service),
):
    """
    Cancel subscription (DELETE method).

    Shopify app subscriptions are cancelled through Shopify admin.
    This endpoint acknowledges the request and directs the merchant.
    """
    tenant_ctx = get_tenant_context(request)

    logger.info("Subscription cancellation requested (DELETE)", extra={
        "tenant_id": tenant_ctx.tenant_id,
    })

    info = billing_service.get_subscription_info()

    if not info.subscription_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No active subscription found",
        )

    return {
        "success": True,
        "message": "To cancel your subscription, please visit your Shopify admin and manage app subscriptions.",
        "subscription_id": info.subscription_id,
        "current_plan": info.plan_name,
    }


@router.put("/payment-method")
async def update_payment_method(request: Request):
    """
    Update payment method.

    Shopify manages payment methods directly — merchants cannot update
    payment methods through the app. Returns 400 with guidance.
    """
    get_tenant_context(request)  # validate auth

    raise HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail="Payment methods are managed through your Shopify admin. "
               "Visit Settings > Payments in your Shopify admin to update.",
    )
