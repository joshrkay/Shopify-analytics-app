"""
Entitlement enforcement for API routes.

Provides middleware and policy evaluation for billing-based feature access control.
Supports both feature-based and category-based enforcement.
"""

from src.entitlements.errors import EntitlementError, EntitlementDeniedError
from src.entitlements.policy import (
    BillingState,
    EntitlementPolicy,
    CategoryEntitlementResult,
    EntitlementCheckResult,
    get_billing_state_from_subscription,
)
from src.entitlements.middleware import (
    EntitlementMiddleware,
    require_category,
    require_category_dependency,
)
from src.entitlements.categories import (
    PremiumCategory,
    is_write_method,
    is_read_method,
    get_category_from_route,
)
from src.entitlements.audit import (
    log_entitlement_denied,
    log_degraded_access_used,
)

__all__ = [
    "EntitlementError",
    "EntitlementDeniedError",
    "BillingState",
    "EntitlementPolicy",
    "CategoryEntitlementResult",
    "EntitlementCheckResult",
    "get_billing_state_from_subscription",
    "EntitlementMiddleware",
    "require_category",
    "require_category_dependency",
    "PremiumCategory",
    "is_write_method",
    "is_read_method",
    "get_category_from_route",
    "log_entitlement_denied",
    "log_degraded_access_used",
]
