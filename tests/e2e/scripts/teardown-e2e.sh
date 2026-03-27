#!/usr/bin/env bash
#
# Stop E2E test environment.
#
# Usage:
#   ./tests/e2e/scripts/teardown-e2e.sh

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
E2E_DIR="$SCRIPT_DIR/.."

echo "=== E2E Environment Teardown ==="

# Stop frontend
if [ -f "$E2E_DIR/.frontend.pid" ]; then
  PID=$(cat "$E2E_DIR/.frontend.pid")
  echo "Stopping frontend (PID: $PID)..."
  kill "$PID" 2>/dev/null || true
  rm -f "$E2E_DIR/.frontend.pid"
fi

# Stop backend
if [ -f "$E2E_DIR/.backend.pid" ]; then
  PID=$(cat "$E2E_DIR/.backend.pid")
  echo "Stopping backend (PID: $PID)..."
  kill "$PID" 2>/dev/null || true
  rm -f "$E2E_DIR/.backend.pid"
fi

# Stop mock servers
if [ -f "$E2E_DIR/.mock-server.pid" ]; then
  PID=$(cat "$E2E_DIR/.mock-server.pid")
  echo "Stopping mock servers (PID: $PID)..."
  kill "$PID" 2>/dev/null || true
  rm -f "$E2E_DIR/.mock-server.pid"
fi

# Stop Docker services
echo "Stopping Docker services..."
docker-compose -f "$E2E_DIR/docker/docker-compose.e2e.yml" down -v 2>/dev/null || true

# Clean up temp files
rm -f "$E2E_DIR/.keys/e2e-private.pem" "$E2E_DIR/.keys/e2e-public.pem" 2>/dev/null || true
rmdir "$E2E_DIR/.keys" 2>/dev/null || true

echo "=== Teardown Complete ==="
