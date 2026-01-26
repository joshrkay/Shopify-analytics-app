"""
Entitlement enforcement for API routes.

Provides middleware and policy evaluation for billing-based feature access control.
"""

from src.entitlements.errors import EntitlementError, EntitlementDeniedError
from src.entitlements.policy import (
    BillingState,
    EntitlementPolicy,
    get_billing_state_from_subscription,
)
from src.entitlements.middleware import EntitlementMiddleware

__all__ = [
    "EntitlementError",
    "EntitlementDeniedError",
    "BillingState",
    "EntitlementPolicy",
    "get_billing_state_from_subscription",
    "EntitlementMiddleware",
]
