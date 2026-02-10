"""
Entitlement evaluation: override → plan → deny. Cache in Redis; fail closed on errors.
"""

import logging
from datetime import datetime, timezone
from typing import List, Optional

from src.entitlements import cache as entitlement_cache
from src.entitlements.loader import get_plan_features
from src.entitlements.models import EntitlementSet, OverrideEntry, ResolutionResult
from src.entitlements.overrides import list_active_overrides
from src.monitoring.entitlement_alerts import emit_evaluation_failure, emit_deny_alert

logger = logging.getLogger(__name__)

# Placeholder: resolve plan from Shopify billing for tenant. Replace with real billing client.
def _get_plan_for_tenant(tenant_id: str) -> str:
    """Return plan name for tenant (e.g. from Shopify billing API or DB). Default free."""
    try:
        # from src.integrations.shopify.billing import get_subscription_plan
        # return get_subscription_plan(tenant_id) or "free"
        return "free"
    except Exception:
        return "free"


def get_entitlements(tenant_id: str) -> ResolutionResult:
    """
    Resolve entitlements for tenant: override → plan → deny.
    Uses cache on hit; on miss computes and caches. Fails closed on error.
    """
    # 1. Cache hit
    cached = entitlement_cache.get_cached(tenant_id)
    if cached is not None:
        return ResolutionResult(allowed=True, entitlement_set=cached)

    # 2. Resolve
    try:
        plan = _get_plan_for_tenant(tenant_id)
        base_features = get_plan_features(plan)
        if base_features is None:
            base_features = ()

        now = datetime.now(timezone.utc)
        overrides: List[OverrideEntry] = list_active_overrides(tenant_id, now=now)
        override_keys = [o.feature_key for o in overrides]
        # Overrides extend plan; do not remove plan features (overrides never mutate plan defaults)
        all_features = list(base_features) + [k for k in override_keys if k not in base_features]
        ent_set = EntitlementSet(
            tenant_id=tenant_id,
            plan=plan,
            features=tuple(all_features),
            overrides_applied=tuple(override_keys),
        )
        # TTL: if overrides exist, use min(override expiry - now, DEFAULT_TTL)
        ttl = None
        if overrides:
            min_expiry = min(o.expires_at for o in overrides)
            delta = (min_expiry - now).total_seconds()
            if delta > 0:
                ttl = min(int(delta), entitlement_cache.DEFAULT_TTL)
        entitlement_cache.set_cached(ent_set, ttl_seconds=ttl)
        return ResolutionResult(allowed=True, entitlement_set=ent_set)
    except Exception as e:
        logger.exception("Entitlement evaluation failed for tenant %s", tenant_id)
        emit_evaluation_failure(tenant_id, str(e))
        return ResolutionResult(
            allowed=False,
            entitlement_set=None,
            deny_reason="Entitlement evaluation failed",
            error_code="ENTITLEMENT_EVAL_FAILED",
        )


def invalidate_entitlements(tenant_id: str) -> None:
    """Clear cache for tenant; next get_entitlements will recompute."""
    entitlement_cache.delete_cached(tenant_id)


def has_feature(tenant_id: str, feature_key: str) -> bool:
    """Convenience: True if tenant has feature. Fails closed (False on error)."""
    result = get_entitlements(tenant_id)
    if not result.allowed or result.entitlement_set is None:
        return False
    return result.entitlement_set.has_feature(feature_key)
