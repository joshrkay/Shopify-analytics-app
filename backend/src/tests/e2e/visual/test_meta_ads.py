"""
Meta (Facebook) Ads API Visual Tests.

Tests Meta Marketing API endpoints with real credentials.
Generates visual output for manual verification.

API Documentation: https://developers.facebook.com/docs/marketing-apis
"""

import logging
import time
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any

import httpx

from src.tests.e2e.visual.run_visual_tests import TestResult, TestStatus

logger = logging.getLogger(__name__)

# Meta Graph API Version
META_API_VERSION = "v19.0"
META_GRAPH_URL = f"https://graph.facebook.com/{META_API_VERSION}"


class MetaAdsVisualTests:
    """Visual tests for Meta Ads API integration."""

    def __init__(
        self,
        access_token: str,
        ad_account_id: str,
        app_id: Optional[str] = None,
        app_secret: Optional[str] = None,
    ):
        self.access_token = access_token
        # Ensure ad_account_id has 'act_' prefix
        self.ad_account_id = ad_account_id if ad_account_id.startswith("act_") else f"act_{ad_account_id}"
        self.app_id = app_id
        self.app_secret = app_secret

        self.base_params = {"access_token": access_token}

    async def run_all_tests(self) -> List[TestResult]:
        """Run all Meta Ads API visual tests."""
        tests = [
            ("Ad Account Info", self.test_ad_account_info),
            ("Campaigns List", self.test_campaigns),
            ("Ad Sets List", self.test_ad_sets),
            ("Ads List", self.test_ads),
            ("Account Insights", self.test_insights),
            ("Custom Audiences", self.test_custom_audiences),
            ("Ad Account Users", self.test_ad_account_users),
        ]

        results = []
        async with httpx.AsyncClient(timeout=30.0) as client:
            self.client = client

            for name, test_func in tests:
                logger.info(f"Running Meta Ads test: {name}")
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

    async def test_ad_account_info(self) -> TestResult:
        """Test fetching ad account information."""
        response = await self.client.get(
            f"{META_GRAPH_URL}/{self.ad_account_id}",
            params={
                **self.base_params,
                "fields": "id,name,account_id,account_status,currency,timezone_name,business,funding_source_details,spend_cap,amount_spent,balance",
            },
        )

        if response.status_code != 200:
            error_data = response.json().get("error", {})
            return TestResult(
                name="Ad Account Info",
                status=TestStatus.FAILED,
                error=f"HTTP {response.status_code}: {error_data.get('message', response.text[:200])}",
            )

        data = response.json()

        # Map account status
        account_status_map = {
            1: "ACTIVE",
            2: "DISABLED",
            3: "UNSETTLED",
            7: "PENDING_RISK_REVIEW",
            8: "PENDING_SETTLEMENT",
            9: "IN_GRACE_PERIOD",
            100: "PENDING_CLOSURE",
            101: "CLOSED",
        }
        status_code = data.get("account_status", 0)
        status_text = account_status_map.get(status_code, f"UNKNOWN ({status_code})")

        return TestResult(
            name="Ad Account Info",
            status=TestStatus.PASSED,
            message=f"Successfully retrieved ad account: {data.get('name')}",
            data={
                "account_id": data.get("account_id"),
                "name": data.get("name"),
                "status": status_text,
                "currency": data.get("currency"),
                "timezone": data.get("timezone_name"),
                "amount_spent": data.get("amount_spent"),
                "balance": data.get("balance"),
                "spend_cap": data.get("spend_cap"),
                "business": data.get("business", {}).get("name") if data.get("business") else None,
            },
        )

    async def test_campaigns(self) -> TestResult:
        """Test fetching campaigns."""
        response = await self.client.get(
            f"{META_GRAPH_URL}/{self.ad_account_id}/campaigns",
            params={
                **self.base_params,
                "fields": "id,name,status,objective,created_time,updated_time,daily_budget,lifetime_budget,start_time,stop_time",
                "limit": 10,
            },
        )

        if response.status_code != 200:
            error_data = response.json().get("error", {})
            return TestResult(
                name="Campaigns List",
                status=TestStatus.FAILED,
                error=f"HTTP {response.status_code}: {error_data.get('message', response.text[:200])}",
            )

        data = response.json()
        campaigns = data.get("data", [])

        campaign_summaries = []
        for c in campaigns[:5]:  # Show first 5
            campaign_summaries.append({
                "id": c.get("id"),
                "name": c.get("name"),
                "status": c.get("status"),
                "objective": c.get("objective"),
                "daily_budget": c.get("daily_budget"),
                "lifetime_budget": c.get("lifetime_budget"),
                "created_time": c.get("created_time"),
            })

        return TestResult(
            name="Campaigns List",
            status=TestStatus.PASSED,
            message=f"Found {len(campaigns)} campaigns (showing first 5)",
            data={
                "total_fetched": len(campaigns),
                "campaigns": campaign_summaries,
                "has_more": "paging" in data and "next" in data.get("paging", {}),
            },
        )

    async def test_ad_sets(self) -> TestResult:
        """Test fetching ad sets."""
        response = await self.client.get(
            f"{META_GRAPH_URL}/{self.ad_account_id}/adsets",
            params={
                **self.base_params,
                "fields": "id,name,status,campaign_id,daily_budget,lifetime_budget,targeting,billing_event,optimization_goal,created_time",
                "limit": 10,
            },
        )

        if response.status_code != 200:
            error_data = response.json().get("error", {})
            return TestResult(
                name="Ad Sets List",
                status=TestStatus.FAILED,
                error=f"HTTP {response.status_code}: {error_data.get('message', response.text[:200])}",
            )

        data = response.json()
        ad_sets = data.get("data", [])

        ad_set_summaries = []
        for a in ad_sets[:5]:  # Show first 5
            targeting = a.get("targeting", {})
            ad_set_summaries.append({
                "id": a.get("id"),
                "name": a.get("name"),
                "status": a.get("status"),
                "campaign_id": a.get("campaign_id"),
                "daily_budget": a.get("daily_budget"),
                "billing_event": a.get("billing_event"),
                "optimization_goal": a.get("optimization_goal"),
                "targeting_countries": targeting.get("geo_locations", {}).get("countries", [])[:3],
                "created_time": a.get("created_time"),
            })

        return TestResult(
            name="Ad Sets List",
            status=TestStatus.PASSED,
            message=f"Found {len(ad_sets)} ad sets (showing first 5)",
            data={
                "total_fetched": len(ad_sets),
                "ad_sets": ad_set_summaries,
            },
        )

    async def test_ads(self) -> TestResult:
        """Test fetching ads."""
        response = await self.client.get(
            f"{META_GRAPH_URL}/{self.ad_account_id}/ads",
            params={
                **self.base_params,
                "fields": "id,name,status,adset_id,campaign_id,creative,created_time,updated_time",
                "limit": 10,
            },
        )

        if response.status_code != 200:
            error_data = response.json().get("error", {})
            return TestResult(
                name="Ads List",
                status=TestStatus.FAILED,
                error=f"HTTP {response.status_code}: {error_data.get('message', response.text[:200])}",
            )

        data = response.json()
        ads = data.get("data", [])

        ad_summaries = []
        for ad in ads[:5]:  # Show first 5
            ad_summaries.append({
                "id": ad.get("id"),
                "name": ad.get("name"),
                "status": ad.get("status"),
                "adset_id": ad.get("adset_id"),
                "campaign_id": ad.get("campaign_id"),
                "creative_id": ad.get("creative", {}).get("id") if ad.get("creative") else None,
                "created_time": ad.get("created_time"),
            })

        return TestResult(
            name="Ads List",
            status=TestStatus.PASSED,
            message=f"Found {len(ads)} ads (showing first 5)",
            data={
                "total_fetched": len(ads),
                "ads": ad_summaries,
            },
        )

    async def test_insights(self) -> TestResult:
        """Test fetching account insights."""
        # Get insights for last 7 days
        end_date = datetime.now().strftime("%Y-%m-%d")
        start_date = (datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d")

        response = await self.client.get(
            f"{META_GRAPH_URL}/{self.ad_account_id}/insights",
            params={
                **self.base_params,
                "fields": "spend,impressions,clicks,cpc,cpm,ctr,reach,frequency,actions,conversions",
                "time_range": f'{{"since":"{start_date}","until":"{end_date}"}}',
                "level": "account",
            },
        )

        if response.status_code != 200:
            error_data = response.json().get("error", {})
            return TestResult(
                name="Account Insights",
                status=TestStatus.FAILED,
                error=f"HTTP {response.status_code}: {error_data.get('message', response.text[:200])}",
            )

        data = response.json()
        insights = data.get("data", [])

        if not insights:
            return TestResult(
                name="Account Insights",
                status=TestStatus.PASSED,
                message="No insights data available for the date range",
                data={
                    "date_range": f"{start_date} to {end_date}",
                    "insights": None,
                },
            )

        insight = insights[0]

        # Parse actions to show key metrics
        actions = {}
        for action in insight.get("actions", []):
            action_type = action.get("action_type")
            value = action.get("value")
            if action_type in ["link_click", "landing_page_view", "purchase", "add_to_cart"]:
                actions[action_type] = value

        return TestResult(
            name="Account Insights",
            status=TestStatus.PASSED,
            message=f"Retrieved insights for {start_date} to {end_date}",
            data={
                "date_range": f"{start_date} to {end_date}",
                "spend": insight.get("spend"),
                "impressions": insight.get("impressions"),
                "clicks": insight.get("clicks"),
                "reach": insight.get("reach"),
                "cpc": insight.get("cpc"),
                "cpm": insight.get("cpm"),
                "ctr": insight.get("ctr"),
                "frequency": insight.get("frequency"),
                "key_actions": actions,
            },
        )

    async def test_custom_audiences(self) -> TestResult:
        """Test fetching custom audiences."""
        response = await self.client.get(
            f"{META_GRAPH_URL}/{self.ad_account_id}/customaudiences",
            params={
                **self.base_params,
                "fields": "id,name,subtype,approximate_count,delivery_status,description,created_time",
                "limit": 10,
            },
        )

        if response.status_code != 200:
            error_data = response.json().get("error", {})
            return TestResult(
                name="Custom Audiences",
                status=TestStatus.FAILED,
                error=f"HTTP {response.status_code}: {error_data.get('message', response.text[:200])}",
            )

        data = response.json()
        audiences = data.get("data", [])

        audience_summaries = []
        for a in audiences[:5]:  # Show first 5
            audience_summaries.append({
                "id": a.get("id"),
                "name": a.get("name"),
                "subtype": a.get("subtype"),
                "approximate_count": a.get("approximate_count"),
                "delivery_status": a.get("delivery_status", {}).get("code") if isinstance(a.get("delivery_status"), dict) else a.get("delivery_status"),
                "created_time": a.get("created_time"),
            })

        return TestResult(
            name="Custom Audiences",
            status=TestStatus.PASSED,
            message=f"Found {len(audiences)} custom audiences (showing first 5)",
            data={
                "total_fetched": len(audiences),
                "audiences": audience_summaries,
            },
        )

    async def test_ad_account_users(self) -> TestResult:
        """Test fetching ad account users."""
        response = await self.client.get(
            f"{META_GRAPH_URL}/{self.ad_account_id}/users",
            params={
                **self.base_params,
                "fields": "id,name,email,role",
                "limit": 10,
            },
        )

        if response.status_code != 200:
            error_data = response.json().get("error", {})
            # Some accounts don't have permission to view users
            if error_data.get("code") == 100:
                return TestResult(
                    name="Ad Account Users",
                    status=TestStatus.SKIPPED,
                    message="Insufficient permissions to view account users",
                )
            return TestResult(
                name="Ad Account Users",
                status=TestStatus.FAILED,
                error=f"HTTP {response.status_code}: {error_data.get('message', response.text[:200])}",
            )

        data = response.json()
        users = data.get("data", [])

        user_summaries = []
        for u in users[:5]:  # Show first 5
            user_summaries.append({
                "id": u.get("id"),
                "name": u.get("name"),
                "email": u.get("email", "")[:5] + "***" if u.get("email") else None,  # Partial mask
                "role": u.get("role"),
            })

        return TestResult(
            name="Ad Account Users",
            status=TestStatus.PASSED,
            message=f"Found {len(users)} users with access (showing first 5)",
            data={
                "total_fetched": len(users),
                "users": user_summaries,
            },
        )
