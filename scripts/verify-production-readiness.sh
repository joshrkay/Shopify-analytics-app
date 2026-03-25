#!/usr/bin/env bash
#
# Production Readiness Verification Script
# Run against the production environment to verify all configuration.
#
# Usage:
#   ./scripts/verify-production-readiness.sh https://app.markinsight.net
#
# Or from Render shell (env vars already set):
#   ./scripts/verify-production-readiness.sh
#

set -euo pipefail

PASS=0
FAIL=0
WARN=0
BASE_URL="${1:-}"

green()  { echo -e "\033[32m✓ PASS\033[0m $1"; ((PASS++)); }
red()    { echo -e "\033[31m✗ FAIL\033[0m $1"; ((FAIL++)); }
yellow() { echo -e "\033[33m⚠ WARN\033[0m $1"; ((WARN++)); }

echo "============================================"
echo " Production Readiness Verification"
echo " $(date -u '+%Y-%m-%d %H:%M:%S UTC')"
echo "============================================"
echo ""

# ─── Section 1: Environment Variables ───────────────────────────────────

echo "── Environment Variables ──"

required_vars=(
  "DATABASE_URL"
  "REDIS_URL"
  "CLERK_FRONTEND_API"
  "CLERK_SECRET_KEY"
  "CLERK_WEBHOOK_SECRET"
  "VITE_CLERK_PUBLISHABLE_KEY"
  "SHOPIFY_API_KEY"
  "SHOPIFY_API_SECRET"
  "ENCRYPTION_KEY"
  "OAUTH_REDIRECT_URI"
)

for var in "${required_vars[@]}"; do
  if [ -n "${!var:-}" ]; then
    green "$var is set"
  else
    red "$var is NOT SET — app will fail"
  fi
done

# OAuth platform credentials (warn if missing, not blocking for all)
oauth_vars=(
  "META_APP_ID"
  "META_APP_SECRET"
  "GOOGLE_CLIENT_ID"
  "GOOGLE_CLIENT_SECRET"
  "GOOGLE_ADS_DEVELOPER_TOKEN"
  "TIKTOK_APP_ID"
  "TIKTOK_APP_SECRET"
  "SNAPCHAT_CLIENT_ID"
  "SNAPCHAT_CLIENT_SECRET"
  "PINTEREST_APP_ID"
  "PINTEREST_APP_SECRET"
  "TWITTER_CLIENT_ID"
  "TWITTER_CLIENT_SECRET"
  "LINKEDIN_CLIENT_ID"
  "LINKEDIN_CLIENT_SECRET"
  "MICROSOFT_ADS_CLIENT_ID"
  "MICROSOFT_ADS_CLIENT_SECRET"
  "HUBSPOT_CLIENT_ID"
  "HUBSPOT_CLIENT_SECRET"
  "OPENROUTER_API_KEY"
)

echo ""
echo "── OAuth / Integration Credentials ──"
for var in "${oauth_vars[@]}"; do
  if [ -n "${!var:-}" ]; then
    green "$var is set"
  else
    yellow "$var is not set — that platform's OAuth won't work"
  fi
done

# ─── Section 2: Billing Test Mode ──────────────────────────────────────

echo ""
echo "── Billing Safety ──"

if [ "${SHOPIFY_BILLING_TEST_MODE:-}" = "true" ]; then
  red "SHOPIFY_BILLING_TEST_MODE=true — charges won't be real! Set to false for production."
elif [ "${SHOPIFY_BILLING_TEST_MODE:-}" = "false" ]; then
  green "SHOPIFY_BILLING_TEST_MODE=false (production billing active)"
else
  yellow "SHOPIFY_BILLING_TEST_MODE not set — defaults depend on code"
fi

# ─── Section 3: Service Connectivity ───────────────────────────────────

echo ""
echo "── Service Connectivity ──"

# Health endpoint
if [ -n "$BASE_URL" ]; then
  HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" "${BASE_URL}/health" 2>/dev/null || echo "000")
  if [ "$HTTP_CODE" = "200" ]; then
    green "Health endpoint returns 200"
  else
    red "Health endpoint returned $HTTP_CODE (expected 200)"
  fi

  # Frontend loads
  HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" "${BASE_URL}/" 2>/dev/null || echo "000")
  if [ "$HTTP_CODE" = "200" ]; then
    green "Frontend loads (/ returns 200)"
  else
    red "Frontend returned $HTTP_CODE"
  fi
else
  yellow "No BASE_URL provided — skipping HTTP checks"
fi

# PostgreSQL
if [ -n "${DATABASE_URL:-}" ]; then
  if python3 -c "
import psycopg2, os
conn = psycopg2.connect(os.environ['DATABASE_URL'])
cur = conn.cursor()
cur.execute('SELECT 1')
conn.close()
print('ok')
" 2>/dev/null | grep -q "ok"; then
    green "PostgreSQL connection OK"
  else
    red "PostgreSQL connection FAILED"
  fi
else
  red "DATABASE_URL not set — cannot check PostgreSQL"
fi

# Redis
if [ -n "${REDIS_URL:-}" ]; then
  if python3 -c "
import redis, os
r = redis.from_url(os.environ['REDIS_URL'])
r.ping()
print('ok')
" 2>/dev/null | grep -q "ok"; then
    green "Redis PING OK"
  else
    red "Redis PING FAILED"
  fi
else
  red "REDIS_URL not set — cannot check Redis"
fi

# Clerk JWKS
if [ -n "${CLERK_FRONTEND_API:-}" ]; then
  JWKS_URL="https://${CLERK_FRONTEND_API}/.well-known/jwks.json"
  HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" "$JWKS_URL" 2>/dev/null || echo "000")
  if [ "$HTTP_CODE" = "200" ]; then
    green "Clerk JWKS endpoint reachable ($JWKS_URL)"
  else
    red "Clerk JWKS returned $HTTP_CODE — JWT verification will fail"
  fi
else
  red "CLERK_FRONTEND_API not set — JWT verification disabled"
fi

# ─── Section 4: Database State ─────────────────────────────────────────

echo ""
echo "── Database State ──"

if [ -n "${DATABASE_URL:-}" ]; then
  # Plans
  PLAN_COUNT=$(python3 -c "
import psycopg2, os
conn = psycopg2.connect(os.environ['DATABASE_URL'])
cur = conn.cursor()
cur.execute('SELECT count(*) FROM plans WHERE is_active = true')
print(cur.fetchone()[0])
conn.close()
" 2>/dev/null || echo "0")
  if [ "$PLAN_COUNT" -gt 0 ] 2>/dev/null; then
    green "Active plans found: $PLAN_COUNT"
  else
    red "No active plans in database — billing won't work"
  fi

  # PlanFeatures
  FEATURE_COUNT=$(python3 -c "
import psycopg2, os
conn = psycopg2.connect(os.environ['DATABASE_URL'])
cur = conn.cursor()
cur.execute('SELECT count(*) FROM plan_features')
print(cur.fetchone()[0])
conn.close()
" 2>/dev/null || echo "0")
  if [ "$FEATURE_COUNT" -gt 0 ] 2>/dev/null; then
    green "PlanFeature rows found: $FEATURE_COUNT"
  else
    red "No PlanFeature rows — entitlements won't resolve correctly"
  fi

  # ShopifyStores
  STORE_COUNT=$(python3 -c "
import psycopg2, os
conn = psycopg2.connect(os.environ['DATABASE_URL'])
cur = conn.cursor()
cur.execute(\"SELECT count(*) FROM shopify_stores WHERE status = 'active'\")
print(cur.fetchone()[0])
conn.close()
" 2>/dev/null || echo "0")
  if [ "$STORE_COUNT" -gt 0 ] 2>/dev/null; then
    green "Active Shopify stores: $STORE_COUNT"
  else
    yellow "No active Shopify stores — paid plan checkout will fail"
  fi

  # dbt marts
  for table in "marts.mart_marketing_metrics" "marts.mart_revenue_metrics" "marts.fct_marketing_metrics"; do
    ROW_COUNT=$(python3 -c "
import psycopg2, os
conn = psycopg2.connect(os.environ['DATABASE_URL'])
cur = conn.cursor()
cur.execute('SELECT count(*) FROM $table')
print(cur.fetchone()[0])
conn.close()
" 2>/dev/null || echo "error")
    if [ "$ROW_COUNT" != "error" ] && [ "$ROW_COUNT" -gt 0 ] 2>/dev/null; then
      green "$table has $ROW_COUNT rows"
    elif [ "$ROW_COUNT" = "0" ]; then
      yellow "$table is empty — analytics/insights will show no data"
    else
      yellow "$table does not exist or query failed — run dbt first"
    fi
  done
fi

# ─── Section 5: OAUTH_REDIRECT_URI consistency ─────────────────────────

echo ""
echo "── Configuration Consistency ──"

if [ -n "${OAUTH_REDIRECT_URI:-}" ] && [ -n "${CORS_ORIGINS:-}" ]; then
  # Extract domain from OAUTH_REDIRECT_URI
  OAUTH_DOMAIN=$(echo "$OAUTH_REDIRECT_URI" | sed 's|https\?://||' | cut -d'/' -f1)
  if echo "$CORS_ORIGINS" | grep -q "$OAUTH_DOMAIN"; then
    green "OAUTH_REDIRECT_URI domain ($OAUTH_DOMAIN) matches CORS_ORIGINS"
  else
    red "OAUTH_REDIRECT_URI domain ($OAUTH_DOMAIN) NOT in CORS_ORIGINS ($CORS_ORIGINS)"
  fi
else
  yellow "Cannot verify OAUTH/CORS consistency — one or both not set"
fi

# ─── Summary ───────────────────────────────────────────────────────────

echo ""
echo "============================================"
echo " RESULTS: $PASS passed, $FAIL failed, $WARN warnings"
echo "============================================"

if [ "$FAIL" -gt 0 ]; then
  echo ""
  echo "Action required: Fix all FAIL items before launch."
  exit 1
else
  echo ""
  echo "No blocking issues found."
  exit 0
fi
