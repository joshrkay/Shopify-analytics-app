"""
Subscription reconciliation job.

Runs hourly to sync subscription state with Shopify Billing API.
Ensures subscription status is accurate even if webhooks are missed.
"""

import logging
import asyncio
import uuid
from datetime import datetime, timezone, timedelta
from typing import List, Optional

from sqlalchemy.orm import Session

from src.models.subscription import Subscription, SubscriptionStatus
from src.models.billing_event import BillingEvent, BillingEventType
from src.models.store import ShopifyStore, StoreStatus
from src.integrations.shopify.billing_client import ShopifyBillingClient, ShopifyBillingError

logger = logging.getLogger(__name__)


class SubscriptionReconciliationJob:
    """
    Reconciles local subscription state with Shopify Billing API.

    Should run hourly via cron or task scheduler.
    Handles:
    - Expired subscriptions
    - Status mismatches
    - Grace period expiration
    """

    def __init__(self, db_session: Session):
        """Initialize reconciliation job."""
        self.db_session = db_session

    async def run(self) -> dict:
        """
        Execute the reconciliation job.

        Returns:
            Summary of reconciliation results
        """
        logger.info("Starting subscription reconciliation job")

        results = {
            "started_at": datetime.now(timezone.utc).isoformat(),
            "stores_processed": 0,
            "subscriptions_checked": 0,
            "subscriptions_updated": 0,
            "subscriptions_expired": 0,
            "errors": [],
        }

        try:
            # Get all active stores
            stores = self.db_session.query(ShopifyStore).filter(
                ShopifyStore.status == StoreStatus.ACTIVE,
            ).all()

            results["stores_processed"] = len(stores)

            for store in stores:
                try:
                    await self._reconcile_store(store, results)
                except Exception as e:
                    error_msg = f"Failed to reconcile store {store.shop_domain}: {str(e)}"
                    logger.error(error_msg, extra={
                        "shop_domain": store.shop_domain,
                        "tenant_id": store.tenant_id,
                    })
                    results["errors"].append(error_msg)

            # Check for expired grace periods
            self._expire_grace_periods(results)

            results["completed_at"] = datetime.now(timezone.utc).isoformat()
            logger.info("Subscription reconciliation completed", extra=results)

        except Exception as e:
            logger.error("Reconciliation job failed", extra={"error": str(e)})
            results["errors"].append(str(e))

        return results

    async def _reconcile_store(self, store: ShopifyStore, results: dict) -> None:
        """
        Reconcile subscriptions for a single store.

        Args:
            store: ShopifyStore to reconcile
            results: Results dict to update
        """
        # Get local active subscriptions
        local_subs = self.db_session.query(Subscription).filter(
            Subscription.tenant_id == store.tenant_id,
            Subscription.status.in_([
                SubscriptionStatus.ACTIVE.value,
                SubscriptionStatus.TRIALING.value,
            ]),
        ).all()

        if not local_subs:
            return

        results["subscriptions_checked"] += len(local_subs)

        # Decrypt access token (implementation depends on encryption method)
        access_token = store.access_token_encrypted  # TODO: Add decryption

        try:
            async with ShopifyBillingClient(store.shop_domain, access_token) as client:
                # Get active subscriptions from Shopify
                shopify_subs = await client.get_active_subscriptions()
                shopify_sub_ids = {sub.subscription_id for sub in shopify_subs}

                for local_sub in local_subs:
                    if not local_sub.shopify_subscription_id:
                        continue

                    if local_sub.shopify_subscription_id not in shopify_sub_ids:
                        # Subscription no longer active in Shopify
                        self._handle_subscription_mismatch(local_sub, store.tenant_id)
                        results["subscriptions_updated"] += 1
                    else:
                        # Check for status/period updates
                        for shopify_sub in shopify_subs:
                            if shopify_sub.subscription_id == local_sub.shopify_subscription_id:
                                self._sync_subscription_details(local_sub, shopify_sub)
                                break

        except ShopifyBillingError as e:
            logger.warning("Failed to fetch Shopify subscriptions", extra={
                "shop_domain": store.shop_domain,
                "error": str(e),
            })

    def _handle_subscription_mismatch(self, subscription: Subscription, tenant_id: str) -> None:
        """
        Handle case where local subscription is active but Shopify shows cancelled.

        Args:
            subscription: Local subscription record
            tenant_id: Tenant identifier
        """
        logger.warning("Subscription mismatch detected", extra={
            "tenant_id": tenant_id,
            "subscription_id": subscription.id,
            "shopify_subscription_id": subscription.shopify_subscription_id,
            "local_status": subscription.status,
        })

        old_status = subscription.status
        subscription.status = SubscriptionStatus.CANCELLED.value
        subscription.cancelled_at = datetime.now(timezone.utc)

        # Record reconciliation event
        event = BillingEvent(
            id=str(uuid.uuid4()),
            tenant_id=tenant_id,
            event_type=BillingEventType.SUBSCRIPTION_CANCELLED.value,
            subscription_id=subscription.id,
            shopify_subscription_id=subscription.shopify_subscription_id,
            extra_metadata={
                "old_status": old_status,
                "source": "reconciliation",
                "reason": "not_found_in_shopify",
            },
        )
        self.db_session.add(event)
        self.db_session.commit()

    def _sync_subscription_details(self, local_sub: Subscription, shopify_sub) -> None:
        """
        Sync subscription details from Shopify to local record.

        Args:
            local_sub: Local subscription record
            shopify_sub: Shopify subscription response
        """
        updated = False

        # Update period end if changed
        if shopify_sub.current_period_end and local_sub.current_period_end != shopify_sub.current_period_end:
            local_sub.current_period_end = shopify_sub.current_period_end
            updated = True

        # Update status if needed
        shopify_status_map = {
            "ACTIVE": SubscriptionStatus.ACTIVE.value,
            "CANCELLED": SubscriptionStatus.CANCELLED.value,
            "EXPIRED": SubscriptionStatus.EXPIRED.value,
        }
        mapped_status = shopify_status_map.get(shopify_sub.status)
        if mapped_status and local_sub.status != mapped_status:
            local_sub.status = mapped_status
            updated = True

        if updated:
            self.db_session.commit()

    def _expire_grace_periods(self, results: dict) -> None:
        """
        Expire subscriptions whose grace period has ended.

        Args:
            results: Results dict to update
        """
        now = datetime.now(timezone.utc)

        # Find subscriptions with expired grace periods
        expired_subs = self.db_session.query(Subscription).filter(
            Subscription.status == SubscriptionStatus.ACTIVE.value,
            Subscription.grace_period_ends_on.isnot(None),
            Subscription.grace_period_ends_on < now,
        ).all()

        for sub in expired_subs:
            logger.info("Expiring subscription due to grace period", extra={
                "subscription_id": sub.id,
                "tenant_id": sub.tenant_id,
                "grace_period_ended": sub.grace_period_ends_on.isoformat(),
            })

            sub.status = SubscriptionStatus.EXPIRED.value

            # Record event
            event = BillingEvent(
                id=str(uuid.uuid4()),
                tenant_id=sub.tenant_id,
                event_type=BillingEventType.SUBSCRIPTION_CANCELLED.value,
                subscription_id=sub.id,
                shopify_subscription_id=sub.shopify_subscription_id,
                extra_metadata={
                    "source": "reconciliation",
                    "reason": "grace_period_expired",
                },
            )
            self.db_session.add(event)
            results["subscriptions_expired"] += 1

        if expired_subs:
            self.db_session.commit()


async def run_reconciliation(db_session: Session) -> dict:
    """
    Convenience function to run reconciliation job.

    Args:
        db_session: Database session

    Returns:
        Job results summary
    """
    job = SubscriptionReconciliationJob(db_session)
    return await job.run()


# Entry point for cron/scheduler
if __name__ == "__main__":
    import os
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        print("DATABASE_URL environment variable is required")
        exit(1)

    engine = create_engine(database_url)
    Session = sessionmaker(bind=engine)
    session = Session()

    try:
        results = asyncio.run(run_reconciliation(session))
        print(f"Reconciliation completed: {results}")
    finally:
        session.close()
