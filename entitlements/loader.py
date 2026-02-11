from __future__ import annotations

import json
from pathlib import Path
from threading import RLock
from typing import Dict, Iterable, List, Optional

from .models import Entitlement, PlanDefinition, PlansConfig, TenantOverride, resolve_entitlement


class EntitlementLoader:
    """Loads plan-to-feature mappings from config/plans.json with reload support."""

    def __init__(self, config_path: str = "config/plans.json") -> None:
        self._config_path = Path(config_path)
        self._lock = RLock()
        self._config: PlansConfig
        self.reload()

    def reload(self) -> None:
        """Reload config from disk (for safe process restart workflows)."""
        raw = self._read_config_file()
        parsed = self._parse_config(raw)
        with self._lock:
            self._config = parsed

    def get_plan(self, plan_key: str) -> PlanDefinition:
        if not plan_key:
            raise ValueError("plan_key is required")
        with self._lock:
            plan = self._config.plans.get(plan_key)
        if plan is None:
            raise KeyError(f"unknown plan_key: {plan_key}")
        return plan

    def resolve_for_tenant(
        self,
        *,
        tenant_id: str,
        plan_key: str,
        overrides: Optional[Iterable[TenantOverride]] = None,
        feature_keys: Optional[Iterable[str]] = None,
    ) -> Entitlement:
        normalized_tenant_id = str(tenant_id).strip()
        if not normalized_tenant_id:
            raise ValueError("tenant_id is required")

        plan = self.get_plan(plan_key)
        override_list = list(overrides or [])
        requested: List[str]

        if feature_keys is None:
            with self._lock:
                known = set(self._config.known_feature_keys())
            override_keys = {
                o.feature_key for o in override_list if o.tenant_id == tenant_id
            }
            requested = sorted(known | override_keys)
        else:
            requested = sorted({str(k) for k in feature_keys if str(k).strip()})

        return resolve_entitlement(
            tenant_id=tenant_id,
            plan=plan,
            overrides=override_list,
            requested_feature_keys=requested,
        )

    def _read_config_file(self) -> dict:
        with self._config_path.open("r", encoding="utf-8") as handle:
            raw = json.load(handle)
        if not isinstance(raw, dict):
            raise ValueError("config/plans.json must contain a top-level object")
        return raw

    @staticmethod
    def _parse_config(raw: dict) -> PlansConfig:
        plans_raw = raw.get("plans")
        if not isinstance(plans_raw, dict):
            raise ValueError("config/plans.json must include an object field named 'plans'")

        plans: Dict[str, PlanDefinition] = {}
        for plan_key, plan_data in plans_raw.items():
            if not isinstance(plan_key, str) or not plan_key.strip():
                raise ValueError("each plan key must be a non-empty string")
            if not isinstance(plan_data, dict):
                raise ValueError(f"plan '{plan_key}' must be an object")

            features = plan_data.get("features", [])
            if not isinstance(features, list):
                raise ValueError(f"plan '{plan_key}' features must be a list of feature keys")

            normalized_features: List[str] = []
            for feature_key in features:
                if not isinstance(feature_key, str) or not feature_key.strip():
                    raise ValueError(f"plan '{plan_key}' has invalid feature key: {feature_key!r}")
                normalized_features.append(feature_key)

            limits = plan_data.get("limits", {})
            if not isinstance(limits, dict):
                raise ValueError(f"plan '{plan_key}' limits must be an object")

            normalized_limits: Dict[str, int] = {}
            for limit_key, limit_value in limits.items():
                if not isinstance(limit_key, str) or not limit_key.strip():
                    raise ValueError(f"plan '{plan_key}' has invalid limit key: {limit_key!r}")
                normalized_limits[limit_key] = int(limit_value)

            plans[plan_key] = PlanDefinition(
                plan_key=plan_key,
                feature_keys=frozenset(normalized_features),
                limits=normalized_limits,
            )

        if not plans:
            raise ValueError("config/plans.json must define at least one plan")

        return PlansConfig(plans=plans)
