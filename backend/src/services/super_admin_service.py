"""
SuperAdminService for managing DB-backed super admin status.

SECURITY CRITICAL:
- Super admin status is NEVER determined from JWT claims
- Only existing super admins can grant/revoke super admin status
- All operations are audited with critical severity events

Super admin privileges include:
- Access to all tenants
- Ability to export audit logs across tenants
- Ability to view system-wide settings
- Ability to grant/revoke super admin to other users

Usage:
    service = SuperAdminService(session, actor_clerk_user_id="user_xxx")

    # Grant super admin (only if actor is super admin)
    service.grant_super_admin(target_clerk_user_id="user_yyy")

    # Revoke super admin
    service.revoke_super_admin(target_clerk_user_id="user_yyy", reason="Role change")
"""

import logging
import uuid
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any

from sqlalchemy.orm import Session

from src.models.user import User
from src.models.tenant import Tenant
from src.platform.audit import (
    AuditAction,
    AuditEvent,
    AuditOutcome,
    write_audit_log_sync,
)

logger = logging.getLogger(__name__)


# =============================================================================
# Exceptions
# =============================================================================

class SuperAdminError(Exception):
    """Base exception for super admin service errors."""
    pass


class NotSuperAdminError(SuperAdminError):
    """Raised when actor is not a super admin."""
    pass


class UserNotFoundError(SuperAdminError):
    """Raised when target user is not found."""
    pass


class AlreadySuperAdminError(SuperAdminError):
    """Raised when user is already a super admin."""
    pass


class NotCurrentlySuperAdminError(SuperAdminError):
    """Raised when user is not currently a super admin."""
    pass


class CannotRevokeLastSuperAdminError(SuperAdminError):
    """Raised when attempting to revoke the last super admin."""
    pass


class SelfOperationError(SuperAdminError):
    """Raised when super admin tries to revoke their own status."""
    pass


# =============================================================================
# Service
# =============================================================================

class SuperAdminService:
    """
    Service for managing super admin status.

    SECURITY: All operations require actor to be an existing super admin.
    """

    # System tenant ID used for audit events with no tenant context
    SYSTEM_TENANT_ID = "system"

    def __init__(
        self,
        session: Session,
        actor_clerk_user_id: Optional[str] = None,
        correlation_id: Optional[str] = None,
    ):
        """
        Initialize service with database session and actor context.

        Args:
            session: SQLAlchemy session for database operations
            actor_clerk_user_id: Clerk user ID of the user performing the action
            correlation_id: Optional correlation ID for audit event tracing
        """
        self.session = session
        self.actor_clerk_user_id = actor_clerk_user_id
        self.correlation_id = correlation_id or str(uuid.uuid4())
        self._actor_user: Optional[User] = None

    # =========================================================================
    # Authorization Checks
    # =========================================================================

    def _get_actor_user(self) -> Optional[User]:
        """Get the actor user from database."""
        if self._actor_user is None and self.actor_clerk_user_id:
            self._actor_user = self.session.query(User).filter(
                User.clerk_user_id == self.actor_clerk_user_id,
                User.is_active == True,
            ).first()
        return self._actor_user

    def is_super_admin(self, clerk_user_id: Optional[str] = None) -> bool:
        """
        Check if a user is a super admin.

        SECURITY: This reads directly from the database, never from JWT claims.

        Args:
            clerk_user_id: Clerk user ID to check (defaults to actor)

        Returns:
            True if user is a super admin
        """
        check_id = clerk_user_id or self.actor_clerk_user_id
        if not check_id:
            return False

        user = self.session.query(User).filter(
            User.clerk_user_id == check_id,
            User.is_active == True,
        ).first()

        return user is not None and user.is_super_admin is True

    def _verify_actor_is_super_admin(self) -> User:
        """
        Verify that the actor is a super admin.

        Returns:
            The actor's User record

        Raises:
            NotSuperAdminError: If actor is not a super admin
        """
        if not self.actor_clerk_user_id:
            raise NotSuperAdminError("No actor specified")

        actor = self._get_actor_user()
        if not actor or not actor.is_super_admin:
            logger.warning(
                "Non-super-admin attempted super admin operation",
                extra={
                    "actor_clerk_user_id": self.actor_clerk_user_id,
                },
            )
            raise NotSuperAdminError(
                "Only super admins can perform this operation"
            )

        return actor

    def _get_user_by_clerk_id(self, clerk_user_id: str) -> User:
        """
        Get user by Clerk user ID.

        Args:
            clerk_user_id: Clerk user ID

        Returns:
            User record

        Raises:
            UserNotFoundError: If user not found
        """
        user = self.session.query(User).filter(
            User.clerk_user_id == clerk_user_id,
        ).first()

        if not user:
            raise UserNotFoundError(f"User {clerk_user_id} not found")

        return user

    # =========================================================================
    # Core Operations
    # =========================================================================

    def grant_super_admin(
        self,
        target_clerk_user_id: str,
        source: str = "admin_api",
    ) -> Dict[str, Any]:
        """
        Grant super admin status to a user.

        SECURITY: Only existing super admins can grant super admin status.

        Args:
            target_clerk_user_id: Clerk user ID to grant super admin to
            source: Source of the grant (admin_api, migration)

        Returns:
            Dict with user_id, clerk_user_id, is_super_admin

        Raises:
            NotSuperAdminError: If actor is not a super admin
            UserNotFoundError: If target user not found
            AlreadySuperAdminError: If target is already a super admin
        """
        # Verify actor is super admin
        actor = self._verify_actor_is_super_admin()

        # Get target user
        target = self._get_user_by_clerk_id(target_clerk_user_id)

        # Check if already super admin
        if target.is_super_admin:
            raise AlreadySuperAdminError(
                f"User {target_clerk_user_id} is already a super admin"
            )

        # Grant super admin
        target.is_super_admin = True
        target.updated_at = datetime.now(timezone.utc)
        self.session.flush()

        logger.info(
            "Super admin status granted",
            extra={
                "target_clerk_user_id": target_clerk_user_id,
                "granted_by": self.actor_clerk_user_id,
                "source": source,
            },
        )

        # Emit audit event
        self._emit_super_admin_granted(
            target_clerk_user_id=target_clerk_user_id,
            granted_by=self.actor_clerk_user_id,
            source=source,
        )

        return {
            "user_id": target.id,
            "clerk_user_id": target.clerk_user_id,
            "is_super_admin": target.is_super_admin,
        }

    def revoke_super_admin(
        self,
        target_clerk_user_id: str,
        reason: str = "administrative action",
    ) -> Dict[str, Any]:
        """
        Revoke super admin status from a user.

        SECURITY: Only existing super admins can revoke super admin status.
        Cannot revoke your own super admin status (prevents lockout).
        Cannot revoke the last super admin (prevents system lockout).

        Args:
            target_clerk_user_id: Clerk user ID to revoke super admin from
            reason: Reason for the revocation

        Returns:
            Dict with user_id, clerk_user_id, is_super_admin

        Raises:
            NotSuperAdminError: If actor is not a super admin
            UserNotFoundError: If target user not found
            NotCurrentlySuperAdminError: If target is not currently a super admin
            SelfOperationError: If trying to revoke own super admin status
            CannotRevokeLastSuperAdminError: If this would remove the last super admin
        """
        # Verify actor is super admin
        actor = self._verify_actor_is_super_admin()

        # Get target user
        target = self._get_user_by_clerk_id(target_clerk_user_id)

        # Check if currently super admin
        if not target.is_super_admin:
            raise NotCurrentlySuperAdminError(
                f"User {target_clerk_user_id} is not a super admin"
            )

        # Prevent self-revocation
        if target.clerk_user_id == actor.clerk_user_id:
            raise SelfOperationError(
                "Cannot revoke your own super admin status"
            )

        # Check if this is the last super admin
        super_admin_count = self.session.query(User).filter(
            User.is_super_admin == True,
            User.is_active == True,
        ).count()

        if super_admin_count <= 1:
            raise CannotRevokeLastSuperAdminError(
                "Cannot revoke the last super admin - system would be locked out"
            )

        # Revoke super admin
        target.is_super_admin = False
        target.updated_at = datetime.now(timezone.utc)
        self.session.flush()

        logger.info(
            "Super admin status revoked",
            extra={
                "target_clerk_user_id": target_clerk_user_id,
                "revoked_by": self.actor_clerk_user_id,
                "reason": reason,
            },
        )

        # Emit audit event
        self._emit_super_admin_revoked(
            target_clerk_user_id=target_clerk_user_id,
            revoked_by=self.actor_clerk_user_id,
            reason=reason,
        )

        return {
            "user_id": target.id,
            "clerk_user_id": target.clerk_user_id,
            "is_super_admin": target.is_super_admin,
        }

    # =========================================================================
    # Queries
    # =========================================================================

    def list_super_admins(self) -> List[Dict[str, Any]]:
        """
        List all super admins.

        SECURITY: Only super admins can list super admins.

        Returns:
            List of super admin user info dicts

        Raises:
            NotSuperAdminError: If actor is not a super admin
        """
        # Verify actor is super admin
        self._verify_actor_is_super_admin()

        users = self.session.query(User).filter(
            User.is_super_admin == True,
            User.is_active == True,
        ).all()

        return [
            {
                "user_id": user.id,
                "clerk_user_id": user.clerk_user_id,
                "email": user.email,
                "full_name": user.full_name,
                "is_super_admin": user.is_super_admin,
            }
            for user in users
        ]

    def get_all_tenants(self) -> List[Dict[str, Any]]:
        """
        Get all tenants (super admin only).

        SECURITY: Only super admins have access to all tenants.

        Returns:
            List of tenant info dicts

        Raises:
            NotSuperAdminError: If actor is not a super admin
        """
        # Verify actor is super admin
        self._verify_actor_is_super_admin()

        tenants = self.session.query(Tenant).filter(
            Tenant.status == "active",
        ).all()

        return [
            {
                "tenant_id": tenant.id,
                "name": tenant.name,
                "slug": tenant.slug,
                "billing_tier": tenant.billing_tier,
                "clerk_org_id": tenant.clerk_org_id,
            }
            for tenant in tenants
        ]

    # =========================================================================
    # Audit Event Emission
    # =========================================================================

    def _emit_super_admin_granted(
        self,
        target_clerk_user_id: str,
        granted_by: str,
        source: str,
    ) -> None:
        """Emit audit event for super admin granted."""
        write_audit_log_sync(
            db=self.session,
            event=AuditEvent(
                action=AuditAction.IDENTITY_SUPER_ADMIN_GRANTED,
                outcome=AuditOutcome.SUCCESS,
                tenant_id=self.SYSTEM_TENANT_ID,
                user_id=granted_by,
                correlation_id=self.correlation_id,
                metadata={
                    "clerk_user_id": target_clerk_user_id,
                    "granted_by": granted_by,
                    "source": source,
                },
            ),
        )

    def _emit_super_admin_revoked(
        self,
        target_clerk_user_id: str,
        revoked_by: str,
        reason: str,
    ) -> None:
        """Emit audit event for super admin revoked."""
        write_audit_log_sync(
            db=self.session,
            event=AuditEvent(
                action=AuditAction.IDENTITY_SUPER_ADMIN_REVOKED,
                outcome=AuditOutcome.SUCCESS,
                tenant_id=self.SYSTEM_TENANT_ID,
                user_id=revoked_by,
                correlation_id=self.correlation_id,
                metadata={
                    "clerk_user_id": target_clerk_user_id,
                    "revoked_by": revoked_by,
                    "reason": reason,
                },
            ),
        )


# =============================================================================
# Convenience Functions
# =============================================================================

def check_is_super_admin(session: Session, clerk_user_id: str) -> bool:
    """
    Convenience function to check if a user is a super admin.

    SECURITY: This reads directly from the database, never from JWT claims.

    Args:
        session: SQLAlchemy session
        clerk_user_id: Clerk user ID to check

    Returns:
        True if user is a super admin
    """
    service = SuperAdminService(session)
    return service.is_super_admin(clerk_user_id)


def grant_super_admin_via_migration(
    session: Session,
    clerk_user_id: str,
) -> Dict[str, Any]:
    """
    Grant super admin status via migration (bootstrap only).

    This bypasses the normal authorization check for initial bootstrap.
    Use ONLY for database migrations or initial setup.

    Args:
        session: SQLAlchemy session
        clerk_user_id: Clerk user ID to grant super admin to

    Returns:
        Dict with user_id, clerk_user_id, is_super_admin
    """
    user = session.query(User).filter(
        User.clerk_user_id == clerk_user_id,
    ).first()

    if not user:
        raise UserNotFoundError(f"User {clerk_user_id} not found")

    user.is_super_admin = True
    user.updated_at = datetime.now(timezone.utc)
    session.flush()

    # Emit audit event
    write_audit_log_sync(
        db=session,
        event=AuditEvent(
            action=AuditAction.IDENTITY_SUPER_ADMIN_GRANTED,
            outcome=AuditOutcome.SUCCESS,
            tenant_id=SuperAdminService.SYSTEM_TENANT_ID,
            user_id="migration",
            correlation_id=str(uuid.uuid4()),
            metadata={
                "clerk_user_id": clerk_user_id,
                "granted_by": "migration",
                "source": "migration",
            },
        ),
    )

    logger.info(
        "Super admin granted via migration",
        extra={"clerk_user_id": clerk_user_id},
    )

    return {
        "user_id": user.id,
        "clerk_user_id": user.clerk_user_id,
        "is_super_admin": user.is_super_admin,
    }
