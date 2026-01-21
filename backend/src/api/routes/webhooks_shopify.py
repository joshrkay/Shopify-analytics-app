"""
Shopify webhook handlers for billing events.

SECURITY:
- All webhooks MUST verify HMAC signature
- No authentication middleware (webhooks are from Shopify, not users)
- tenant_id is derived from shop_domain, never from payload
"""

import logging
import json
from typing import Dict, Any

from fastapi import APIRouter, Request, HTTPException, status, Header

from src.integrations.shopify.billing_client import ShopifyBillingClient
from src.services.billing_service import WebhookProcessor

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/webhooks/shopify", tags=["webhooks"])


async def verify_webhook(request: Request, x_shopify_hmac_sha256: str = Header(...)) -> bytes:
    """
    Verify Shopify webhook HMAC signature.

    Args:
        request: FastAPI request
        x_shopify_hmac_sha256: HMAC signature from header

    Returns:
        Raw request body bytes

    Raises:
        HTTPException: If signature is invalid
    """
    body = await request.body()

    if not ShopifyBillingClient.verify_webhook_signature(body, x_shopify_hmac_sha256):
        logger.warning("Invalid webhook signature", extra={
            "path": request.url.path,
        })
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid webhook signature"
        )

    return body


def get_db_session(request: Request):
    """Get database session from request state."""
    if hasattr(request.app.state, "db_session"):
        return request.app.state.db_session
    raise HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail="Database not configured"
    )


@router.post("/app-subscriptions-update")
async def handle_subscription_update(
    request: Request,
    x_shopify_topic: str = Header(..., alias="X-Shopify-Topic"),
    x_shopify_shop_domain: str = Header(..., alias="X-Shopify-Shop-Domain"),
    x_shopify_hmac_sha256: str = Header(..., alias="X-Shopify-Hmac-Sha256"),
):
    """
    Handle app_subscriptions/update webhook.

    Called when subscription status changes (activated, cancelled, etc).
    """
    # Verify signature
    body = await verify_webhook(request, x_shopify_hmac_sha256)

    try:
        payload = json.loads(body)
    except json.JSONDecodeError:
        logger.error("Invalid webhook JSON payload")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid JSON payload"
        )

    logger.info("Received subscription update webhook", extra={
        "topic": x_shopify_topic,
        "shop_domain": x_shopify_shop_domain,
        "subscription_status": payload.get("app_subscription", {}).get("status"),
    })

    try:
        db_session = get_db_session(request)
        processor = WebhookProcessor(db_session)

        success = processor.process_webhook(
            topic="app_subscriptions/update",
            shop_domain=x_shopify_shop_domain,
            payload=payload,
        )

        if not success:
            logger.warning("Webhook processing returned false", extra={
                "topic": x_shopify_topic,
                "shop_domain": x_shopify_shop_domain,
            })

        return {"status": "processed"}

    except Exception as e:
        logger.error("Failed to process subscription webhook", extra={
            "topic": x_shopify_topic,
            "shop_domain": x_shopify_shop_domain,
            "error": str(e),
        })
        # Return 200 to prevent Shopify retries for processing errors
        # (we've received and logged the webhook)
        return {"status": "error", "message": str(e)}


@router.post("/billing-attempt-success")
async def handle_billing_success(
    request: Request,
    x_shopify_topic: str = Header(..., alias="X-Shopify-Topic"),
    x_shopify_shop_domain: str = Header(..., alias="X-Shopify-Shop-Domain"),
    x_shopify_hmac_sha256: str = Header(..., alias="X-Shopify-Hmac-Sha256"),
):
    """
    Handle subscription_billing_attempts/success webhook.

    Called when a billing attempt succeeds (payment processed).
    """
    body = await verify_webhook(request, x_shopify_hmac_sha256)

    try:
        payload = json.loads(body)
    except json.JSONDecodeError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid JSON payload"
        )

    logger.info("Received billing success webhook", extra={
        "topic": x_shopify_topic,
        "shop_domain": x_shopify_shop_domain,
    })

    try:
        db_session = get_db_session(request)
        processor = WebhookProcessor(db_session)

        processor.process_webhook(
            topic="subscription_billing_attempts/success",
            shop_domain=x_shopify_shop_domain,
            payload=payload,
        )

        return {"status": "processed"}

    except Exception as e:
        logger.error("Failed to process billing success webhook", extra={
            "shop_domain": x_shopify_shop_domain,
            "error": str(e),
        })
        return {"status": "error", "message": str(e)}


@router.post("/billing-attempt-failure")
async def handle_billing_failure(
    request: Request,
    x_shopify_topic: str = Header(..., alias="X-Shopify-Topic"),
    x_shopify_shop_domain: str = Header(..., alias="X-Shopify-Shop-Domain"),
    x_shopify_hmac_sha256: str = Header(..., alias="X-Shopify-Hmac-Sha256"),
):
    """
    Handle subscription_billing_attempts/failure webhook.

    Called when a billing attempt fails (payment declined).
    Immediately downgrades access.
    """
    body = await verify_webhook(request, x_shopify_hmac_sha256)

    try:
        payload = json.loads(body)
    except json.JSONDecodeError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid JSON payload"
        )

    logger.warning("Received billing failure webhook", extra={
        "topic": x_shopify_topic,
        "shop_domain": x_shopify_shop_domain,
    })

    try:
        db_session = get_db_session(request)
        processor = WebhookProcessor(db_session)

        processor.process_webhook(
            topic="subscription_billing_attempts/failure",
            shop_domain=x_shopify_shop_domain,
            payload=payload,
        )

        return {"status": "processed"}

    except Exception as e:
        logger.error("Failed to process billing failure webhook", extra={
            "shop_domain": x_shopify_shop_domain,
            "error": str(e),
        })
        return {"status": "error", "message": str(e)}


@router.post("/app-uninstalled")
async def handle_app_uninstalled(
    request: Request,
    x_shopify_topic: str = Header(..., alias="X-Shopify-Topic"),
    x_shopify_shop_domain: str = Header(..., alias="X-Shopify-Shop-Domain"),
    x_shopify_hmac_sha256: str = Header(..., alias="X-Shopify-Hmac-Sha256"),
):
    """
    Handle app/uninstalled webhook.

    Called when the merchant uninstalls the app.
    Cancels subscription and cleans up store data.
    """
    body = await verify_webhook(request, x_shopify_hmac_sha256)

    try:
        payload = json.loads(body)
    except json.JSONDecodeError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid JSON payload"
        )

    logger.info("Received app uninstalled webhook", extra={
        "topic": x_shopify_topic,
        "shop_domain": x_shopify_shop_domain,
    })

    try:
        db_session = get_db_session(request)

        # Find and update store status
        from src.models.store import ShopifyStore, StoreStatus
        from src.models.subscription import Subscription, SubscriptionStatus
        from src.models.billing_event import BillingEvent, BillingEventType
        import uuid
        from datetime import datetime, timezone

        store = db_session.query(ShopifyStore).filter(
            ShopifyStore.shop_domain == x_shopify_shop_domain,
        ).first()

        if store:
            # Update store status
            store.status = StoreStatus.UNINSTALLED

            # Cancel any active subscriptions
            active_subs = db_session.query(Subscription).filter(
                Subscription.tenant_id == store.tenant_id,
                Subscription.status.in_([
                    SubscriptionStatus.ACTIVE.value,
                    SubscriptionStatus.TRIALING.value,
                ]),
            ).all()

            for sub in active_subs:
                sub.status = SubscriptionStatus.CANCELLED.value
                sub.cancelled_at = datetime.now(timezone.utc)

                # Record cancellation event
                event = BillingEvent(
                    id=str(uuid.uuid4()),
                    tenant_id=store.tenant_id,
                    event_type=BillingEventType.SUBSCRIPTION_CANCELLED.value,
                    subscription_id=sub.id,
                    shopify_subscription_id=sub.shopify_subscription_id,
                    extra_metadata={"reason": "app_uninstalled"},
                )
                db_session.add(event)

            db_session.commit()

            logger.info("App uninstall processed", extra={
                "shop_domain": x_shopify_shop_domain,
                "tenant_id": store.tenant_id,
                "cancelled_subscriptions": len(active_subs),
            })

        return {"status": "processed"}

    except Exception as e:
        logger.error("Failed to process app uninstall webhook", extra={
            "shop_domain": x_shopify_shop_domain,
            "error": str(e),
        })
        return {"status": "error", "message": str(e)}
