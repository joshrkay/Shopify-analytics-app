from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from types import MappingProxyType
from typing import Dict, FrozenSet, Iterable, Literal, Mapping, Optional

ResolutionSource = Literal["override", "plan", "deny"]
OverrideEffect = Literal["grant", "deny"]


@dataclass(frozen=True)
class TenantOverride:
    """A per-tenant entitlement override with mandatory expiry."""

    tenant_id: str
    feature_key: str
    effect: OverrideEffect
    expires_at: datetime

    def __post_init__(self) -> None:
        if not self.tenant_id:
            raise ValueError("tenant_id is required")
        if not self.feature_key:
            raise ValueError("feature_key is required")
        if self.expires_at.tzinfo is None:
            raise ValueError("expires_at must be timezone-aware")
        if self.effect not in ("grant", "deny"):
            raise ValueError("effect must be one of: grant, deny")

    def is_active(self, now: Optional[datetime] = None) -> bool:
        compare_at = now or datetime.now(timezone.utc)
        return self.expires_at > compare_at


@dataclass(frozen=True)
class FeatureEntitlement:
    """Resolution for a single feature key."""

    feature_key: str
    granted: bool
    source: ResolutionSource


@dataclass(frozen=True)
class Entitlement:
    """Typed entitlement snapshot for a tenant."""

    tenant_id: str
    plan_key: str
    features: Mapping[str, FeatureEntitlement]
    resolved_at: datetime
    active_override_count: int = 0

    def __post_init__(self) -> None:
        object.__setattr__(self, "features", MappingProxyType(dict(self.features)))

    def has_feature(self, feature_key: str) -> bool:
        if not self.tenant_id:
            raise ValueError("tenant_id is required for entitlement lookups")
        result = self.features.get(feature_key)
        return bool(result and result.granted)


@dataclass(frozen=True)
class PlanDefinition:
    """Plan defaults from config/plans.json."""

    plan_key: str
    feature_keys: FrozenSet[str]
    limits: Mapping[str, int] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "feature_keys", frozenset(self.feature_keys))
        object.__setattr__(self, "limits", MappingProxyType(dict(self.limits)))


@dataclass(frozen=True)
class PlansConfig:
    """Parsed plan mapping loaded from config/plans.json."""

    plans: Mapping[str, PlanDefinition]

    def __post_init__(self) -> None:
        object.__setattr__(self, "plans", MappingProxyType(dict(self.plans)))

    def known_feature_keys(self) -> FrozenSet[str]:
        keys: set[str] = set()
        for plan in self.plans.values():
            keys.update(plan.feature_keys)
        return frozenset(keys)


def resolve_entitlement(
    *,
    tenant_id: str,
    plan: PlanDefinition,
    overrides: Iterable[TenantOverride],
    requested_feature_keys: Iterable[str],
    now: Optional[datetime] = None,
) -> Entitlement:
    """Resolve entitlements in deterministic order: override -> plan -> deny."""
    if not tenant_id:
        raise ValueError("tenant_id is required")

    resolved_at = now or datetime.now(timezone.utc)

    active_overrides: Dict[str, TenantOverride] = {}
    for override in overrides:
        if override.tenant_id != tenant_id:
            continue
        if override.is_active(resolved_at):
            existing = active_overrides.get(override.feature_key)
            if existing is None or override.expires_at > existing.expires_at:
                # Deterministic precedence for duplicate overrides: furthest expiry wins.
                active_overrides[override.feature_key] = override

    features: Dict[str, FeatureEntitlement] = {}
    for feature_key in sorted(set(requested_feature_keys)):
        override = active_overrides.get(feature_key)
        if override:
            features[feature_key] = FeatureEntitlement(
                feature_key=feature_key,
                granted=override.effect == "grant",
                source="override",
            )
            continue

        if feature_key in plan.feature_keys:
            features[feature_key] = FeatureEntitlement(
                feature_key=feature_key,
                granted=True,
                source="plan",
            )
            continue

        features[feature_key] = FeatureEntitlement(
            feature_key=feature_key,
            granted=False,
            source="deny",
        )

    return Entitlement(
        tenant_id=tenant_id,
        plan_key=plan.plan_key,
        features=features,
        resolved_at=resolved_at,
        active_override_count=len(active_overrides),
    )
