"""
Audit log retention configuration.

Retention periods are configurable per billing plan.

Story 10.4 - Retention Enforcement
"""

import os
from typing import Dict

# Default retention periods per plan (in days)
PLAN_RETENTION_DEFAULTS: Dict[str, int] = {
    "free": 30,
    "starter": 90,
    "growth": 180,
    "professional": 365,
    "pro": 730,
    "enterprise": 1825,
}

# Fallback for unknown plans
DEFAULT_RETENTION_DAYS = 90

# Compliance constraints
MINIMUM_RETENTION_DAYS = 30
MAXIMUM_RETENTION_DAYS = 1825  # 5 years

# Batch size for deletion (avoid long transactions)
DELETION_BATCH_SIZE = int(os.getenv("AUDIT_DELETION_BATCH_SIZE", "1000"))

# Dry-run mode (set to "false" to enable actual deletion)
RETENTION_DRY_RUN = os.getenv("AUDIT_RETENTION_DRY_RUN", "true").lower() == "true"


def get_retention_days(plan_id: str) -> int:
    """
    Get retention period for a billing plan.

    Args:
        plan_id: The billing plan identifier

    Returns:
        Retention period in days, clamped to compliance constraints
    """
    days = PLAN_RETENTION_DEFAULTS.get(plan_id, DEFAULT_RETENTION_DAYS)
    return max(MINIMUM_RETENTION_DAYS, min(days, MAXIMUM_RETENTION_DAYS))
