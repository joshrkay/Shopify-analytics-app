"""
Entitlement error hierarchy.

Provides:
- EntitlementError: base for all entitlement failures
- EntitlementEvaluationError: evaluation failed (fail-closed)
- FeatureDeniedError: feature not entitled
- OverrideValidationError: invalid override (e.g. missing expiry)
"""

from typing import Optional


class EntitlementError(Exception):
    """Base exception for entitlement-related failures."""

    def __init__(self, message: str):
        self.message = message
        super().__init__(message)


class EntitlementEvaluationError(EntitlementError):
    """
    Raised when entitlement evaluation fails (fail-closed).

    Carries a machine-readable error_code for the UI to display.
    """

    def __init__(
        self,
        tenant_id: str,
        detail: str,
        cause: Optional[Exception] = None,
    ):
        self.tenant_id = tenant_id
        self.detail = detail
        self.cause = cause
        self.error_code = "ENTITLEMENT_EVAL_FAILED"
        super().__init__(f"Entitlement evaluation failed for {tenant_id}: {detail}")

    def to_dict(self) -> dict:
        return {
            "error": self.error_code,
            "message": self.detail,
            "tenant_id": self.tenant_id,
        }


class FeatureDeniedError(EntitlementError):
    """Raised when a feature is explicitly denied for the tenant."""

    def __init__(self, tenant_id: str, feature_key: str, reason: str):
        self.tenant_id = tenant_id
        self.feature_key = feature_key
        self.reason = reason
        self.error_code = "FEATURE_DENIED"
        super().__init__(f"Feature {feature_key} denied for {tenant_id}: {reason}")

    def to_dict(self) -> dict:
        return {
            "error": self.error_code,
            "feature_key": self.feature_key,
            "message": self.reason,
            "tenant_id": self.tenant_id,
        }


class OverrideValidationError(EntitlementError):
    """Raised when an override fails validation (e.g. missing or past expiry)."""

    def __init__(self, message: str, field: Optional[str] = None):
        self.field = field
        self.error_code = "OVERRIDE_VALIDATION_FAILED"
        super().__init__(message)

    def to_dict(self) -> dict:
        d: dict = {"error": self.error_code, "message": str(self)}
        if self.field is not None:
            d["field"] = self.field
        return d
