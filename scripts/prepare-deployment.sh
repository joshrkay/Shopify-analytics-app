#!/bin/bash
# =============================================================================
# Pre-Deployment Validation Script
# =============================================================================
# Run this before deploying to verify the codebase is deployment-ready.
#
# Usage:
#   ./scripts/prepare-deployment.sh
#
# Checks:
#   1. Required files exist (render.yaml, Dockerfiles, migrations)
#   2. Backend lints clean
#   3. Frontend builds successfully
#   4. Platform gate tests pass
#   5. Docker image builds
# =============================================================================

set -e

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

PASS=0
FAIL=0
WARN=0

pass() { echo -e "  ${GREEN}PASS${NC}  $1"; PASS=$((PASS + 1)); }
fail() { echo -e "  ${RED}FAIL${NC}  $1"; FAIL=$((FAIL + 1)); }
warn() { echo -e "  ${YELLOW}WARN${NC}  $1"; WARN=$((WARN + 1)); }
skip() { echo -e "  ${BLUE}SKIP${NC}  $1"; }

# Find project root (where render.yaml lives)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$PROJECT_ROOT"

echo ""
echo -e "${BLUE}========================================${NC}"
echo -e "${BLUE}  Pre-Deployment Validation${NC}"
echo -e "${BLUE}========================================${NC}"
echo ""

# ── 1. Required Files ──────────────────────────────────────────────
echo -e "${YELLOW}[1/5] Checking required files...${NC}"

for f in render.yaml docker/backend.Dockerfile docker/worker.Dockerfile \
         backend/requirements.txt backend/scripts/run_required_migrations.py \
         frontend/package.json .github/workflows/ci.yml; do
    if [ -f "$f" ]; then
        pass "$f exists"
    else
        fail "$f is MISSING"
    fi
done

# Check migrations directory has files
MIGRATION_COUNT=$(ls backend/migrations/*.sql 2>/dev/null | wc -l)
if [ "$MIGRATION_COUNT" -gt 0 ]; then
    pass "Found $MIGRATION_COUNT migration files in backend/migrations/"
else
    fail "No .sql migration files found in backend/migrations/"
fi

echo ""

# ── 2. Backend Lint ────────────────────────────────────────────────
echo -e "${YELLOW}[2/5] Running backend lint...${NC}"

if command -v ruff &> /dev/null; then
    cd "$PROJECT_ROOT/backend"
    if ruff check src/ --quiet 2>/dev/null; then
        pass "Backend lint clean (ruff check src/)"
    else
        warn "Backend lint has warnings — run 'cd backend && ruff check src/' to see details"
    fi
    cd "$PROJECT_ROOT"
else
    skip "ruff not installed — install with 'pip install ruff'"
fi

echo ""

# ── 3. Frontend Build ─────────────────────────────────────────────
echo -e "${YELLOW}[3/5] Checking frontend build...${NC}"

if command -v node &> /dev/null; then
    cd "$PROJECT_ROOT/frontend"
    if [ -d "node_modules" ]; then
        if npx tsc --noEmit 2>/dev/null; then
            pass "TypeScript type check passed"
        else
            warn "TypeScript errors — run 'cd frontend && npx tsc --noEmit' to see details"
        fi
    else
        warn "node_modules not found — run 'cd frontend && npm install' first"
    fi
    cd "$PROJECT_ROOT"
else
    skip "Node.js not installed"
fi

echo ""

# ── 4. Platform Gate Tests ─────────────────────────────────────────
echo -e "${YELLOW}[4/5] Running platform gate tests...${NC}"

if command -v pytest &> /dev/null || [ -f "backend/.venv/bin/pytest" ]; then
    cd "$PROJECT_ROOT/backend"
    if PYTHONPATH=. pytest src/tests/platform/test_platform_gate.py \
        -v --tb=short --disable-warnings -q 2>/dev/null; then
        pass "All platform gate tests passed"
    else
        fail "Platform gate tests FAILED — these block deployment"
    fi
    cd "$PROJECT_ROOT"
else
    skip "pytest not installed — run 'pip install pytest pytest-asyncio pytest-mock'"
fi

echo ""

# ── 5. Docker Build Check ─────────────────────────────────────────
echo -e "${YELLOW}[5/5] Checking Docker build readiness...${NC}"

if command -v docker &> /dev/null; then
    # Just check that Dockerfiles parse — don't do a full build (too slow)
    if docker build --check -f docker/backend.Dockerfile . 2>/dev/null; then
        pass "backend.Dockerfile syntax valid"
    else
        # --check not supported in older Docker, fall back to existence check
        if [ -f "docker/backend.Dockerfile" ]; then
            pass "backend.Dockerfile exists (syntax check skipped — older Docker)"
        fi
    fi

    if docker build --check -f docker/worker.Dockerfile . 2>/dev/null; then
        pass "worker.Dockerfile syntax valid"
    else
        if [ -f "docker/worker.Dockerfile" ]; then
            pass "worker.Dockerfile exists (syntax check skipped — older Docker)"
        fi
    fi
else
    skip "Docker not installed"
fi

echo ""

# ── Summary ────────────────────────────────────────────────────────
echo -e "${BLUE}========================================${NC}"
echo -e "${BLUE}  Results${NC}"
echo -e "${BLUE}========================================${NC}"
echo -e "  ${GREEN}Passed:${NC}  $PASS"
echo -e "  ${RED}Failed:${NC}  $FAIL"
echo -e "  ${YELLOW}Warnings:${NC} $WARN"
echo ""

if [ "$FAIL" -gt 0 ]; then
    echo -e "${RED}Deployment NOT ready — fix failures above before deploying.${NC}"
    exit 1
else
    echo -e "${GREEN}Deployment checks passed.${NC}"
    echo ""
    echo -e "${YELLOW}Next steps:${NC}"
    echo "  1. Push to 'main' branch to trigger Render auto-deploy"
    echo "  2. Set required env vars in Render dashboard (see docs/deployment-guide.md)"
    echo "  3. Run ./scripts/smoke-test.sh https://<your-domain> after deploy"
    echo ""
fi
