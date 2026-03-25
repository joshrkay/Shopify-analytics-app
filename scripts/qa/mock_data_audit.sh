#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT_DIR"

PATTERN='mock|hardcod|fake|sample data|sample_data|stub|placeholder|TODO: mock'

echo "== Mock/Fake Data Audit =="
echo "Repo: $ROOT_DIR"
echo

TARGETS=(
  frontend/src
  backend/src
  docker/superset
)

IGNORE_GLOBS=(
  '!**/*.test.*'
  '!**/__tests__/**'
  '!**/tests/**'
  '!**/*.spec.*'
  '!**/*.md'
)

cmd=(rg -n -i "$PATTERN")
for g in "${IGNORE_GLOBS[@]}"; do
  cmd+=( -g "$g" )
done
cmd+=("${TARGETS[@]}")

"${cmd[@]}" || true

echo
cat <<'SUMMARY'
Severity guide:
- HIGH: production runtime code that can surface non-real data to users.
- MEDIUM: fallback logic requiring product decision/labeling.
- LOW: tests/docs/demo assets.
SUMMARY
