"""
Shopify API Visual Tests.

Tests Shopify GraphQL Admin API and REST API endpoints with real credentials.
Generates visual output for manual verification.
"""

import logging
import time
from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
from typing import Optional, List, Dict, Any

import httpx

from src.tests.e2e.visual.run_visual_tests import TestResult, TestStatus

logger = logging.getLogger(__name__)

# Shopify API Version
SHOPIFY_API_VERSION = "2024-01"


class ShopifyVisualTests:
    """Visual tests for Shopify API integration."""

    def __init__(
        self,
        shop_domain: str,
        access_token: str,
        api_version: str = SHOPIFY_API_VERSION,
    ):
        self.shop_domain = shop_domain.replace("https://", "").replace("http://", "")
        self.access_token = access_token
        self.api_version = api_version
        self.base_url = f"https://{self.shop_domain}/admin/api/{api_version}"
        self.graphql_url = f"https://{self.shop_domain}/admin/api/{api_version}/graphql.json"

        self.headers = {
            "X-Shopify-Access-Token": access_token,
            "Content-Type": "application/json",
        }

    async def run_all_tests(self) -> List[TestResult]:
        """Run all Shopify API visual tests."""
        tests = [
            ("Shop Information", self.test_shop_info),
            ("Products List", self.test_products),
            ("Orders List", self.test_orders),
            ("Customers List", self.test_customers),
            ("Inventory Levels", self.test_inventory),
            ("GraphQL Query", self.test_graphql),
            ("Webhook Subscriptions", self.test_webhooks),
        ]

        results = []
        async with httpx.AsyncClient(timeout=30.0) as client:
            self.client = client

            for name, test_func in tests:
                logger.info(f"Running Shopify test: {name}")
                start = time.time()
                try:
                    result = await test_func()
                    result.duration_ms = (time.time() - start) * 1000
                    results.append(result)
                except Exception as e:
                    logger.error(f"Test {name} failed with error: {e}")
                    results.append(TestResult(
                        name=name,
                        status=TestStatus.ERROR,
                        duration_ms=(time.time() - start) * 1000,
                        error=str(e),
                    ))

        return results

    async def test_shop_info(self) -> TestResult:
        """Test fetching shop information."""
        response = await self.client.get(
            f"{self.base_url}/shop.json",
            headers=self.headers,
        )

        if response.status_code != 200:
            return TestResult(
                name="Shop Information",
                status=TestStatus.FAILED,
                error=f"HTTP {response.status_code}: {response.text[:200]}",
            )

        data = response.json()
        shop = data.get("shop", {})

        return TestResult(
            name="Shop Information",
            status=TestStatus.PASSED,
            message=f"Successfully retrieved shop: {shop.get('name')}",
            data={
                "shop_name": shop.get("name"),
                "shop_domain": shop.get("domain"),
                "shop_email": shop.get("email"),
                "currency": shop.get("currency"),
                "country": shop.get("country_name"),
                "timezone": shop.get("timezone"),
                "plan_name": shop.get("plan_name"),
                "created_at": shop.get("created_at"),
            },
        )

    async def test_products(self) -> TestResult:
        """Test fetching products."""
        response = await self.client.get(
            f"{self.base_url}/products.json",
            headers=self.headers,
            params={"limit": 10},
        )

        if response.status_code != 200:
            return TestResult(
                name="Products List",
                status=TestStatus.FAILED,
                error=f"HTTP {response.status_code}: {response.text[:200]}",
            )

        data = response.json()
        products = data.get("products", [])

        product_summaries = []
        for p in products[:5]:  # Show first 5
            product_summaries.append({
                "id": p.get("id"),
                "title": p.get("title"),
                "vendor": p.get("vendor"),
                "product_type": p.get("product_type"),
                "status": p.get("status"),
                "variants_count": len(p.get("variants", [])),
                "created_at": p.get("created_at"),
            })

        return TestResult(
            name="Products List",
            status=TestStatus.PASSED,
            message=f"Found {len(products)} products (showing first 5)",
            data={
                "total_fetched": len(products),
                "products": product_summaries,
            },
        )

    async def test_orders(self) -> TestResult:
        """Test fetching orders."""
        # Get orders from last 30 days
        since_date = (datetime.now(timezone.utc) - timedelta(days=30)).strftime("%Y-%m-%d")

        response = await self.client.get(
            f"{self.base_url}/orders.json",
            headers=self.headers,
            params={
                "limit": 10,
                "status": "any",
                "created_at_min": since_date,
            },
        )

        if response.status_code != 200:
            return TestResult(
                name="Orders List",
                status=TestStatus.FAILED,
                error=f"HTTP {response.status_code}: {response.text[:200]}",
            )

        data = response.json()
        orders = data.get("orders", [])

        order_summaries = []
        for o in orders[:5]:  # Show first 5
            order_summaries.append({
                "id": o.get("id"),
                "order_number": o.get("order_number"),
                "total_price": o.get("total_price"),
                "currency": o.get("currency"),
                "financial_status": o.get("financial_status"),
                "fulfillment_status": o.get("fulfillment_status"),
                "line_items_count": len(o.get("line_items", [])),
                "created_at": o.get("created_at"),
            })

        return TestResult(
            name="Orders List",
            status=TestStatus.PASSED,
            message=f"Found {len(orders)} orders in last 30 days (showing first 5)",
            data={
                "total_fetched": len(orders),
                "date_range": f"Since {since_date}",
                "orders": order_summaries,
            },
        )

    async def test_customers(self) -> TestResult:
        """Test fetching customers."""
        response = await self.client.get(
            f"{self.base_url}/customers.json",
            headers=self.headers,
            params={"limit": 10},
        )

        if response.status_code != 200:
            return TestResult(
                name="Customers List",
                status=TestStatus.FAILED,
                error=f"HTTP {response.status_code}: {response.text[:200]}",
            )

        data = response.json()
        customers = data.get("customers", [])

        customer_summaries = []
        for c in customers[:5]:  # Show first 5
            customer_summaries.append({
                "id": c.get("id"),
                "email": c.get("email", "")[:5] + "***" if c.get("email") else None,  # Partial mask
                "first_name": c.get("first_name"),
                "orders_count": c.get("orders_count"),
                "total_spent": c.get("total_spent"),
                "state": c.get("state"),
                "created_at": c.get("created_at"),
            })

        return TestResult(
            name="Customers List",
            status=TestStatus.PASSED,
            message=f"Found {len(customers)} customers (showing first 5)",
            data={
                "total_fetched": len(customers),
                "customers": customer_summaries,
            },
        )

    async def test_inventory(self) -> TestResult:
        """Test fetching inventory levels."""
        # First get locations
        locations_response = await self.client.get(
            f"{self.base_url}/locations.json",
            headers=self.headers,
        )

        if locations_response.status_code != 200:
            return TestResult(
                name="Inventory Levels",
                status=TestStatus.FAILED,
                error=f"Failed to get locations: HTTP {locations_response.status_code}",
            )

        locations = locations_response.json().get("locations", [])
        if not locations:
            return TestResult(
                name="Inventory Levels",
                status=TestStatus.PASSED,
                message="No inventory locations found",
                data={"locations": []},
            )

        location_id = locations[0].get("id")

        # Get inventory levels for first location
        inventory_response = await self.client.get(
            f"{self.base_url}/inventory_levels.json",
            headers=self.headers,
            params={
                "location_ids": location_id,
                "limit": 10,
            },
        )

        if inventory_response.status_code != 200:
            return TestResult(
                name="Inventory Levels",
                status=TestStatus.FAILED,
                error=f"HTTP {inventory_response.status_code}: {inventory_response.text[:200]}",
            )

        data = inventory_response.json()
        levels = data.get("inventory_levels", [])

        return TestResult(
            name="Inventory Levels",
            status=TestStatus.PASSED,
            message=f"Found {len(levels)} inventory levels at {len(locations)} location(s)",
            data={
                "locations_count": len(locations),
                "first_location": locations[0].get("name") if locations else None,
                "inventory_levels_count": len(levels),
                "sample_levels": levels[:5],
            },
        )

    async def test_graphql(self) -> TestResult:
        """Test GraphQL Admin API."""
        query = """
        {
            shop {
                name
                currencyCode
                primaryDomain {
                    url
                    host
                }
                plan {
                    displayName
                    partnerDevelopment
                    shopifyPlus
                }
            }
            products(first: 3) {
                edges {
                    node {
                        id
                        title
                        status
                        totalInventory
                    }
                }
            }
        }
        """

        response = await self.client.post(
            self.graphql_url,
            headers=self.headers,
            json={"query": query},
        )

        if response.status_code != 200:
            return TestResult(
                name="GraphQL Query",
                status=TestStatus.FAILED,
                error=f"HTTP {response.status_code}: {response.text[:200]}",
            )

        data = response.json()

        if "errors" in data:
            return TestResult(
                name="GraphQL Query",
                status=TestStatus.FAILED,
                error=f"GraphQL errors: {data['errors']}",
            )

        shop_data = data.get("data", {}).get("shop", {})
        products_data = data.get("data", {}).get("products", {}).get("edges", [])

        return TestResult(
            name="GraphQL Query",
            status=TestStatus.PASSED,
            message=f"GraphQL query successful - Shop: {shop_data.get('name')}",
            data={
                "shop": {
                    "name": shop_data.get("name"),
                    "currency": shop_data.get("currencyCode"),
                    "domain": shop_data.get("primaryDomain", {}).get("host"),
                    "plan": shop_data.get("plan", {}).get("displayName"),
                },
                "products_sample": [
                    {
                        "id": p["node"]["id"],
                        "title": p["node"]["title"],
                        "status": p["node"]["status"],
                        "inventory": p["node"]["totalInventory"],
                    }
                    for p in products_data
                ],
            },
        )

    async def test_webhooks(self) -> TestResult:
        """Test webhook subscriptions."""
        response = await self.client.get(
            f"{self.base_url}/webhooks.json",
            headers=self.headers,
        )

        if response.status_code != 200:
            return TestResult(
                name="Webhook Subscriptions",
                status=TestStatus.FAILED,
                error=f"HTTP {response.status_code}: {response.text[:200]}",
            )

        data = response.json()
        webhooks = data.get("webhooks", [])

        webhook_summaries = []
        for w in webhooks:
            webhook_summaries.append({
                "id": w.get("id"),
                "topic": w.get("topic"),
                "address": w.get("address", "")[:50] + "..." if len(w.get("address", "")) > 50 else w.get("address"),
                "format": w.get("format"),
                "created_at": w.get("created_at"),
            })

        return TestResult(
            name="Webhook Subscriptions",
            status=TestStatus.PASSED,
            message=f"Found {len(webhooks)} registered webhooks",
            data={
                "webhooks_count": len(webhooks),
                "webhooks": webhook_summaries,
            },
        )
