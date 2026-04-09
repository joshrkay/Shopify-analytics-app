"""
Shopify webhook handlers for billing events.

SECURITY: All webhooks MUST verify HMAC signature before processing.
Shopify signs webhooks with the app's API secret.

Replay protection: Deduplicates using X-Shopify-Webhook-Id header with a
TTL-based in-memory cache (1 hour window). This prevents replayed or
retried webhooks from being processed twice.

Documentation: https://shopify.dev/docs/apps/webhooks/configuration/https
"""

import os
import hmac
import hashlib
import base64
import logging
import threading
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Request, HTTPException, status, Header, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/webhooks/shopify", tags=["webhooks"])

# ---------------------------------------------------------------------------
# Webhook replay protection — deduplication via X-Shopify-Webhook-Id
# ---------------------------------------------------------------------------
_WEBHOOK_ID_TTL_SECONDS = 3600  # 1 hour
_seen_webhook_ids: dict[str, float] = {}  # webhook_id -> timestamp
_seen_lock = threading.Lock()


def _is_duplicate_webhook(webhook_id: str | None) -> bool:
    """Return True if this webhook ID was already processed recently."""
    if not webhook_id:
        return False  # No ID header — fall through to HMAC check

    now = datetime.now(timezone.utc).timestamp()

    with _seen_lock:
        # Evict expired entries (keep lock duration short — dict is small)
        expired = [
            wid for wid, ts in _seen_webhook_ids.items()
            if now - ts > _WEBHOOK_ID_TTL_SECONDS
        ]
        for wid in expired:
            del _seen_webhook_ids[wid]

        if webhook_id in _seen_webhook_ids:
            return True

        _seen_webhook_ids[webhook_id] = now
        return False

# Webhook topics we handle
WEBHOOK_TOPIC_SUBSCRIPTION_UPDATE = "app_subscriptions/update"
WEBHOOK_TOPIC_APP_UNINSTALLED = "app/uninstalled"
WEBHOOK_TOPIC_ORDERS_CREATE = "orders/create"
WEBHOOK_TOPIC_ORDERS_UPDATED = "orders/updated"


class WebhookResponse(BaseModel):
    """Standard webhook response."""
    received: bool = True
    message: str = "Webhook processed"


def verify_shopify_webhook(
    data: bytes,
    hmac_header: str,
    api_secret: str
) -> bool:
    """
    Verify Shopify webhook HMAC signature.

    Shopify signs webhooks using HMAC-SHA256 with the app's API secret.

    Args:
        data: Raw request body bytes
        hmac_header: X-Shopify-Hmac-Sha256 header value
        api_secret: Shopify app API secret

    Returns:
        True if signature is valid, False otherwise
    """
    if not hmac_header or not api_secret:
        return False

    try:
        # Compute HMAC
        computed_hmac = hmac.new(
            api_secret.encode("utf-8"),
            data,
            hashlib.sha256
        )
        computed_digest = base64.b64encode(computed_hmac.digest()).decode("utf-8")

        # Constant-time comparison to prevent timing attacks
        return hmac.compare_digest(computed_digest, hmac_header)
    except Exception as e:
        logger.error("HMAC verification error", extra={"error": str(e)})
        return False


async def get_verified_webhook_body(request: Request) -> tuple[dict, str]:
    """
    Get and verify webhook body with HMAC signature.

    Args:
        request: FastAPI request

    Returns:
        Tuple of (parsed body dict, shop domain)

    Raises:
        HTTPException: If verification fails
    """
    # Replay protection: reject duplicate webhook deliveries
    webhook_id = request.headers.get("X-Shopify-Webhook-Id")
    if _is_duplicate_webhook(webhook_id):
        logger.info("Duplicate webhook rejected", extra={"webhook_id": webhook_id})
        raise HTTPException(
            status_code=status.HTTP_200_OK,
            detail="Already processed",
        )

    # Get HMAC header
    hmac_header = request.headers.get("X-Shopify-Hmac-Sha256")
    if not hmac_header:
        logger.warning("Missing HMAC header in webhook")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing HMAC signature"
        )

    # Get shop domain header
    shop_domain = request.headers.get("X-Shopify-Shop-Domain")
    if not shop_domain:
        logger.warning("Missing shop domain header in webhook")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Missing shop domain"
        )

    # Get API secret
    api_secret = os.getenv("SHOPIFY_API_SECRET")
    if not api_secret:
        logger.error("SHOPIFY_API_SECRET not configured")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Webhook verification not configured"
        )

    # Read raw body for HMAC verification
    body = await request.body()

    # Verify HMAC
    if not verify_shopify_webhook(body, hmac_header, api_secret):
        logger.warning("Invalid webhook HMAC", extra={
            "shop_domain": shop_domain
        })
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid HMAC signature"
        )

    # Parse JSON body
    import json
    try:
        data = json.loads(body)
    except json.JSONDecodeError:
        logger.error("Invalid JSON in webhook body")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid JSON body"
        )

    return data, shop_domain


# Import shared database session dependency
from src.database.session import get_db_session  # noqa: E402


@router.post("/subscription-update", response_model=WebhookResponse)
async def handle_subscription_update(
    request: Request,
    session: Session = Depends(get_db_session),
    x_shopify_topic: Optional[str] = Header(None, alias="X-Shopify-Topic"),
    x_shopify_api_version: Optional[str] = Header(None, alias="X-Shopify-API-Version")
):
    """
    Handle app_subscriptions/update webhook from Shopify.

    This webhook is sent when:
    - Subscription is activated (merchant approves charge)
    - Subscription is cancelled
    - Payment fails and subscription is frozen
    - Subscription is renewed

    SECURITY: Verifies HMAC signature before processing.
    """
    data, shop_domain = await get_verified_webhook_body(request)

    logger.info("Subscription update webhook received", extra={
        "shop_domain": shop_domain,
        "topic": x_shopify_topic,
        "api_version": x_shopify_api_version
    })

    # Extract subscription data
    subscription_gid = data.get("app_subscription", {}).get("admin_graphql_api_id")
    subscription_status = data.get("app_subscription", {}).get("status")

    if not subscription_gid:
        logger.warning("Webhook missing subscription ID", extra={
            "shop_domain": shop_domain,
            "data_keys": list(data.keys())
        })
        return WebhookResponse(message="Missing subscription ID")

    logger.info("Processing subscription update", extra={
        "shop_domain": shop_domain,
        "subscription_gid": subscription_gid,
        "status": subscription_status
    })

    try:
        # Find store by shop domain
        from src.models.store import ShopifyStore
        store = session.query(ShopifyStore).filter(
            ShopifyStore.shop_domain == shop_domain
        ).first()

        if not store:
            logger.warning("Store not found for webhook", extra={
                "shop_domain": shop_domain
            })
            return WebhookResponse(message="Store not found")

        # Process based on status
        from src.services.billing_service import BillingService

        billing_service = BillingService(session, store.tenant_id)

        if subscription_status == "ACTIVE":
            # Subscription activated
            current_period_end = None
            if data.get("app_subscription", {}).get("current_period_end"):
                current_period_end = datetime.fromisoformat(
                    data["app_subscription"]["current_period_end"].replace("Z", "+00:00")
                )

            billing_service.activate_subscription(
                shopify_subscription_id=subscription_gid,
                current_period_end=current_period_end
            )
            logger.info("Subscription activated via webhook", extra={
                "shop_domain": shop_domain,
                "subscription_gid": subscription_gid
            })

        elif subscription_status == "CANCELLED":
            # Subscription cancelled
            billing_service.cancel_subscription(
                shopify_subscription_id=subscription_gid,
                cancelled_at=datetime.now(timezone.utc)
            )
            logger.info("Subscription cancelled via webhook", extra={
                "shop_domain": shop_domain,
                "subscription_gid": subscription_gid
            })

        elif subscription_status == "FROZEN":
            # Payment failed
            billing_service.freeze_subscription(
                shopify_subscription_id=subscription_gid,
                reason="payment_failed"
            )
            logger.warning("Subscription frozen via webhook", extra={
                "shop_domain": shop_domain,
                "subscription_gid": subscription_gid
            })

        elif subscription_status == "DECLINED":
            # Merchant declined charge
            billing_service.cancel_subscription(
                shopify_subscription_id=subscription_gid
            )
            logger.info("Subscription declined via webhook", extra={
                "shop_domain": shop_domain,
                "subscription_gid": subscription_gid
            })

        else:
            logger.info("Unhandled subscription status", extra={
                "shop_domain": shop_domain,
                "status": subscription_status
            })

        return WebhookResponse(message=f"Processed status: {subscription_status}")

    except Exception as e:
        logger.error("Error processing subscription webhook", extra={
            "shop_domain": shop_domain,
            "error": str(e)
        })
        session.rollback()
        # Return 200 to acknowledge receipt (Shopify will retry on 4xx/5xx)
        return WebhookResponse(message=f"Error: {str(e)}")


@router.post("/app-uninstalled", response_model=WebhookResponse)
async def handle_app_uninstalled(
    request: Request,
    session: Session = Depends(get_db_session),
    x_shopify_topic: Optional[str] = Header(None, alias="X-Shopify-Topic")
):
    """
    Handle app/uninstalled webhook from Shopify.

    This webhook is sent when the merchant uninstalls the app.
    We should:
    - Cancel any active subscriptions
    - Mark the store as uninstalled
    - Retain data for potential reinstallation (per GDPR)

    SECURITY: Verifies HMAC signature before processing.
    """
    data, shop_domain = await get_verified_webhook_body(request)

    logger.info("App uninstalled webhook received", extra={
        "shop_domain": shop_domain,
        "topic": x_shopify_topic
    })

    try:
        from src.models.store import ShopifyStore
        from src.models.subscription import Subscription, SubscriptionStatus

        # Find and update store
        store = session.query(ShopifyStore).filter(
            ShopifyStore.shop_domain == shop_domain
        ).first()

        if store:
            store.status = "uninstalled"
            store.uninstalled_at = datetime.now(timezone.utc)
            # Clear access token for security
            store.access_token_encrypted = None

            # Cancel any active subscriptions
            subscriptions = session.query(Subscription).filter(
                Subscription.store_id == store.id,
                Subscription.status.in_([
                    SubscriptionStatus.ACTIVE.value,
                    SubscriptionStatus.PENDING.value,
                    SubscriptionStatus.FROZEN.value
                ])
            ).all()

            for sub in subscriptions:
                sub.status = SubscriptionStatus.CANCELLED.value
                sub.cancelled_at = datetime.now(timezone.utc)

            session.commit()

            logger.info("Store marked as uninstalled", extra={
                "shop_domain": shop_domain,
                "store_id": store.id,
                "subscriptions_cancelled": len(subscriptions)
            })
        else:
            logger.warning("Store not found for uninstall webhook", extra={
                "shop_domain": shop_domain
            })

        return WebhookResponse(message="App uninstalled processed")

    except Exception as e:
        logger.error("Error processing uninstall webhook", extra={
            "shop_domain": shop_domain,
            "error": str(e)
        })
        session.rollback()
        return WebhookResponse(message=f"Error: {str(e)}")


@router.post("/customers-redact", response_model=WebhookResponse)
async def handle_customers_redact(request: Request):
    """
    Handle customers/redact webhook (GDPR compliance).

    Shopify requires apps to handle this mandatory webhook.
    This analytics app stores store-level metrics only, not individual customer PII.
    Customer orders are aggregated into revenue/order metrics without customer identifiers.
    """
    data, shop_domain = await get_verified_webhook_body(request)

    # Extract customer info for audit logging (do not store)
    customer_id = data.get("customer", {}).get("id")

    logger.info("Customers redact webhook processed", extra={
        "shop_domain": shop_domain,
        "customer_id": customer_id,
        "action": "acknowledged",
        "data_stored": "none",
        "reason": "App stores aggregated store-level metrics only, no individual customer PII"
    })

    # GDPR COMPLIANCE NOTE:
    # This app does NOT store individual customer data.
    # All data is aggregated at the store level (order counts, revenue totals).
    # No customer-specific data needs to be deleted.

    return WebhookResponse(message="Customer redact acknowledged - no customer PII stored")


@router.post("/shop-redact", response_model=WebhookResponse)
async def handle_shop_redact(
    request: Request,
    session: Session = Depends(get_db_session)
):
    """
    Handle shop/redact webhook (GDPR compliance).

    Shopify requires apps to handle this mandatory webhook.
    Deletes all data associated with the shop (triggered 48 hours after uninstall).
    """
    data, shop_domain = await get_verified_webhook_body(request)

    logger.info("Shop redact webhook received - initiating data deletion", extra={
        "shop_domain": shop_domain
    })

    try:
        from src.models.store import ShopifyStore
        from src.models.subscription import Subscription
        from src.models.billing_event import BillingEvent
        from src.models.usage import UsageRecord

        # Find the store
        store = session.query(ShopifyStore).filter(
            ShopifyStore.shop_domain == shop_domain
        ).first()

        if store:
            store_id = store.id
            tenant_id = store.tenant_id

            # Delete related records (order matters for foreign keys)
            usage_deleted = session.query(UsageRecord).filter(
                UsageRecord.store_id == store_id
            ).delete(synchronize_session=False)

            billing_events_deleted = session.query(BillingEvent).filter(
                BillingEvent.store_id == store_id
            ).delete(synchronize_session=False)

            subscriptions_deleted = session.query(Subscription).filter(
                Subscription.store_id == store_id
            ).delete(synchronize_session=False)

            # Delete the store itself
            session.delete(store)
            session.commit()

            logger.info("Shop data deleted per GDPR request", extra={
                "shop_domain": shop_domain,
                "store_id": store_id,
                "tenant_id": tenant_id,
                "usage_records_deleted": usage_deleted,
                "billing_events_deleted": billing_events_deleted,
                "subscriptions_deleted": subscriptions_deleted
            })
        else:
            logger.info("Shop not found for redact - may already be deleted", extra={
                "shop_domain": shop_domain
            })

        return WebhookResponse(message="Shop redact completed - all data deleted")

    except Exception as e:
        logger.error("Error processing shop redact webhook", extra={
            "shop_domain": shop_domain,
            "error": str(e)
        })
        session.rollback()
        return WebhookResponse(message=f"Error during shop redact: {str(e)}")


@router.post("/customers-data-request", response_model=WebhookResponse)
async def handle_customers_data_request(request: Request):
    """
    Handle customers/data_request webhook (GDPR compliance).

    Shopify requires apps to handle this mandatory webhook.
    This analytics app stores store-level metrics only, not individual customer data.
    """
    data, shop_domain = await get_verified_webhook_body(request)

    # Extract request details for audit logging
    customer_id = data.get("customer", {}).get("id")
    data_request = data.get("data_request", {})
    request_id = data_request.get("id")

    logger.info("Customers data request webhook processed", extra={
        "shop_domain": shop_domain,
        "customer_id": customer_id,
        "request_id": request_id,
        "action": "acknowledged",
        "data_provided": "none",
        "reason": "App stores aggregated store-level metrics only, no individual customer data"
    })

    # GDPR COMPLIANCE NOTE:
    # This app does NOT store individual customer data.
    # All analytics are aggregated at the store level.
    # There is no customer-specific data to export.
    #
    # Per Shopify guidelines, we acknowledge the request.
    # If we stored customer data, we would POST it to data_request.url

    return WebhookResponse(
        message="Data request acknowledged - no individual customer data stored in this app"
    )


def _extract_utm_from_note_attributes(note_attributes: list) -> dict:
    """Extract UTM parameters from Shopify order note_attributes array.

    Shopify stores UTM params as:
    [{"name": "utm_source", "value": "google"}, ...]
    """
    utm_fields = {}
    if not note_attributes:
        return utm_fields
    for attr in note_attributes:
        name = (attr.get("name") or "").lower()
        value = attr.get("value")
        if name in ("utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content"):
            utm_fields[name] = value
    return utm_fields


@router.post("/orders-create", response_model=WebhookResponse)
async def handle_orders_create(
    request: Request,
    session: Session = Depends(get_db_session),
    x_shopify_topic: Optional[str] = Header(None, alias="X-Shopify-Topic"),
):
    """
    Handle orders/create webhook from Shopify.

    Provides real-time order data (including UTM attribution params)
    without waiting for the 60-minute Airbyte sync cycle.
    """
    data, shop_domain = await get_verified_webhook_body(request)

    logger.info("Order create webhook received", extra={
        "shop_domain": shop_domain,
        "topic": x_shopify_topic,
    })

    try:
        from src.models.store import ShopifyStore
        from src.models.webhook_order_event import WebhookOrderEvent

        # Look up store to get tenant_id
        store = session.query(ShopifyStore).filter(
            ShopifyStore.shop_domain == shop_domain
        ).first()

        if not store:
            logger.warning("Store not found for order webhook", extra={
                "shop_domain": shop_domain,
            })
            return WebhookResponse(message="Store not found")

        # Extract UTM params from note_attributes
        note_attributes = data.get("note_attributes", [])
        utm = _extract_utm_from_note_attributes(note_attributes)

        # Parse order_created_at
        order_created_at = None
        if data.get("created_at"):
            order_created_at = datetime.fromisoformat(
                data["created_at"].replace("Z", "+00:00")
            )

        event = WebhookOrderEvent(
            tenant_id=store.tenant_id,
            shop_domain=shop_domain,
            shopify_order_id=str(data.get("id", "")),
            order_name=data.get("name"),
            order_number=str(data.get("order_number", "")),
            total_price=data.get("total_price"),
            subtotal_price=data.get("subtotal_price"),
            currency=data.get("currency"),
            financial_status=data.get("financial_status"),
            fulfillment_status=data.get("fulfillment_status"),
            utm_source=utm.get("utm_source"),
            utm_medium=utm.get("utm_medium"),
            utm_campaign=utm.get("utm_campaign"),
            utm_term=utm.get("utm_term"),
            utm_content=utm.get("utm_content"),
            note_attributes_json=note_attributes,
            raw_payload=data,
            event_type="created",
            order_created_at=order_created_at,
            received_at=datetime.now(timezone.utc),
        )

        session.add(event)
        session.commit()

        logger.info("Order create event stored", extra={
            "shop_domain": shop_domain,
            "order_name": data.get("name"),
            "has_utm": bool(utm),
        })

        return WebhookResponse(message="Order create processed")

    except Exception as e:
        logger.error("Error processing order create webhook", extra={
            "shop_domain": shop_domain,
            "error": str(e),
        })
        session.rollback()
        return WebhookResponse(message=f"Error: {str(e)}")


@router.post("/orders-updated", response_model=WebhookResponse)
async def handle_orders_updated(
    request: Request,
    session: Session = Depends(get_db_session),
    x_shopify_topic: Optional[str] = Header(None, alias="X-Shopify-Topic"),
):
    """
    Handle orders/updated webhook from Shopify.

    Updates existing order events with new financial/fulfillment status
    (e.g., refunds, cancellations, fulfillment changes).
    """
    data, shop_domain = await get_verified_webhook_body(request)

    logger.info("Order updated webhook received", extra={
        "shop_domain": shop_domain,
        "topic": x_shopify_topic,
    })

    try:
        from src.models.store import ShopifyStore
        from src.models.webhook_order_event import WebhookOrderEvent

        store = session.query(ShopifyStore).filter(
            ShopifyStore.shop_domain == shop_domain
        ).first()

        if not store:
            logger.warning("Store not found for order update webhook", extra={
                "shop_domain": shop_domain,
            })
            return WebhookResponse(message="Store not found")

        shopify_order_id = str(data.get("id", ""))

        # Extract UTM params from note_attributes
        note_attributes = data.get("note_attributes", [])
        utm = _extract_utm_from_note_attributes(note_attributes)

        # Parse order_created_at
        order_created_at = None
        if data.get("created_at"):
            order_created_at = datetime.fromisoformat(
                data["created_at"].replace("Z", "+00:00")
            )

        # Upsert: update existing or insert new
        existing = session.query(WebhookOrderEvent).filter(
            WebhookOrderEvent.tenant_id == store.tenant_id,
            WebhookOrderEvent.shopify_order_id == shopify_order_id,
        ).first()

        if existing:
            existing.total_price = data.get("total_price")
            existing.subtotal_price = data.get("subtotal_price")
            existing.financial_status = data.get("financial_status")
            existing.fulfillment_status = data.get("fulfillment_status")
            existing.raw_payload = data
            existing.event_type = "updated"
            # Preserve original UTM params — don't overwrite if already set
            if not existing.utm_source and utm.get("utm_source"):
                existing.utm_source = utm.get("utm_source")
                existing.utm_medium = utm.get("utm_medium")
                existing.utm_campaign = utm.get("utm_campaign")
                existing.utm_term = utm.get("utm_term")
                existing.utm_content = utm.get("utm_content")
        else:
            event = WebhookOrderEvent(
                tenant_id=store.tenant_id,
                shop_domain=shop_domain,
                shopify_order_id=shopify_order_id,
                order_name=data.get("name"),
                order_number=str(data.get("order_number", "")),
                total_price=data.get("total_price"),
                subtotal_price=data.get("subtotal_price"),
                currency=data.get("currency"),
                financial_status=data.get("financial_status"),
                fulfillment_status=data.get("fulfillment_status"),
                utm_source=utm.get("utm_source"),
                utm_medium=utm.get("utm_medium"),
                utm_campaign=utm.get("utm_campaign"),
                utm_term=utm.get("utm_term"),
                utm_content=utm.get("utm_content"),
                note_attributes_json=note_attributes,
                raw_payload=data,
                event_type="updated",
                order_created_at=order_created_at,
                received_at=datetime.now(timezone.utc),
            )
            session.add(event)

        session.commit()

        logger.info("Order update event stored", extra={
            "shop_domain": shop_domain,
            "order_id": shopify_order_id,
            "financial_status": data.get("financial_status"),
            "is_update": existing is not None,
        })

        return WebhookResponse(message="Order update processed")

    except Exception as e:
        logger.error("Error processing order update webhook", extra={
            "shop_domain": shop_domain,
            "error": str(e),
        })
        session.rollback()
        return WebhookResponse(message=f"Error: {str(e)}")
