#!/usr/bin/env python3
"""
Seed fake but realistic test data into the PostgreSQL analytics warehouse.

Simulates what Airbyte would sync from Meta Ads, Google Ads, and Shopify.
Creates all tables required by dbt source definitions if they don't already exist.

Usage:
    python scripts/seed_pipeline_test_data.py [--db-url URL] [--clean] [--show-expected]

Environment:
    DATABASE_URL  — PostgreSQL connection string (fallback if --db-url not given)
    DB_HOST, DB_PORT, DB_USER, DB_PASSWORD, DB_NAME  — alternative connection params

After seeding, the following expected metric values can be used in integration tests:

  Tenant:            test-tenant-seed-001
  Shop domain:       seed-store.myshopify.com
  Date range:        14 days ending 2 days ago (relative to today)

  Meta Ads spend:    $1,190.00  (85.00/day × 14 days, 8 ad rows/day × 2 campaigns)
  Google Ads spend:  $2,002.00  (143.00/day × 14 days, 8 ad rows/day × 2 campaigns)
  Total ad spend:    $3,192.00

  Shopify orders:    50 (40 paid, 5 pending, 5 partially_refunded)
  Revenue gross:     $10,000.00  (50 × $200.00)
  Revenue net:       $8,750.00   (50 × $175.00 subtotal)
  Unique customers:  10

  Expected ROAS:     8750.00 / 3192.00 ≈ 2.7411
  Expected AOV:      8750.00 / 50 = $175.00
  Expected CAC:      3192.00 / 10 = $319.20
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import uuid
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

try:
    import psycopg2
    import psycopg2.extras
except ImportError:
    print("ERROR: psycopg2 is required.  Install with: pip install psycopg2-binary")
    sys.exit(1)

# ---------------------------------------------------------------------------
# Deterministic seed constants — never change these without updating tests
# ---------------------------------------------------------------------------

TENANT_ID = "test-tenant-seed-001"
SHOP_DOMAIN = "seed-store.myshopify.com"
META_ADS_ACCOUNT_ID = "422959152328586"   # bare numeric (act_ prefix added in raw data)
GOOGLE_ADS_CUSTOMER_ID = "1234567890"

END_DATE = date.today() - timedelta(days=2)    # 2-day buffer avoids freshness warnings
START_DATE = END_DATE - timedelta(days=13)      # 14 days inclusive
DATE_RANGE = [START_DATE + timedelta(days=i) for i in range(14)]

EMITTED_AT = datetime.now(timezone.utc)         # single emission timestamp for all rows

# ----- Meta Ads: 2 campaigns × 2 adsets × 2 ads = 8 rows/day -----
# fmt: off
META_ADS_ROWS = [
    # campaign_id, campaign_name, adset_id, adset_name, ad_id, ad_name, spend, imp, clicks, conv, conv_val
    ("meta_camp_001","Brand Awareness","meta_adset_001","Lookalike Audience","meta_ad_001","Brand Ad 1",  10.00, 500, 25, 2.0, 150.00),
    ("meta_camp_001","Brand Awareness","meta_adset_001","Lookalike Audience","meta_ad_002","Brand Ad 2",   8.00, 400, 20, 1.5, 120.00),
    ("meta_camp_001","Brand Awareness","meta_adset_002","Interest Targeting","meta_ad_003","Brand Ad 3",  12.00, 600, 30, 2.5, 180.00),
    ("meta_camp_001","Brand Awareness","meta_adset_002","Interest Targeting","meta_ad_004","Brand Ad 4",   9.00, 450, 22, 1.8, 140.00),
    ("meta_camp_002","Retargeting",    "meta_adset_003","Cart Abandoners",   "meta_ad_005","Retarg Ad 1", 15.00, 300, 35, 5.0, 400.00),
    ("meta_camp_002","Retargeting",    "meta_adset_003","Cart Abandoners",   "meta_ad_006","Retarg Ad 2", 11.00, 250, 28, 3.5, 280.00),
    ("meta_camp_002","Retargeting",    "meta_adset_004","Past Purchasers",   "meta_ad_007","Retarg Ad 3", 13.00, 280, 32, 4.0, 320.00),
    ("meta_camp_002","Retargeting",    "meta_adset_004","Past Purchasers",   "meta_ad_008","Retarg Ad 4",  7.00, 200, 18, 2.0, 160.00),
]
# Per-day spend: 10+8+12+9+15+11+13+7 = 85.00  →  total 14 days = 1190.00

# ----- Google Ads: 2 campaigns × 2 ad groups × 2 ads = 8 rows/day -----
GOOGLE_ADS_ROWS = [
    # campaign_id, campaign_name, ad_group_id, ad_group_name, ad_id, spend (cost), imp, clicks, conv, conv_val
    ("goog_camp_001","Search Brand","goog_adgrp_001","Brand Terms",   "goog_ad_001", 20.00, 200, 40, 4.0, 300.00),
    ("goog_camp_001","Search Brand","goog_adgrp_001","Brand Terms",   "goog_ad_002", 15.00, 150, 30, 3.0, 225.00),
    ("goog_camp_001","Search Brand","goog_adgrp_002","Product Terms", "goog_ad_003", 18.00, 180, 36, 3.5, 265.00),
    ("goog_camp_001","Search Brand","goog_adgrp_002","Product Terms", "goog_ad_004", 12.00, 120, 24, 2.5, 190.00),
    ("goog_camp_002","Shopping",    "goog_adgrp_003","All Products",  "goog_ad_005", 25.00, 250, 50, 5.0, 400.00),
    ("goog_camp_002","Shopping",    "goog_adgrp_003","All Products",  "goog_ad_006", 17.00, 170, 34, 4.0, 320.00),
    ("goog_camp_002","Shopping",    "goog_adgrp_004","Top Products",  "goog_ad_007", 22.00, 220, 44, 4.5, 360.00),
    ("goog_camp_002","Shopping",    "goog_adgrp_004","Top Products",  "goog_ad_008", 14.00, 140, 28, 3.0, 240.00),
]
# Per-day spend: 20+15+18+12+25+17+22+14 = 143.00  →  total 14 days = 2002.00
# fmt: on

# ----- Shopify: 10 customers, each places 5 orders = 50 orders -----
CUSTOMERS = [
    {
        "id": f"cust_{i:04d}",
        "email": f"customer{i}@seed-example.com",
        "first_name": f"Seed{i}",
        "last_name": "Tester",
    }
    for i in range(1, 11)
]

# 50 orders: 40 paid, 5 pending, 5 partially_refunded
_STATUS_LIST = ["paid"] * 40 + ["pending"] * 5 + ["partially_refunded"] * 5

ORDERS: list[dict] = []
for _i in range(50):
    _order_num = 1001 + _i
    _customer = CUSTOMERS[_i % 10]
    _order_date = DATE_RANGE[_i % 14]
    _status = _STATUS_LIST[_i]
    _ts = datetime(_order_date.year, _order_date.month, _order_date.day, 10, 0, 0, tzinfo=timezone.utc)
    ORDERS.append(
        {
            "id": f"ord_{_order_num:06d}",
            "name": f"#{_order_num}",
            "order_number": str(_order_num),
            "email": _customer["email"],
            "customer": {"id": _customer["id"], "email": _customer["email"]},
            "created_at": _ts.isoformat(),
            "updated_at": _ts.isoformat(),
            "cancelled_at": None,
            "closed_at": None,
            "financial_status": _status,
            "fulfillment_status": "fulfilled" if _status == "paid" else "unfulfilled",
            "total_price": "200.00",
            "subtotal_price": "175.00",
            "total_tax": "25.00",
            "currency": "USD",
            "tags": "seed-data,pipeline-test",
            "note": None,
            "shop_url": f"https://{SHOP_DOMAIN}",
            "total_shipping_price_set": {"shop_money": {"amount": "10.00", "currency_code": "USD"}},
            "refunds": (
                []
                if _status != "partially_refunded"
                else [{"id": "ref_auto", "amount": "20.00"}]
            ),
        }
    )

# Computed expected values (deterministic from seed constants above)
EXPECTED = {
    "tenant_id": TENANT_ID,
    "shop_domain": SHOP_DOMAIN,
    "date_range_start": str(START_DATE),
    "date_range_end": str(END_DATE),
    "meta_ads_raw_rows": len(META_ADS_ROWS) * len(DATE_RANGE),
    "google_ads_raw_rows": len(GOOGLE_ADS_ROWS) * len(DATE_RANGE),
    "shopify_orders_raw_rows": len(ORDERS),
    "shopify_customers_raw_rows": len(CUSTOMERS),
    "meta_ads_daily_spend": 85.00,
    "meta_ads_total_spend": 85.00 * 14,          # 1190.00
    "google_ads_daily_spend": 143.00,
    "google_ads_total_spend": 143.00 * 14,        # 2002.00
    "total_ad_spend": 85.00 * 14 + 143.00 * 14,  # 3192.00
    "total_orders": 50,
    "total_revenue_gross": 50 * 200.00,           # 10000.00
    "total_revenue_net": 50 * 175.00,             # 8750.00
    "unique_customers": 10,
    "expected_aov": 175.00,
    "expected_roas": round(50 * 175.00 / (85.00 * 14 + 143.00 * 14), 4),  # ~2.7411
    "expected_cac": round((85.00 * 14 + 143.00 * 14) / 10, 2),            # 319.20
}

# ---------------------------------------------------------------------------
# DDL — minimal column sets required by dbt models
# ---------------------------------------------------------------------------

DDL = {
    "platform": {
        "shopify_stores": """
            CREATE TABLE IF NOT EXISTS platform.shopify_stores (
                id              TEXT NOT NULL PRIMARY KEY,
                tenant_id       TEXT NOT NULL,
                shop_domain     TEXT NOT NULL,
                timezone        TEXT,
                status          TEXT NOT NULL DEFAULT 'active',
                currency        TEXT,
                country         TEXT
            )
        """,
        "tenant_airbyte_connections": """
            CREATE TABLE IF NOT EXISTS platform.tenant_airbyte_connections (
                airbyte_connection_id TEXT NOT NULL PRIMARY KEY,
                tenant_id             TEXT NOT NULL,
                source_type           TEXT NOT NULL,
                connection_name       TEXT,
                status                TEXT NOT NULL DEFAULT 'active',
                is_enabled            BOOLEAN NOT NULL DEFAULT TRUE,
                configuration         JSONB
            )
        """,
    },
    "airbyte_raw": {
        "_airbyte_raw_shopify_orders": """
            CREATE TABLE IF NOT EXISTS airbyte_raw._airbyte_raw_shopify_orders (
                _airbyte_ab_id      TEXT NOT NULL PRIMARY KEY,
                _airbyte_emitted_at TIMESTAMPTZ NOT NULL,
                _airbyte_data       JSONB NOT NULL
            )
        """,
        "_airbyte_raw_shopify_customers": """
            CREATE TABLE IF NOT EXISTS airbyte_raw._airbyte_raw_shopify_customers (
                _airbyte_ab_id      TEXT NOT NULL PRIMARY KEY,
                _airbyte_emitted_at TIMESTAMPTZ NOT NULL,
                _airbyte_data       JSONB NOT NULL
            )
        """,
        "_airbyte_raw_meta_ads": """
            CREATE TABLE IF NOT EXISTS airbyte_raw._airbyte_raw_meta_ads (
                _airbyte_ab_id      TEXT NOT NULL PRIMARY KEY,
                _airbyte_emitted_at TIMESTAMPTZ NOT NULL,
                _airbyte_data       JSONB NOT NULL
            )
        """,
        "_airbyte_raw_google_ads": """
            CREATE TABLE IF NOT EXISTS airbyte_raw._airbyte_raw_google_ads (
                _airbyte_ab_id      TEXT NOT NULL PRIMARY KEY,
                _airbyte_emitted_at TIMESTAMPTZ NOT NULL,
                _airbyte_data       JSONB NOT NULL
            )
        """,
    },
}

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_ab_id(prefix: str, *parts: str) -> str:
    """Deterministic Airbyte-style record ID from a prefix + natural key."""
    key = "|".join(str(p) for p in parts)
    return f"seed-{prefix}-{uuid.uuid5(uuid.NAMESPACE_DNS, key)}"


def get_connection(db_url: str | None) -> psycopg2.extensions.connection:
    if db_url:
        return psycopg2.connect(db_url)
    # Fall back to individual env vars
    host = os.environ.get("DB_HOST", "localhost")
    port = int(os.environ.get("DB_PORT", "5432"))
    user = os.environ.get("DB_USER", "postgres")
    password = os.environ.get("DB_PASSWORD", "")
    dbname = os.environ.get("DB_NAME", "shopify_analytics")
    return psycopg2.connect(host=host, port=port, user=user, password=password, dbname=dbname)


def ensure_schemas(cur: psycopg2.extensions.cursor) -> None:
    for schema in ("platform", "airbyte_raw"):
        cur.execute(f"CREATE SCHEMA IF NOT EXISTS {schema}")


def ensure_tables(cur: psycopg2.extensions.cursor) -> None:
    for schema, tables in DDL.items():
        for _table_name, ddl in tables.items():
            cur.execute(ddl)


def clean_seed_data(cur: psycopg2.extensions.cursor) -> None:
    """Remove all rows inserted by this seeder (identified by tenant_id / seed prefix)."""
    print("  Cleaning existing seed data...")
    cur.execute(
        "DELETE FROM platform.shopify_stores WHERE tenant_id = %s",
        (TENANT_ID,),
    )
    cur.execute(
        "DELETE FROM platform.tenant_airbyte_connections WHERE tenant_id = %s",
        (TENANT_ID,),
    )
    # Airbyte raw rows: keyed by our deterministic seed- prefix
    for table in (
        "airbyte_raw._airbyte_raw_shopify_orders",
        "airbyte_raw._airbyte_raw_shopify_customers",
        "airbyte_raw._airbyte_raw_meta_ads",
        "airbyte_raw._airbyte_raw_google_ads",
    ):
        cur.execute(f"DELETE FROM {table} WHERE _airbyte_ab_id LIKE 'seed-%%'")  # noqa: E501


# ---------------------------------------------------------------------------
# Seed functions
# ---------------------------------------------------------------------------


def seed_platform_tables(cur: psycopg2.extensions.cursor) -> None:
    print("  Seeding platform.shopify_stores...")
    cur.execute(
        """
        INSERT INTO platform.shopify_stores (id, tenant_id, shop_domain, timezone, status, currency, country)
        VALUES (%s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (id) DO UPDATE SET
            tenant_id   = EXCLUDED.tenant_id,
            shop_domain = EXCLUDED.shop_domain,
            timezone    = EXCLUDED.timezone,
            status      = EXCLUDED.status
        """,
        ("store-seed-001", TENANT_ID, SHOP_DOMAIN, "America/New_York", "active", "USD", "US"),
    )

    print("  Seeding platform.tenant_airbyte_connections (3 connections)...")
    connections = [
        (
            "conn-shopify-seed-001",
            TENANT_ID,
            "shopify",
            "Seed Shopify Store",
            "active",
            True,
            json.dumps({"shop_domain": SHOP_DOMAIN}),
        ),
        (
            "conn-meta-seed-001",
            TENANT_ID,
            "source-facebook-marketing",
            "Seed Meta Ads Account",
            "active",
            True,
            json.dumps({"account_id": META_ADS_ACCOUNT_ID}),
        ),
        (
            "conn-google-seed-001",
            TENANT_ID,
            "source-google-ads",
            "Seed Google Ads Account",
            "active",
            True,
            json.dumps({"customer_id": GOOGLE_ADS_CUSTOMER_ID}),
        ),
    ]
    cur.executemany(
        """
        INSERT INTO platform.tenant_airbyte_connections
            (airbyte_connection_id, tenant_id, source_type, connection_name, status, is_enabled, configuration)
        VALUES (%s, %s, %s, %s, %s, %s, %s::jsonb)
        ON CONFLICT (airbyte_connection_id) DO UPDATE SET
            tenant_id   = EXCLUDED.tenant_id,
            source_type = EXCLUDED.source_type,
            status      = EXCLUDED.status,
            is_enabled  = EXCLUDED.is_enabled,
            configuration = EXCLUDED.configuration
        """,
        connections,
    )


def seed_meta_ads(cur: psycopg2.extensions.cursor) -> None:
    rows = []
    for spend_date in DATE_RANGE:
        date_str = str(spend_date)
        for (camp_id, camp_name, adset_id, adset_name, ad_id, ad_name,
             spend, impressions, clicks, conversions, conv_value) in META_ADS_ROWS:
            ab_id = _make_ab_id("meta", camp_id, adset_id, ad_id, date_str)
            payload = {
                "account_id": f"act_{META_ADS_ACCOUNT_ID}",  # with act_ prefix as Meta returns it
                "campaign_id": camp_id,
                "adset_id": adset_id,
                "ad_id": ad_id,
                "date_start": date_str,
                "date_stop": date_str,
                "spend": str(spend),
                "impressions": str(impressions),
                "clicks": str(clicks),
                "conversions": str(conversions),
                "conversion_value": str(conv_value),
                "currency": "USD",
                "campaign_name": camp_name,
                "adset_name": adset_name,
                "ad_name": ad_name,
                "objective": "OUTCOME_SALES",
                "reach": str(int(impressions * 0.9)),
                "frequency": "1.11",
                "placement": "feed",
            }
            rows.append((ab_id, EMITTED_AT, json.dumps(payload)))

    print(f"  Seeding airbyte_raw._airbyte_raw_meta_ads ({len(rows)} rows)...")
    psycopg2.extras.execute_batch(
        cur,
        """
        INSERT INTO airbyte_raw._airbyte_raw_meta_ads (_airbyte_ab_id, _airbyte_emitted_at, _airbyte_data)
        VALUES (%s, %s, %s::jsonb)
        ON CONFLICT (_airbyte_ab_id) DO UPDATE SET
            _airbyte_emitted_at = EXCLUDED._airbyte_emitted_at,
            _airbyte_data       = EXCLUDED._airbyte_data
        """,
        rows,
        page_size=100,
    )


def seed_google_ads(cur: psycopg2.extensions.cursor) -> None:
    rows = []
    for spend_date in DATE_RANGE:
        date_str = str(spend_date)
        for (camp_id, camp_name, adgrp_id, adgrp_name, ad_id,
             spend, impressions, clicks, conversions, conv_value) in GOOGLE_ADS_ROWS:
            ab_id = _make_ab_id("google", camp_id, adgrp_id, ad_id, date_str)
            payload = {
                "customer_id": GOOGLE_ADS_CUSTOMER_ID,
                "campaign_id": camp_id,
                "ad_group_id": adgrp_id,
                "ad_id": ad_id,
                "date": date_str,
                # Use cost (decimal), not cost_micros, for simplicity
                "cost": str(spend),
                "cost_micros": None,
                "impressions": str(impressions),
                "clicks": str(clicks),
                "conversions": str(conversions),
                "conversion_value": str(conv_value),
                "currency_code": "USD",
                "campaign_name": camp_name,
                "ad_group_name": adgrp_name,
                "ad_type": "EXPANDED_TEXT_AD",
                "device": "DESKTOP",
                "network": "search",
            }
            rows.append((ab_id, EMITTED_AT, json.dumps(payload)))

    print(f"  Seeding airbyte_raw._airbyte_raw_google_ads ({len(rows)} rows)...")
    psycopg2.extras.execute_batch(
        cur,
        """
        INSERT INTO airbyte_raw._airbyte_raw_google_ads (_airbyte_ab_id, _airbyte_emitted_at, _airbyte_data)
        VALUES (%s, %s, %s::jsonb)
        ON CONFLICT (_airbyte_ab_id) DO UPDATE SET
            _airbyte_emitted_at = EXCLUDED._airbyte_emitted_at,
            _airbyte_data       = EXCLUDED._airbyte_data
        """,
        rows,
        page_size=100,
    )


def seed_shopify_orders(cur: psycopg2.extensions.cursor) -> None:
    rows = []
    for order in ORDERS:
        ab_id = _make_ab_id("shopify-order", order["id"])
        rows.append((ab_id, EMITTED_AT, json.dumps(order)))

    print(f"  Seeding airbyte_raw._airbyte_raw_shopify_orders ({len(rows)} rows)...")
    psycopg2.extras.execute_batch(
        cur,
        """
        INSERT INTO airbyte_raw._airbyte_raw_shopify_orders (_airbyte_ab_id, _airbyte_emitted_at, _airbyte_data)
        VALUES (%s, %s, %s::jsonb)
        ON CONFLICT (_airbyte_ab_id) DO UPDATE SET
            _airbyte_emitted_at = EXCLUDED._airbyte_emitted_at,
            _airbyte_data       = EXCLUDED._airbyte_data
        """,
        rows,
        page_size=100,
    )


def seed_shopify_customers(cur: psycopg2.extensions.cursor) -> None:
    rows = []
    created_ts = datetime(START_DATE.year, START_DATE.month, START_DATE.day,
                          9, 0, 0, tzinfo=timezone.utc)
    for customer in CUSTOMERS:
        ab_id = _make_ab_id("shopify-customer", customer["id"])
        payload = {
            **customer,
            "shop_url": f"https://{SHOP_DOMAIN}",
            "created_at": created_ts.isoformat(),
            "updated_at": created_ts.isoformat(),
            "phone": None,
            "verified_email": True,
            "tags": "seed-data",
        }
        rows.append((ab_id, EMITTED_AT, json.dumps(payload)))

    print(f"  Seeding airbyte_raw._airbyte_raw_shopify_customers ({len(rows)} rows)...")
    psycopg2.extras.execute_batch(
        cur,
        """
        INSERT INTO airbyte_raw._airbyte_raw_shopify_customers (_airbyte_ab_id, _airbyte_emitted_at, _airbyte_data)
        VALUES (%s, %s, %s::jsonb)
        ON CONFLICT (_airbyte_ab_id) DO UPDATE SET
            _airbyte_emitted_at = EXCLUDED._airbyte_emitted_at,
            _airbyte_data       = EXCLUDED._airbyte_data
        """,
        rows,
        page_size=100,
    )


def print_expected(verbose: bool = False) -> None:
    print()
    print("=" * 58)
    print("  SEED DATA — EXPECTED METRIC VALUES")
    print("=" * 58)
    for k, v in EXPECTED.items():
        print(f"  {k:<28} {v}")
    print("=" * 58)
    if verbose:
        print()
        print("  Raw row counts to verify immediately after seeding:")
        print(f"    airbyte_raw._airbyte_raw_meta_ads:          {EXPECTED['meta_ads_raw_rows']}")
        print(f"    airbyte_raw._airbyte_raw_google_ads:        {EXPECTED['google_ads_raw_rows']}")
        print(f"    airbyte_raw._airbyte_raw_shopify_orders:    {EXPECTED['shopify_orders_raw_rows']}")
        print(f"    airbyte_raw._airbyte_raw_shopify_customers: {EXPECTED['shopify_customers_raw_rows']}")
    print()


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Seed test data into the MarkInsight analytics warehouse."
    )
    parser.add_argument(
        "--db-url",
        default=os.environ.get("DATABASE_URL"),
        help="PostgreSQL connection URL (default: $DATABASE_URL)",
    )
    parser.add_argument(
        "--clean",
        action="store_true",
        help="Delete existing seed rows before inserting (safe re-run)",
    )
    parser.add_argument(
        "--show-expected",
        action="store_true",
        help="Print expected metric values and exit (no DB needed)",
    )
    args = parser.parse_args()

    if args.show_expected:
        print_expected(verbose=True)
        return 0

    if not args.db_url:
        # Check if individual env vars are set
        if not os.environ.get("DB_HOST"):
            print("ERROR: Set DATABASE_URL or DB_HOST/DB_USER/DB_PASSWORD/DB_NAME env vars.")
            return 1

    print("Connecting to database...")
    try:
        conn = get_connection(args.db_url)
    except Exception as e:
        print(f"ERROR: Could not connect to database: {e}")
        return 1

    print("Connected.")
    try:
        with conn:
            with conn.cursor() as cur:
                print("\n[1/2] Creating schemas and tables if needed...")
                ensure_schemas(cur)
                ensure_tables(cur)

                if args.clean:
                    print("\n[1.5] Cleaning existing seed data...")
                    clean_seed_data(cur)

                print("\n[2/2] Inserting seed data...")
                seed_platform_tables(cur)
                seed_meta_ads(cur)
                seed_google_ads(cur)
                seed_shopify_orders(cur)
                seed_shopify_customers(cur)

        print("\n✓ Seed complete.")
        print_expected()
        return 0

    except Exception as e:
        print(f"\nERROR during seeding: {e}")
        import traceback
        traceback.print_exc()
        return 1
    finally:
        conn.close()


if __name__ == "__main__":
    sys.exit(main())
