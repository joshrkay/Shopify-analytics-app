#!/usr/bin/env python3
"""
End-to-end pipeline integration test.

Flow: seed raw data → dbt run → validate SQL at each stage → verify metrics.

Usage:
    python scripts/test_pipeline_integration.py [options]

    --db-url URL         PostgreSQL connection URL
    --profiles-dir DIR   dbt profiles directory (default: analytics/)
    --target TARGET      dbt target name (default: dev)
    --skip-seed          Skip data seeding (assume already seeded)
    --skip-dbt           Skip dbt run (assume already built)
    --full-refresh       Pass --full-refresh to dbt run (recommended for clean state)
    --keep-data          Do not clean seed data after test (default: clean up)

Exit codes:
    0  All stages passed
    1  One or more stages failed

The test validates the following stages:
    Stage 1  Raw tables        — airbyte_raw schema populated with seed rows
    Stage 2  Platform tables   — platform schema has tenant + connections
    Stage 3  Staging views     — staging.stg_* views return rows for seed tenant
    Stage 4  Canonical tables  — analytics.orders + analytics.marketing_spend
    Stage 5  Mart tables       — marts.mart_marketing_metrics
    Stage 6  Metric math       — AOV, ROAS, CAC match known seed values

For API endpoint validation, set MARKINSIGHT_API_URL and MARKINSIGHT_API_TOKEN.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import subprocess
import sys
import time
from decimal import Decimal
from pathlib import Path
from typing import Any

try:
    import psycopg2
    import psycopg2.extras
except ImportError:
    print("ERROR: psycopg2 is required.  Install with: pip install psycopg2-binary")
    sys.exit(1)

REPO_ROOT = Path(__file__).resolve().parent.parent
ANALYTICS_DIR = REPO_ROOT / "analytics"

# Pull seed constants from the seeder module without re-importing side effects
_seeder_path = REPO_ROOT / "scripts" / "seed_pipeline_test_data.py"
_spec = importlib.util.spec_from_file_location("seeder", _seeder_path)
_seeder = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_seeder)  # type: ignore[union-attr]

TENANT_ID = _seeder.TENANT_ID
SHOP_DOMAIN = _seeder.SHOP_DOMAIN
EXPECTED = _seeder.EXPECTED

TOLERANCE_PCT = Decimal("0.01")   # 1% tolerance on aggregate values
ABS_TOLERANCE = Decimal("0.02")   # $0.02 absolute tolerance on unit values

# ---------------------------------------------------------------------------
# Test framework helpers
# ---------------------------------------------------------------------------


class Stage:
    def __init__(self, name: str) -> None:
        self.name = name
        self.checks: list[tuple[bool, str]] = []

    def ok(self, label: str) -> None:
        self.checks.append((True, label))
        print(f"    ✓ {label}")

    def fail(self, label: str) -> None:
        self.checks.append((False, label))
        print(f"    ✗ {label}")

    @property
    def passed(self) -> bool:
        return all(ok for ok, _ in self.checks) and bool(self.checks)

    @property
    def failures(self) -> list[str]:
        return [label for ok, label in self.checks if not ok]


def _q(cur, sql: str, params: tuple = ()) -> tuple | None:
    try:
        cur.execute(sql, params)
        return cur.fetchone()
    except Exception as e:
        # Rollback so subsequent queries on this connection are not blocked
        cur.connection.rollback()
        return None


def _within(actual: Decimal, expected: Decimal, pct: Decimal = TOLERANCE_PCT) -> bool:
    if expected == 0:
        return actual == 0
    return abs((actual - expected) / expected) <= pct


def _approx(actual: Decimal, expected: Decimal, tol: Decimal = ABS_TOLERANCE) -> bool:
    return abs(actual - expected) <= tol


def _dec(val: Any) -> Decimal:
    return Decimal(str(val or 0))


# ---------------------------------------------------------------------------
# Database connection
# ---------------------------------------------------------------------------


def get_conn(db_url: str | None) -> psycopg2.extensions.connection:
    if db_url:
        return psycopg2.connect(db_url)
    db_url = os.environ.get("DATABASE_URL")
    if db_url:
        return psycopg2.connect(db_url)
    return psycopg2.connect(
        host=os.environ.get("DB_HOST", "localhost"),
        port=int(os.environ.get("DB_PORT", "5432")),
        user=os.environ.get("DB_USER", "postgres"),
        password=os.environ.get("DB_PASSWORD", ""),
        dbname=os.environ.get("DB_NAME", "shopify_analytics"),
    )


# ---------------------------------------------------------------------------
# Stage 1: Raw tables
# ---------------------------------------------------------------------------


def check_stage_raw(cur, stage: Stage) -> None:
    checks = [
        ("airbyte_raw._airbyte_raw_meta_ads",           EXPECTED["meta_ads_raw_rows"],           "meta_ads_raw"),
        ("airbyte_raw._airbyte_raw_google_ads",          EXPECTED["google_ads_raw_rows"],          "google_ads_raw"),
        ("airbyte_raw._airbyte_raw_shopify_orders",      EXPECTED["shopify_orders_raw_rows"],      "shopify_orders_raw"),
        ("airbyte_raw._airbyte_raw_shopify_customers",   EXPECTED["shopify_customers_raw_rows"],   "shopify_customers_raw"),
    ]
    for table, expected_count, label in checks:
        row = _q(cur, f"SELECT count(*) FROM {table} WHERE _airbyte_ab_id LIKE 'seed-%%'")
        if row is None:
            stage.fail(f"{label}: table not found")
            continue
        actual = int(row[0])
        if actual >= expected_count:
            stage.ok(f"{label}: {actual} rows (expected {expected_count})")
        else:
            stage.fail(f"{label}: {actual} rows (expected {expected_count})")


# ---------------------------------------------------------------------------
# Stage 2: Platform tables
# ---------------------------------------------------------------------------


def check_stage_platform(cur, stage: Stage) -> None:
    row = _q(cur, "SELECT count(*) FROM platform.shopify_stores WHERE tenant_id = %s", (TENANT_ID,))
    if row and int(row[0]) >= 1:
        stage.ok(f"shopify_stores: {int(row[0])} row(s) for tenant")
    else:
        stage.fail(f"shopify_stores: no row for tenant {TENANT_ID}")

    row = _q(cur,
             "SELECT count(*) FROM platform.tenant_airbyte_connections WHERE tenant_id = %s AND status = 'active'",
             (TENANT_ID,))
    if row and int(row[0]) >= 3:
        stage.ok(f"tenant_airbyte_connections: {int(row[0])} active connections")
    else:
        stage.fail(f"tenant_airbyte_connections: expected 3 active connections, got {row[0] if row else 0}")

    # Verify connection source types
    row = _q(cur,
             """
             SELECT array_agg(source_type ORDER BY source_type)
             FROM platform.tenant_airbyte_connections
             WHERE tenant_id = %s AND status = 'active'
             """,
             (TENANT_ID,))
    if row and row[0]:
        types = sorted(row[0])
        expected_types = sorted(["shopify", "source-facebook-marketing", "source-google-ads"])
        if types == expected_types:
            stage.ok(f"connection source types: {types}")
        else:
            stage.fail(f"connection source types: expected {expected_types}, got {types}")
    else:
        stage.fail("connection source types: could not read")


# ---------------------------------------------------------------------------
# Stage 3: Staging views (post-dbt)
# ---------------------------------------------------------------------------


def check_stage_staging(cur, stage: Stage) -> None:
    staging_checks = [
        ("staging.stg_shopify_orders",         "tenant_id", "shopify_staging_orders"),
        ("staging.stg_facebook_ads_performance","tenant_id", "meta_ads_staging"),
        ("staging.stg_google_ads_performance",  "tenant_id", "google_ads_staging"),
    ]
    for view, tenant_col, label in staging_checks:
        row = _q(cur, f"SELECT count(*) FROM {view} WHERE {tenant_col} = %s", (TENANT_ID,))
        if row is None:
            stage.fail(f"{label}: view {view} not accessible")
            continue
        count = int(row[0])
        if count > 0:
            stage.ok(f"{label}: {count} rows")
        else:
            stage.fail(f"{label}: 0 rows for tenant — staging join may have failed")

    # Spot-check: staging Meta Ads should have the act_ prefix stripped
    row = _q(cur,
             """
             SELECT count(*) FROM staging.stg_facebook_ads_performance
             WHERE tenant_id = %s AND ad_account_id LIKE 'act_%%'
             """,
             (TENANT_ID,))
    if row is not None:
        act_prefixed = int(row[0])
        if act_prefixed == 0:
            stage.ok("meta_ads_account_id_prefix_stripped: no act_ prefix in staging")
        else:
            stage.fail(f"meta_ads_account_id_prefix_stripped: {act_prefixed} rows still have act_ prefix")


# ---------------------------------------------------------------------------
# Stage 4: Canonical tables (post-dbt)
# ---------------------------------------------------------------------------


def check_stage_canonical(cur, stage: Stage) -> None:
    # analytics.orders
    row = _q(cur,
             "SELECT count(*), sum(revenue_gross), sum(revenue_net) FROM analytics.orders WHERE tenant_id = %s",
             (TENANT_ID,))
    if row is None:
        stage.fail("canonical_orders: analytics.orders not accessible")
    else:
        order_count = int(row[0])
        rev_gross = _dec(row[1])
        rev_net = _dec(row[2])

        if order_count == EXPECTED["total_orders"]:
            stage.ok(f"canonical_orders_count: {order_count}")
        else:
            stage.fail(f"canonical_orders_count: expected {EXPECTED['total_orders']}, got {order_count}")

        if _within(rev_gross, _dec(EXPECTED["total_revenue_gross"])):
            stage.ok(f"canonical_orders_revenue_gross: {rev_gross:.2f}")
        else:
            stage.fail(f"canonical_orders_revenue_gross: expected ~{EXPECTED['total_revenue_gross']}, got {rev_gross:.2f}")

        if _within(rev_net, _dec(EXPECTED["total_revenue_net"])):
            stage.ok(f"canonical_orders_revenue_net: {rev_net:.2f}")
        else:
            stage.fail(f"canonical_orders_revenue_net: expected ~{EXPECTED['total_revenue_net']}, got {rev_net:.2f}")

    # analytics.marketing_spend
    row = _q(cur,
             """
             SELECT
                 count(*),
                 sum(CASE WHEN source_platform = 'meta_ads'   THEN spend ELSE 0 END),
                 sum(CASE WHEN source_platform = 'google_ads' THEN spend ELSE 0 END),
                 sum(spend)
             FROM analytics.marketing_spend
             WHERE tenant_id = %s
             """,
             (TENANT_ID,))
    if row is None:
        stage.fail("canonical_marketing_spend: analytics.marketing_spend not accessible")
    else:
        ms_count = int(row[0])
        meta_spend = _dec(row[1])
        google_spend = _dec(row[2])
        total_spend = _dec(row[3])

        if ms_count > 0:
            stage.ok(f"canonical_marketing_spend_count: {ms_count} rows")
        else:
            stage.fail("canonical_marketing_spend_count: 0 rows")

        if _within(meta_spend, _dec(EXPECTED["meta_ads_total_spend"])):
            stage.ok(f"canonical_meta_ads_spend: {meta_spend:.2f}")
        else:
            stage.fail(f"canonical_meta_ads_spend: expected ~{EXPECTED['meta_ads_total_spend']}, got {meta_spend:.2f}")

        if _within(google_spend, _dec(EXPECTED["google_ads_total_spend"])):
            stage.ok(f"canonical_google_ads_spend: {google_spend:.2f}")
        else:
            stage.fail(f"canonical_google_ads_spend: expected ~{EXPECTED['google_ads_total_spend']}, got {google_spend:.2f}")

        if _within(total_spend, _dec(EXPECTED["total_ad_spend"])):
            stage.ok(f"canonical_total_ad_spend: {total_spend:.2f}")
        else:
            stage.fail(f"canonical_total_ad_spend: expected ~{EXPECTED['total_ad_spend']}, got {total_spend:.2f}")

    # Tenant isolation: no NULL tenant_id rows
    for table in ("analytics.orders", "analytics.marketing_spend"):
        row = _q(cur, f"SELECT count(*) FROM {table} WHERE tenant_id IS NULL")
        short = table.split(".")[1]
        if row is not None and int(row[0]) == 0:
            stage.ok(f"no_null_tenant_in_{short}")
        elif row is not None:
            stage.fail(f"no_null_tenant_in_{short}: {int(row[0])} rows have NULL tenant_id")


# ---------------------------------------------------------------------------
# Stage 5: Mart tables (post-dbt)
# ---------------------------------------------------------------------------


def check_stage_marts(cur, stage: Stage) -> None:
    for mart_table, label in [
        ("marts.mart_marketing_metrics", "mart_marketing_metrics"),
        ("marts.fct_marketing_metrics",  "fct_marketing_metrics"),
    ]:
        row = _q(cur, f"SELECT count(*) FROM {mart_table} WHERE tenant_id = %s", (TENANT_ID,))
        if row is None:
            stage.fail(f"{label}: table not accessible")
            continue
        count = int(row[0])
        if count > 0:
            stage.ok(f"{label}: {count} rows")
        else:
            stage.fail(f"{label}: 0 rows — mart may not have built from seed data")

    # Verify no NULL or Inf ROAS in marts
    for mart_table, label in [
        ("marts.mart_marketing_metrics", "mart_marketing_metrics"),
    ]:
        row = _q(cur,
                 f"""
                 SELECT count(*) FROM {mart_table}
                 WHERE tenant_id = %s
                   AND (net_roas IS NULL
                        OR net_roas = 'Infinity'::numeric
                        OR net_roas = '-Infinity'::numeric)
                 """,
                 (TENANT_ID,))
        if row is not None:
            bad = int(row[0])
            if bad == 0:
                stage.ok(f"{label}_roas_no_null_or_inf")
            else:
                stage.fail(f"{label}_roas_no_null_or_inf: {bad} rows with NULL/Inf ROAS")


# ---------------------------------------------------------------------------
# Stage 6: Metric math spot-checks
# ---------------------------------------------------------------------------


def check_stage_metrics(cur, stage: Stage) -> None:
    # AOV
    row = _q(cur,
             """
             SELECT sum(revenue_net)::numeric / nullif(count(*), 0)
             FROM analytics.orders WHERE tenant_id = %s
             """,
             (TENANT_ID,))
    if row and row[0]:
        aov = _dec(row[0])
        if _approx(aov, _dec(EXPECTED["expected_aov"])):
            stage.ok(f"AOV = {aov:.2f} (expected {EXPECTED['expected_aov']})")
        else:
            stage.fail(f"AOV = {aov:.2f} (expected {EXPECTED['expected_aov']})")
    else:
        stage.fail("AOV: could not compute (check analytics.orders)")

    # ROAS
    row = _q(cur,
             """
             WITH rev AS (
                 SELECT sum(revenue_net) AS total_rev
                 FROM analytics.orders WHERE tenant_id = %s
             ),
             sp AS (
                 SELECT sum(spend) AS total_spend
                 FROM analytics.marketing_spend WHERE tenant_id = %s
             )
             SELECT total_rev / nullif(total_spend, 0) FROM rev CROSS JOIN sp
             """,
             (TENANT_ID, TENANT_ID))
    if row and row[0]:
        roas = _dec(row[0])
        expected_roas = _dec(EXPECTED["expected_roas"])
        if _within(roas, expected_roas):
            stage.ok(f"ROAS = {roas:.4f} (expected ~{expected_roas})")
        else:
            stage.fail(f"ROAS = {roas:.4f} (expected ~{expected_roas})")
    else:
        stage.fail("ROAS: could not compute")

    # CAC
    row = _q(cur,
             """
             WITH first_orders AS (
                 SELECT customer_key, min(order_created_at) AS first_order_at
                 FROM analytics.orders WHERE tenant_id = %s
                 GROUP BY customer_key
             ),
             n_new AS (SELECT count(*) AS n FROM first_orders),
             sp   AS (SELECT sum(spend) AS s FROM analytics.marketing_spend WHERE tenant_id = %s)
             SELECT sp.s / nullif(n_new.n, 0) FROM n_new CROSS JOIN sp
             """,
             (TENANT_ID, TENANT_ID))
    if row and row[0]:
        cac = _dec(row[0])
        expected_cac = _dec(EXPECTED["expected_cac"])
        if _within(cac, expected_cac):
            stage.ok(f"CAC = {cac:.2f} (expected ~{expected_cac})")
        else:
            stage.fail(f"CAC = {cac:.2f} (expected ~{expected_cac})")
    else:
        stage.fail("CAC: could not compute")

    # LTV (revenue_net per unique customer)
    row = _q(cur,
             """
             SELECT sum(revenue_net) / nullif(count(DISTINCT customer_key), 0)
             FROM analytics.orders WHERE tenant_id = %s
             """,
             (TENANT_ID,))
    if row and row[0]:
        ltv = _dec(row[0])
        # Each customer places 5 orders × $175 net = $875 LTV
        expected_ltv = Decimal("875.00")
        if _within(ltv, expected_ltv):
            stage.ok(f"LTV (revenue per customer) = {ltv:.2f} (expected ~{expected_ltv})")
        else:
            stage.fail(f"LTV (revenue per customer) = {ltv:.2f} (expected ~{expected_ltv})")
    else:
        stage.fail("LTV: could not compute")

    # Verify orders financial_status distribution
    row = _q(cur,
             """
             SELECT
                 sum(CASE WHEN financial_status = 'paid'                THEN 1 ELSE 0 END),
                 sum(CASE WHEN financial_status = 'pending'             THEN 1 ELSE 0 END),
                 sum(CASE WHEN financial_status = 'partially_refunded'  THEN 1 ELSE 0 END)
             FROM analytics.orders WHERE tenant_id = %s
             """,
             (TENANT_ID,))
    if row:
        paid, pending, partial = int(row[0] or 0), int(row[1] or 0), int(row[2] or 0)
        expected_dist = (40, 5, 5)
        if (paid, pending, partial) == expected_dist:
            stage.ok(f"order_status_distribution: paid={paid}, pending={pending}, partial_refund={partial}")
        else:
            stage.fail(f"order_status_distribution: expected paid=40/pending=5/partial=5, got {paid}/{pending}/{partial}")


# ---------------------------------------------------------------------------
# Stage 7: Optional API endpoint validation
# ---------------------------------------------------------------------------


def check_stage_api(stage: Stage) -> None:
    api_url = os.environ.get("MARKINSIGHT_API_URL")
    api_token = os.environ.get("MARKINSIGHT_API_TOKEN")
    if not api_url or not api_token:
        stage.ok("api_check_skipped: set MARKINSIGHT_API_URL + MARKINSIGHT_API_TOKEN to enable")
        return

    try:
        import urllib.request
        req = urllib.request.Request(
            f"{api_url.rstrip('/')}/api/health",
            headers={"Authorization": f"Bearer {api_token}"},
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            if resp.status == 200:
                stage.ok(f"api_health: 200 OK from {api_url}/api/health")
            else:
                stage.fail(f"api_health: HTTP {resp.status} from {api_url}/api/health")
    except Exception as e:
        stage.fail(f"api_health: {e}")


# ---------------------------------------------------------------------------
# SQL validation queries printed to stdout for manual inspection
# ---------------------------------------------------------------------------

STAGE_QUERIES: dict[str, str] = {
    "raw_meta_ads_row_count": """
        SELECT count(*) FROM airbyte_raw._airbyte_raw_meta_ads
        WHERE _airbyte_ab_id LIKE 'seed-%';
    """,
    "canonical_orders_summary": """
        SELECT count(*), round(sum(revenue_gross),2), round(sum(revenue_net),2)
        FROM analytics.orders
        WHERE tenant_id = 'test-tenant-seed-001';
    """,
    "canonical_spend_by_platform": """
        SELECT source_platform, round(sum(spend),2) AS total_spend
        FROM analytics.marketing_spend
        WHERE tenant_id = 'test-tenant-seed-001'
        GROUP BY source_platform ORDER BY source_platform;
    """,
    "aov_check": """
        SELECT round(sum(revenue_net)::numeric / nullif(count(*),0), 2) AS aov
        FROM analytics.orders
        WHERE tenant_id = 'test-tenant-seed-001';
        -- Expected: 175.00
    """,
    "roas_check": """
        WITH rev AS (
            SELECT sum(revenue_net) AS r FROM analytics.orders WHERE tenant_id = 'test-tenant-seed-001'
        ),
        sp AS (
            SELECT sum(spend) AS s FROM analytics.marketing_spend WHERE tenant_id = 'test-tenant-seed-001'
        )
        SELECT round(r / nullif(s, 0), 4) AS roas FROM rev CROSS JOIN sp;
        -- Expected: ~2.7411
    """,
    "cac_check": """
        WITH first_orders AS (
            SELECT customer_key FROM analytics.orders
            WHERE tenant_id = 'test-tenant-seed-001'
            GROUP BY customer_key
        ),
        n_new AS (SELECT count(*) AS n FROM first_orders),
        sp AS (SELECT sum(spend) AS s FROM analytics.marketing_spend WHERE tenant_id = 'test-tenant-seed-001')
        SELECT round(s / nullif(n, 0), 2) AS cac FROM n_new CROSS JOIN sp;
        -- Expected: 319.20
    """,
    "idempotency_check": """
        -- Run this query before AND after a second 'dbt run' (incremental).
        -- Row counts must not increase.
        SELECT
            'analytics.orders'          AS table_name, count(*) AS row_count
            FROM analytics.orders WHERE tenant_id = 'test-tenant-seed-001'
        UNION ALL
        SELECT
            'analytics.marketing_spend' AS table_name, count(*) AS row_count
            FROM analytics.marketing_spend WHERE tenant_id = 'test-tenant-seed-001';
    """,
}


# ---------------------------------------------------------------------------
# dbt runner
# ---------------------------------------------------------------------------


def run_dbt_cmd(*args: str, profiles_dir: str, target: str) -> tuple[int, str]:
    cmd = ["dbt", *args, "--profiles-dir", profiles_dir, "--project-dir", str(ANALYTICS_DIR)]
    if target:
        cmd += ["--target", target]
    result = subprocess.run(cmd, capture_output=True, text=True, cwd=ANALYTICS_DIR)
    return result.returncode, result.stdout + result.stderr


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> int:
    parser = argparse.ArgumentParser(
        description="End-to-end pipeline integration test for MarkInsight."
    )
    parser.add_argument("--db-url", default=os.environ.get("DATABASE_URL"))
    parser.add_argument("--profiles-dir", default=str(ANALYTICS_DIR))
    parser.add_argument("--target", default=os.environ.get("DBT_TARGET", "dev"))
    parser.add_argument("--skip-seed",  action="store_true", help="Skip seeding step")
    parser.add_argument("--skip-dbt",   action="store_true", help="Skip dbt run step")
    parser.add_argument("--full-refresh", action="store_true",
                        help="Run dbt with --full-refresh (recommended for first run)")
    parser.add_argument("--keep-data",  action="store_true",
                        help="Do not clean seed data after test")
    parser.add_argument("--print-queries", action="store_true",
                        help="Print reference SQL queries for manual inspection")
    args = parser.parse_args()

    if args.print_queries:
        print("\n=== Reference SQL Queries ===\n")
        for name, query in STAGE_QUERIES.items():
            print(f"-- {name}")
            print(query.strip())
            print()
        return 0

    print("=" * 60)
    print("  MarkInsight Pipeline Integration Test")
    print("=" * 60)

    all_stages: list[Stage] = []

    # -----------------------------------------------------------------------
    # Step 0: Seed data
    # -----------------------------------------------------------------------
    if not args.skip_seed:
        print("\n[Step 0] Seeding raw test data...")
        seed_script = REPO_ROOT / "scripts" / "seed_pipeline_test_data.py"
        seed_cmd = [sys.executable, str(seed_script), "--clean"]
        if args.db_url:
            seed_cmd += ["--db-url", args.db_url]
        rc = subprocess.run(seed_cmd).returncode
        if rc != 0:
            print("ERROR: Seeding failed — aborting integration test.")
            return 1
        print()

    # -----------------------------------------------------------------------
    # Step 1: Validate raw tables immediately after seeding
    # -----------------------------------------------------------------------
    print("\n[Stage 1] Raw tables (airbyte_raw schema)")
    s1 = Stage("raw_tables")
    conn = get_conn(args.db_url)
    try:
        with conn.cursor() as cur:
            check_stage_raw(cur, s1)
            check_stage_platform(cur, s1)
    finally:
        conn.close()
    all_stages.append(s1)
    if not s1.passed:
        print(f"  ABORT: stage 1 failed — seeding prerequisite not met.")
        _print_summary(all_stages)
        return 1

    # -----------------------------------------------------------------------
    # Step 2: Run dbt
    # -----------------------------------------------------------------------
    if not args.skip_dbt:
        dbt_run_args = ["run"]
        if args.full_refresh:
            dbt_run_args.append("--full-refresh")
        print(f"\n[Step 2] Running: dbt {' '.join(dbt_run_args)}")
        rc, output = run_dbt_cmd(
            *dbt_run_args,
            profiles_dir=args.profiles_dir,
            target=args.target,
        )
        if rc != 0:
            # Print last 20 lines of output for context
            for line in output.splitlines()[-20:]:
                print(f"  {line}")
            print(f"\nERROR: dbt run failed (exit {rc})")
            _print_summary(all_stages)
            return 1
        print("  dbt run completed successfully.")

    # -----------------------------------------------------------------------
    # Steps 3–7: Validate transformed data
    # -----------------------------------------------------------------------
    conn = get_conn(args.db_url)
    try:
        with conn.cursor() as cur:
            print("\n[Stage 3] Staging views (post-dbt)")
            s3 = Stage("staging_views")
            check_stage_staging(cur, s3)
            all_stages.append(s3)

            print("\n[Stage 4] Canonical tables (analytics schema)")
            s4 = Stage("canonical_tables")
            check_stage_canonical(cur, s4)
            all_stages.append(s4)

            print("\n[Stage 5] Mart tables (marts schema)")
            s5 = Stage("mart_tables")
            check_stage_marts(cur, s5)
            all_stages.append(s5)

            print("\n[Stage 6] Metric math: AOV, ROAS, CAC, LTV")
            s6 = Stage("metric_math")
            check_stage_metrics(cur, s6)
            all_stages.append(s6)
    finally:
        conn.close()

    print("\n[Stage 7] API endpoint health check")
    s7 = Stage("api_endpoints")
    check_stage_api(s7)
    all_stages.append(s7)

    # -----------------------------------------------------------------------
    # Cleanup (unless --keep-data)
    # -----------------------------------------------------------------------
    if not args.keep_data:
        print("\n[Cleanup] Removing seed data...")
        conn = get_conn(args.db_url)
        try:
            with conn:
                with conn.cursor() as cur:
                    _seeder.clean_seed_data(cur)
            print("  Seed data removed.")
        except Exception as e:
            print(f"  WARNING: cleanup failed: {e}")
        finally:
            conn.close()

    return _print_summary(all_stages)


def _print_summary(stages: list[Stage]) -> int:
    print()
    print("=" * 60)
    print("  Integration Test Summary")
    print("=" * 60)
    total_checks = sum(len(s.checks) for s in stages)
    total_passed = sum(sum(1 for ok, _ in s.checks if ok) for s in stages)
    total_failed = total_checks - total_passed

    for stage in stages:
        status = "PASS" if stage.passed else "FAIL"
        checks = len(stage.checks)
        passed = sum(1 for ok, _ in stage.checks if ok)
        print(f"  [{status}] {stage.name}: {passed}/{checks} checks")
        for label in stage.failures:
            print(f"         ✗ {label}")

    print()
    print(f"  Total: {total_passed}/{total_checks} checks passed")
    print("=" * 60)
    return 0 if total_failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
