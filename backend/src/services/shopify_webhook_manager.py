"""
Shopify Webhook Manager — registers webhook subscriptions via GraphQL Admin API.

Since the app is self-hosted (no Shopify CLI), webhooks must be registered
programmatically after OAuth connect. This service handles that registration.
"""

import logging
import os
from typing import Dict, List, Optional

import httpx

logger = logging.getLogger(__name__)

SHOPIFY_API_VERSION = "2025-01"

# Webhook topics to register and their callback paths
WEBHOOK_SUBSCRIPTIONS = [
    {
        "topic": "ORDERS_CREATE",
        "path": "/api/webhooks/shopify/orders-create",
    },
    {
        "topic": "ORDERS_UPDATED",
        "path": "/api/webhooks/shopify/orders-updated",
    },
]


class ShopifyWebhookManager:
    """Manages Shopify webhook subscriptions via GraphQL Admin API."""

    def __init__(self, shop_domain: str, access_token: str):
        self.shop_domain = shop_domain.replace("https://", "").replace("http://", "").rstrip("/")
        self.access_token = access_token
        self.graphql_url = (
            f"https://{self.shop_domain}/admin/api/{SHOPIFY_API_VERSION}/graphql.json"
        )

    async def _execute_graphql(self, query: str, variables: Optional[Dict] = None) -> Dict:
        """Execute a GraphQL query against Shopify Admin API."""
        payload = {"query": query}
        if variables:
            payload["variables"] = variables

        async with httpx.AsyncClient(
            timeout=httpx.Timeout(connect=10.0, read=30.0, write=30.0, pool=10.0),
            headers={
                "Content-Type": "application/json",
                "X-Shopify-Access-Token": self.access_token,
            },
        ) as client:
            response = await client.post(self.graphql_url, json=payload)
            response.raise_for_status()
            result = response.json()

            if "errors" in result:
                logger.error("GraphQL errors in webhook manager", extra={
                    "shop_domain": self.shop_domain,
                    "errors": result["errors"],
                })

            return result.get("data", {})

    async def register_webhooks(self) -> List[Dict]:
        """
        Register all required webhook subscriptions.

        Returns list of registration results (topic, success, errors).
        """
        base_url = os.getenv(
            "WEBHOOK_BASE_URL",
            os.getenv("APPLICATION_URL", "https://shopify-analytics-app-pmsl.onrender.com"),
        )

        results = []
        for sub in WEBHOOK_SUBSCRIPTIONS:
            callback_url = f"{base_url}{sub['path']}"
            result = await self._register_webhook(sub["topic"], callback_url)
            results.append(result)

        return results

    async def _register_webhook(self, topic: str, callback_url: str) -> Dict:
        """Register a single webhook subscription."""
        mutation = """
        mutation webhookSubscriptionCreate($topic: WebhookSubscriptionTopic!, $webhookSubscription: WebhookSubscriptionInput!) {
            webhookSubscriptionCreate(topic: $topic, webhookSubscription: $webhookSubscription) {
                webhookSubscription {
                    id
                    topic
                    endpoint {
                        __typename
                        ... on WebhookHttpEndpoint {
                            callbackUrl
                        }
                    }
                }
                userErrors {
                    field
                    message
                }
            }
        }
        """

        variables = {
            "topic": topic,
            "webhookSubscription": {
                "callbackUrl": callback_url,
                "format": "JSON",
            },
        }

        try:
            data = await self._execute_graphql(mutation, variables)
            create_data = data.get("webhookSubscriptionCreate", {})
            user_errors = create_data.get("userErrors", [])

            if user_errors:
                # Check if already registered (not a real error)
                already_exists = any(
                    "already" in (e.get("message", "")).lower() for e in user_errors
                )
                if already_exists:
                    logger.info("Webhook already registered", extra={
                        "shop_domain": self.shop_domain,
                        "topic": topic,
                    })
                    return {"topic": topic, "success": True, "already_existed": True}

                logger.warning("Webhook registration errors", extra={
                    "shop_domain": self.shop_domain,
                    "topic": topic,
                    "errors": user_errors,
                })
                return {"topic": topic, "success": False, "errors": user_errors}

            webhook_id = (create_data.get("webhookSubscription") or {}).get("id")
            logger.info("Webhook registered successfully", extra={
                "shop_domain": self.shop_domain,
                "topic": topic,
                "webhook_id": webhook_id,
                "callback_url": callback_url,
            })
            return {"topic": topic, "success": True, "webhook_id": webhook_id}

        except Exception as e:
            logger.error("Failed to register webhook", extra={
                "shop_domain": self.shop_domain,
                "topic": topic,
                "error": str(e),
            })
            return {"topic": topic, "success": False, "error": str(e)}

    async def list_webhooks(self) -> List[Dict]:
        """List all currently registered webhook subscriptions."""
        query = """
        query {
            webhookSubscriptions(first: 25) {
                edges {
                    node {
                        id
                        topic
                        endpoint {
                            __typename
                            ... on WebhookHttpEndpoint {
                                callbackUrl
                            }
                        }
                        createdAt
                    }
                }
            }
        }
        """

        data = await self._execute_graphql(query)
        edges = data.get("webhookSubscriptions", {}).get("edges", [])
        return [edge["node"] for edge in edges]


async def register_webhooks(shop_domain: str, access_token: str) -> List[Dict]:
    """Convenience function to register all webhooks for a shop."""
    manager = ShopifyWebhookManager(shop_domain, access_token)
    return await manager.register_webhooks()
