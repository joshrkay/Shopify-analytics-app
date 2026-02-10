"""
Entitlement check dependencies (re-exports from require_entitlement).

Use EntitlementService with string feature keys.
"""

from src.api.dependencies.require_entitlement import (
    create_entitlement_check,
    require_entitlement,
    check_ai_insights_entitlement,
    check_ai_recommendations_entitlement,
    check_ai_actions_entitlement,
    check_llm_routing_entitlement,
    check_custom_reports_entitlement,
    check_custom_dashboards_entitlement,
)

__all__ = [
    "create_entitlement_check",
    "require_entitlement",
    "check_ai_insights_entitlement",
    "check_ai_recommendations_entitlement",
    "check_ai_actions_entitlement",
    "check_llm_routing_entitlement",
    "check_custom_reports_entitlement",
    "check_custom_dashboards_entitlement",
]
