#!/usr/bin/env python3
"""
E2E Visual Test Runner for API Integrations.

This script runs visual end-to-end tests against real APIs and generates
an HTML report for visual verification of the results.

Usage:
    # Run all tests
    python -m src.tests.e2e.visual.run_visual_tests --all

    # Run specific platform tests
    python -m src.tests.e2e.visual.run_visual_tests --shopify --meta --google

    # Dry run (validate configuration only)
    python -m src.tests.e2e.visual.run_visual_tests --dry-run

    # Custom output directory
    python -m src.tests.e2e.visual.run_visual_tests --all --output-dir ./reports
"""

import os
import sys
import argparse
import asyncio
import logging
from datetime import datetime
from pathlib import Path
from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any
from enum import Enum

# Add backend to path
backend_dir = Path(__file__).parent.parent.parent.parent.parent
sys.path.insert(0, str(backend_dir))

from dotenv import load_dotenv

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


class TestStatus(str, Enum):
    """Test execution status."""
    PENDING = "pending"
    RUNNING = "running"
    PASSED = "passed"
    FAILED = "failed"
    SKIPPED = "skipped"
    ERROR = "error"


@dataclass
class TestResult:
    """Result of a single test."""
    name: str
    status: TestStatus
    duration_ms: float = 0.0
    message: Optional[str] = None
    error: Optional[str] = None
    data: Optional[Dict[str, Any]] = None
    screenshots: List[str] = field(default_factory=list)


@dataclass
class PlatformTestResults:
    """Results for a platform test suite."""
    platform: str
    status: TestStatus
    tests: List[TestResult] = field(default_factory=list)
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None

    @property
    def duration_ms(self) -> float:
        if self.start_time and self.end_time:
            return (self.end_time - self.start_time).total_seconds() * 1000
        return 0.0

    @property
    def passed_count(self) -> int:
        return len([t for t in self.tests if t.status == TestStatus.PASSED])

    @property
    def failed_count(self) -> int:
        return len([t for t in self.tests if t.status == TestStatus.FAILED])

    @property
    def error_count(self) -> int:
        return len([t for t in self.tests if t.status == TestStatus.ERROR])


@dataclass
class VisualTestConfig:
    """Configuration for visual tests."""
    # Shopify
    shopify_shop_domain: Optional[str] = None
    shopify_access_token: Optional[str] = None
    shopify_api_key: Optional[str] = None
    shopify_api_secret: Optional[str] = None

    # Meta Ads
    meta_app_id: Optional[str] = None
    meta_app_secret: Optional[str] = None
    meta_access_token: Optional[str] = None
    meta_ad_account_id: Optional[str] = None

    # Google Ads
    google_client_id: Optional[str] = None
    google_client_secret: Optional[str] = None
    google_refresh_token: Optional[str] = None
    google_developer_token: Optional[str] = None
    google_customer_id: Optional[str] = None

    @classmethod
    def from_env(cls) -> "VisualTestConfig":
        """Load configuration from environment variables."""
        return cls(
            # Shopify
            shopify_shop_domain=os.getenv("SHOPIFY_SHOP_DOMAIN"),
            shopify_access_token=os.getenv("SHOPIFY_ACCESS_TOKEN"),
            shopify_api_key=os.getenv("SHOPIFY_API_KEY"),
            shopify_api_secret=os.getenv("SHOPIFY_API_SECRET"),
            # Meta Ads
            meta_app_id=os.getenv("META_APP_ID"),
            meta_app_secret=os.getenv("META_APP_SECRET"),
            meta_access_token=os.getenv("META_ACCESS_TOKEN"),
            meta_ad_account_id=os.getenv("META_AD_ACCOUNT_ID"),
            # Google Ads
            google_client_id=os.getenv("GOOGLE_CLIENT_ID"),
            google_client_secret=os.getenv("GOOGLE_CLIENT_SECRET"),
            google_refresh_token=os.getenv("GOOGLE_REFRESH_TOKEN"),
            google_developer_token=os.getenv("GOOGLE_DEVELOPER_TOKEN"),
            google_customer_id=os.getenv("GOOGLE_CUSTOMER_ID"),
        )

    def has_shopify_credentials(self) -> bool:
        """Check if Shopify credentials are configured."""
        return bool(self.shopify_shop_domain and self.shopify_access_token)

    def has_meta_credentials(self) -> bool:
        """Check if Meta Ads credentials are configured."""
        return bool(self.meta_access_token and self.meta_ad_account_id)

    def has_google_credentials(self) -> bool:
        """Check if Google Ads credentials are configured."""
        return bool(
            self.google_client_id
            and self.google_client_secret
            and self.google_refresh_token
            and self.google_developer_token
            and self.google_customer_id
        )


class VisualTestRunner:
    """Orchestrates visual API tests."""

    def __init__(self, config: VisualTestConfig, output_dir: Path):
        self.config = config
        self.output_dir = output_dir
        self.results: List[PlatformTestResults] = []

    async def run_shopify_tests(self) -> PlatformTestResults:
        """Run Shopify API visual tests."""
        from src.tests.e2e.visual.test_shopify import ShopifyVisualTests

        results = PlatformTestResults(platform="Shopify", status=TestStatus.RUNNING)
        results.start_time = datetime.now()

        if not self.config.has_shopify_credentials():
            results.status = TestStatus.SKIPPED
            results.tests.append(TestResult(
                name="Configuration Check",
                status=TestStatus.SKIPPED,
                message="Shopify credentials not configured"
            ))
            results.end_time = datetime.now()
            return results

        try:
            tester = ShopifyVisualTests(
                shop_domain=self.config.shopify_shop_domain,
                access_token=self.config.shopify_access_token,
            )
            results.tests = await tester.run_all_tests()

            # Determine overall status
            if any(t.status == TestStatus.ERROR for t in results.tests):
                results.status = TestStatus.ERROR
            elif any(t.status == TestStatus.FAILED for t in results.tests):
                results.status = TestStatus.FAILED
            else:
                results.status = TestStatus.PASSED

        except Exception as e:
            results.status = TestStatus.ERROR
            results.tests.append(TestResult(
                name="Test Suite Execution",
                status=TestStatus.ERROR,
                error=str(e)
            ))

        results.end_time = datetime.now()
        return results

    async def run_meta_tests(self) -> PlatformTestResults:
        """Run Meta Ads API visual tests."""
        from src.tests.e2e.visual.test_meta_ads import MetaAdsVisualTests

        results = PlatformTestResults(platform="Meta Ads", status=TestStatus.RUNNING)
        results.start_time = datetime.now()

        if not self.config.has_meta_credentials():
            results.status = TestStatus.SKIPPED
            results.tests.append(TestResult(
                name="Configuration Check",
                status=TestStatus.SKIPPED,
                message="Meta Ads credentials not configured"
            ))
            results.end_time = datetime.now()
            return results

        try:
            tester = MetaAdsVisualTests(
                access_token=self.config.meta_access_token,
                ad_account_id=self.config.meta_ad_account_id,
                app_id=self.config.meta_app_id,
                app_secret=self.config.meta_app_secret,
            )
            results.tests = await tester.run_all_tests()

            if any(t.status == TestStatus.ERROR for t in results.tests):
                results.status = TestStatus.ERROR
            elif any(t.status == TestStatus.FAILED for t in results.tests):
                results.status = TestStatus.FAILED
            else:
                results.status = TestStatus.PASSED

        except Exception as e:
            results.status = TestStatus.ERROR
            results.tests.append(TestResult(
                name="Test Suite Execution",
                status=TestStatus.ERROR,
                error=str(e)
            ))

        results.end_time = datetime.now()
        return results

    async def run_google_tests(self) -> PlatformTestResults:
        """Run Google Ads API visual tests."""
        from src.tests.e2e.visual.test_google_ads import GoogleAdsVisualTests

        results = PlatformTestResults(platform="Google Ads", status=TestStatus.RUNNING)
        results.start_time = datetime.now()

        if not self.config.has_google_credentials():
            results.status = TestStatus.SKIPPED
            results.tests.append(TestResult(
                name="Configuration Check",
                status=TestStatus.SKIPPED,
                message="Google Ads credentials not configured"
            ))
            results.end_time = datetime.now()
            return results

        try:
            tester = GoogleAdsVisualTests(
                client_id=self.config.google_client_id,
                client_secret=self.config.google_client_secret,
                refresh_token=self.config.google_refresh_token,
                developer_token=self.config.google_developer_token,
                customer_id=self.config.google_customer_id,
            )
            results.tests = await tester.run_all_tests()

            if any(t.status == TestStatus.ERROR for t in results.tests):
                results.status = TestStatus.ERROR
            elif any(t.status == TestStatus.FAILED for t in results.tests):
                results.status = TestStatus.FAILED
            else:
                results.status = TestStatus.PASSED

        except Exception as e:
            results.status = TestStatus.ERROR
            results.tests.append(TestResult(
                name="Test Suite Execution",
                status=TestStatus.ERROR,
                error=str(e)
            ))

        results.end_time = datetime.now()
        return results

    async def run_all(
        self,
        run_shopify: bool = True,
        run_meta: bool = True,
        run_google: bool = True,
    ) -> List[PlatformTestResults]:
        """Run all specified platform tests."""
        tasks = []

        if run_shopify:
            logger.info("Starting Shopify API tests...")
            tasks.append(("Shopify", self.run_shopify_tests()))

        if run_meta:
            logger.info("Starting Meta Ads API tests...")
            tasks.append(("Meta", self.run_meta_tests()))

        if run_google:
            logger.info("Starting Google Ads API tests...")
            tasks.append(("Google", self.run_google_tests()))

        # Run tests concurrently
        for name, coro in tasks:
            try:
                result = await coro
                self.results.append(result)
                logger.info(f"{name} tests completed: {result.status.value}")
            except Exception as e:
                logger.error(f"{name} tests failed: {e}")
                self.results.append(PlatformTestResults(
                    platform=name,
                    status=TestStatus.ERROR,
                    tests=[TestResult(
                        name="Test Execution",
                        status=TestStatus.ERROR,
                        error=str(e)
                    )]
                ))

        return self.results

    def generate_report(self) -> Path:
        """Generate HTML report from test results."""
        from src.tests.e2e.visual.report_generator import HTMLReportGenerator

        generator = HTMLReportGenerator(self.results, self.output_dir)
        return generator.generate()


def parse_args():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="E2E Visual Test Runner for API Integrations",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Run all tests
  python -m src.tests.e2e.visual.run_visual_tests --all

  # Run specific platform tests
  python -m src.tests.e2e.visual.run_visual_tests --shopify --meta

  # Dry run to validate configuration
  python -m src.tests.e2e.visual.run_visual_tests --dry-run
        """,
    )

    parser.add_argument(
        "--all",
        action="store_true",
        help="Run all platform tests",
    )
    parser.add_argument(
        "--shopify",
        action="store_true",
        help="Run Shopify API tests",
    )
    parser.add_argument(
        "--meta",
        action="store_true",
        help="Run Meta Ads API tests",
    )
    parser.add_argument(
        "--google",
        action="store_true",
        help="Run Google Ads API tests",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate configuration without running tests",
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        default="./reports",
        help="Output directory for HTML reports (default: ./reports)",
    )
    parser.add_argument(
        "--env-file",
        type=str,
        default=".env.visual",
        help="Path to environment file (default: .env.visual)",
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Enable verbose logging",
    )

    return parser.parse_args()


async def main():
    """Main entry point."""
    args = parse_args()

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    # Load environment file
    env_file = Path(args.env_file)
    if env_file.exists():
        load_dotenv(env_file)
        logger.info(f"Loaded environment from {env_file}")
    else:
        # Try default .env file
        load_dotenv()
        logger.warning(f"Environment file {env_file} not found, using default .env")

    # Load configuration
    config = VisualTestConfig.from_env()

    # Determine which tests to run
    run_shopify = args.all or args.shopify
    run_meta = args.all or args.meta
    run_google = args.all or args.google

    # If no specific tests selected, run all
    if not any([run_shopify, run_meta, run_google, args.dry_run]):
        run_shopify = run_meta = run_google = True

    # Print configuration status
    print("\n" + "=" * 60)
    print("E2E Visual API Test Runner")
    print("=" * 60)
    print(f"\nConfiguration Status:")
    print(f"  Shopify: {'Configured' if config.has_shopify_credentials() else 'Not configured'}")
    print(f"  Meta Ads: {'Configured' if config.has_meta_credentials() else 'Not configured'}")
    print(f"  Google Ads: {'Configured' if config.has_google_credentials() else 'Not configured'}")

    if args.dry_run:
        print("\n[DRY RUN] Configuration validated. No tests will be executed.")
        return

    # Create output directory
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    # Run tests
    print(f"\nRunning tests:")
    if run_shopify:
        print("  - Shopify API")
    if run_meta:
        print("  - Meta Ads API")
    if run_google:
        print("  - Google Ads API")
    print()

    runner = VisualTestRunner(config, output_dir)
    results = await runner.run_all(
        run_shopify=run_shopify,
        run_meta=run_meta,
        run_google=run_google,
    )

    # Generate report
    report_path = runner.generate_report()

    # Print summary
    print("\n" + "=" * 60)
    print("Test Results Summary")
    print("=" * 60)

    total_passed = 0
    total_failed = 0
    total_errors = 0

    for result in results:
        status_icon = {
            TestStatus.PASSED: "[PASS]",
            TestStatus.FAILED: "[FAIL]",
            TestStatus.ERROR: "[ERROR]",
            TestStatus.SKIPPED: "[SKIP]",
        }.get(result.status, "[?]")

        print(f"\n{result.platform}: {status_icon}")
        print(f"  Duration: {result.duration_ms:.2f}ms")
        print(f"  Tests: {result.passed_count} passed, {result.failed_count} failed, {result.error_count} errors")

        total_passed += result.passed_count
        total_failed += result.failed_count
        total_errors += result.error_count

        for test in result.tests:
            test_icon = {
                TestStatus.PASSED: "  [PASS]",
                TestStatus.FAILED: "  [FAIL]",
                TestStatus.ERROR: "  [ERROR]",
                TestStatus.SKIPPED: "  [SKIP]",
            }.get(test.status, "  [?]")
            print(f"    {test_icon} {test.name}")
            if test.error:
                print(f"           Error: {test.error[:100]}...")

    print("\n" + "-" * 60)
    print(f"Total: {total_passed} passed, {total_failed} failed, {total_errors} errors")
    print(f"\nHTML Report: {report_path}")
    print("=" * 60 + "\n")

    # Return exit code
    if total_errors > 0 or total_failed > 0:
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
