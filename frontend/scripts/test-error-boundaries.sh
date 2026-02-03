#!/bin/bash
#
# Error Boundary Test Script
#
# This script runs all error boundary tests for CI/CD pipelines like Codex.
# It tests both unit tests and multi-tenant integration tests.
#
# Usage:
#   ./scripts/test-error-boundaries.sh
#
# Exit codes:
#   0 - All tests passed
#   1 - Tests failed or error occurred

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
FRONTEND_DIR="$(dirname "$SCRIPT_DIR")"

echo "=========================================="
echo "Error Boundary Test Suite"
echo "=========================================="
echo ""

cd "$FRONTEND_DIR"

# Check if node_modules exists
if [ ! -d "node_modules" ]; then
    echo "Installing dependencies..."
    npm install
    echo ""
fi

echo "Running error boundary tests..."
echo ""

# Run the specific error boundary test files
npx vitest run \
    src/tests/errorBoundary.test.tsx \
    src/tests/errorBoundaryMultiTenant.test.tsx \
    --reporter=verbose \
    --no-coverage

TEST_EXIT_CODE=$?

echo ""
echo "=========================================="

if [ $TEST_EXIT_CODE -eq 0 ]; then
    echo "✓ All error boundary tests passed!"
    echo "=========================================="
    exit 0
else
    echo "✗ Error boundary tests failed!"
    echo "=========================================="
    exit 1
fi
