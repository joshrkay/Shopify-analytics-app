#!/usr/bin/env python3
"""
App startup smoke test — verifies the FastAPI app can be imported cleanly.

Why this matters
----------------
Route modules are imported at module scope in main.py.  A NameError or
ImportError in any route module crashes the *entire* app at startup — all
routes 503, not just the broken one.

This script catches that before a Docker image is built or a Render deploy
runs.  It is intentionally cheap: no database, no Clerk credentials, no
external services — just "can Python load the application code?"

What it checks
--------------
1. Every route module imported by main.py can be imported without errors.
2. The FastAPI `app` object is created successfully.
3. At least one route is registered (basic sanity — catches empty-app edge cases).

Usage (from backend/):
    python scripts/smoke_test_startup.py

Exit codes:
    0 — app loads cleanly
    1 — import failed (app would crash on startup)
"""

import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent  # backend/

# ---------------------------------------------------------------------------
# The smoke script runs inside a subprocess so we get a clean Python process
# with no inherited state from the test runner or CI environment.
# ---------------------------------------------------------------------------

_SMOKE_SCRIPT = r"""
import sys
import os

# Minimal env — no real credentials needed for import-time checks
os.environ.setdefault("DATABASE_URL",      "sqlite:///:memory:")
os.environ.setdefault("CLERK_FRONTEND_API","test.clerk.accounts.dev")
os.environ.setdefault("ENV",               "test")
# Suppress JWKS probe output during smoke test
os.environ.setdefault("PYTHONDONTWRITEBYTECODE", "1")

try:
    import main
except Exception as exc:
    import traceback
    traceback.print_exc()
    print(f"\nFAIL: `import main` raised {type(exc).__name__}: {exc}", file=sys.stderr)
    sys.exit(1)

# Verify app object and routes exist
try:
    app = main.app
except AttributeError:
    print("FAIL: main.py does not expose an `app` object", file=sys.stderr)
    sys.exit(1)

route_count = len(app.routes)
if route_count == 0:
    print("FAIL: app.routes is empty — no routes were registered", file=sys.stderr)
    sys.exit(1)

# Report a sample of registered paths for visibility
api_routes = [
    r.path for r in app.routes
    if hasattr(r, "path") and r.path.startswith("/api")
]
print(f"OK: {route_count} total routes registered, {len(api_routes)} /api routes")
if api_routes:
    sample = api_routes[:5]
    print(f"    Sample: {', '.join(sample)}")
    if len(api_routes) > 5:
        print(f"    ... and {len(api_routes) - 5} more")

sys.exit(0)
"""


def main() -> int:
    print("=" * 65)
    print("App Startup Smoke Test")
    print("=" * 65)
    print(f"Root: {ROOT}")
    print(
        "Testing: PYTHONPATH=backend python -c '<import main; verify app.routes>'\n"
    )

    env = os.environ.copy()
    env["PYTHONPATH"] = str(ROOT)

    try:
        result = subprocess.run(
            [sys.executable, "-c", _SMOKE_SCRIPT],
            cwd=str(ROOT),
            capture_output=True,
            text=True,
            timeout=60,
            env=env,
        )
    except subprocess.TimeoutExpired:
        print("✗ SMOKE TEST TIMED OUT (60s)")
        print(
            "  The app took more than 60 seconds to import.\n"
            "  Check for blocking I/O or infinite loops at module scope."
        )
        return 1

    if result.stdout:
        print(result.stdout.rstrip())
    if result.stderr:
        # Print stderr to stderr so CI log viewers show it as an error block
        print(result.stderr.rstrip(), file=sys.stderr)

    print()
    print("=" * 65)
    if result.returncode == 0:
        print("✓ SMOKE TEST PASSED — app imports without errors")
    else:
        print("✗ SMOKE TEST FAILED — app would crash on startup")
        print(
            "  Every NameError/ImportError in a route module crashes all routes.\n"
            "  Fix the import errors shown above, then re-run:\n"
            "    cd backend && python scripts/smoke_test_startup.py"
        )
    print("=" * 65)

    return result.returncode


if __name__ == "__main__":
    sys.exit(main())
