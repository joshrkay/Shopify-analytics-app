#!/bin/bash
# =============================================================================
# One-time full rebuild of dbt models after V1→V2 migration
# =============================================================================
# Run this ONCE after:
#   1. PR #395 (seed tenant_airbyte_connections) is deployed
#   2. PR #396 (V1→V2 staging migration) is deployed
#   3. PR #400 (seed test orders) is deployed
#   4. PR cleanup_v1_raw_tables migration has run
#
# This clears stale incremental data from prior V1 runs and rebuilds
# all models from the current V2 typed tables.
#
# Usage:
#   # On Render shell:
#   cd /app && bash scripts/dbt_full_rebuild.sh
#
#   # Locally (requires DATABASE_URL or DB_* env vars):
#   bash scripts/dbt_full_rebuild.sh
# =============================================================================

set -euo pipefail

# Determine dbt project directory
DBT_DIR="${DBT_PROJECT_DIR:-$(cd "$(dirname "$0")/../analytics" && pwd)}"
echo "=== dbt Full Rebuild ==="
echo "Project dir: $DBT_DIR"
echo "Started at: $(date -u +%Y-%m-%dT%H:%M:%SZ)"
echo ""

cd "$DBT_DIR"

echo "--- Step 1: Install dbt packages ---"
dbt deps --profiles-dir . --project-dir .

echo ""
echo "--- Step 2: Full refresh (clears stale incremental data) ---"
dbt run --full-refresh --profiles-dir . --project-dir .

echo ""
echo "--- Step 3: Run data quality tests ---"
dbt test --profiles-dir . --project-dir . || echo "WARNING: Some tests failed — check output above"

echo ""
echo "=== Rebuild complete at $(date -u +%Y-%m-%dT%H:%M:%SZ) ==="
echo ""
echo "Verify with:"
echo "  SELECT count(*) FROM staging.stg_shopify_orders;"
echo "  SELECT count(*) FROM canonical.orders;"
echo "  SELECT count(*), min(period_start), max(period_end) FROM marts.mart_revenue_metrics;"
