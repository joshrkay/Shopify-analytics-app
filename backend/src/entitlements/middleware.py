"""
FastAPI middleware for category-based entitlement enforcement.

Enforces premium category access based on billing_state matrix.
Emits audit logs for all entitlement checks and degraded access usage.
"""

import logging
from typing import Optional, Callable
from datetime import datetime, timezone

from fastapi import Request, HTTPException, status
from fastapi.routing import APIRoute
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response, JSONResponse
from sqlalchemy.orm import Session

from src.platform.tenant_context import get_tenant_context, TenantContext
from src.entitlements.policy import EntitlementPolicy, BillingState, CategoryEntitlementResult
from src.entitlements.errors import EntitlementDeniedError
from src.entitlements.categories import PremiumCategory, get_category_from_route
from src.entitlements.audit import log_entitlement_denied, log_degraded_access_used
from src.models.subscription import Subscription

logger = logging.getLogger(__name__)


# Metadata keys for route requirements
REQUIRED_CATEGORY_KEY = "required_category"
REQUIRED_FEATURE_KEY = "required_feature"


def get_db_session_from_request(request: Request) -> Optional[Session]:
    """
    Extract database session from request state.
    
    Routes should set request.state.db with the session.
    """
    return getattr(request.state, "db", None)


def get_correlation_id(request: Request) -> Optional[str]:
    """Get correlation ID from request state or headers."""
    if hasattr(request.state, "correlation_id"):
        return request.state.correlation_id
    return request.headers.get("X-Correlation-ID")


class EntitlementMiddleware(BaseHTTPMiddleware):
    """
    FastAPI middleware that enforces category-based entitlements on protected routes.
    
    Routes can be marked with required_category metadata:
        @router.get("/export")
        @require_category("exports")
        async def export_handler(request: Request):
            ...
    
    Or use the require_category dependency/decorator.
    """
    
    def __init__(self, app, db_session_factory: Optional[Callable[[], Session]] = None):
        """
        Initialize entitlement middleware.
        
        Args:
            app: FastAPI application
            db_session_factory: Optional factory function to create DB sessions
        """
        super().__init__(app)
        self.db_session_factory = db_session_factory
    
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        """
        Process request and check category entitlements for protected routes.
        
        Skips entitlement check if:
        - Route has no required_category metadata
        - Route is health check or webhook
        - No database session available (falls back to allowing, with warning)
        """
        # Skip for health and webhooks
        if request.url.path == "/health" or request.url.path.startswith("/api/webhooks/"):
            return await call_next(request)
        
        # Get route and check for required_category metadata
        route = request.scope.get("route")
        if not route or not isinstance(route, APIRoute):
            return await call_next(request)
        
        # Check route endpoint for required_category
        required_category: Optional[PremiumCategory] = None
        if hasattr(route, "endpoint"):
            # Check function metadata (set by @require_category decorator)
            category_value = getattr(route.endpoint, "__required_category__", None)
            if category_value:
                try:
                    required_category = PremiumCategory(category_value)
                except ValueError:
                    logger.warning(
                        f"Invalid category value: {category_value}",
                        extra={"path": request.url.path}
                    )
        
        # Also check route object metadata
        if not required_category:
            category_value = getattr(route, REQUIRED_CATEGORY_KEY, None)
            if category_value:
                try:
                    required_category = PremiumCategory(category_value)
                except ValueError:
                    logger.warning(
                        f"Invalid category value: {category_value}",
                        extra={"path": request.url.path}
                    )
        
        # Fallback: infer category from route path
        if not required_category:
            inferred = get_category_from_route(request.url.path, request.method)
            # Only enforce if it's a premium category (not OTHER)
            if inferred != PremiumCategory.OTHER:
                required_category = inferred
        
        if not required_category:
            # No category requirement - allow
            return await call_next(request)
        
        # Get tenant context (must exist from TenantContextMiddleware)
        try:
            tenant_context = get_tenant_context(request)
        except HTTPException:
            # Tenant context missing - let TenantContextMiddleware handle it
            return await call_next(request)
        
        # Get database session
        db_session = get_db_session_from_request(request)
        if not db_session and self.db_session_factory:
            try:
                db_session = self.db_session_factory()
            except Exception as e:
                logger.warning(
                    "Failed to create DB session for entitlement check",
                    extra={"error": str(e), "tenant_id": tenant_context.tenant_id}
                )
        
        if not db_session:
            logger.warning(
                "No DB session available for entitlement check - allowing request",
                extra={
                    "tenant_id": tenant_context.tenant_id,
                    "category": required_category.value,
                    "path": request.url.path,
                }
            )
            # Allow request but log warning (fail-open for availability)
            return await call_next(request)
        
        # Evaluate category entitlement
        policy = EntitlementPolicy(db_session)
        
        # Fetch subscription
        subscription = db_session.query(Subscription).filter(
            Subscription.tenant_id == tenant_context.tenant_id
        ).order_by(Subscription.created_at.desc()).first()
        
        # If no subscription found, try to get any subscription for this tenant
        if not subscription:
            subscription = db_session.query(Subscription).filter(
                Subscription.tenant_id == tenant_context.tenant_id
            ).first()
        
        result = policy.check_category_entitlement(
            tenant_id=tenant_context.tenant_id,
            category=required_category,
            method=request.method,
            subscription=subscription,
        )
        
        correlation_id = get_correlation_id(request)
        
        # Emit audit logs
        if not result.is_entitled:
            await log_entitlement_denied(
                db=db_session,
                tenant_id=tenant_context.tenant_id,
                user_id=tenant_context.user_id,
                category=required_category,
                billing_state=result.billing_state,
                plan_id=result.plan_id,
                reason=result.reason,
                correlation_id=correlation_id,
            )
        elif result.is_degraded_access:
            await log_degraded_access_used(
                db=db_session,
                tenant_id=tenant_context.tenant_id,
                user_id=tenant_context.user_id,
                category=required_category,
                billing_state=result.billing_state,
                plan_id=result.plan_id,
                correlation_id=correlation_id,
            )
        
        # Check entitlement result
        if not result.is_entitled:
            # Determine HTTP status based on billing_state
            http_status = status.HTTP_402_PAYMENT_REQUIRED
            
            # Build response with headers
            response_headers = {
                "X-Billing-State": result.billing_state.value,
            }
            
            if result.grace_period_remaining_days is not None:
                response_headers["X-Grace-Period-Remaining"] = str(result.grace_period_remaining_days)
            
            if result.action_required:
                response_headers["X-Billing-Action-Required"] = result.action_required
            
            # For expired blocks, return HTTP 402 with BILLING_EXPIRED code
            if result.billing_state == BillingState.EXPIRED:
                error_detail = {
                    "error": "entitlement_denied",
                    "code": "BILLING_EXPIRED",
                    "category": required_category.value,
                    "billing_state": result.billing_state.value,
                    "plan_id": result.plan_id,
                    "reason": result.reason,
                    "machine_readable": {
                        "code": "BILLING_EXPIRED",
                        "billing_state": result.billing_state.value,
                        "category": required_category.value,
                    }
                }
                
                logger.warning(
                    "Entitlement check denied - expired",
                    extra={
                        "tenant_id": tenant_context.tenant_id,
                        "user_id": tenant_context.user_id,
                        "category": required_category.value,
                        "billing_state": result.billing_state.value,
                        "plan_id": result.plan_id,
                        "reason": result.reason,
                    }
                )
                
                return JSONResponse(
                    status_code=http_status,
                    content=error_detail,
                    headers=response_headers,
                )
            
            # Other denials
            error = EntitlementDeniedError(
                feature=required_category.value,  # Using category as feature for compatibility
                reason=result.reason or "Category access denied",
                billing_state=result.billing_state.value,
                plan_id=result.plan_id,
                http_status=http_status,
            )
            
            logger.warning(
                "Entitlement check denied",
                extra={
                    "tenant_id": tenant_context.tenant_id,
                    "user_id": tenant_context.user_id,
                    "category": required_category.value,
                    "billing_state": result.billing_state.value,
                    "plan_id": result.plan_id,
                    "reason": result.reason,
                }
            )
            
            error_dict = error.to_dict()
            error_dict["category"] = required_category.value
            error_dict["machine_readable"]["category"] = required_category.value
            
            return JSONResponse(
                status_code=http_status,
                content=error_dict,
                headers=response_headers,
            )
        
        # Entitlement granted (possibly in degraded mode)
        response = await call_next(request)
        
        # Add response headers
        response.headers["X-Billing-State"] = result.billing_state.value
        
        if result.grace_period_remaining_days is not None:
            response.headers["X-Grace-Period-Remaining"] = str(result.grace_period_remaining_days)
        
        if result.action_required:
            response.headers["X-Billing-Action-Required"] = result.action_required
        
        # Log warning if in degraded mode
        if result.is_degraded_access:
            logger.info(
                "Request allowed in degraded access mode",
                extra={
                    "tenant_id": tenant_context.tenant_id,
                    "user_id": tenant_context.user_id,
                    "category": required_category.value,
                    "billing_state": result.billing_state.value,
                    "path": request.url.path,
                }
            )
        
        return response


def require_category(category: PremiumCategory):
    """
    Decorator to mark a route as requiring a premium category.
    
    Usage:
        @router.get("/export")
        @require_category(PremiumCategory.EXPORTS)
        async def export_handler(request: Request):
            ...
    """
    def decorator(func):
        # Store category requirement in function metadata
        func.__required_category__ = category.value
        return func
    
    return decorator


def require_category_dependency(category: PremiumCategory):
    """
    FastAPI dependency to require a premium category.
    
    Usage:
        @router.get("/export")
        async def export_handler(
            request: Request,
            _: None = Depends(require_category_dependency(PremiumCategory.EXPORTS))
        ):
            ...
    """
    from fastapi import Depends
    from functools import wraps
    
    async def check_category(request: Request):
        # This will be called by FastAPI dependency system
        # The middleware will handle the actual enforcement
        # This dependency just marks the route
        return None
    
    # Mark the dependency function with category metadata
    check_category.__required_category__ = category.value
    
    return Depends(check_category)
