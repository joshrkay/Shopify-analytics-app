"""
Entitlement check dependencies.

FastAPI dependencies that block access when entitlement is missing.
All protected routes must declare required feature key(s).
Uses EntitlementService with string feature keys (no hard-coded plan logic).
"""

import logging
from typing import Callable, List

from fastapi import Request, HTTPException, status, Depends

from src.platform.tenant_context import get_tenant_context
from src.database.session import get_db_session
from src.entitlements.service import EntitlementService
from src.entitlements.errors import EntitlementEvaluationError

logger = logging.getLogger(__name__)


def create_entitlement_check(
    feature_key: str,
    feature_name: str,
    default_required_plan: str = "paid",
) -> Callable:
    """
    Factory that creates a dependency checking a single feature by key.

    Args:
        feature_key: Feature key string (e.g. "ai_insights", "custom_dashboards")
        feature_name: Human-readable name for error messages
        default_required_plan: Fallback for error message if not in grant

    Returns:
        FastAPI dependency that raises 402 if not entitled, else returns db_session
    """

    def check_entitlement(
        request: Request,
        db_session=Depends(get_db_session),
    ):
        tenant_ctx = get_tenant_context(request)
        service = EntitlementService(db_session)
        try:
            grant = service.check_feature(tenant_ctx.tenant_id, feature_key)
        except EntitlementEvaluationError as e:
            logger.warning(
                "Entitlement evaluation failed",
                extra={"tenant_id": tenant_ctx.tenant_id, "feature_key": feature_key},
            )
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail={"error": e.error_code, "message": e.detail},
            ) from e
        if not grant.granted:
            logger.warning(
                "%s access denied - not entitled",
                feature_name,
                extra={"tenant_id": tenant_ctx.tenant_id, "feature_key": feature_key},
            )
            raise HTTPException(
                status_code=status.HTTP_402_PAYMENT_REQUIRED,
                detail={
                    "error": "FEATURE_DENIED",
                    "message": f"{feature_name} requires a {default_required_plan} plan",
                    "feature_key": feature_key,
                },
            )
        return db_session

    return check_entitlement


def require_entitlement(*feature_keys: str):
    """
    Dependency that requires at least one of the given feature keys to be granted.

    Use on a route: Depends(require_entitlement("ai_insights", "custom_dashboards"))
    Raises 402 if none of the features are entitled.
    """

    def _check(
        request: Request,
        db_session=Depends(get_db_session),
    ):
        if not feature_keys:
            return db_session
        tenant_ctx = get_tenant_context(request)
        service = EntitlementService(db_session)
        try:
            resolved = service.get_entitlements(tenant_ctx.tenant_id)
        except EntitlementEvaluationError as e:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail={"error": e.error_code, "message": e.detail},
            ) from e
        for key in feature_keys:
            grant = resolved.features.get(key)
            if grant and grant.granted:
                return db_session
        logger.warning(
            "Entitlement denied: none of [%s] granted",
            ",".join(feature_keys),
            extra={"tenant_id": tenant_ctx.tenant_id},
        )
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail={
                "error": "FEATURE_DENIED",
                "message": "This feature requires a higher plan",
                "feature_keys": list(feature_keys),
            },
        )

    return _check


# Pre-configured checks for common features (string keys)
check_ai_insights_entitlement = create_entitlement_check(
    feature_key="ai_insights",
    feature_name="AI Insights",
    default_required_plan="paid",
)
check_ai_recommendations_entitlement = create_entitlement_check(
    feature_key="ai_recommendations",
    feature_name="AI Recommendations",
    default_required_plan="paid",
)
check_ai_actions_entitlement = create_entitlement_check(
    feature_key="ai_actions",
    feature_name="AI Actions",
    default_required_plan="Growth",
)
check_llm_routing_entitlement = create_entitlement_check(
    feature_key="llm_routing",
    feature_name="LLM Routing",
    default_required_plan="Pro",
)
check_custom_reports_entitlement = create_entitlement_check(
    feature_key="custom_reports",
    feature_name="Custom Reports",
    default_required_plan="Growth",
)
check_custom_dashboards_entitlement = create_entitlement_check(
    feature_key="custom_dashboards",
    feature_name="Custom Dashboards",
    default_required_plan="Growth",
)
