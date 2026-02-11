from __future__ import annotations

from datetime import datetime, timezone
from typing import Callable, Iterable, Optional

from .cache import EntitlementCache, invalidate_entitlements
from .loader import EntitlementLoader
from .models import Entitlement, TenantOverride


FAIL_CLOSED_ERROR_CODE = "ENTITLEMENTS_UNAVAILABLE_FAIL_CLOSED"


class EntitlementEvaluationError(RuntimeError):
    def __init__(self, tenant_id: str, message: str, error_code: str = FAIL_CLOSED_ERROR_CODE):
        super().__init__(message)
        self.tenant_id = tenant_id
        self.error_code = error_code


def _normalize_plan_key(plan_key: str) -> str:
    normalized = str(plan_key).strip()
    if normalized.startswith("plan_"):
        return normalized[len("plan_") :]
    return normalized


class EntitlementService:
    """Lazy per-request evaluation with cache and safe invalidation."""

    def __init__(
        self,
        *,
        loader: Optional[EntitlementLoader] = None,
        cache: Optional[EntitlementCache] = None,
        plan_resolver: Optional[Callable[[str], str]] = None,
        overrides_resolver: Optional[Callable[[str], Iterable[TenantOverride]]] = None,
        audit_sink: Optional[Callable[[str, dict], None]] = None,
        support_alert_sink: Optional[Callable[[str, dict], None]] = None,
    ) -> None:
        self.loader = loader or EntitlementLoader()
        self.cache = cache or EntitlementCache()
        self._plan_resolver = plan_resolver or (lambda tenant_id: "free")
        self._overrides_resolver = overrides_resolver or (lambda tenant_id: [])
        self._audit_sink = audit_sink or (lambda event, payload: None)
        self._support_alert_sink = support_alert_sink or (lambda code, payload: None)

    def get_entitlements(self, tenant_id: str) -> Entitlement:
        """Lazy evaluation on protected requests: cache-hit or compute on demand."""
        if not str(tenant_id).strip():
            raise ValueError("tenant_id is required")

        cached = self.cache.get(tenant_id)
        if cached is not None:
            return cached

        return self._compute_and_cache(tenant_id)

    def handle_billing_webhook(self, tenant_id: str) -> Entitlement:
        """Immediate recompute on webhook receipt."""
        if not str(tenant_id).strip():
            raise ValueError("tenant_id is required")
        invalidate_entitlements(tenant_id, cache=self.cache)
        return self._compute_and_cache(tenant_id)

    def invalidate_for_override_change(self, tenant_id: str, expires_at: Optional[datetime] = None) -> None:
        invalidate_entitlements(tenant_id, cache=self.cache)
        if expires_at is not None:
            self.cache.track_override_expiry(tenant_id=tenant_id, expires_at=expires_at)

    def _compute_and_cache(self, tenant_id: str) -> Entitlement:
        try:
            raw_plan_key = self._plan_resolver(tenant_id)
            plan_key = _normalize_plan_key(raw_plan_key)
            overrides = list(self._overrides_resolver(tenant_id))

            entitlement = self.loader.resolve_for_tenant(
                tenant_id=tenant_id,
                plan_key=plan_key,
                overrides=overrides,
                feature_keys=None,
            )
            self.cache.set(entitlement)
            return entitlement
        except Exception as exc:  # fail-closed by returning no entitlements through error path
            payload = {
                "tenant_id": tenant_id,
                "error": str(exc),
                "error_code": FAIL_CLOSED_ERROR_CODE,
                "occurred_at": datetime.now(timezone.utc).isoformat(),
            }
            self._audit_sink("entitlements.evaluation_failed", payload)
            self._support_alert_sink(FAIL_CLOSED_ERROR_CODE, payload)
            raise EntitlementEvaluationError(
                tenant_id=tenant_id,
                message="Entitlements unavailable. Access denied.",
                error_code=FAIL_CLOSED_ERROR_CODE,
            ) from exc


# compatibility top-level API requested in task
_default_service = EntitlementService()


def get_entitlements(tenant_id: str) -> Entitlement:
    return _default_service.get_entitlements(tenant_id)


def webhook_recompute_entitlements(tenant_id: str) -> Entitlement:
    return _default_service.handle_billing_webhook(tenant_id)
