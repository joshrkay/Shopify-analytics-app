"""
Google Ads API Visual Tests.

Tests Google Ads API endpoints with real credentials.
Generates visual output for manual verification.

API Documentation: https://developers.google.com/google-ads/api/docs/start
"""

import logging
import time
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any

import httpx

from src.tests.e2e.visual.run_visual_tests import TestResult, TestStatus

logger = logging.getLogger(__name__)

# Google Ads API Version
GOOGLE_ADS_API_VERSION = "v16"
GOOGLE_ADS_BASE_URL = f"https://googleads.googleapis.com/{GOOGLE_ADS_API_VERSION}"
GOOGLE_OAUTH_TOKEN_URL = "https://oauth2.googleapis.com/token"


class GoogleAdsVisualTests:
    """Visual tests for Google Ads API integration."""

    def __init__(
        self,
        client_id: str,
        client_secret: str,
        refresh_token: str,
        developer_token: str,
        customer_id: str,
        login_customer_id: Optional[str] = None,
    ):
        self.client_id = client_id
        self.client_secret = client_secret
        self.refresh_token = refresh_token
        self.developer_token = developer_token
        # Remove hyphens from customer ID
        self.customer_id = customer_id.replace("-", "")
        self.login_customer_id = login_customer_id.replace("-", "") if login_customer_id else self.customer_id

        self.access_token: Optional[str] = None

    async def _get_access_token(self) -> str:
        """Get OAuth access token from refresh token."""
        if self.access_token:
            return self.access_token

        async with httpx.AsyncClient() as client:
            response = await client.post(
                GOOGLE_OAUTH_TOKEN_URL,
                data={
                    "client_id": self.client_id,
                    "client_secret": self.client_secret,
                    "refresh_token": self.refresh_token,
                    "grant_type": "refresh_token",
                },
            )

            if response.status_code != 200:
                raise Exception(f"Failed to get access token: {response.text}")

            data = response.json()
            self.access_token = data["access_token"]
            return self.access_token

    def _get_headers(self) -> Dict[str, str]:
        """Get request headers for Google Ads API."""
        return {
            "Authorization": f"Bearer {self.access_token}",
            "developer-token": self.developer_token,
            "login-customer-id": self.login_customer_id,
            "Content-Type": "application/json",
        }

    async def _execute_query(self, query: str) -> Dict[str, Any]:
        """Execute a Google Ads Query Language (GAQL) query."""
        url = f"{GOOGLE_ADS_BASE_URL}/customers/{self.customer_id}/googleAds:searchStream"

        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                url,
                headers=self._get_headers(),
                json={"query": query},
            )

            if response.status_code != 200:
                error_text = response.text
                try:
                    error_data = response.json()
                    if "error" in error_data:
                        error_text = error_data["error"].get("message", error_text)
                except Exception:
                    pass
                raise Exception(f"Query failed: HTTP {response.status_code}: {error_text}")

            # Parse streaming response (NDJSON format)
            results = []
            for line in response.text.strip().split("\n"):
                if line:
                    import json
                    data = json.loads(line)
                    if "results" in data:
                        results.extend(data["results"])

            return {"results": results}

    async def run_all_tests(self) -> List[TestResult]:
        """Run all Google Ads API visual tests."""
        # First, get access token
        try:
            await self._get_access_token()
        except Exception as e:
            return [TestResult(
                name="OAuth Authentication",
                status=TestStatus.ERROR,
                error=f"Failed to authenticate: {str(e)}",
            )]

        tests = [
            ("Customer Info", self.test_customer_info),
            ("Campaigns List", self.test_campaigns),
            ("Ad Groups List", self.test_ad_groups),
            ("Ads List", self.test_ads),
            ("Keywords List", self.test_keywords),
            ("Account Performance", self.test_performance),
            ("Conversion Actions", self.test_conversions),
        ]

        results = []
        for name, test_func in tests:
            logger.info(f"Running Google Ads test: {name}")
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

    async def test_customer_info(self) -> TestResult:
        """Test fetching customer (account) information."""
        query = """
            SELECT
                customer.id,
                customer.descriptive_name,
                customer.currency_code,
                customer.time_zone,
                customer.manager,
                customer.test_account,
                customer.status
            FROM customer
            LIMIT 1
        """

        try:
            data = await self._execute_query(query)
            results = data.get("results", [])

            if not results:
                return TestResult(
                    name="Customer Info",
                    status=TestStatus.FAILED,
                    error="No customer data returned",
                )

            customer = results[0].get("customer", {})

            # Map status
            status_map = {
                "ENABLED": "ENABLED",
                "CANCELED": "CANCELED",
                "SUSPENDED": "SUSPENDED",
                "CLOSED": "CLOSED",
            }

            return TestResult(
                name="Customer Info",
                status=TestStatus.PASSED,
                message=f"Successfully retrieved customer: {customer.get('descriptiveName')}",
                data={
                    "customer_id": customer.get("id"),
                    "name": customer.get("descriptiveName"),
                    "currency": customer.get("currencyCode"),
                    "timezone": customer.get("timeZone"),
                    "is_manager": customer.get("manager"),
                    "is_test_account": customer.get("testAccount"),
                    "status": customer.get("status"),
                },
            )
        except Exception as e:
            return TestResult(
                name="Customer Info",
                status=TestStatus.FAILED,
                error=str(e),
            )

    async def test_campaigns(self) -> TestResult:
        """Test fetching campaigns."""
        query = """
            SELECT
                campaign.id,
                campaign.name,
                campaign.status,
                campaign.advertising_channel_type,
                campaign.start_date,
                campaign.end_date,
                campaign_budget.amount_micros
            FROM campaign
            ORDER BY campaign.id
            LIMIT 10
        """

        try:
            data = await self._execute_query(query)
            results = data.get("results", [])

            campaign_summaries = []
            for r in results[:5]:  # Show first 5
                campaign = r.get("campaign", {})
                budget = r.get("campaignBudget", {})
                campaign_summaries.append({
                    "id": campaign.get("id"),
                    "name": campaign.get("name"),
                    "status": campaign.get("status"),
                    "channel_type": campaign.get("advertisingChannelType"),
                    "start_date": campaign.get("startDate"),
                    "end_date": campaign.get("endDate"),
                    "budget_micros": budget.get("amountMicros"),
                })

            return TestResult(
                name="Campaigns List",
                status=TestStatus.PASSED,
                message=f"Found {len(results)} campaigns (showing first 5)",
                data={
                    "total_fetched": len(results),
                    "campaigns": campaign_summaries,
                },
            )
        except Exception as e:
            return TestResult(
                name="Campaigns List",
                status=TestStatus.FAILED,
                error=str(e),
            )

    async def test_ad_groups(self) -> TestResult:
        """Test fetching ad groups."""
        query = """
            SELECT
                ad_group.id,
                ad_group.name,
                ad_group.status,
                ad_group.type,
                campaign.id,
                campaign.name
            FROM ad_group
            ORDER BY ad_group.id
            LIMIT 10
        """

        try:
            data = await self._execute_query(query)
            results = data.get("results", [])

            ad_group_summaries = []
            for r in results[:5]:  # Show first 5
                ad_group = r.get("adGroup", {})
                campaign = r.get("campaign", {})
                ad_group_summaries.append({
                    "id": ad_group.get("id"),
                    "name": ad_group.get("name"),
                    "status": ad_group.get("status"),
                    "type": ad_group.get("type"),
                    "campaign_id": campaign.get("id"),
                    "campaign_name": campaign.get("name"),
                })

            return TestResult(
                name="Ad Groups List",
                status=TestStatus.PASSED,
                message=f"Found {len(results)} ad groups (showing first 5)",
                data={
                    "total_fetched": len(results),
                    "ad_groups": ad_group_summaries,
                },
            )
        except Exception as e:
            return TestResult(
                name="Ad Groups List",
                status=TestStatus.FAILED,
                error=str(e),
            )

    async def test_ads(self) -> TestResult:
        """Test fetching ads."""
        query = """
            SELECT
                ad_group_ad.ad.id,
                ad_group_ad.ad.type,
                ad_group_ad.status,
                ad_group_ad.ad.name,
                ad_group_ad.ad.final_urls,
                ad_group.id,
                ad_group.name,
                campaign.id
            FROM ad_group_ad
            ORDER BY ad_group_ad.ad.id
            LIMIT 10
        """

        try:
            data = await self._execute_query(query)
            results = data.get("results", [])

            ad_summaries = []
            for r in results[:5]:  # Show first 5
                ad_group_ad = r.get("adGroupAd", {})
                ad = ad_group_ad.get("ad", {})
                ad_group = r.get("adGroup", {})
                campaign = r.get("campaign", {})
                ad_summaries.append({
                    "id": ad.get("id"),
                    "name": ad.get("name"),
                    "type": ad.get("type"),
                    "status": ad_group_ad.get("status"),
                    "final_urls": ad.get("finalUrls", [])[:2],  # First 2 URLs
                    "ad_group_id": ad_group.get("id"),
                    "campaign_id": campaign.get("id"),
                })

            return TestResult(
                name="Ads List",
                status=TestStatus.PASSED,
                message=f"Found {len(results)} ads (showing first 5)",
                data={
                    "total_fetched": len(results),
                    "ads": ad_summaries,
                },
            )
        except Exception as e:
            return TestResult(
                name="Ads List",
                status=TestStatus.FAILED,
                error=str(e),
            )

    async def test_keywords(self) -> TestResult:
        """Test fetching keywords."""
        query = """
            SELECT
                ad_group_criterion.criterion_id,
                ad_group_criterion.keyword.text,
                ad_group_criterion.keyword.match_type,
                ad_group_criterion.status,
                ad_group.id,
                ad_group.name
            FROM ad_group_criterion
            WHERE ad_group_criterion.type = 'KEYWORD'
            ORDER BY ad_group_criterion.criterion_id
            LIMIT 10
        """

        try:
            data = await self._execute_query(query)
            results = data.get("results", [])

            keyword_summaries = []
            for r in results[:5]:  # Show first 5
                criterion = r.get("adGroupCriterion", {})
                keyword = criterion.get("keyword", {})
                ad_group = r.get("adGroup", {})
                keyword_summaries.append({
                    "criterion_id": criterion.get("criterionId"),
                    "text": keyword.get("text"),
                    "match_type": keyword.get("matchType"),
                    "status": criterion.get("status"),
                    "ad_group_id": ad_group.get("id"),
                    "ad_group_name": ad_group.get("name"),
                })

            return TestResult(
                name="Keywords List",
                status=TestStatus.PASSED,
                message=f"Found {len(results)} keywords (showing first 5)",
                data={
                    "total_fetched": len(results),
                    "keywords": keyword_summaries,
                },
            )
        except Exception as e:
            return TestResult(
                name="Keywords List",
                status=TestStatus.FAILED,
                error=str(e),
            )

    async def test_performance(self) -> TestResult:
        """Test fetching account performance metrics."""
        # Get data for last 7 days
        end_date = datetime.now().strftime("%Y-%m-%d")
        start_date = (datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d")

        query = f"""
            SELECT
                customer.id,
                metrics.impressions,
                metrics.clicks,
                metrics.cost_micros,
                metrics.conversions,
                metrics.conversions_value,
                metrics.average_cpc,
                metrics.ctr
            FROM customer
            WHERE segments.date BETWEEN '{start_date}' AND '{end_date}'
        """

        try:
            data = await self._execute_query(query)
            results = data.get("results", [])

            if not results:
                return TestResult(
                    name="Account Performance",
                    status=TestStatus.PASSED,
                    message="No performance data available for the date range",
                    data={
                        "date_range": f"{start_date} to {end_date}",
                        "metrics": None,
                    },
                )

            # Aggregate metrics
            total_impressions = 0
            total_clicks = 0
            total_cost_micros = 0
            total_conversions = 0
            total_conversions_value = 0

            for r in results:
                metrics = r.get("metrics", {})
                total_impressions += int(metrics.get("impressions", 0) or 0)
                total_clicks += int(metrics.get("clicks", 0) or 0)
                total_cost_micros += int(metrics.get("costMicros", 0) or 0)
                total_conversions += float(metrics.get("conversions", 0) or 0)
                total_conversions_value += float(metrics.get("conversionsValue", 0) or 0)

            return TestResult(
                name="Account Performance",
                status=TestStatus.PASSED,
                message=f"Retrieved performance for {start_date} to {end_date}",
                data={
                    "date_range": f"{start_date} to {end_date}",
                    "impressions": total_impressions,
                    "clicks": total_clicks,
                    "cost": total_cost_micros / 1_000_000,  # Convert micros to currency
                    "conversions": total_conversions,
                    "conversions_value": total_conversions_value,
                    "ctr": (total_clicks / total_impressions * 100) if total_impressions > 0 else 0,
                    "avg_cpc": (total_cost_micros / total_clicks / 1_000_000) if total_clicks > 0 else 0,
                },
            )
        except Exception as e:
            return TestResult(
                name="Account Performance",
                status=TestStatus.FAILED,
                error=str(e),
            )

    async def test_conversions(self) -> TestResult:
        """Test fetching conversion actions."""
        query = """
            SELECT
                conversion_action.id,
                conversion_action.name,
                conversion_action.type,
                conversion_action.status,
                conversion_action.category,
                conversion_action.counting_type
            FROM conversion_action
            LIMIT 10
        """

        try:
            data = await self._execute_query(query)
            results = data.get("results", [])

            conversion_summaries = []
            for r in results[:5]:  # Show first 5
                conversion = r.get("conversionAction", {})
                conversion_summaries.append({
                    "id": conversion.get("id"),
                    "name": conversion.get("name"),
                    "type": conversion.get("type"),
                    "status": conversion.get("status"),
                    "category": conversion.get("category"),
                    "counting_type": conversion.get("countingType"),
                })

            return TestResult(
                name="Conversion Actions",
                status=TestStatus.PASSED,
                message=f"Found {len(results)} conversion actions (showing first 5)",
                data={
                    "total_fetched": len(results),
                    "conversion_actions": conversion_summaries,
                },
            )
        except Exception as e:
            return TestResult(
                name="Conversion Actions",
                status=TestStatus.FAILED,
                error=str(e),
            )
