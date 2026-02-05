"""
Stateless parsers for dbt artifacts.

Supports:
- run_results.json (per-model execution metadata)
- freshness.json  (per-source freshness checks)

Deterministic and idempotent: pure functions that operate on already-loaded
artifact dicts. No I/O is performed here.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import List, Optional


# ── Helpers ──────────────────────────────────────────────────────────────────


def _parse_timestamp(raw: object) -> Optional[datetime]:
    """Parse dbt timestamp fields into timezone-aware UTC datetimes."""
    if raw is None:
        return None
    if isinstance(raw, (int, float)):
        return datetime.fromtimestamp(raw, tz=timezone.utc)
    if isinstance(raw, str):
        try:
            ts = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        except ValueError:
            return None
        return ts if ts.tzinfo else ts.replace(tzinfo=timezone.utc)
    return None


def _compute_age_minutes(max_loaded_at: Optional[datetime], snapshotted_at: Optional[datetime]) -> Optional[float]:
    """Compute age in minutes between freshness snapshot and max_loaded_at."""
    if max_loaded_at is None or snapshotted_at is None:
        return None
    return (snapshotted_at - max_loaded_at).total_seconds() / 60.0


# ── Data classes ─────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class DbtModelRun:
    """Single model execution from run_results.json."""

    unique_id: str
    status: str
    completed_at: Optional[datetime]
    execution_time_seconds: Optional[float]
    thread_id: Optional[str]
    adapter_response: Optional[dict]


@dataclass(frozen=True)
class DbtSourceFreshness:
    """Freshness check result from freshness.json."""

    unique_id: str
    status: str
    max_loaded_at: Optional[datetime]
    snapshotted_at: Optional[datetime]
    age_minutes: Optional[float]
    adapter_response: Optional[dict]


# ── Parsers ──────────────────────────────────────────────────────────────────


def parse_run_results(payload: dict) -> List[DbtModelRun]:
    """
    Parse dbt run_results.json payload into DbtModelRun entries.

    Args:
        payload: Dict loaded from run_results.json.

    Returns:
        List of DbtModelRun rows (empty on invalid/empty payload).
    """
    results = payload.get("results") if isinstance(payload, dict) else None
    if not isinstance(results, list):
        return []

    parsed: List[DbtModelRun] = []
    for item in results:
        if not isinstance(item, dict):
            continue
        parsed.append(
            DbtModelRun(
                unique_id=str(item.get("unique_id", "")),
                status=str(item.get("status", "unknown")),
                completed_at=_parse_timestamp(item.get("completed_at")),
                execution_time_seconds=(
                    float(item["execution_time"]) if isinstance(item.get("execution_time"), (int, float)) else None
                ),
                thread_id=str(item.get("thread_id")) if item.get("thread_id") is not None else None,
                adapter_response=item.get("adapter_response") if isinstance(item.get("adapter_response"), dict) else None,
            )
        )

    return parsed


def parse_freshness_results(payload: dict) -> List[DbtSourceFreshness]:
    """
    Parse dbt freshness.json payload into DbtSourceFreshness entries.

    Args:
        payload: Dict loaded from freshness.json.

    Returns:
        List of DbtSourceFreshness rows (empty on invalid/empty payload).
    """
    sources = payload.get("sources") if isinstance(payload, dict) else None
    if not isinstance(sources, list):
        return []

    parsed: List[DbtSourceFreshness] = []
    for item in sources:
        if not isinstance(item, dict):
            continue

        max_loaded = _parse_timestamp(item.get("max_loaded_at"))
        snapshotted = _parse_timestamp(item.get("snapshotted_at"))

        parsed.append(
            DbtSourceFreshness(
                unique_id=str(item.get("unique_id", "")),
                status=str(item.get("status", "unknown")),
                max_loaded_at=max_loaded,
                snapshotted_at=snapshotted,
                age_minutes=_compute_age_minutes(max_loaded, snapshotted),
                adapter_response=item.get("adapter_response") if isinstance(item.get("adapter_response"), dict) else None,
            )
        )

    return parsed
