"""
Shopify Billing API client for managing recurring subscriptions.

Uses Shopify's GraphQL Admin API for billing operations.
All billing MUST go through Shopify Billing API for public apps.
"""

import os
import hmac
import hashlib
import logging
from typing import Optional, Dict, Any
from dataclasses import dataclass
from datetime import datetime

import httpx

logger = logging.getLogger(__name__)


@dataclass
class ShopifySubscriptionResponse:
    """Response from Shopify subscription API."""
    subscription_id: str
    confirmation_url: Optional[str] = None
    status: Optional[str] = None
    current_period_end: Optional[datetime] = None
    created_at: Optional[datetime] = None
    name: Optional[str] = None
    return_url: Optional[str] = None
    test: bool = False


@dataclass
class ShopifyPlanConfig:
    """Configuration for a Shopify billing plan."""
    name: str
    price: float  # In dollars
    interval: str = "EVERY_30_DAYS"  # or "ANNUAL"
    trial_days: int = 0
    test: bool = False


class ShopifyBillingError(Exception):
    """Error from Shopify Billing API."""

    def __init__(self, message: str, code: Optional[str] = None, details: Optional[Dict] = None):
        super().__init__(message)
        self.code = code
        self.details = details or {}


class ShopifyBillingClient:
    """
    Client for Shopify Billing API (GraphQL Admin API).

    Handles:
    - Creating recurring application charges
    - Querying subscription status
    - Managing subscription lifecycle
    """

    GRAPHQL_API_VERSION = "2024-01"

    def __init__(
        self,
        shop_domain: str,
        access_token: str,
        api_key: Optional[str] = None,
        api_secret: Optional[str] = None,
    ):
        """
        Initialize Shopify Billing client.

        Args:
            shop_domain: The shop's myshopify.com domain (e.g., 'example.myshopify.com')
            access_token: Shop's access token for API calls
            api_key: Shopify app API key (from env if not provided)
            api_secret: Shopify app API secret (from env if not provided)
        """
        self.shop_domain = shop_domain.replace("https://", "").replace("http://", "")
        self.access_token = access_token
        self.api_key = api_key or os.getenv("SHOPIFY_API_KEY")
        self.api_secret = api_secret or os.getenv("SHOPIFY_API_SECRET")

        self.graphql_url = f"https://{self.shop_domain}/admin/api/{self.GRAPHQL_API_VERSION}/graphql.json"

        self._client = httpx.AsyncClient(
            headers={
                "X-Shopify-Access-Token": self.access_token,
                "Content-Type": "application/json",
            },
            timeout=30.0,
        )

    async def close(self):
        """Close the HTTP client."""
        await self._client.aclose()

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.close()

    async def _execute_graphql(self, query: str, variables: Optional[Dict] = None) -> Dict[str, Any]:
        """
        Execute a GraphQL query against Shopify Admin API.

        Args:
            query: GraphQL query string
            variables: Optional variables for the query

        Returns:
            Response data from Shopify

        Raises:
            ShopifyBillingError: If the API call fails
        """
        payload = {"query": query}
        if variables:
            payload["variables"] = variables

        try:
            response = await self._client.post(self.graphql_url, json=payload)
            response.raise_for_status()

            data = response.json()

            if "errors" in data:
                errors = data["errors"]
                error_msg = errors[0].get("message", "Unknown GraphQL error") if errors else "Unknown error"
                logger.error("Shopify GraphQL error", extra={
                    "shop_domain": self.shop_domain,
                    "errors": errors,
                })
                raise ShopifyBillingError(error_msg, details={"errors": errors})

            return data.get("data", {})

        except httpx.HTTPStatusError as e:
            logger.error("Shopify API HTTP error", extra={
                "shop_domain": self.shop_domain,
                "status_code": e.response.status_code,
                "response": e.response.text[:500],
            })
            raise ShopifyBillingError(
                f"Shopify API error: {e.response.status_code}",
                code=str(e.response.status_code),
            )
        except httpx.RequestError as e:
            logger.error("Shopify API request error", extra={
                "shop_domain": self.shop_domain,
                "error": str(e),
            })
            raise ShopifyBillingError(f"Request failed: {str(e)}")

    async def create_subscription(
        self,
        plan: ShopifyPlanConfig,
        return_url: str,
    ) -> ShopifySubscriptionResponse:
        """
        Create a recurring application subscription.

        Args:
            plan: Plan configuration with name, price, interval
            return_url: URL to redirect merchant after approval

        Returns:
            ShopifySubscriptionResponse with confirmation_url for merchant approval
        """
        mutation = """
        mutation appSubscriptionCreate($name: String!, $returnUrl: URL!, $test: Boolean, $lineItems: [AppSubscriptionLineItemInput!]!, $trialDays: Int) {
            appSubscriptionCreate(
                name: $name
                returnUrl: $returnUrl
                test: $test
                trialDays: $trialDays
                lineItems: $lineItems
            ) {
                appSubscription {
                    id
                    name
                    status
                    createdAt
                    currentPeriodEnd
                    test
                }
                confirmationUrl
                userErrors {
                    field
                    message
                }
            }
        }
        """

        variables = {
            "name": plan.name,
            "returnUrl": return_url,
            "test": plan.test,
            "trialDays": plan.trial_days,
            "lineItems": [
                {
                    "plan": {
                        "appRecurringPricingDetails": {
                            "price": {
                                "amount": plan.price,
                                "currencyCode": "USD"
                            },
                            "interval": plan.interval,
                        }
                    }
                }
            ],
        }

        data = await self._execute_graphql(mutation, variables)
        result = data.get("appSubscriptionCreate", {})

        user_errors = result.get("userErrors", [])
        if user_errors:
            error_msg = user_errors[0].get("message", "Subscription creation failed")
            logger.error("Shopify subscription creation failed", extra={
                "shop_domain": self.shop_domain,
                "user_errors": user_errors,
            })
            raise ShopifyBillingError(error_msg, details={"user_errors": user_errors})

        subscription = result.get("appSubscription", {})
        confirmation_url = result.get("confirmationUrl")

        if not subscription or not confirmation_url:
            raise ShopifyBillingError("No subscription returned from Shopify")

        logger.info("Shopify subscription created", extra={
            "shop_domain": self.shop_domain,
            "subscription_id": subscription.get("id"),
            "plan_name": plan.name,
        })

        return ShopifySubscriptionResponse(
            subscription_id=subscription.get("id"),
            confirmation_url=confirmation_url,
            status=subscription.get("status"),
            current_period_end=self._parse_datetime(subscription.get("currentPeriodEnd")),
            created_at=self._parse_datetime(subscription.get("createdAt")),
            name=subscription.get("name"),
            test=subscription.get("test", False),
        )

    async def get_subscription(self, subscription_id: str) -> Optional[ShopifySubscriptionResponse]:
        """
        Get subscription details by ID.

        Args:
            subscription_id: Shopify subscription GID

        Returns:
            ShopifySubscriptionResponse or None if not found
        """
        query = """
        query getSubscription($id: ID!) {
            node(id: $id) {
                ... on AppSubscription {
                    id
                    name
                    status
                    createdAt
                    currentPeriodEnd
                    test
                }
            }
        }
        """

        data = await self._execute_graphql(query, {"id": subscription_id})
        node = data.get("node")

        if not node:
            return None

        return ShopifySubscriptionResponse(
            subscription_id=node.get("id"),
            status=node.get("status"),
            current_period_end=self._parse_datetime(node.get("currentPeriodEnd")),
            created_at=self._parse_datetime(node.get("createdAt")),
            name=node.get("name"),
            test=node.get("test", False),
        )

    async def get_active_subscriptions(self) -> list[ShopifySubscriptionResponse]:
        """
        Get all active subscriptions for the shop.

        Returns:
            List of active subscriptions
        """
        query = """
        query getActiveSubscriptions {
            currentAppInstallation {
                activeSubscriptions {
                    id
                    name
                    status
                    createdAt
                    currentPeriodEnd
                    test
                }
            }
        }
        """

        data = await self._execute_graphql(query)
        installation = data.get("currentAppInstallation", {})
        subscriptions = installation.get("activeSubscriptions", [])

        return [
            ShopifySubscriptionResponse(
                subscription_id=sub.get("id"),
                status=sub.get("status"),
                current_period_end=self._parse_datetime(sub.get("currentPeriodEnd")),
                created_at=self._parse_datetime(sub.get("createdAt")),
                name=sub.get("name"),
                test=sub.get("test", False),
            )
            for sub in subscriptions
        ]

    async def cancel_subscription(self, subscription_id: str) -> bool:
        """
        Cancel an active subscription.

        Args:
            subscription_id: Shopify subscription GID

        Returns:
            True if successfully cancelled
        """
        mutation = """
        mutation appSubscriptionCancel($id: ID!) {
            appSubscriptionCancel(id: $id) {
                appSubscription {
                    id
                    status
                }
                userErrors {
                    field
                    message
                }
            }
        }
        """

        data = await self._execute_graphql(mutation, {"id": subscription_id})
        result = data.get("appSubscriptionCancel", {})

        user_errors = result.get("userErrors", [])
        if user_errors:
            error_msg = user_errors[0].get("message", "Cancellation failed")
            logger.error("Shopify subscription cancellation failed", extra={
                "shop_domain": self.shop_domain,
                "subscription_id": subscription_id,
                "user_errors": user_errors,
            })
            raise ShopifyBillingError(error_msg, details={"user_errors": user_errors})

        subscription = result.get("appSubscription", {})
        logger.info("Shopify subscription cancelled", extra={
            "shop_domain": self.shop_domain,
            "subscription_id": subscription_id,
            "new_status": subscription.get("status"),
        })

        return True

    @staticmethod
    def verify_webhook_signature(
        payload: bytes,
        signature: str,
        secret: Optional[str] = None,
    ) -> bool:
        """
        Verify Shopify webhook HMAC signature.

        Args:
            payload: Raw request body bytes
            signature: X-Shopify-Hmac-Sha256 header value
            secret: Webhook secret (uses SHOPIFY_API_SECRET env var if not provided)

        Returns:
            True if signature is valid
        """
        secret = secret or os.getenv("SHOPIFY_API_SECRET")
        if not secret:
            logger.error("SHOPIFY_API_SECRET not configured for webhook verification")
            return False

        computed_hmac = hmac.new(
            secret.encode("utf-8"),
            payload,
            hashlib.sha256,
        ).digest()

        import base64
        computed_signature = base64.b64encode(computed_hmac).decode("utf-8")

        return hmac.compare_digest(computed_signature, signature)

    @staticmethod
    def _parse_datetime(value: Optional[str]) -> Optional[datetime]:
        """Parse ISO datetime string from Shopify."""
        if not value:
            return None
        try:
            # Handle both formats Shopify might return
            if value.endswith("Z"):
                value = value[:-1] + "+00:00"
            return datetime.fromisoformat(value)
        except (ValueError, TypeError):
            return None
