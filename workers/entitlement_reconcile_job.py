from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

from entitlements.cache import EntitlementCache
from entitlements.service import EntitlementService


@dataclass
class ReconcileStats:
    started_at: str
    completed_at: Optional[str] = None
    expired_override_invalidations: int = 0
    webhook_recomputes: int = 0
    errors: int = 0


def run_entitlement_reconcile_cycle(service: Optional[EntitlementService] = None) -> ReconcileStats:
    """Background drift reconciliation job.

    Responsibilities:
    - invalidate tenants whose override expiry passed
    - trigger lazy recompute naturally on next request
    """

    svc = service or EntitlementService(cache=EntitlementCache())
    stats = ReconcileStats(started_at=datetime.now(timezone.utc).isoformat())

    try:
        expired_tenants = svc.cache.invalidate_expired_overrides()
        stats.expired_override_invalidations = len(expired_tenants)
    except Exception:
        stats.errors += 1

    stats.completed_at = datetime.now(timezone.utc).isoformat()
    return stats


def run_forever(interval_seconds: int = 60) -> None:
    import time

    while True:
        run_entitlement_reconcile_cycle()
        time.sleep(interval_seconds)
