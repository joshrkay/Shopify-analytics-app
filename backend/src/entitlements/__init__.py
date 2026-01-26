"""
Entitlements enforcement system for billing-based feature access control.

This module provides:
- EntitlementLoader: Load entitlements from config/plans.json
- AccessRules: Define access rules by billing state
- EntitlementCache: Redis-backed cache with real-time invalidation
- EntitlementMiddleware: FastAPI middleware for API enforcement
- AuditLogger: Log all access denials for compliance
- Category-based enforcement for premium features

Grace period: 3 days (configurable via billing_rules.grace_period_days)
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
    EntitlementAuditLogger,
    AccessDenialEvent,
    log_entitlement_denied,
    log_degraded_access_used,
)

__all__ = [
    # Errors
    "EntitlementError",
    "EntitlementDeniedError",
    # Policy
    "BillingState",
    "EntitlementPolicy",
    "CategoryEntitlementResult",
    "EntitlementCheckResult",
    "get_billing_state_from_subscription",
    # Middleware
    "EntitlementMiddleware",
    "require_category",
    "require_category_dependency",
    # Categories
    "PremiumCategory",
    "is_write_method",
    "is_read_method",
    "get_category_from_route",
    # Audit
    "EntitlementAuditLogger",
    "AccessDenialEvent",
    "log_entitlement_denied",
    "log_degraded_access_used",
]
