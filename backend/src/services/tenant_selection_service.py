"""
Tenant Selection Service for explicit tenant context resolution.

This service handles:
- Getting user's accessible tenants
- Setting/getting active tenant selection
- Validating tenant access (DB-level validation, never trust client)
- Auto-selecting tenant for single-tenant users
- Emitting audit events on invalid tenant access attempts

SECURITY REQUIREMENTS:
- NEVER trust tenant_id from client without DB validation
- Always validate user has active access to the tenant
- Emit audit event on any cross-tenant access attempt
"""

import logging
import uuid
from typing import Optional, List, Dict, Any, Tuple

from sqlalchemy.orm import Session

from src.models.user import User
from src.models.tenant import Tenant, TenantStatus
from src.models.user_tenant_roles import UserTenantRole
from src.platform.audit import (
    AuditAction,
    AuditEvent,
    AuditOutcome,
    write_audit_log_sync,
)

logger = logging.getLogger(__name__)


class TenantSelectionError(Exception):
    """Base exception for tenant selection errors."""
    pass


class TenantAccessDeniedError(TenantSelectionError):
    """Raised when user doesn't have access to requested tenant."""
    pass


class TenantNotFoundError(TenantSelectionError):
    """Raised when tenant doesn't exist."""
    pass


class NoTenantAccessError(TenantSelectionError):
    """Raised when user has no tenant access at all."""
    pass


class TenantSelectionRequiredError(TenantSelectionError):
    """Raised when user has multiple tenants but none selected."""
    pass


class TenantSelectionService:
    """
    Service for managing user's active tenant selection.

    Handles the complete flow of:
    1. Resolving allowed tenants from database
    2. Auto-selecting if user has exactly 1 tenant
    3. Validating tenant access for multi-tenant users
    4. Storing active tenant selection
    5. Emitting audit events on invalid access attempts
    """

    # Key used in user.extra_metadata for active tenant storage
    ACTIVE_TENANT_KEY = "active_tenant_id"

    def __init__(
        self,
        session: Session,
        correlation_id: Optional[str] = None,
    ):
        """
        Initialize service with database session.

        Args:
            session: SQLAlchemy session for database operations
            correlation_id: Optional correlation ID for audit trail
        """
        self.session = session
        self.correlation_id = correlation_id or str(uuid.uuid4())

    def get_user_tenants(
        self,
        clerk_user_id: str,
    ) -> List[Dict[str, Any]]:
        """
        Get all tenants a user has access to.

        Args:
            clerk_user_id: Clerk user identifier

        Returns:
            List of tenant dicts with id, name, roles, is_admin
        """
        user = self._get_user(clerk_user_id)
        if not user:
            return []

        roles = self.session.query(UserTenantRole).filter(
            UserTenantRole.user_id == user.id,
            UserTenantRole.is_active == True,
        ).all()

        tenants = []
        seen_tenant_ids = set()

        for role in roles:
            tenant = role.tenant
            if tenant.status != TenantStatus.ACTIVE:
                continue

            if tenant.id in seen_tenant_ids:
                # Add role to existing tenant entry
                for t in tenants:
                    if t["id"] == tenant.id:
                        if role.role not in t["roles"]:
                            t["roles"].append(role.role)
                        break
                continue

            seen_tenant_ids.add(tenant.id)
            tenants.append({
                "id": tenant.id,
                "name": tenant.name,
                "slug": tenant.slug,
                "billing_tier": tenant.billing_tier,
                "roles": [role.role],
                "is_admin": role.is_admin_role,
            })

        return tenants

    def get_active_tenant_id(
        self,
        clerk_user_id: str,
    ) -> Optional[str]:
        """
        Get the user's currently active tenant ID.

        Args:
            clerk_user_id: Clerk user identifier

        Returns:
            Active tenant ID or None if not set
        """
        user = self._get_user(clerk_user_id)
        if not user:
            return None

        metadata = user.extra_metadata or {}
        return metadata.get(self.ACTIVE_TENANT_KEY)

    def set_active_tenant(
        self,
        clerk_user_id: str,
        tenant_id: str,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Set the user's active tenant.

        SECURITY: Validates user has access to the tenant before setting.
        Emits audit event on success and on invalid access attempts.

        Args:
            clerk_user_id: Clerk user identifier
            tenant_id: Tenant ID to set as active
            ip_address: Client IP for audit logging
            user_agent: User agent for audit logging

        Returns:
            Dict with tenant details and success status

        Raises:
            TenantAccessDeniedError: If user doesn't have access to tenant
            TenantNotFoundError: If tenant doesn't exist
        """
        user = self._get_user(clerk_user_id)
        if not user:
            raise TenantAccessDeniedError("User not found")

        # Validate tenant exists and is active
        tenant = self.session.query(Tenant).filter(
            Tenant.id == tenant_id,
        ).first()

        if not tenant:
            self._emit_cross_tenant_attempt(
                clerk_user_id=clerk_user_id,
                requested_tenant_id=tenant_id,
                reason="tenant_not_found",
                ip_address=ip_address,
                user_agent=user_agent,
            )
            raise TenantNotFoundError(f"Tenant not found: {tenant_id}")

        if tenant.status != TenantStatus.ACTIVE:
            self._emit_cross_tenant_attempt(
                clerk_user_id=clerk_user_id,
                requested_tenant_id=tenant_id,
                reason="tenant_inactive",
                ip_address=ip_address,
                user_agent=user_agent,
            )
            raise TenantAccessDeniedError(f"Tenant is not active: {tenant_id}")

        # Validate user has access to tenant
        has_access = self.session.query(UserTenantRole).filter(
            UserTenantRole.user_id == user.id,
            UserTenantRole.tenant_id == tenant_id,
            UserTenantRole.is_active == True,
        ).first() is not None

        if not has_access:
            self._emit_cross_tenant_attempt(
                clerk_user_id=clerk_user_id,
                requested_tenant_id=tenant_id,
                reason="no_access",
                ip_address=ip_address,
                user_agent=user_agent,
            )
            raise TenantAccessDeniedError(
                f"User does not have access to tenant: {tenant_id}"
            )

        # Store active tenant in user metadata
        previous_tenant_id = self.get_active_tenant_id(clerk_user_id)
        metadata = user.extra_metadata or {}
        metadata[self.ACTIVE_TENANT_KEY] = tenant_id
        user.extra_metadata = metadata
        self.session.flush()

        # Emit successful selection audit event
        self._emit_tenant_selected(
            clerk_user_id=clerk_user_id,
            tenant_id=tenant_id,
            previous_tenant_id=previous_tenant_id,
            ip_address=ip_address,
            user_agent=user_agent,
        )

        logger.info(
            "Set active tenant",
            extra={
                "clerk_user_id": clerk_user_id,
                "tenant_id": tenant_id,
                "previous_tenant_id": previous_tenant_id,
            }
        )

        return {
            "tenant_id": tenant_id,
            "name": tenant.name,
            "previous_tenant_id": previous_tenant_id,
        }

    def resolve_active_tenant(
        self,
        clerk_user_id: str,
        jwt_active_tenant_id: Optional[str] = None,
    ) -> Tuple[str, bool]:
        """
        Resolve the active tenant for a user.

        Resolution order:
        1. JWT-provided active_tenant_id (if valid)
        2. Stored active_tenant_id (if valid)
        3. Auto-select if user has exactly 1 tenant
        4. Raise TenantSelectionRequiredError if multiple tenants

        Args:
            clerk_user_id: Clerk user identifier
            jwt_active_tenant_id: Active tenant ID from JWT (if present)

        Returns:
            Tuple of (resolved_tenant_id, was_auto_selected)

        Raises:
            NoTenantAccessError: If user has no tenant access
            TenantSelectionRequiredError: If user has multiple tenants and none selected
        """
        user = self._get_user(clerk_user_id)
        if not user:
            raise NoTenantAccessError("User not found")

        # Get user's accessible tenants
        tenants = self.get_user_tenants(clerk_user_id)

        if not tenants:
            raise NoTenantAccessError("User has no tenant access")

        tenant_ids = [t["id"] for t in tenants]

        # 1. Try JWT-provided active_tenant_id
        if jwt_active_tenant_id and jwt_active_tenant_id in tenant_ids:
            return jwt_active_tenant_id, False

        # 2. Try stored active_tenant_id
        stored_tenant_id = self.get_active_tenant_id(clerk_user_id)
        if stored_tenant_id and stored_tenant_id in tenant_ids:
            return stored_tenant_id, False

        # 3. Auto-select if exactly 1 tenant
        if len(tenants) == 1:
            auto_tenant_id = tenants[0]["id"]
            # Store the auto-selection
            metadata = user.extra_metadata or {}
            metadata[self.ACTIVE_TENANT_KEY] = auto_tenant_id
            user.extra_metadata = metadata
            self.session.flush()

            logger.info(
                "Auto-selected single tenant",
                extra={
                    "clerk_user_id": clerk_user_id,
                    "tenant_id": auto_tenant_id,
                }
            )
            return auto_tenant_id, True

        # 4. Multiple tenants but no selection - require explicit selection
        raise TenantSelectionRequiredError(
            f"User has {len(tenants)} tenants but no active selection. "
            "Use POST /me/active-tenant to select one."
        )

    def validate_tenant_access(
        self,
        clerk_user_id: str,
        tenant_id: str,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
    ) -> bool:
        """
        Validate that a user has access to a specific tenant.

        Emits audit event if access is denied.

        Args:
            clerk_user_id: Clerk user identifier
            tenant_id: Tenant ID to validate access for
            ip_address: Client IP for audit logging
            user_agent: User agent for audit logging

        Returns:
            True if user has access, False otherwise
        """
        user = self._get_user(clerk_user_id)
        if not user:
            return False

        has_access = self.session.query(UserTenantRole).filter(
            UserTenantRole.user_id == user.id,
            UserTenantRole.tenant_id == tenant_id,
            UserTenantRole.is_active == True,
        ).first() is not None

        if not has_access:
            self._emit_cross_tenant_attempt(
                clerk_user_id=clerk_user_id,
                requested_tenant_id=tenant_id,
                reason="validation_failed",
                ip_address=ip_address,
                user_agent=user_agent,
            )

        return has_access

    # =========================================================================
    # Private Helper Methods
    # =========================================================================

    def _get_user(self, clerk_user_id: str) -> Optional[User]:
        """Get user by Clerk user ID."""
        return self.session.query(User).filter(
            User.clerk_user_id == clerk_user_id,
            User.is_active == True,
        ).first()

    def _emit_cross_tenant_attempt(
        self,
        clerk_user_id: str,
        requested_tenant_id: str,
        reason: str,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
    ) -> None:
        """
        Emit audit event for cross-tenant access attempt.

        This is called when a user attempts to access a tenant
        they don't have permission for.
        """
        event = AuditEvent(
            tenant_id=requested_tenant_id,
            action=AuditAction.AUTH_CROSS_TENANT_ACCESS_ATTEMPT,
            user_id=clerk_user_id,
            ip_address=ip_address,
            user_agent=user_agent,
            resource_type="tenant",
            resource_id=requested_tenant_id,
            metadata={
                "clerk_user_id": clerk_user_id,
                "requested_tenant_id": requested_tenant_id,
                "reason": reason,
            },
            correlation_id=self.correlation_id,
            source="api",
            outcome=AuditOutcome.DENIED,
            error_code="cross_tenant_access_attempt",
        )

        write_audit_log_sync(self.session, event)

        logger.warning(
            "Cross-tenant access attempt",
            extra={
                "clerk_user_id": clerk_user_id,
                "requested_tenant_id": requested_tenant_id,
                "reason": reason,
                "correlation_id": self.correlation_id,
            }
        )

    def _emit_tenant_selected(
        self,
        clerk_user_id: str,
        tenant_id: str,
        previous_tenant_id: Optional[str],
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
    ) -> None:
        """Emit audit event for successful tenant selection."""
        event = AuditEvent(
            tenant_id=tenant_id,
            action=AuditAction.AUTH_TENANT_SELECTED,
            user_id=clerk_user_id,
            ip_address=ip_address,
            user_agent=user_agent,
            resource_type="tenant",
            resource_id=tenant_id,
            metadata={
                "clerk_user_id": clerk_user_id,
                "tenant_id": tenant_id,
                "previous_tenant_id": previous_tenant_id,
            },
            correlation_id=self.correlation_id,
            source="api",
            outcome=AuditOutcome.SUCCESS,
        )

        write_audit_log_sync(self.session, event)

        logger.info(
            "Tenant selected",
            extra={
                "clerk_user_id": clerk_user_id,
                "tenant_id": tenant_id,
                "previous_tenant_id": previous_tenant_id,
                "correlation_id": self.correlation_id,
            }
        )
