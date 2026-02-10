"""
Redis cache for per-tenant entitlements. TTL respects earliest override expiry when present.
"""

import json
import logging
from typing import Optional

from src.entitlements.models import EntitlementSet

logger = logging.getLogger(__name__)

# Key prefix and default TTL (seconds)
CACHE_KEY_PREFIX = "entitlements:"
DEFAULT_TTL = 3600  # 1 hour when no override expiry


def _key(tenant_id: str) -> str:
    return f"{CACHE_KEY_PREFIX}{tenant_id}"


def _serialize(ent: EntitlementSet) -> str:
    return json.dumps({
        "tenant_id": ent.tenant_id,
        "plan": ent.plan,
        "features": list(ent.features),
        "overrides_applied": list(ent.overrides_applied),
    })


def _deserialize(data: str) -> EntitlementSet:
    o = json.loads(data)
    return EntitlementSet(
        tenant_id=o["tenant_id"],
        plan=o["plan"],
        features=tuple(o["features"]),
        overrides_applied=tuple(o.get("overrides_applied") or []),
    )


def get_redis_client():
    """Lazy Redis client; replace with your connection pool."""
    try:
        import redis
        import os
        url = os.getenv("REDIS_URL", "redis://localhost:6379/0")
        return redis.from_url(url, decode_responses=True)
    except Exception as e:
        logger.warning("Redis unavailable: %s", e)
        return None


def get_cached(tenant_id: str) -> Optional[EntitlementSet]:
    """Return cached entitlements for tenant or None on miss/failure."""
    client = get_redis_client()
    if not client:
        return None
    try:
        raw = client.get(_key(tenant_id))
        if not raw:
            return None
        return _deserialize(raw)
    except Exception as e:
        logger.warning("Entitlements cache get failed: %s", e)
        return None


def set_cached(ent: EntitlementSet, ttl_seconds: Optional[int] = None) -> None:
    """Cache entitlements. ttl_seconds: use DEFAULT_TTL if None."""
    client = get_redis_client()
    if not client:
        return
    ttl = ttl_seconds if ttl_seconds is not None else DEFAULT_TTL
    try:
        client.setex(_key(ent.tenant_id), ttl, _serialize(ent))
    except Exception as e:
        logger.warning("Entitlements cache set failed: %s", e)


def delete_cached(tenant_id: str) -> None:
    """Invalidate cache for tenant."""
    client = get_redis_client()
    if not client:
        return
    try:
        client.delete(_key(tenant_id))
    except Exception as e:
        logger.warning("Entitlements cache delete failed: %s", e)
