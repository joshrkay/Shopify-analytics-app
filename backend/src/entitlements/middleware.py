"""
FastAPI middleware for entitlement enforcement.

Enforces feature access based on billing_state and plan features.
Emits audit logs for all entitlement checks.
"""

import logging
from typing import Optional, Callable
from datetime import datetime, timezone

from fastapi import Request, HTTPException, status
from fastapi.routing import APIRoute
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response
from sqlalchemy.orm import Session

from src.platform.tenant_context import get_tenant_context, TenantContext
from src.platform.audit import AuditAction, log_system_audit_event
from src.entitlements.policy import EntitlementPolicy, BillingState
from src.entitlements.errors import EntitlementDeniedError
from src.models.subscription import Subscription

logger = logging.getLogger(__name__)


# Metadata key for route feature requirements
REQUIRED_FEATURE_KEY = "required_feature"


def get_db_session_from_request(request: Request) -> Optional[Session]:
    """
    Extract database session from request state.
    
    Routes should set request.state.db with the session.
    """
    return getattr(request.state, "db", None)


class EntitlementMiddleware(BaseHTTPMiddleware):
    """
    FastAPI middleware that enforces feature entitlements on protected routes.
    
    Routes can be marked with required_feature metadata:
        @router.get("/premium-endpoint")
        @router.get("/premium-endpoint").route.required_feature = "premium_feature"
    
    Or use the require_feature decorator.
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
        Process request and check entitlements for protected routes.
        
        Skips entitlement check if:
        - Route has no required_feature metadata
        - Route is health check or webhook
        - No database session available (falls back to allowing, with warning)
        """
        # Skip for health and webhooks
        if request.url.path == "/health" or request.url.path.startswith("/api/webhooks/"):
            return await call_next(request)
        
        # Get route and check for required_feature metadata
        route = request.scope.get("route")
        if not route or not isinstance(route, APIRoute):
            return await call_next(request)
        
        # Check route endpoint for required_feature
        required_feature = None
        if hasattr(route, "endpoint"):
            # Check function metadata (set by @require_feature decorator)
            required_feature = getattr(route.endpoint, "__required_feature__", None)
        
        # Also check route object metadata
        if not required_feature:
            required_feature = getattr(route, REQUIRED_FEATURE_KEY, None)
        
        if not required_feature:
            # No feature requirement - allow
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
                    "feature": required_feature,
                    "path": request.url.path,
                }
            )
            # Allow request but log warning (fail-open for availability)
            return await call_next(request)
        
        # Evaluate entitlement
        policy = EntitlementPolicy(db_session)
        
        # Fetch subscription (check multiple statuses)
        subscription = db_session.query(Subscription).filter(
            Subscription.tenant_id == tenant_context.tenant_id
        ).order_by(Subscription.created_at.desc()).first()
        
        # If no subscription found, try to get any subscription for this tenant
        if not subscription:
            subscription = db_session.query(Subscription).filter(
                Subscription.tenant_id == tenant_context.tenant_id
            ).first()
        
        result = policy.check_feature_entitlement(
            tenant_id=tenant_context.tenant_id,
            feature=required_feature,
            subscription=subscription,
        )
        
        # Emit audit log
        await self._emit_audit_log(
            request=request,
            tenant_context=tenant_context,
            feature=required_feature,
            result=result,
            db_session=db_session,
        )
        
        # Check entitlement result
        if not result.is_entitled:
            # Determine HTTP status based on billing_state
            http_status = status.HTTP_402_PAYMENT_REQUIRED
            
            if result.billing_state == BillingState.EXPIRED:
                http_status = status.HTTP_402_PAYMENT_REQUIRED
            elif result.billing_state == BillingState.CANCELED:
                http_status = status.HTTP_402_PAYMENT_REQUIRED
            elif result.billing_state == BillingState.PAST_DUE:
                http_status = status.HTTP_402_PAYMENT_REQUIRED
            
            error = EntitlementDeniedError(
                feature=required_feature,
                reason=result.reason or "Feature not entitled",
                billing_state=result.billing_state.value,
                plan_id=result.plan_id,
                required_plan=result.required_plan,
                http_status=http_status,
            )
            
            logger.warning(
                "Entitlement check denied",
                extra={
                    "tenant_id": tenant_context.tenant_id,
                    "user_id": tenant_context.user_id,
                    "feature": required_feature,
                    "billing_state": result.billing_state.value,
                    "plan_id": result.plan_id,
                    "reason": result.reason,
                }
            )
            
            raise HTTPException(
                status_code=http_status,
                detail=error.to_dict(),
            )
        
        # Entitlement granted
        # Add warning header if in grace period
        if result.billing_state == BillingState.GRACE_PERIOD and result.grace_period_ends_on:
            response = await call_next(request)
            response.headers["X-Billing-Warning"] = "payment_grace_period"
            response.headers["X-Grace-Period-Ends"] = result.grace_period_ends_on.isoformat()
            return response
        
        return await call_next(request)
    
    async def _emit_audit_log(
        self,
        request: Request,
        tenant_context: TenantContext,
        feature: str,
        result,
        db_session: Session,
    ) -> None:
        """
        Emit audit log for entitlement check.
        
        Logs entitlement.denied or entitlement.allowed events.
        """
        try:
            from sqlalchemy.ext.asyncio import AsyncSession
            
            # Determine audit action
            audit_action = AuditAction.ENTITLEMENT_DENIED if not result.is_entitled else AuditAction.ENTITLEMENT_ALLOWED
            
            # Try async audit logging
            if isinstance(db_session, AsyncSession):
                await log_system_audit_event(
                    db=db_session,
                    tenant_id=tenant_context.tenant_id,
                    action=audit_action,
                    resource_type="entitlement",
                    resource_id=feature,
                    metadata={
                        "feature": feature,
                        "is_entitled": result.is_entitled,
                        "billing_state": result.billing_state.value,
                        "plan_id": result.plan_id,
                        "plan_name": result.plan_id,  # Could fetch plan name if needed
                        "reason": result.reason,
                        "path": request.url.path,
                        "method": request.method,
                    },
                )
            else:
                # For sync sessions, log via structured logging
                # The audit system will pick this up if configured
                logger.info(
                    "Entitlement check",
                    extra={
                        "tenant_id": tenant_context.tenant_id,
                        "user_id": tenant_context.user_id,
                        "action": audit_action.value,
                        "feature": feature,
                        "billing_state": result.billing_state.value,
                        "plan_id": result.plan_id,
                        "is_entitled": result.is_entitled,
                        "reason": result.reason,
                        "resource_type": "entitlement",
                        "resource_id": feature,
                    }
                )
        except Exception as e:
            logger.error(
                "Failed to emit entitlement audit log",
                extra={
                    "error": str(e),
                    "tenant_id": tenant_context.tenant_id,
                    "feature": feature,
                }
            )


def require_feature(feature: str):
    """
    Decorator to mark a route as requiring a feature.
    
    Usage:
        @router.get("/premium-endpoint")
        @require_feature("premium_feature")
        async def premium_handler(request: Request):
            ...
    """
    def decorator(func):
        # Store feature requirement in function metadata
        func.__required_feature__ = feature
        return func
    
    return decorator


# Audit actions are defined in src/platform/audit.py
