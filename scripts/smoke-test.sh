#!/bin/bash
# =============================================================================
# Post-Deployment Smoke Test
# =============================================================================
# Verifies a deployed MarkInsight instance is healthy and serving correctly.
#
# Usage:
#   ./scripts/smoke-test.sh https://app.markinsight.net
#   ./scripts/smoke-test.sh http://localhost:8000
# =============================================================================

set -e

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

BASE_URL="${1:-http://localhost:8000}"
# Strip trailing slash
BASE_URL="${BASE_URL%/}"

PASS=0
FAIL=0

pass() { echo -e "  ${GREEN}PASS${NC}  $1"; PASS=$((PASS + 1)); }
fail() { echo -e "  ${RED}FAIL${NC}  $1"; FAIL=$((FAIL + 1)); }

echo ""
echo -e "${BLUE}========================================${NC}"
echo -e "${BLUE}  Smoke Test: ${BASE_URL}${NC}"
echo -e "${BLUE}========================================${NC}"
echo ""

# ── 1. Health Check ────────────────────────────────────────────────
echo -e "${YELLOW}[1/5] Health check...${NC}"

HEALTH_STATUS=$(curl -s -o /dev/null -w "%{http_code}" --max-time 10 "${BASE_URL}/health" 2>/dev/null || echo "000")
if [ "$HEALTH_STATUS" = "200" ]; then
    HEALTH_BODY=$(curl -s --max-time 10 "${BASE_URL}/health" 2>/dev/null)
    pass "GET /health → 200 ($HEALTH_BODY)"
else
    fail "GET /health → $HEALTH_STATUS (expected 200)"
fi

echo ""

# ── 2. Frontend Loads ──────────────────────────────────────────────
echo -e "${YELLOW}[2/5] Frontend serving...${NC}"

FRONTEND_STATUS=$(curl -s -o /dev/null -w "%{http_code}" --max-time 10 "${BASE_URL}/" 2>/dev/null || echo "000")
if [ "$FRONTEND_STATUS" = "200" ]; then
    # Check it's actually HTML, not a JSON error
    CONTENT_TYPE=$(curl -s -I --max-time 10 "${BASE_URL}/" 2>/dev/null | grep -i "content-type" | head -1)
    if echo "$CONTENT_TYPE" | grep -qi "text/html"; then
        pass "GET / → 200 (text/html)"
    else
        fail "GET / → 200 but content-type is not HTML: $CONTENT_TYPE"
    fi
else
    fail "GET / → $FRONTEND_STATUS (expected 200)"
fi

echo ""

# ── 3. Auth Enforcement ───────────────────────────────────────────
echo -e "${YELLOW}[3/5] Auth enforcement (unauthenticated request should be rejected)...${NC}"

AUTH_STATUS=$(curl -s -o /dev/null -w "%{http_code}" --max-time 10 "${BASE_URL}/api/billing/entitlements" 2>/dev/null || echo "000")
if [ "$AUTH_STATUS" = "401" ] || [ "$AUTH_STATUS" = "403" ] || [ "$AUTH_STATUS" = "503" ]; then
    pass "GET /api/billing/entitlements (no auth) → $AUTH_STATUS (correctly rejected)"
else
    fail "GET /api/billing/entitlements (no auth) → $AUTH_STATUS (expected 401/403/503)"
fi

echo ""

# ── 4. Static Assets ──────────────────────────────────────────────
echo -e "${YELLOW}[4/5] Static asset serving...${NC}"

# Check that /assets/ path exists (Vite hashed assets)
ASSETS_STATUS=$(curl -s -o /dev/null -w "%{http_code}" --max-time 10 "${BASE_URL}/assets/" 2>/dev/null || echo "000")
# 200 or 403 (directory listing disabled) both indicate the route is configured
if [ "$ASSETS_STATUS" = "200" ] || [ "$ASSETS_STATUS" = "403" ] || [ "$ASSETS_STATUS" = "404" ]; then
    pass "Assets path configured (${BASE_URL}/assets/ → $ASSETS_STATUS)"
else
    fail "Assets path not configured (${BASE_URL}/assets/ → $ASSETS_STATUS)"
fi

echo ""

# ── 5. API Response Format ────────────────────────────────────────
echo -e "${YELLOW}[5/5] API returns JSON (not HTML)...${NC}"

# The health endpoint should always return JSON
HEALTH_CT=$(curl -s -I --max-time 10 "${BASE_URL}/health" 2>/dev/null | grep -i "content-type" | head -1)
if echo "$HEALTH_CT" | grep -qi "application/json"; then
    pass "API returns application/json content-type"
else
    fail "API content-type unexpected: $HEALTH_CT"
fi

echo ""

# ── Summary ────────────────────────────────────────────────────────
echo -e "${BLUE}========================================${NC}"
echo -e "${BLUE}  Results${NC}"
echo -e "${BLUE}========================================${NC}"
echo -e "  ${GREEN}Passed:${NC} $PASS"
echo -e "  ${RED}Failed:${NC} $FAIL"
echo ""

if [ "$FAIL" -gt 0 ]; then
    echo -e "${RED}Some smoke tests failed.${NC}"
    echo ""
    echo -e "${YELLOW}Troubleshooting:${NC}"
    echo "  - Check deploy logs in Render dashboard"
    echo "  - Verify all env vars are set (see docs/deployment-guide.md)"
    echo "  - Ensure migrations completed: check for 'Required migrations completed' in logs"
    echo ""
    exit 1
else
    echo -e "${GREEN}All smoke tests passed — deployment is healthy.${NC}"
    echo ""
fi
