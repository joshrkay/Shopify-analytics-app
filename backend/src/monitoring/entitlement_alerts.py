"""
Alerts for entitlement evaluation failures and repeated deny events.
"""

import logging
import time
from collections import defaultdict

logger = logging.getLogger(__name__)

# In-memory counter for deny events per minute (sliding window); replace with metrics backend if needed
_deny_counts: defaultdict[str, list] = defaultdict(list)
DENY_THRESHOLD_PER_MIN = 10


def emit_evaluation_failure(tenant_id: str, error_message: str) -> None:
    """Emit support alert + audit event for evaluation failure."""
    logger.error(
        "Entitlement evaluation failure",
        extra={"tenant_id": tenant_id, "error": error_message},
    )
    # TODO: send to PagerDuty/OpsGenie/support channel
    # TODO: write audit event entitlement.eval_failed


def _record_deny(tenant_id: str) -> None:
    now = time.time()
    _deny_counts[tenant_id].append(now)
    # Prune older than 1 minute
    cutoff = now - 60
    _deny_counts[tenant_id] = [t for t in _deny_counts[tenant_id] if t > cutoff]


def record_deny_and_alert(tenant_id: str, feature_key: str) -> None:
    """Record a deny event; alert if over threshold per minute."""
    _record_deny(tenant_id)
    count = len(_deny_counts[tenant_id])
    if count >= DENY_THRESHOLD_PER_MIN:
        emit_deny_alert(tenant_id, feature_key, count)


def emit_deny_alert(tenant_id: str, feature_key: str, count: int) -> None:
    """Alert on repeated deny events (>N/min)."""
    logger.warning(
        "Repeated entitlement deny events",
        extra={"tenant_id": tenant_id, "feature_key": feature_key, "count_per_min": count},
    )
    # TODO: send to support/ops
