from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from entitlements.cache import CACHE_SCHEMA_VERSION, EntitlementCache, _decode_entitlement, _encode_entitlement
from entitlements.loader import EntitlementLoader
from entitlements.models import PlanDefinition, TenantOverride, resolve_entitlement
from entitlements.service import EntitlementEvaluationError, EntitlementService


class _FakeRedis:
    def __init__(self):
        self.store = {}
        self.zsets = {}

    def get(self, key):
        return self.store.get(key)

    def setex(self, key, ttl, value):
        self.store[key] = value

    def delete(self, key):
        self.store.pop(key, None)

    def zadd(self, key, members):
        z = self.zsets.setdefault(key, {})
        z.update(members)

    def zscore(self, key, member):
        return self.zsets.get(key, {}).get(member)

    def zrangebyscore(self, key, min_score, max_score):
        z = self.zsets.get(key, {})
        return [m for m, s in z.items() if min_score <= s <= max_score]

    def zrem(self, key, member):
        self.zsets.get(key, {}).pop(member, None)



def test_duplicate_override_same_expiry_denies_fail_safe():
    now = datetime.now(timezone.utc)
    same_expiry = now + timedelta(minutes=10)
    plan = PlanDefinition(plan_key="growth", feature_keys=frozenset({"reports.advanced"}))

    grant = TenantOverride(
        tenant_id="tenant-1",
        feature_key="reports.advanced",
        effect="grant",
        expires_at=same_expiry,
    )
    deny = TenantOverride(
        tenant_id="tenant-1",
        feature_key="reports.advanced",
        effect="deny",
        expires_at=same_expiry,
    )

    entitlement = resolve_entitlement(
        tenant_id="tenant-1",
        plan=plan,
        overrides=[grant, deny],
        requested_feature_keys=["reports.advanced"],
        now=now,
    )

    assert entitlement.features["reports.advanced"].source == "override"
    assert entitlement.features["reports.advanced"].granted is False



def test_loader_strips_feature_keys_and_plan_key(tmp_path):
    config_file = tmp_path / "plans.json"
    config_file.write_text(
        '{"plans": {" growth ": {"features": [" reports.basic ", "exports.csv"], "limits": {" team_members ": 3}}}}',
        encoding="utf-8",
    )

    loader = EntitlementLoader(str(config_file))
    entitlement = loader.resolve_for_tenant(
        tenant_id="tenant-1",
        plan_key="growth",
        feature_keys=[" reports.basic ", " exports.csv "],
    )

    assert entitlement.has_feature("reports.basic") is True
    assert entitlement.has_feature("exports.csv") is True



def test_service_normalizes_shopify_plan_prefix():
    service = EntitlementService(
        plan_resolver=lambda tenant_id: "plan_growth",
        overrides_resolver=lambda tenant_id: [],
    )

    entitlement = service.get_entitlements("tenant-1")
    assert entitlement.plan_key == "growth"



def test_cache_tracks_earliest_override_expiry_per_tenant():
    cache = EntitlementCache(redis_url="")
    fake = _FakeRedis()
    cache._redis = fake

    now = datetime.now(timezone.utc)
    later = now + timedelta(minutes=30)
    sooner = now + timedelta(minutes=5)

    cache.track_override_expiry(tenant_id="tenant-1", expires_at=later)
    cache.track_override_expiry(tenant_id="tenant-1", expires_at=sooner)

    score = fake.zscore(cache._expiry_index_key(), "tenant-1")
    assert score == int(sooner.timestamp())



def test_cache_requires_schema_version_match():
    now = datetime.now(timezone.utc)
    plan = PlanDefinition(plan_key="free", feature_keys=frozenset({"reports.basic"}))
    entitlement = resolve_entitlement(
        tenant_id="tenant-1",
        plan=plan,
        overrides=[],
        requested_feature_keys=["reports.basic"],
        now=now,
    )
    payload = _encode_entitlement(entitlement)
    assert payload["schema_version"] == CACHE_SCHEMA_VERSION

    payload["schema_version"] = 999
    with pytest.raises(ValueError):
        _decode_entitlement(payload)



def test_fail_closed_error_code_surfaces():
    service = EntitlementService(
        cache=EntitlementCache(redis_url=""),
        plan_resolver=lambda tenant_id: (_ for _ in ()).throw(RuntimeError("boom")),
    )

    with pytest.raises(EntitlementEvaluationError) as exc:
        service.get_entitlements("tenant-1")

    assert exc.value.error_code == "ENTITLEMENTS_UNAVAILABLE_FAIL_CLOSED"


# =============================================================================
# Regression tests for fixed validation bugs
# =============================================================================


def test_whitespace_only_tenant_id_rejected_by_resolve_entitlement():
    """Whitespace-only tenant_id must be rejected (regression for duplicate-line bug)."""
    plan = PlanDefinition(plan_key="free", feature_keys=frozenset({"reports.basic"}))

    with pytest.raises(ValueError, match="tenant_id is required"):
        resolve_entitlement(
            tenant_id="   ",
            plan=plan,
            overrides=[],
            requested_feature_keys=["reports.basic"],
        )


def test_empty_tenant_id_rejected_by_resolve_entitlement():
    """Empty string tenant_id must be rejected."""
    plan = PlanDefinition(plan_key="free", feature_keys=frozenset({"reports.basic"}))

    with pytest.raises(ValueError, match="tenant_id is required"):
        resolve_entitlement(
            tenant_id="",
            plan=plan,
            overrides=[],
            requested_feature_keys=["reports.basic"],
        )


def test_whitespace_only_feature_key_rejected_by_override():
    """Whitespace-only feature_key must be rejected on TenantOverride (regression)."""
    now = datetime.now(timezone.utc)

    with pytest.raises(ValueError, match="feature_key is required"):
        TenantOverride(
            tenant_id="tenant-1",
            feature_key="   ",
            effect="grant",
            expires_at=now + timedelta(hours=1),
        )


def test_whitespace_only_tenant_id_rejected_by_override():
    """Whitespace-only tenant_id must be rejected on TenantOverride (regression)."""
    now = datetime.now(timezone.utc)

    with pytest.raises(ValueError, match="tenant_id is required"):
        TenantOverride(
            tenant_id="   ",
            feature_key="reports.basic",
            effect="grant",
            expires_at=now + timedelta(hours=1),
        )


def test_whitespace_only_tenant_id_rejected_by_loader(tmp_path):
    """Whitespace-only tenant_id must be rejected by EntitlementLoader (regression)."""
    config_file = tmp_path / "plans.json"
    config_file.write_text(
        '{"plans": {"free": {"features": ["reports.basic"], "limits": {}}}}',
        encoding="utf-8",
    )

    loader = EntitlementLoader(str(config_file))

    with pytest.raises(ValueError, match="tenant_id is required"):
        loader.resolve_for_tenant(
            tenant_id="   ",
            plan_key="free",
        )
