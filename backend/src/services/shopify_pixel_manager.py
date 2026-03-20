"""
Shopify Pixel Manager — registers and manages Web Pixels via GraphQL Admin API.

Since the app is self-hosted (no Shopify CLI), Web Pixels must be created
programmatically via the webPixelCreate mutation after OAuth connect.

App pixels run in a sandboxed worker and subscribe to Shopify customer events
(page_viewed, product_viewed, checkout_started, etc.).
"""

import json
import logging
import os
from typing import Any, Dict, Optional

import httpx

logger = logging.getLogger(__name__)

SHOPIFY_API_VERSION = "2025-01"


class ShopifyPixelManager:
    """Manages Shopify Web Pixel registration via GraphQL Admin API."""

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
                logger.error("GraphQL errors in pixel manager", extra={
                    "shop_domain": self.shop_domain,
                    "errors": result["errors"],
                })

            return result.get("data", {})

    async def create_web_pixel(self) -> Dict[str, Any]:
        """
        Create a Web Pixel for this app on the merchant's store.

        The pixel settings include the backend endpoint URL where pixel events
        are sent for processing.

        Returns:
            Dict with pixel_id, success status, and any errors.
        """
        base_url = os.getenv(
            "PIXEL_ENDPOINT_URL",
            os.getenv("APPLICATION_URL", "https://shopify-analytics-app-pmsl.onrender.com"),
        )
        endpoint_url = f"{base_url}/api/pixel/events"

        # Pixel settings are passed as a JSON string
        settings = json.dumps({
            "endpoint_url": endpoint_url,
            "shop_domain": self.shop_domain,
        })

        mutation = """
        mutation webPixelCreate($webPixel: WebPixelInput!) {
            webPixelCreate(webPixel: $webPixel) {
                webPixel {
                    id
                    settings
                }
                userErrors {
                    code
                    field
                    message
                }
            }
        }
        """

        variables = {
            "webPixel": {
                "settings": settings,
            },
        }

        try:
            data = await self._execute_graphql(mutation, variables)
            create_data = data.get("webPixelCreate", {})
            user_errors = create_data.get("userErrors", [])

            if user_errors:
                # Check if pixel already exists for this app
                already_exists = any(
                    "already" in (e.get("message", "")).lower()
                    or e.get("code") == "TAKEN"
                    for e in user_errors
                )
                if already_exists:
                    logger.info("Web pixel already exists", extra={
                        "shop_domain": self.shop_domain,
                    })
                    return {"success": True, "already_existed": True}

                logger.warning("Web pixel creation errors", extra={
                    "shop_domain": self.shop_domain,
                    "errors": user_errors,
                })
                return {"success": False, "errors": user_errors}

            pixel = create_data.get("webPixel", {})
            pixel_id = pixel.get("id")

            logger.info("Web pixel created successfully", extra={
                "shop_domain": self.shop_domain,
                "pixel_id": pixel_id,
                "endpoint_url": endpoint_url,
            })
            return {"success": True, "pixel_id": pixel_id}

        except Exception as e:
            logger.error("Failed to create web pixel", extra={
                "shop_domain": self.shop_domain,
                "error": str(e),
            })
            return {"success": False, "error": str(e)}

    async def get_web_pixel(self) -> Optional[Dict]:
        """Query the existing web pixel for this app."""
        query = """
        query {
            webPixel {
                id
                settings
            }
        }
        """

        try:
            data = await self._execute_graphql(query)
            return data.get("webPixel")
        except Exception as e:
            logger.error("Failed to query web pixel", extra={
                "shop_domain": self.shop_domain,
                "error": str(e),
            })
            return None

    async def delete_web_pixel(self, pixel_id: str) -> bool:
        """Delete a web pixel by ID."""
        mutation = """
        mutation webPixelDelete($id: ID!) {
            webPixelDelete(id: $id) {
                deletedWebPixelId
                userErrors {
                    code
                    field
                    message
                }
            }
        }
        """

        try:
            data = await self._execute_graphql(mutation, {"id": pixel_id})
            delete_data = data.get("webPixelDelete", {})
            user_errors = delete_data.get("userErrors", [])

            if user_errors:
                logger.warning("Web pixel deletion errors", extra={
                    "shop_domain": self.shop_domain,
                    "pixel_id": pixel_id,
                    "errors": user_errors,
                })
                return False

            logger.info("Web pixel deleted", extra={
                "shop_domain": self.shop_domain,
                "pixel_id": pixel_id,
            })
            return True

        except Exception as e:
            logger.error("Failed to delete web pixel", extra={
                "shop_domain": self.shop_domain,
                "error": str(e),
            })
            return False


async def create_web_pixel(shop_domain: str, access_token: str) -> Dict[str, Any]:
    """Convenience function to create a web pixel for a shop."""
    manager = ShopifyPixelManager(shop_domain, access_token)
    return await manager.create_web_pixel()
