#!/usr/bin/env python3
"""
Airbyte OSS connectivity and OAuth readiness check.

Run from the project root:
    python3 scripts/check_airbyte.py

Or on the Render shell:
    python3 scripts/check_airbyte.py

Checks (in order):
  1. Required env vars are present
  2. Airbyte health endpoint responds
  3. Workspace exists and is accessible
  4. Source connectors needed for OAuth are available
  5. OAuth initiate endpoint works for a test platform (google_ads)
"""

import asyncio
import json
import os
import sys
from urllib.parse import urlparse

try:
    import httpx
except ImportError:
    print("ERROR: httpx not installed. Run: pip install httpx")
    sys.exit(1)

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

BASE_URL = os.environ.get("AIRBYTE_BASE_URL", "").rstrip("/")
API_TOKEN = os.environ.get("AIRBYTE_API_TOKEN", "")
WORKSPACE_ID = os.environ.get("AIRBYTE_WORKSPACE_ID", "")
OAUTH_REDIRECT_URI = os.environ.get(
    "OAUTH_REDIRECT_URI",
    "https://app.markinsight.net/api/sources/oauth/callback",
)

# Platforms we need OAuth to work for
OAUTH_PLATFORMS = {
    "google_ads": "source-google-ads",
    "meta_ads": "source-facebook-marketing",
    "tiktok_ads": "source-tiktok-marketing",
    "snapchat_ads": "source-snapchat-marketing",
}

PASS = "\033[32mPASS\033[0m"
FAIL = "\033[31mFAIL\033[0m"
WARN = "\033[33mWARN\033[0m"
INFO = "\033[36mINFO\033[0m"


def _p(label: str, result: str, detail: str = ""):
    pad = 50
    line = f"  [{result}]  {label}"
    if detail:
        line += f"\n         {detail}"
    print(line)


# ---------------------------------------------------------------------------
# Checks
# ---------------------------------------------------------------------------

def check_env_vars():
    print("\n── 1. Environment variables ──────────────────────────────")
    ok = True

    for name, val in [
        ("AIRBYTE_BASE_URL", BASE_URL),
        ("AIRBYTE_API_TOKEN", API_TOKEN),
        ("AIRBYTE_WORKSPACE_ID", WORKSPACE_ID),
    ]:
        if val:
            display = val if name != "AIRBYTE_API_TOKEN" else val[:8] + "…"
            _p(name, PASS, display)
        else:
            _p(name, FAIL, "not set — add to .env or Render environment")
            ok = False

    # Warn if still pointing at Airbyte Cloud
    if BASE_URL == "https://api.airbyte.com/v1":
        _p("BASE_URL target", WARN,
           "Points to Airbyte Cloud, not OSS. "
           "Set AIRBYTE_BASE_URL=http://<your-airbyte-host>:<port>/api/v1")
    elif BASE_URL:
        parsed = urlparse(BASE_URL)
        _p("BASE_URL target", INFO,
           f"host={parsed.hostname}  port={parsed.port}  path={parsed.path}")

    return ok


async def check_health(client: httpx.AsyncClient) -> bool:
    print("\n── 2. Health check ───────────────────────────────────────")
    try:
        r = await client.get(f"{BASE_URL}/health", timeout=10)
        if r.status_code == 200:
            data = r.json()
            _p("/health", PASS, json.dumps(data))
            return True
        else:
            _p("/health", FAIL, f"HTTP {r.status_code}: {r.text[:200]}")
            return False
    except Exception as e:
        _p("/health", FAIL, f"Connection error: {e}")
        return False


async def check_workspace(client: httpx.AsyncClient) -> bool:
    print("\n── 3. Workspace accessible ───────────────────────────────")
    if not WORKSPACE_ID:
        _p("workspace", FAIL, "AIRBYTE_WORKSPACE_ID not set — skipping")
        return False
    try:
        r = await client.get(f"{BASE_URL}/workspaces/{WORKSPACE_ID}", timeout=10)
        if r.status_code == 200:
            data = r.json()
            name = data.get("name") or data.get("workspaceId", WORKSPACE_ID)
            _p(f"workspace '{name}'", PASS, f"id={WORKSPACE_ID}")
            return True
        elif r.status_code == 404:
            _p("workspace", FAIL,
               f"Workspace {WORKSPACE_ID} not found. "
               "Check AIRBYTE_WORKSPACE_ID matches an existing workspace.")
            return False
        else:
            _p("workspace", FAIL, f"HTTP {r.status_code}: {r.text[:200]}")
            return False
    except Exception as e:
        _p("workspace", FAIL, f"Error: {e}")
        return False


async def check_source_connectors(client: httpx.AsyncClient) -> bool:
    """
    List source definitions and verify the connectors we need are present.
    This confirms Airbyte OSS has the connector docker images available.
    """
    print("\n── 4. Source connectors available ────────────────────────")
    try:
        # Airbyte OSS Platform API endpoint for source definitions
        r = await client.get(
            f"{BASE_URL}/source_definitions",
            params={"workspaceId": WORKSPACE_ID},
            timeout=15,
        )
        if r.status_code == 404:
            # Try alternate path (newer OSS / Cloud v1)
            r = await client.get(f"{BASE_URL}/sources/definitions", timeout=15)

        if r.status_code != 200:
            _p("source_definitions", WARN,
               f"HTTP {r.status_code} — cannot list connectors. "
               "OAuth may still work if connectors are installed.")
            return True  # non-fatal

        data = r.json()
        definitions = data.get("sourceDefinitions") or data.get("data", [])
        available = {
            d.get("dockerRepository", "").lower(): d.get("name", "")
            for d in definitions
        }

        all_ok = True
        for platform, source_type in OAUTH_PLATFORMS.items():
            # source type like "source-google-ads" → docker repo "airbyte/source-google-ads"
            repo_key = f"airbyte/{source_type}"
            matched = any(repo_key in k for k in available)
            if matched:
                _p(f"{platform} ({source_type})", PASS)
            else:
                _p(f"{platform} ({source_type})", WARN,
                   "Connector not found in definitions list. "
                   "It may need to be added to the workspace.")
                all_ok = False

        return all_ok

    except Exception as e:
        _p("source_definitions", WARN, f"Could not check: {e}")
        return True  # non-fatal


async def check_oauth_initiate(client: httpx.AsyncClient) -> bool:
    """
    Call initiate_o_auth for google_ads and confirm we get a consent URL back.
    This is the exact call the application makes.
    """
    print("\n── 5. OAuth initiate endpoint ────────────────────────────")
    if not WORKSPACE_ID:
        _p("initiate_o_auth", FAIL, "AIRBYTE_WORKSPACE_ID not set — skipping")
        return False

    payload = {
        "workspaceId": WORKSPACE_ID,
        "sourceType": "source-google-ads",
        "redirectUrl": OAUTH_REDIRECT_URI,
        "oAuthInputConfiguration": {},
    }

    try:
        r = await client.post(
            f"{BASE_URL}/sources/initiate_o_auth",
            json=payload,
            timeout=15,
        )

        if r.status_code == 200:
            data = r.json()
            url = data.get("consentUrl") or data.get("consent_url", "")
            if url:
                # Truncate for display
                display = url[:80] + "…" if len(url) > 80 else url
                _p("initiate_o_auth (google_ads)", PASS, f"consentUrl: {display}")
                return True
            else:
                _p("initiate_o_auth", WARN,
                   f"200 but no consentUrl in response: {json.dumps(data)[:300]}")
                return False

        elif r.status_code == 404:
            _p("initiate_o_auth", FAIL,
               "404 — endpoint not found at /sources/initiate_o_auth. "
               "Your Airbyte OSS version may use the older path: "
               "POST /api/v1/source_oauths/get_consent_url")
            return False

        elif r.status_code in (400, 422):
            # Could be OAuth creds not configured in Airbyte for this connector
            body = r.json() if r.headers.get("content-type", "").startswith("application/json") else r.text
            _p("initiate_o_auth", WARN,
               f"HTTP {r.status_code} — OAuth credentials may not be configured "
               f"in Airbyte for source-google-ads. Response: {str(body)[:300]}")
            return False

        else:
            _p("initiate_o_auth", FAIL, f"HTTP {r.status_code}: {r.text[:300]}")
            return False

    except Exception as e:
        _p("initiate_o_auth", FAIL, f"Error: {e}")
        return False


# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------

async def main():
    print("=" * 60)
    print("  Airbyte OSS connectivity check")
    print("=" * 60)

    env_ok = check_env_vars()
    if not env_ok:
        print("\n⚠  Fix missing env vars before proceeding.\n")
        sys.exit(1)

    headers = {
        "Authorization": f"Bearer {API_TOKEN}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }

    async with httpx.AsyncClient(headers=headers) as client:
        health_ok = await check_health(client)
        if not health_ok:
            print("\n⚠  Airbyte is unreachable. Check BASE_URL and network.\n")
            sys.exit(1)

        workspace_ok = await check_workspace(client)
        await check_source_connectors(client)
        oauth_ok = await check_oauth_initiate(client)

    print("\n── Summary ───────────────────────────────────────────────")
    results = [
        ("Env vars", env_ok),
        ("Health", health_ok),
        ("Workspace", workspace_ok),
        ("OAuth initiate", oauth_ok),
    ]
    all_pass = all(ok for _, ok in results)
    for label, ok in results:
        _p(label, PASS if ok else FAIL)

    print()
    if all_pass:
        print("  ✓ Airbyte OSS is ready for OAuth delegation.\n")
    else:
        print("  ✗ One or more checks failed. See details above.\n")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
