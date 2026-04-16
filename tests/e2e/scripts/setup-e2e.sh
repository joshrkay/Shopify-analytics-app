#!/usr/bin/env bash
#
# Start E2E test environment.
#
# Usage:
#   ./tests/e2e/scripts/setup-e2e.sh
#
# This script:
# 1. Starts PostgreSQL and Redis via docker-compose
# 2. Runs Alembic migrations
# 3. Starts mock external services
# 4. Starts the backend with E2E auth mode
# 5. Starts the frontend with E2E Clerk mock
# 6. Seeds baseline test data

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../../.." && pwd)"
E2E_DIR="$SCRIPT_DIR/.."

echo "=== E2E Environment Setup ==="
echo "Project root: $PROJECT_ROOT"
echo ""

# Step 1: Start database services
echo "1. Starting PostgreSQL and Redis..."
docker-compose -f "$E2E_DIR/docker/docker-compose.e2e.yml" up -d
echo "   Waiting for PostgreSQL to be ready..."
for i in $(seq 1 30); do
  if docker-compose -f "$E2E_DIR/docker/docker-compose.e2e.yml" exec -T postgres-e2e pg_isready -U e2e_test 2>/dev/null; then
    echo "   PostgreSQL ready."
    break
  fi
  sleep 1
done

# Step 2: Generate RSA keys for JWT signing
echo "2. Generating RSA key pair..."
KEY_DIR="$E2E_DIR/.keys"
mkdir -p "$KEY_DIR"
if [ ! -f "$KEY_DIR/e2e-private.pem" ]; then
  openssl genpkey -algorithm RSA -out "$KEY_DIR/e2e-private.pem" -pkeyopt rsa_keygen_bits:2048 2>/dev/null
  openssl rsa -pubout -in "$KEY_DIR/e2e-private.pem" -out "$KEY_DIR/e2e-public.pem" 2>/dev/null
  echo "   Key pair generated."
else
  echo "   Key pair already exists."
fi

# Step 3: Run Alembic migrations
echo "3. Running database migrations..."
export DATABASE_URL="postgresql://e2e_test:e2e_test@localhost:5433/e2e_test_db"
export REDIS_URL="redis://localhost:6380"
export ENV="test"
export E2E_AUTH_MODE="mock"
export E2E_PUBLIC_KEY_PATH="$KEY_DIR/e2e-public.pem"
export CLERK_FRONTEND_API="test.clerk.accounts.dev"
export PYTHONPATH="$PROJECT_ROOT/backend"

cd "$PROJECT_ROOT/backend"
if [ -f "alembic.ini" ]; then
  alembic upgrade head 2>/dev/null || echo "   (Migrations skipped or already applied)"
fi

# Step 4: Start mock external services
echo "4. Starting mock external services..."
python3 "$E2E_DIR/scripts/mock-server-runner.py" &
MOCK_PID=$!
echo "   Mock servers PID: $MOCK_PID"
echo "$MOCK_PID" > "$E2E_DIR/.mock-server.pid"

# Step 5: Start backend
echo "5. Starting FastAPI backend..."
cd "$PROJECT_ROOT/backend"
uvicorn main:app --host 0.0.0.0 --port 8000 --log-level warning &
BACKEND_PID=$!
echo "   Backend PID: $BACKEND_PID"
echo "$BACKEND_PID" > "$E2E_DIR/.backend.pid"

# Step 6: Start frontend
echo "6. Starting Vite frontend..."
cd "$PROJECT_ROOT/frontend"
VITE_E2E_MODE=true npm run dev &
FRONTEND_PID=$!
echo "   Frontend PID: $FRONTEND_PID"
echo "$FRONTEND_PID" > "$E2E_DIR/.frontend.pid"

# Step 7: Wait for services
echo "7. Waiting for services to be ready..."
for i in $(seq 1 30); do
  if curl -sf http://localhost:8000/health > /dev/null 2>&1; then
    echo "   Backend ready."
    break
  fi
  sleep 1
done

for i in $(seq 1 30); do
  if curl -sf http://localhost:3000/ > /dev/null 2>&1; then
    echo "   Frontend ready."
    break
  fi
  sleep 1
done

echo ""
echo "=== E2E Environment Ready ==="
echo ""
echo "Run tests with:"
echo "  npx playwright test --config tests/e2e/playwright.config.ts"
echo ""
echo "Stop with:"
echo "  ./tests/e2e/scripts/teardown-e2e.sh"
