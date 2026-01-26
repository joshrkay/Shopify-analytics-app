"""
Entitlement enforcement system for billing-based feature access control.

This module provides:
- EntitlementLoader: Load entitlements from config/plans.json
- AccessRules: Define access rules by billing state
- EntitlementCache: Redis-backed cache with real-time invalidation
- EntitlementMiddleware: FastAPI middleware for API enforcement
- EntitlementAuditLogger: Log all access denials for compliance
- Category-based enforcement: require_category decorator
- Policy evaluation: EntitlementPolicy for billing state checks

Grace period: 3 days (configurable via billing_rules.grace_period_days)
"""

from src.entitlements.loader import EntitlementLoader, PlanEntitlements
from src.entitlements.rules import AccessRules, AccessLevel, BillingState
from src.entitlements.cache import EntitlementCache
from src.entitlements.middleware import (
    EntitlementMiddleware,
    require_entitlement,
    require_billing_state,
    require_category,
    require_category_dependency,
)
from src.entitlements.audit import (
    EntitlementAuditLogger,
    AccessDenialEvent,
    log_entitlement_denied,
    log_degraded_access_used,
)
from src.entitlements.errors import EntitlementError, EntitlementDeniedError
from src.entitlements.policy import (
    EntitlementPolicy,
    CategoryEntitlementResult,
    EntitlementCheckResult,
    get_billing_state_from_subscription,
)
from src.entitlements.categories import (
    PremiumCategory,
    is_write_method,
    is_read_method,
    get_category_from_route,
)

__all__ = [
    # Loader
    "EntitlementLoader",
    "PlanEntitlements",
    # Rules
    "AccessRules",
    "AccessLevel",
    "BillingState",
    # Cache
    "EntitlementCache",
    # Middleware
    "EntitlementMiddleware",
    "require_entitlement",
    "require_billing_state",
    "require_category",
    "require_category_dependency",
    # Audit
    "EntitlementAuditLogger",
    "AccessDenialEvent",
    "log_entitlement_denied",
    "log_degraded_access_used",
    # Errors
    "EntitlementError",
    "EntitlementDeniedError",
    # Policy
    "EntitlementPolicy",
    "CategoryEntitlementResult",
    "EntitlementCheckResult",
    "get_billing_state_from_subscription",
    # Categories
    "PremiumCategory",
    "is_write_method",
    "is_read_method",
    "get_category_from_route",
]
