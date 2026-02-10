#!/bin/bash
# Run this from your Shopify-analytics-app repo root
# Usage: bash apply.sh

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

echo "Copying fixed files..."
cp "$SCRIPT_DIR/main.tsx" frontend/src/main.tsx
cp "$SCRIPT_DIR/tenant_context.py" backend/src/platform/tenant_context.py

echo "Creating commit..."
git add frontend/src/main.tsx backend/src/platform/tenant_context.py
git commit -m "fix: replace silent throw with visible error + bypass tenant auth for static files

- main.tsx: Show 'Configuration Error' UI instead of throwing when
  VITE_CLERK_PUBLISHABLE_KEY is missing (prevents white screen)
- tenant_context.py: Skip auth middleware for non-API routes so
  static files like vite.svg don't get 500 errors"

echo "Pushing to main..."
git push origin main

echo "Done! Render will auto-deploy from the new commit."
