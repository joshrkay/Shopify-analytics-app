#!/usr/bin/env python3
"""
Production environment verification script.

Validates that all required services, credentials, and data are properly
configured for a production deployment of the Shopify Analytics App.

Usage:
    cd backend && PYTHONPATH=. python scripts/verify_production.py

Exit codes:
    0 - All checks passed
    1 - One or more checks failed
"""

import base64
import json
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen

# ---------------------------------------------------------------------------
# Path setup (matches existing scripts pattern)
# ---------------------------------------------------------------------------
backend_dir = Path(__file__).parent.parent
sys.path.insert(0, str(backend_dir))


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------
@dataclass
class CheckResult:
    name: str
    passed: bool
    message: str
    remediation: Optional[str] = None


# ---------------------------------------------------------------------------
# ANSI color output — disabled when NO_COLOR is set or stdout is not a TTY
# ---------------------------------------------------------------------------
_use_color = sys.stdout.isatty() and not os.environ.get("NO_COLOR")

GREEN = "\033[92m" if _use_color else ""
RED = "\033[91m" if _use_color else ""
BOLD = "\033[1m" if _use_color else ""
RESET = "\033[0m" if _use_color else ""


def _print_result(result: CheckResult) -> None:
    tag = f"{GREEN}PASS{RESET}" if result.passed else f"{RED}FAIL{RESET}"
    print(f"  [{tag}] {result.name}: {result.message}")
    if result.remediation and not result.passed:
        for line in result.remediation.split("\n"):
            print(f"         -> {line}")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _get_database_url() -> str:
    database_url = os.environ.get("DATABASE_URL", "")
    if database_url.startswith("postgres://"):
        database_url = database_url.replace("postgres://", "postgresql://", 1)
    return database_url


def _pg_connect():
    """Return a psycopg2 connection or raise."""
    import psycopg2

    url = _get_database_url()
    if not url:
        raise RuntimeError("DATABASE_URL is not set")
    return psycopg2.connect(url)


# ---------------------------------------------------------------------------
# Check 1: Required environment variables
# ---------------------------------------------------------------------------
REQUIRED_ENV_VARS = [
    "DATABASE_URL",
    "REDIS_URL",
    "CLERK_SECRET_KEY",
    "CLERK_FRONTEND_API",
    "CLERK_WEBHOOK_SECRET",
    "SHOPIFY_API_KEY",
    "SHOPIFY_API_SECRET",
    "OPENROUTER_API_KEY",
    "ENCRYPTION_KEY",
    "SUPERSET_EMBED_URL",
    "SUPERSET_USERNAME",
    "SUPERSET_PASSWORD",
    "SUPERSET_JWT_SECRET",
    "APP_BASE_URL",
    "APP_URL",
    "OAUTH_REDIRECT_URI",
    "CORS_ORIGINS",
    "AIRBYTE_WORKSPACE_ID",
    "AIRBYTE_API_TOKEN",
]


def check_env_vars() -> CheckResult:
    missing = [v for v in REQUIRED_ENV_VARS if not os.environ.get(v)]
    if not missing:
        return CheckResult(
            name="Environment Variables",
            passed=True,
            message=f"All {len(REQUIRED_ENV_VARS)} required variables are set",
        )
    return CheckResult(
        name="Environment Variables",
        passed=False,
        message=f"{len(missing)} required variable(s) missing: {', '.join(missing)}",
        remediation="Set these in Render dashboard or .env file",
    )


# ---------------------------------------------------------------------------
# Check 2: Airbyte health endpoint
# ---------------------------------------------------------------------------
def check_airbyte_health() -> CheckResult:
    base_url = os.environ.get("AIRBYTE_BASE_URL", "https://api.airbyte.com/v1").rstrip("/")
    token = os.environ.get("AIRBYTE_API_TOKEN")
    username = os.environ.get("AIRBYTE_USERNAME")
    password = os.environ.get("AIRBYTE_PASSWORD")

    headers = {"Accept": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    elif username and password:
        creds = base64.b64encode(f"{username}:{password}".encode()).decode()
        headers["Authorization"] = f"Basic {creds}"

    url = f"{base_url}/health"
    try:
        req = Request(url, headers=headers)
        resp = urlopen(req, timeout=10)
        body = json.loads(resp.read().decode())
        if body.get("available", False):
            return CheckResult(name="Airbyte Health", passed=True, message="API is available")
        return CheckResult(
            name="Airbyte Health",
            passed=False,
            message=f"API responded but reported unavailable: {body}",
            remediation="Check Airbyte service status and database connectivity",
        )
    except (HTTPError, URLError, OSError) as e:
        return CheckResult(
            name="Airbyte Health",
            passed=False,
            message=f"Cannot reach {url}: {e}",
            remediation="Verify AIRBYTE_API_TOKEN is valid and Airbyte API is network-reachable",
        )


# ---------------------------------------------------------------------------
# Check 3: Redis PING
# ---------------------------------------------------------------------------
def check_redis() -> CheckResult:
    redis_url = os.environ.get("REDIS_URL")
    if not redis_url:
        return CheckResult(
            name="Redis Connection",
            passed=False,
            message="REDIS_URL is not set",
            remediation="Set REDIS_URL in environment (e.g. redis://host:6379/0)",
        )
    try:
        import redis

        r = redis.from_url(redis_url, socket_timeout=5.0, socket_connect_timeout=5.0)
        r.ping()
        return CheckResult(name="Redis Connection", passed=True, message="PING successful")
    except Exception as e:
        return CheckResult(
            name="Redis Connection",
            passed=False,
            message=f"PING failed: {e}",
            remediation="Verify REDIS_URL is correct and Redis is running",
        )


# ---------------------------------------------------------------------------
# Check 4: PostgreSQL connection
# ---------------------------------------------------------------------------
def check_postgres() -> CheckResult:
    if not _get_database_url():
        return CheckResult(
            name="PostgreSQL Connection",
            passed=False,
            message="DATABASE_URL is not set",
            remediation="Set DATABASE_URL in environment",
        )
    try:
        conn = _pg_connect()
        cur = conn.cursor()
        cur.execute("SELECT 1")
        cur.close()
        conn.close()
        return CheckResult(name="PostgreSQL Connection", passed=True, message="Connection successful")
    except Exception as e:
        return CheckResult(
            name="PostgreSQL Connection",
            passed=False,
            message=f"Connection failed: {e}",
            remediation="Verify DATABASE_URL is correct and PostgreSQL is reachable",
        )


# ---------------------------------------------------------------------------
# Check 5: dbt marts have rows
# ---------------------------------------------------------------------------
def check_dbt_marts() -> CheckResult:
    tables = ["marts.mart_marketing_metrics", "marts.mart_revenue_metrics"]
    empty_tables: list[str] = []
    errors: list[str] = []

    try:
        conn = _pg_connect()
        cur = conn.cursor()
        for table in tables:
            try:
                cur.execute(f"SELECT COUNT(*) FROM {table}")  # noqa: S608 — table name is hardcoded
                count = cur.fetchone()[0]
                if count == 0:
                    empty_tables.append(table)
            except Exception as e:
                errors.append(f"{table}: {e}")
                conn.rollback()
        cur.close()
        conn.close()
    except Exception as e:
        return CheckResult(
            name="dbt Marts Data",
            passed=False,
            message=f"Cannot connect to database: {e}",
            remediation="Fix PostgreSQL connection first, then re-run",
        )

    if errors:
        return CheckResult(
            name="dbt Marts Data",
            passed=False,
            message=f"Query errors: {'; '.join(errors)}",
            remediation="Run 'dbt run' to build mart models. Tables may not exist yet.",
        )
    if empty_tables:
        return CheckResult(
            name="dbt Marts Data",
            passed=False,
            message=f"Empty tables: {', '.join(empty_tables)}",
            remediation="Run 'dbt run' to populate mart models with data",
        )
    return CheckResult(name="dbt Marts Data", passed=True, message="All mart tables have rows")


# ---------------------------------------------------------------------------
# Check 6: Active plans exist
# ---------------------------------------------------------------------------
def check_active_plans() -> CheckResult:
    try:
        conn = _pg_connect()
        cur = conn.cursor()
        cur.execute("SELECT count(*) FROM plans WHERE is_active = true")
        count = cur.fetchone()[0]
        cur.close()
        conn.close()
        if count > 0:
            return CheckResult(
                name="Active Plans", passed=True, message=f"{count} active plan(s) found"
            )
        return CheckResult(
            name="Active Plans",
            passed=False,
            message="No active plans found in plans table",
            remediation="Run 'python -m scripts.seed_billing_plans' to create billing plans",
        )
    except Exception as e:
        return CheckResult(
            name="Active Plans",
            passed=False,
            message=f"Query failed: {e}",
            remediation="Fix PostgreSQL connection first, then re-run",
        )


# ---------------------------------------------------------------------------
# Check 7: PlanFeature rows for each active plan
# ---------------------------------------------------------------------------
def check_plan_features() -> CheckResult:
    try:
        conn = _pg_connect()
        cur = conn.cursor()
        cur.execute(
            """
            SELECT p.id, p.name
            FROM plans p
            LEFT JOIN plan_features pf ON pf.plan_id = p.id
            WHERE p.is_active = true
            GROUP BY p.id, p.name
            HAVING COUNT(pf.id) = 0
            """
        )
        rows = cur.fetchall()
        cur.close()
        conn.close()
        if not rows:
            return CheckResult(
                name="Plan Features", passed=True, message="All active plans have features"
            )
        plan_names = [r[1] for r in rows]
        return CheckResult(
            name="Plan Features",
            passed=False,
            message=f"Plans missing features: {', '.join(plan_names)}",
            remediation="Run 'python -m scripts.seed_billing_plans' to populate PlanFeature rows",
        )
    except Exception as e:
        return CheckResult(
            name="Plan Features",
            passed=False,
            message=f"Query failed: {e}",
            remediation="Fix PostgreSQL connection first, then re-run",
        )


# ---------------------------------------------------------------------------
# Check 8: Clerk JWKS endpoint reachable
# ---------------------------------------------------------------------------
def check_clerk_jwks() -> CheckResult:
    clerk_api = os.environ.get("CLERK_FRONTEND_API", "")
    if not clerk_api:
        return CheckResult(
            name="Clerk JWKS",
            passed=False,
            message="CLERK_FRONTEND_API is not set",
            remediation="Set CLERK_FRONTEND_API to your Clerk frontend API domain",
        )

    clerk_api = clerk_api.rstrip("/")
    if not clerk_api.startswith("http"):
        clerk_api = f"https://{clerk_api}"

    url = f"{clerk_api}/.well-known/jwks.json"
    try:
        req = Request(url, headers={"Accept": "application/json"})
        resp = urlopen(req, timeout=10)
        body = json.loads(resp.read().decode())
        keys = body.get("keys", [])
        if keys:
            return CheckResult(
                name="Clerk JWKS",
                passed=True,
                message=f"Reachable — {len(keys)} signing key(s) found",
            )
        return CheckResult(
            name="Clerk JWKS",
            passed=False,
            message="JWKS endpoint returned empty keys array",
            remediation="Verify CLERK_FRONTEND_API points to the correct Clerk instance",
        )
    except (HTTPError, URLError, OSError) as e:
        return CheckResult(
            name="Clerk JWKS",
            passed=False,
            message=f"Cannot reach {url}: {e}",
            remediation="Verify CLERK_FRONTEND_API is correct and the endpoint is publicly accessible",
        )


# ---------------------------------------------------------------------------
# Check 9: Billing test mode is off
# ---------------------------------------------------------------------------
def check_billing_test_mode() -> CheckResult:
    value = os.environ.get("SHOPIFY_BILLING_TEST_MODE", "")
    if value.lower() == "true":
        return CheckResult(
            name="Billing Test Mode",
            passed=False,
            message=f"SHOPIFY_BILLING_TEST_MODE is '{value}' — must be disabled for production",
            remediation="Set SHOPIFY_BILLING_TEST_MODE to 'false' or remove it from environment",
        )
    return CheckResult(
        name="Billing Test Mode",
        passed=True,
        message="Test mode is off" + (f" (value: '{value}')" if value else " (not set)"),
    )


# ---------------------------------------------------------------------------
# Check 10: OAUTH_REDIRECT_URI domain matches CORS_ORIGINS
# ---------------------------------------------------------------------------
def check_oauth_cors_match() -> CheckResult:
    redirect_uri = os.environ.get("OAUTH_REDIRECT_URI", "")
    cors_raw = os.environ.get("CORS_ORIGINS", "")

    if not redirect_uri:
        return CheckResult(
            name="OAuth/CORS Domain Match",
            passed=False,
            message="OAUTH_REDIRECT_URI is not set",
            remediation="Set OAUTH_REDIRECT_URI (e.g. https://app.markinsight.net/api/sources/oauth/callback)",
        )
    if not cors_raw:
        return CheckResult(
            name="OAuth/CORS Domain Match",
            passed=False,
            message="CORS_ORIGINS is not set",
            remediation="Set CORS_ORIGINS (e.g. https://app.markinsight.net)",
        )

    parsed = urlparse(redirect_uri)
    redirect_origin = f"{parsed.scheme}://{parsed.netloc}"

    cors_origins = [o.strip() for o in cors_raw.split(",") if o.strip()]
    if redirect_origin in cors_origins:
        return CheckResult(
            name="OAuth/CORS Domain Match",
            passed=True,
            message=f"'{redirect_origin}' found in CORS_ORIGINS",
        )
    return CheckResult(
        name="OAuth/CORS Domain Match",
        passed=False,
        message=f"'{redirect_origin}' not found in CORS_ORIGINS",
        remediation=f"Add '{redirect_origin}' to CORS_ORIGINS to allow OAuth callbacks",
    )


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------
ALL_CHECKS = [
    check_env_vars,
    check_airbyte_health,
    check_redis,
    check_postgres,
    check_dbt_marts,
    check_active_plans,
    check_plan_features,
    check_clerk_jwks,
    check_billing_test_mode,
    check_oauth_cors_match,
]


def run_all_checks() -> List[CheckResult]:
    results: List[CheckResult] = []
    for check_fn in ALL_CHECKS:
        try:
            result = check_fn()
        except Exception as e:
            result = CheckResult(
                name=check_fn.__name__.replace("check_", "").replace("_", " ").title(),
                passed=False,
                message=f"Unexpected error: {e}",
                remediation="Check script logs and environment configuration",
            )
        results.append(result)
        _print_result(result)
    return results


def main() -> int:
    print(f"\n{BOLD}Production Environment Verification{RESET}")
    print("=" * 50)
    print()

    results = run_all_checks()

    passed = sum(1 for r in results if r.passed)
    failed = sum(1 for r in results if not r.passed)
    total = len(results)

    print()
    print("=" * 50)
    status = f"{BOLD}Summary:{RESET} {passed}/{total} passed"
    if failed:
        status += f", {RED}{failed} failed{RESET}"
    print(status)
    print()

    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
