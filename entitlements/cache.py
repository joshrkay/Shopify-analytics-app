from __future__ import annotations

import json
import os
import time
from datetime import datetime, timezone
from typing import Dict, Optional

from .models import Entitlement, FeatureEntitlement

CACHE_SCHEMA_VERSION = 1


class EntitlementCache:
    """Redis-backed entitlement cache with in-memory fallback."""

    def __init__(self, redis_url: Optional[str] = None, ttl_seconds: int = 300) -> None:
        self._ttl_seconds = ttl_seconds
        self._redis = None
        self._mem: Dict[str, tuple[int, dict]] = {}
        redis_url = redis_url or os.getenv("REDIS_URL")

        if redis_url:
            try:
                import redis

                self._redis = redis.from_url(redis_url, decode_responses=True)
                self._redis.ping()
            except Exception:
                self._redis = None

    @staticmethod
    def _require_tenant_id(tenant_id: str) -> str:
        normalized = str(tenant_id).strip()
        if not normalized:
            raise ValueError("tenant_id is required")
        return normalized

    @staticmethod
    def _key(tenant_id: str) -> str:
        return f"entitlements:v1:{tenant_id}"

    @staticmethod
    def _expiry_index_key() -> str:
        return "entitlements:override_expiry"

    def get(self, tenant_id: str) -> Optional[Entitlement]:
        normalized_tenant_id = self._require_tenant_id(tenant_id)
        key = self._key(normalized_tenant_id)

        if self._redis is not None:
            raw = self._redis.get(key)
            if not raw:
                return None
            return _decode_entitlement(json.loads(raw))

        data = self._mem.get(key)
        if not data:
            return None

        cached_at, payload = data
        if int(time.time()) - cached_at > self._ttl_seconds:
            self._mem.pop(key, None)
            return None
        return _decode_entitlement(payload)

    def set(self, entitlement: Entitlement, *, ttl_seconds: Optional[int] = None) -> None:
        normalized_tenant_id = self._require_tenant_id(entitlement.tenant_id)
        ttl = ttl_seconds or self._ttl_seconds
        key = self._key(normalized_tenant_id)
        payload = _encode_entitlement(entitlement)

        if self._redis is not None:
            self._redis.setex(key, ttl, json.dumps(payload))
            return

        self._mem[key] = (int(time.time()), payload)

    def invalidate(self, tenant_id: str) -> None:
        normalized_tenant_id = self._require_tenant_id(tenant_id)
        key = self._key(normalized_tenant_id)
        if self._redis is not None:
            self._redis.delete(key)
        self._mem.pop(key, None)

    def track_override_expiry(self, *, tenant_id: str, expires_at: datetime) -> None:
        """Track earliest known override expiry so worker invalidates promptly."""
        normalized_tenant_id = self._require_tenant_id(tenant_id)
        score = int(expires_at.timestamp())
        if self._redis is not None:
            existing_score = self._redis.zscore(self._expiry_index_key(), normalized_tenant_id)
            if existing_score is None:
                self._redis.zadd(self._expiry_index_key(), {normalized_tenant_id: score})
            else:
                self._redis.zadd(self._expiry_index_key(), {normalized_tenant_id: min(int(existing_score), score)})
            return

        # in-memory fallback: force refresh behavior
        self._mem.pop(self._key(normalized_tenant_id), None)

    def invalidate_expired_overrides(self, *, now: Optional[datetime] = None) -> list[str]:
        """Invalidate tenants whose tracked override expiry has passed."""
        ts = int((now or datetime.now(timezone.utc)).timestamp())
        invalidated: list[str] = []

        if self._redis is None:
            return invalidated

        due = self._redis.zrangebyscore(self._expiry_index_key(), 0, ts)
        for tenant_id in due:
            self.invalidate(tenant_id)
            invalidated.append(tenant_id)
            self._redis.zrem(self._expiry_index_key(), tenant_id)

        return invalidated


def invalidate_entitlements(tenant_id: str, *, cache: Optional[EntitlementCache] = None) -> None:
    (cache or EntitlementCache()).invalidate(tenant_id)


def _encode_entitlement(entitlement: Entitlement) -> dict:
    return {
        "schema_version": CACHE_SCHEMA_VERSION,
        "tenant_id": entitlement.tenant_id,
        "plan_key": entitlement.plan_key,
        "active_override_count": entitlement.active_override_count,
        "resolved_at": entitlement.resolved_at.isoformat(),
        "features": {
            key: {
                "feature_key": value.feature_key,
                "granted": value.granted,
                "source": value.source,
            }
            for key, value in entitlement.features.items()
        },
    }


def _decode_entitlement(raw: dict) -> Entitlement:
    if int(raw.get("schema_version", CACHE_SCHEMA_VERSION)) != CACHE_SCHEMA_VERSION:
        raise ValueError("Unsupported entitlement cache schema version")

    features = {
        key: FeatureEntitlement(
            feature_key=value["feature_key"],
            granted=bool(value["granted"]),
            source=value["source"],
        )
        for key, value in raw["features"].items()
    }
    return Entitlement(
        tenant_id=raw["tenant_id"],
        plan_key=raw["plan_key"],
        features=features,
        resolved_at=datetime.fromisoformat(raw["resolved_at"]),
        active_override_count=int(raw.get("active_override_count", 0)),
    )
