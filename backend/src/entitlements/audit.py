"""
Audit logging for entitlement enforcement.

Emits structured audit events for entitlement denials and degraded access usage.
"""

import logging
from typing import Optional, Union
from datetime import datetime, timezone

from sqlalchemy.orm import Session
from sqlalchemy.ext.asyncio import AsyncSession

from src.platform.audit import AuditAction, log_system_audit_event
from src.entitlements.policy import BillingState, CategoryEntitlementResult
from src.entitlements.categories import PremiumCategory

logger = logging.getLogger(__name__)


async def log_entitlement_denied(
    db: Union[Session, AsyncSession],
    tenant_id: str,
    user_id: str,
    category: PremiumCategory,
    billing_state: BillingState,
    plan_id: Optional[str],
    reason: Optional[str] = None,
    correlation_id: Optional[str] = None,
) -> None:
    """
    Log entitlement denial audit event.
    
    Args:
        db: Database session (sync or async)
        tenant_id: Tenant ID
        user_id: User ID
        category: Premium category that was denied
        billing_state: Current billing state
        plan_id: Current plan ID
        reason: Denial reason
        correlation_id: Optional correlation ID for tracing
    """
    try:
        metadata = {
            "category": category.value,
            "billing_state": billing_state.value,
            "plan_id": plan_id,
            "reason": reason,
        }
        
        if isinstance(db, AsyncSession):
            await log_system_audit_event(
                db=db,
                tenant_id=tenant_id,
                action=AuditAction.ENTITLEMENT_DENIED,
                resource_type="entitlement",
                resource_id=category.value,
                metadata=metadata,
                correlation_id=correlation_id,
            )
        else:
            # For sync sessions, use structured logging
            logger.warning(
                "Entitlement denied",
                extra={
                    "tenant_id": tenant_id,
                    "user_id": user_id,
                    "action": AuditAction.ENTITLEMENT_DENIED.value,
                    "category": category.value,
                    "billing_state": billing_state.value,
                    "plan_id": plan_id,
                    "reason": reason,
                    "resource_type": "entitlement",
                    "resource_id": category.value,
                    "correlation_id": correlation_id,
                }
            )
    except Exception as e:
        logger.error(
            "Failed to log entitlement denied audit event",
            extra={
                "error": str(e),
                "tenant_id": tenant_id,
                "category": category.value,
            }
        )


async def log_degraded_access_used(
    db: Union[Session, AsyncSession],
    tenant_id: str,
    user_id: str,
    category: PremiumCategory,
    billing_state: BillingState,
    plan_id: Optional[str],
    correlation_id: Optional[str] = None,
) -> None:
    """
    Log degraded access usage audit event.
    
    This is emitted when a request is allowed but in a degraded mode
    (e.g., past_due with warning, grace_period read-only, canceled read-only).
    
    Args:
        db: Database session (sync or async)
        tenant_id: Tenant ID
        user_id: User ID
        category: Premium category accessed
        billing_state: Current billing state
        plan_id: Current plan ID
        correlation_id: Optional correlation ID for tracing
    """
    try:
        metadata = {
            "category": category.value,
            "billing_state": billing_state.value,
            "plan_id": plan_id,
            "degraded_mode": True,
        }
        
        if isinstance(db, AsyncSession):
            await log_system_audit_event(
                db=db,
                tenant_id=tenant_id,
                action=AuditAction.ENTITLEMENT_DEGRADED_ACCESS_USED,
                resource_type="entitlement",
                resource_id=category.value,
                metadata=metadata,
                correlation_id=correlation_id,
            )
        else:
            # For sync sessions, use structured logging
            logger.info(
                "Degraded access used",
                extra={
                    "tenant_id": tenant_id,
                    "user_id": user_id,
                    "action": "entitlement.degraded_access_used",
                    "category": category.value,
                    "billing_state": billing_state.value,
                    "plan_id": plan_id,
                    "resource_type": "entitlement",
                    "resource_id": category.value,
                    "correlation_id": correlation_id,
                }
            )
    except Exception as e:
        logger.error(
            "Failed to log degraded access audit event",
            extra={
                "error": str(e),
                "tenant_id": tenant_id,
                "category": category.value,
            }
        )
