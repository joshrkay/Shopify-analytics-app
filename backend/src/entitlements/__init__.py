"""
Entitlements: plan-based feature keys with per-tenant overrides.

Resolution order: override → plan → deny.
Source of truth for billing: Shopify; config: config/plans.json.
"""

from src.entitlements.models import (
    EntitlementSet,
    OverrideEntry,
    PlanConfig,
    ResolutionResult,
)

__all__ = [
    "EntitlementSet",
    "OverrideEntry",
    "PlanConfig",
    "ResolutionResult",
]
