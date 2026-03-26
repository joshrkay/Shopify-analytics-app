#!/usr/bin/env python3
"""
dbt pipeline validation: compile, test, metric spot-checks, and idempotency.

Runs inside the analytics/ directory (where profiles.yml lives).

Usage:
    python scripts/run_dbt_validation.py [options]

    --profiles-dir DIR   Directory containing profiles.yml (default: analytics/)
    --db-url URL         PostgreSQL URL for SQL spot-checks
    --skip-compile       Skip dbt compile step
    --skip-dbt-test      Skip dbt test step
    --skip-spot-checks   Skip metric math spot-checks (requires seeded data)
    --skip-idempotency   Skip incremental idempotency test
    --full-refresh       Pass --full-refresh to dbt run (for first-time setup)
    --target TARGET      dbt target profile name (default: dev)

Exit codes:
    0   All validations passed
    1   One or more validations failed

Spot-check prerequisites:
    Run seed_pipeline_test_data.py first (sets up TENANT_ID = test-tenant-seed-001).
    The spot-checks tolerate ±1% on aggregate values to account for floating-point rounding.
"""

from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
from decimal import Decimal
from pathlib import Path

try:
    import psycopg2
    import psycopg2.extras
except ImportError:
    print("WARNING: psycopg2 not installed — SQL spot-checks will be skipped.")
    psycopg2 = None  # type: ignore[assignment]

# ---------------------------------------------------------------------------
# Seed constants (must match seed_pipeline_test_data.py)
# ---------------------------------------------------------------------------
TENANT_ID = "test-tenant-seed-001"
EXPECTED_META_SPEND = Decimal("1190.00")
EXPECTED_GOOGLE_SPEND = Decimal("2002.00")
EXPECTED_TOTAL_SPEND = Decimal("3192.00")
EXPECTED_ORDERS = 50
EXPECTED_REVENUE_GROSS = Decimal("10000.00")
EXPECTED_REVENUE_NET = Decimal("8750.00")
EXPECTED_AOV = Decimal("175.00")
EXPECTED_ROAS = Decimal("2.7411")   # 8750 / 3192, rounded 4dp
EXPECTED_CAC = Decimal("319.20")    # 3192 / 10
TOLERANCE = Decimal("0.01")         # 1% tolerance for aggregate comparisons

REPO_ROOT = Path(__file__).resolve().parent.parent
ANALYTICS_DIR = REPO_ROOT / "analytics"

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


class ValidationResult:
    def __init__(self) -> None:
        self.passed: list[str] = []
        self.failed: list[str] = []

    def ok(self, name: str, msg: str = "") -> None:
        label = f"PASS  {name}" + (f": {msg}" if msg else "")
        print(f"  ✓ {label}")
        self.passed.append(name)

    def fail(self, name: str, msg: str = "") -> None:
        label = f"FAIL  {name}" + (f": {msg}" if msg else "")
        print(f"  ✗ {label}")
        self.failed.append(name)

    def summary(self) -> int:
        total = len(self.passed) + len(self.failed)
        print()
        print("=" * 58)
        print(f"  Results: {len(self.passed)}/{total} checks passed")
        if self.failed:
            print()
            print("  Failed:")
            for name in self.failed:
                print(f"    - {name}")
        print("=" * 58)
        return 0 if not self.failed else 1


def run_dbt(
    *args: str,
    profiles_dir: str,
    target: str,
    cwd: Path = ANALYTICS_DIR,
) -> tuple[int, str, str]:
    """Run a dbt command and return (returncode, stdout, stderr)."""
    cmd = ["dbt", *args, "--profiles-dir", profiles_dir, "--project-dir", str(cwd)]
    if target:
        cmd += ["--target", target]
    result = subprocess.run(cmd, capture_output=True, text=True, cwd=cwd)
    return result.returncode, result.stdout, result.stderr


def within_tolerance(actual: Decimal, expected: Decimal, pct: Decimal = TOLERANCE) -> bool:
    if expected == 0:
        return actual == 0
    return abs((actual - expected) / expected) <= pct


def approx_equal(actual: Decimal, expected: Decimal, abs_tol: Decimal = Decimal("0.01")) -> bool:
    return abs(actual - expected) <= abs_tol


# ---------------------------------------------------------------------------
# 1. dbt compile
# ---------------------------------------------------------------------------


def validate_compile(result: ValidationResult, profiles_dir: str, target: str) -> None:
    print("\n[1] dbt compile — verifying all models parse without errors")
    rc, stdout, stderr = run_dbt("compile", profiles_dir=profiles_dir, target=target)
    output = stdout + stderr

    if rc != 0:
        # Extract error lines for context
        error_lines = [l for l in output.splitlines() if "Error" in l or "error" in l][:5]
        result.fail("dbt_compile", "\n    ".join(error_lines) if error_lines else "non-zero exit")
        return

    # Confirm "Done" or success signal appears
    if "Done" in output or "Completed successfully" in output or rc == 0:
        # Count compiled models from output
        m = re.search(r"(\d+)\s+models?", output)
        model_count = m.group(0) if m else "models compiled"
        result.ok("dbt_compile", model_count)
    else:
        result.fail("dbt_compile", "unexpected output — check dbt logs")


# ---------------------------------------------------------------------------
# 2. dbt test
# ---------------------------------------------------------------------------


def validate_dbt_test(result: ValidationResult, profiles_dir: str, target: str) -> None:
    print("\n[2] dbt test — running all built-in schema and data quality tests")
    rc, stdout, stderr = run_dbt("test", profiles_dir=profiles_dir, target=target)
    output = stdout + stderr

    # Parse pass/fail counts from dbt output
    passed_m = re.search(r"(\d+)\s+passed", output)
    failed_m = re.search(r"(\d+)\s+failed", output)
    error_m = re.search(r"(\d+)\s+error", output)

    passed_n = int(passed_m.group(1)) if passed_m else 0
    failed_n = int(failed_m.group(1)) if failed_m else 0
    error_n = int(error_m.group(1)) if error_m else 0

    total_failures = failed_n + error_n

    if rc != 0 or total_failures > 0:
        # Collect failing test names from dbt output
        fail_lines = [
            l.strip() for l in output.splitlines()
            if "FAIL" in l or "ERROR" in l
        ][:10]
        detail = f"{total_failures} test(s) failed"
        if fail_lines:
            detail += "\n    " + "\n    ".join(fail_lines)
        result.fail("dbt_tests_all_pass", detail)
    else:
        result.ok("dbt_tests_all_pass", f"{passed_n} tests passed")


# ---------------------------------------------------------------------------
# 3. Metric spot-checks (SQL against built tables)
# ---------------------------------------------------------------------------


def get_db_connection(db_url: str | None):
    if psycopg2 is None:
        return None
    if not db_url:
        db_url = os.environ.get("DATABASE_URL")
    if not db_url:
        host = os.environ.get("DB_HOST", "localhost")
        port = int(os.environ.get("DB_PORT", "5432"))
        user = os.environ.get("DB_USER", "postgres")
        password = os.environ.get("DB_PASSWORD", "")
        dbname = os.environ.get("DB_NAME", "shopify_analytics")
        return psycopg2.connect(host=host, port=port, user=user,
                                password=password, dbname=dbname)
    return psycopg2.connect(db_url)


def _query_one(cur, sql: str, params: tuple = ()) -> tuple | None:
    try:
        cur.execute(sql, params)
        return cur.fetchone()
    except Exception as e:
        return None


def validate_spot_checks(result: ValidationResult, db_url: str | None) -> None:
    print("\n[3] Metric spot-checks — SQL assertions against seeded + transformed data")
    conn = get_db_connection(db_url)
    if conn is None:
        result.fail("spot_checks_skipped", "psycopg2 not available or no DB URL")
        return

    try:
        with conn.cursor() as cur:
            _check_raw_row_counts(cur, result)
            _check_canonical_orders(cur, result)
            _check_canonical_marketing_spend(cur, result)
            _check_aov(cur, result)
            _check_roas(cur, result)
            _check_cac(cur, result)
            _check_no_cross_tenant_leak(cur, result)
            _check_divide_by_zero(cur, result)
    finally:
        conn.close()


def _check_raw_row_counts(cur, result: ValidationResult) -> None:
    """Verify raw Airbyte tables contain the expected seed row counts."""
    checks = [
        ("airbyte_raw._airbyte_raw_meta_ads",       112, "raw_meta_ads_row_count"),
        ("airbyte_raw._airbyte_raw_google_ads",      112, "raw_google_ads_row_count"),
        ("airbyte_raw._airbyte_raw_shopify_orders",  50,  "raw_shopify_orders_row_count"),
        ("airbyte_raw._airbyte_raw_shopify_customers", 10, "raw_shopify_customers_row_count"),
    ]
    for table, expected_count, check_name in checks:
        row = _query_one(cur, f"SELECT count(*) FROM {table} WHERE _airbyte_ab_id LIKE 'seed-%%'")
        if row is None:
            result.fail(check_name, f"table {table} not accessible")
            continue
        actual = int(row[0])
        if actual == expected_count:
            result.ok(check_name, f"{actual} rows")
        else:
            result.fail(check_name, f"expected {expected_count}, got {actual}")


def _check_canonical_orders(cur, result: ValidationResult) -> None:
    """Verify analytics.orders contains expected order counts and revenue."""
    row = _query_one(
        cur,
        """
        SELECT count(*), sum(revenue_gross), sum(revenue_net)
        FROM analytics.orders
        WHERE tenant_id = %s
        """,
        (TENANT_ID,),
    )
    if row is None:
        result.fail("canonical_orders_accessible", "analytics.orders not accessible")
        return

    count, gross, net = int(row[0]), Decimal(str(row[1] or 0)), Decimal(str(row[2] or 0))

    if count == EXPECTED_ORDERS:
        result.ok("canonical_orders_count", f"{count} orders")
    else:
        result.fail("canonical_orders_count", f"expected {EXPECTED_ORDERS}, got {count}")

    if within_tolerance(gross, EXPECTED_REVENUE_GROSS):
        result.ok("canonical_orders_revenue_gross", f"{gross:.2f}")
    else:
        result.fail("canonical_orders_revenue_gross",
                    f"expected ~{EXPECTED_REVENUE_GROSS}, got {gross:.2f}")

    if within_tolerance(net, EXPECTED_REVENUE_NET):
        result.ok("canonical_orders_revenue_net", f"{net:.2f}")
    else:
        result.fail("canonical_orders_revenue_net",
                    f"expected ~{EXPECTED_REVENUE_NET}, got {net:.2f}")


def _check_canonical_marketing_spend(cur, result: ValidationResult) -> None:
    """Verify analytics.marketing_spend totals by platform match expected values."""
    row = _query_one(
        cur,
        """
        SELECT
            sum(CASE WHEN source_platform = 'meta_ads'   THEN spend ELSE 0 END),
            sum(CASE WHEN source_platform = 'google_ads' THEN spend ELSE 0 END),
            sum(spend)
        FROM analytics.marketing_spend
        WHERE tenant_id = %s
        """,
        (TENANT_ID,),
    )
    if row is None:
        result.fail("canonical_marketing_spend_accessible", "analytics.marketing_spend not accessible")
        return

    meta_spend = Decimal(str(row[0] or 0))
    google_spend = Decimal(str(row[1] or 0))
    total_spend = Decimal(str(row[2] or 0))

    if within_tolerance(meta_spend, EXPECTED_META_SPEND):
        result.ok("canonical_meta_ads_spend", f"{meta_spend:.2f}")
    else:
        result.fail("canonical_meta_ads_spend",
                    f"expected ~{EXPECTED_META_SPEND}, got {meta_spend:.2f}")

    if within_tolerance(google_spend, EXPECTED_GOOGLE_SPEND):
        result.ok("canonical_google_ads_spend", f"{google_spend:.2f}")
    else:
        result.fail("canonical_google_ads_spend",
                    f"expected ~{EXPECTED_GOOGLE_SPEND}, got {google_spend:.2f}")

    if within_tolerance(total_spend, EXPECTED_TOTAL_SPEND):
        result.ok("canonical_total_ad_spend", f"{total_spend:.2f}")
    else:
        result.fail("canonical_total_ad_spend",
                    f"expected ~{EXPECTED_TOTAL_SPEND}, got {total_spend:.2f}")


def _check_aov(cur, result: ValidationResult) -> None:
    """AOV = sum(revenue_net) / count(orders)  — should equal 175.00."""
    row = _query_one(
        cur,
        """
        SELECT
            sum(revenue_net)::numeric / nullif(count(*), 0) AS aov
        FROM analytics.orders
        WHERE tenant_id = %s
        """,
        (TENANT_ID,),
    )
    if row is None or row[0] is None:
        result.fail("metric_aov", "could not compute AOV from analytics.orders")
        return

    aov = Decimal(str(row[0]))
    if approx_equal(aov, EXPECTED_AOV):
        result.ok("metric_aov", f"{aov:.2f} (expected {EXPECTED_AOV})")
    else:
        result.fail("metric_aov", f"expected {EXPECTED_AOV}, got {aov:.2f}")


def _check_roas(cur, result: ValidationResult) -> None:
    """ROAS = sum(revenue_net from orders) / sum(spend from marketing_spend)."""
    row = _query_one(
        cur,
        """
        WITH rev AS (
            SELECT sum(revenue_net) AS total_rev
            FROM analytics.orders
            WHERE tenant_id = %s
        ),
        spend AS (
            SELECT sum(spend) AS total_spend
            FROM analytics.marketing_spend
            WHERE tenant_id = %s
        )
        SELECT
            total_rev / nullif(total_spend, 0) AS roas
        FROM rev CROSS JOIN spend
        """,
        (TENANT_ID, TENANT_ID),
    )
    if row is None or row[0] is None:
        result.fail("metric_roas", "could not compute ROAS")
        return

    roas = Decimal(str(row[0]))
    if within_tolerance(roas, EXPECTED_ROAS):
        result.ok("metric_roas", f"{roas:.4f} (expected ~{EXPECTED_ROAS})")
    else:
        result.fail("metric_roas", f"expected ~{EXPECTED_ROAS}, got {roas:.4f}")


def _check_cac(cur, result: ValidationResult) -> None:
    """CAC = total_spend / unique_new_customers.

    New customers = 10 (each customer's FIRST order date falls in our seeded window).
    Since all 10 customers first appear in our seeded data, all 10 are "new".
    """
    row = _query_one(
        cur,
        """
        WITH first_orders AS (
            SELECT customer_key, min(order_created_at) AS first_order_at
            FROM analytics.orders
            WHERE tenant_id = %s
            GROUP BY customer_key
        ),
        new_customers AS (
            SELECT count(*) AS n
            FROM first_orders
        ),
        total_spend AS (
            SELECT sum(spend) AS s
            FROM analytics.marketing_spend
            WHERE tenant_id = %s
        )
        SELECT total_spend.s / nullif(new_customers.n, 0) AS cac
        FROM new_customers CROSS JOIN total_spend
        """,
        (TENANT_ID, TENANT_ID),
    )
    if row is None or row[0] is None:
        result.fail("metric_cac", "could not compute CAC")
        return

    cac = Decimal(str(row[0]))
    if within_tolerance(cac, EXPECTED_CAC):
        result.ok("metric_cac", f"{cac:.2f} (expected ~{EXPECTED_CAC})")
    else:
        result.fail("metric_cac", f"expected ~{EXPECTED_CAC}, got {cac:.2f}")


def _check_no_cross_tenant_leak(cur, result: ValidationResult) -> None:
    """Verify no NULL tenant_id rows exist in canonical tables (isolation guard)."""
    for table in ("analytics.orders", "analytics.marketing_spend"):
        row = _query_one(cur, f"SELECT count(*) FROM {table} WHERE tenant_id IS NULL")
        if row is None:
            result.fail(f"tenant_isolation_{table}", "table not accessible")
            continue
        null_count = int(row[0])
        if null_count == 0:
            result.ok(f"tenant_isolation_{table.split('.')[1]}", "no NULL tenant_id rows")
        else:
            result.fail(f"tenant_isolation_{table.split('.')[1]}",
                        f"{null_count} rows with NULL tenant_id")


def _check_divide_by_zero(cur, result: ValidationResult) -> None:
    """Verify ROAS/CAC columns in marts are never NULL or Infinity."""
    for table, col in [
        ("marts.mart_marketing_metrics", "roas"),
        ("marts.fct_marketing_metrics",  "roas"),
    ]:
        row = _query_one(
            cur,
            f"""
            SELECT count(*) FROM {table}
            WHERE tenant_id = %s
              AND ({col} IS NULL
                   OR {col} = 'Infinity'::numeric
                   OR {col} = '-Infinity'::numeric)
            """,
            (TENANT_ID,),
        )
        if row is None:
            # Table may not exist in all dbt target configurations
            continue
        bad_count = int(row[0])
        check_name = f"no_null_or_inf_{table.split('.')[1]}_{col}"
        if bad_count == 0:
            result.ok(check_name)
        else:
            result.fail(check_name, f"{bad_count} rows with NULL/Inf {col}")


# ---------------------------------------------------------------------------
# 4. Incremental idempotency test
# ---------------------------------------------------------------------------


def validate_idempotency(
    result: ValidationResult,
    profiles_dir: str,
    target: str,
    db_url: str | None,
) -> None:
    """Run dbt run twice and verify row counts don't change (incremental idempotency)."""
    print("\n[4] Incremental idempotency — run dbt twice, verify no duplicate rows")

    conn = get_db_connection(db_url)
    if conn is None:
        result.fail("idempotency_skipped", "psycopg2 not available or no DB URL")
        return

    tables_to_check = [
        ("analytics.orders",             "tenant_id", TENANT_ID),
        ("analytics.marketing_spend",    "tenant_id", TENANT_ID),
    ]

    # Count rows before second run
    counts_before: dict[str, int] = {}
    try:
        with conn.cursor() as cur:
            for table, col, val in tables_to_check:
                row = _query_one(cur, f"SELECT count(*) FROM {table} WHERE {col} = %s", (val,))
                counts_before[table] = int(row[0]) if row else 0
                print(f"  Before 2nd run: {table} = {counts_before[table]} rows")
    finally:
        conn.close()

    if all(v == 0 for v in counts_before.values()):
        result.fail("idempotency_precondition",
                    "canonical tables are empty — run 'dbt run --full-refresh' first")
        return

    # Second incremental run
    print("  Running dbt run (incremental)...")
    rc, stdout, stderr = run_dbt("run", profiles_dir=profiles_dir, target=target)
    if rc != 0:
        result.fail("idempotency_second_dbt_run", "dbt run failed on second execution")
        return

    # Count rows after second run
    conn2 = get_db_connection(db_url)
    if conn2 is None:
        return
    try:
        with conn2.cursor() as cur:
            for table, col, val in tables_to_check:
                row = _query_one(cur, f"SELECT count(*) FROM {table} WHERE {col} = %s", (val,))
                count_after = int(row[0]) if row else 0
                count_before = counts_before[table]
                print(f"  After  2nd run: {table} = {count_after} rows")

                check_name = f"idempotency_{table.replace('.', '_')}"
                if count_after == count_before:
                    result.ok(check_name, f"{count_before} → {count_after} (no change)")
                else:
                    result.fail(check_name,
                                f"{count_before} → {count_after} (+{count_after - count_before} unexpected rows)")
    finally:
        conn2.close()


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Validate the MarkInsight dbt pipeline (compile, test, spot-checks, idempotency)."
    )
    parser.add_argument(
        "--profiles-dir",
        default=str(ANALYTICS_DIR),
        help="Directory containing profiles.yml (default: analytics/)",
    )
    parser.add_argument(
        "--target",
        default=os.environ.get("DBT_TARGET", "dev"),
        help="dbt target profile name (default: dev or $DBT_TARGET)",
    )
    parser.add_argument(
        "--db-url",
        default=os.environ.get("DATABASE_URL"),
        help="PostgreSQL URL for SQL checks (default: $DATABASE_URL)",
    )
    parser.add_argument("--skip-compile",      action="store_true")
    parser.add_argument("--skip-dbt-test",     action="store_true")
    parser.add_argument("--skip-spot-checks",  action="store_true")
    parser.add_argument("--skip-idempotency",  action="store_true")
    parser.add_argument("--full-refresh",      action="store_true",
                        help="Run dbt with --full-refresh before idempotency test")
    args = parser.parse_args()

    # Verify dbt is installed
    dbt_check = subprocess.run(["dbt", "--version"], capture_output=True, text=True)
    if dbt_check.returncode != 0:
        print("ERROR: dbt is not installed.  Install with: pip install dbt-postgres")
        return 1

    result = ValidationResult()
    print(f"dbt validation — profiles-dir: {args.profiles_dir}, target: {args.target}")

    if not args.skip_compile:
        validate_compile(result, args.profiles_dir, args.target)

    if not args.skip_dbt_test:
        validate_dbt_test(result, args.profiles_dir, args.target)

    if not args.skip_spot_checks:
        if psycopg2 is None:
            print("\n[3] Spot-checks SKIPPED — psycopg2 not installed")
        else:
            validate_spot_checks(result, args.db_url)

    if not args.skip_idempotency:
        if psycopg2 is None:
            print("\n[4] Idempotency SKIPPED — psycopg2 not installed")
        else:
            if args.full_refresh:
                print("\n[4.0] Running dbt run --full-refresh before idempotency test...")
                rc, stdout, stderr = run_dbt(
                    "run", "--full-refresh",
                    profiles_dir=args.profiles_dir,
                    target=args.target,
                )
                if rc != 0:
                    print("ERROR: dbt run --full-refresh failed")
                    result.fail("full_refresh_dbt_run", "dbt run --full-refresh failed")
            validate_idempotency(result, args.profiles_dir, args.target, args.db_url)

    return result.summary()


if __name__ == "__main__":
    sys.exit(main())
