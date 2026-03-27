#!/usr/bin/env python3
"""
Airbyte Cloud connection health checker.

Authenticates with Airbyte Cloud API and reports the status of all
connections, sources, and destinations in the workspace.

Usage:
    # Requires env vars: AIRBYTE_CLOUD_CLIENT_ID, AIRBYTE_CLOUD_CLIENT_SECRET, AIRBYTE_CLOUD_WORKSPACE_ID
    python scripts/check_airbyte_health.py

    # Or pass explicitly:
    python scripts/check_airbyte_health.py \
        --client-id c867... --client-secret p0oD... --workspace-id 6a58...
"""

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from urllib.request import Request, urlopen
from urllib.error import HTTPError


API_BASE = "https://api.airbyte.com/v1"


def get_token(client_id: str, client_secret: str) -> str:
    """Get an OAuth token from Airbyte Cloud API."""
    req = Request(
        f"{API_BASE}/applications/token",
        data=json.dumps({
            "client_id": client_id,
            "client_secret": client_secret,
        }).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urlopen(req) as resp:
        return json.loads(resp.read())["access_token"]


def api_get(path: str, token: str, params: dict | None = None) -> dict:
    """Make a GET request to the Airbyte Cloud API."""
    url = f"{API_BASE}{path}"
    if params:
        qs = "&".join(f"{k}={v}" for k, v in params.items())
        url = f"{url}?{qs}"
    req = Request(url, headers={"Authorization": f"Bearer {token}"})
    with urlopen(req) as resp:
        return json.loads(resp.read())


def format_ago(ts_str: str | None) -> str:
    """Format an ISO timestamp as a human-readable 'X ago' string."""
    if not ts_str:
        return "never"
    try:
        ts = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
        delta = datetime.now(timezone.utc) - ts
        hours = delta.total_seconds() / 3600
        if hours < 1:
            return f"{int(delta.total_seconds() / 60)}m ago"
        if hours < 24:
            return f"{int(hours)}h ago"
        return f"{int(hours / 24)}d ago"
    except (ValueError, TypeError):
        return ts_str


def main():
    parser = argparse.ArgumentParser(description="Check Airbyte Cloud connection health")
    parser.add_argument("--client-id", default=os.environ.get("AIRBYTE_CLOUD_CLIENT_ID"))
    parser.add_argument("--client-secret", default=os.environ.get("AIRBYTE_CLOUD_CLIENT_SECRET"))
    parser.add_argument("--workspace-id", default=os.environ.get("AIRBYTE_CLOUD_WORKSPACE_ID"))
    args = parser.parse_args()

    if not all([args.client_id, args.client_secret, args.workspace_id]):
        print("ERROR: Missing credentials. Set AIRBYTE_CLOUD_CLIENT_ID, "
              "AIRBYTE_CLOUD_CLIENT_SECRET, AIRBYTE_CLOUD_WORKSPACE_ID env vars "
              "or pass --client-id, --client-secret, --workspace-id.")
        sys.exit(1)

    # Authenticate
    print("Authenticating with Airbyte Cloud API...")
    try:
        token = get_token(args.client_id, args.client_secret)
    except HTTPError as e:
        print(f"ERROR: Authentication failed: {e.code} {e.reason}")
        sys.exit(1)

    # List connections
    print(f"\n{'='*70}")
    print(f"AIRBYTE CLOUD HEALTH REPORT — Workspace {args.workspace_id}")
    print(f"{'='*70}\n")

    connections = api_get("/connections", token, {"workspaceId": args.workspace_id})
    sources = api_get("/sources", token, {"workspaceId": args.workspace_id})
    destinations = api_get("/destinations", token, {"workspaceId": args.workspace_id})

    # Index sources and destinations by ID
    src_map = {s["sourceId"]: s for s in sources.get("data", [])}
    dst_map = {d["destinationId"]: d for d in destinations.get("data", [])}

    print(f"Sources: {len(src_map)}")
    for s in src_map.values():
        print(f"  - {s['name']} ({s['sourceType']}) [{s['sourceId'][:8]}...]")

    print(f"\nDestinations: {len(dst_map)}")
    for d in dst_map.values():
        print(f"  - {d['name']} ({d['destinationType']}) [{d['destinationId'][:8]}...]")

    print(f"\nConnections: {len(connections.get('data', []))}")
    print(f"{'-'*70}")

    issues = []
    for conn in connections.get("data", []):
        cid = conn["connectionId"]
        name = conn.get("name", "unnamed")
        schedule = conn.get("schedule", {})
        schedule_type = schedule.get("scheduleType", "manual")
        status = conn.get("status", "unknown")

        # Get latest job
        try:
            jobs = api_get("/jobs", token, {"connectionId": cid, "limit": "1"})
            job_list = jobs.get("data", [])
        except HTTPError:
            job_list = []

        if job_list:
            latest = job_list[0]
            job_status = latest.get("status", "unknown")
            job_rows = latest.get("rowsSynced", 0)
            job_started = latest.get("startTime")
            job_duration = latest.get("duration")
        else:
            job_status = "no_jobs"
            job_rows = 0
            job_started = None
            job_duration = None

        # Status indicators
        status_icon = "OK" if job_status == "succeeded" else "FAIL" if job_status == "failed" else "??"
        schedule_icon = "AUTO" if schedule_type != "manual" else "MANUAL"

        print(f"\n  [{status_icon}] {name}")
        print(f"      Connection ID: {cid}")
        print(f"      Status: {status} | Schedule: {schedule_icon} ({schedule_type})")
        print(f"      Last sync: {format_ago(job_started)} | {job_status} | {job_rows} rows | {job_duration or 'N/A'}")

        # Flag issues
        if job_status == "failed":
            issues.append(f"FAILED: {name} — last sync failed (started {format_ago(job_started)})")
        if schedule_type == "manual":
            issues.append(f"MANUAL: {name} — schedule is manual (should be automatic for production)")
        if job_status == "succeeded" and job_rows == 0:
            issues.append(f"EMPTY: {name} — last sync succeeded but returned 0 rows")

    # Summary
    print(f"\n{'='*70}")
    if issues:
        print(f"ISSUES FOUND ({len(issues)}):")
        for issue in issues:
            print(f"  - {issue}")
    else:
        print("All connections healthy.")
    print(f"{'='*70}")

    sys.exit(1 if any(i.startswith("FAILED") for i in issues) else 0)


if __name__ == "__main__":
    main()
