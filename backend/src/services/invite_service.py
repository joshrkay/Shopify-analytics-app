"""
InviteService for managing Clerk-backed tenant invitations.

Handles:
- Creating invitations (admin API or Clerk webhook)
- Accepting invitations (via Clerk webhook)
- Revoking invitations (admin action)
- Expiring stale invitations (scheduled job)
- Audit event emission

Two sources of invitations:
1. Admin API: POST /api/tenants/{id}/invites
2. Clerk webhooks: organizationInvitation.created
"""

import logging
import uuid
from datetime import datetime, timezone, timedelta
from typing import Optional, Dict, Any, List

from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError

from src.models.tenant_invite import TenantInvite, InviteStatus
from src.models.tenant import Tenant, TenantStatus
from src.models.user import User
from src.models.user_tenant_roles import UserTenantRole
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

class InviteServiceError(Exception):
    """Base exception for invite service errors."""
    pass


class TenantNotFoundError(InviteServiceError):
    """Raised when tenant is not found."""
    pass


class TenantNotActiveError(InviteServiceError):
    """Raised when tenant is not active."""
    pass


class InviteNotFoundError(InviteServiceError):
    """Raised when invitation is not found."""
    pass


class InviteExpiredError(InviteServiceError):
    """Raised when invitation has expired."""
    pass


class InviteRevokedError(InviteServiceError):
    """Raised when invitation has been revoked."""
    pass


class InviteAlreadyAcceptedError(InviteServiceError):
    """Raised when invitation has already been accepted."""
    pass


class DuplicateInviteError(InviteServiceError):
    """Raised when a duplicate pending invite exists."""
    pass


class UserAlreadyMemberError(InviteServiceError):
    """Raised when user is already a member of the tenant."""
    pass


class InvalidStateError(InviteServiceError):
    """Raised when invite is in an invalid state for the operation."""
    pass


class UserNotFoundError(InviteServiceError):
    """Raised when user is not found."""
    pass


# =============================================================================
# Service
# =============================================================================

class InviteService:
    """Service for managing tenant invitations."""

    def __init__(self, session: Session, correlation_id: Optional[str] = None):
        """
        Initialize service with database session.

        Args:
            session: SQLAlchemy session for database operations
            correlation_id: Optional correlation ID for audit event tracing
        """
        self.session = session
        self.correlation_id = correlation_id or str(uuid.uuid4())

    # =========================================================================
    # Core Operations
    # =========================================================================

    def create_invite(
        self,
        tenant_id: str,
        email: str,
        role: str = "MERCHANT_VIEWER",
        invited_by: Optional[str] = None,
        expires_in_days: int = 30,
        clerk_invitation_id: Optional[str] = None,
    ) -> TenantInvite:
        """
        Create a new invitation for a user to join a tenant.

        Args:
            tenant_id: Tenant to invite user to
            email: Email address of invitee
            role: Role to assign upon acceptance
            invited_by: clerk_user_id of inviter (None for system/webhook)
            expires_in_days: Days until invitation expires
            clerk_invitation_id: Clerk invitation ID (from webhook)

        Returns:
            Created TenantInvite

        Raises:
            TenantNotFoundError: If tenant doesn't exist
            TenantNotActiveError: If tenant is not active
            DuplicateInviteError: If pending invite exists for email
            UserAlreadyMemberError: If user already has access
            ValueError: If email or role is invalid
        """
        # Validate email
        if not email or "@" not in email:
            raise ValueError("Invalid email address")

        # Validate role
        valid_roles = {
            "MERCHANT_ADMIN", "MERCHANT_VIEWER",
            "AGENCY_ADMIN", "AGENCY_VIEWER",
            "admin", "owner", "editor", "viewer"
        }
        if role not in valid_roles:
            raise ValueError(f"Invalid role: {role}")

        # Verify tenant exists and is active
        tenant = self._get_tenant(tenant_id)
        if not tenant.is_active:
            raise TenantNotActiveError(f"Tenant {tenant_id} is not active")

        # Check for existing pending invite
        existing = self._get_pending_invite_by_email(tenant_id, email)
        if existing and not existing.is_expired:
            raise DuplicateInviteError(
                f"Pending invitation already exists for {email}"
            )

        # Check if user already has access
        user = self.session.query(User).filter(User.email == email).first()
        if user:
            existing_role = self.session.query(UserTenantRole).filter(
                UserTenantRole.user_id == user.id,
                UserTenantRole.tenant_id == tenant_id,
                UserTenantRole.is_active == True,
            ).first()

            if existing_role:
                raise UserAlreadyMemberError(
                    f"User {email} already has access to tenant"
                )

        # Create invitation
        invite = TenantInvite.create_invite(
            tenant_id=tenant_id,
            email=email,
            role=role,
            invited_by=invited_by,
            expires_in_days=expires_in_days,
            clerk_invitation_id=clerk_invitation_id,
        )

        self.session.add(invite)
        self.session.flush()

        logger.info(
            "Created invitation",
            extra={
                "invite_id": invite.id,
                "tenant_id": tenant_id,
                "email": email,
                "role": role,
                "invited_by": invited_by,
            }
        )

        # Emit audit event
        self._emit_invite_sent(invite)

        return invite

    def accept_invite(
        self,
        invite_id: str,
        clerk_user_id: str,
    ) -> Dict[str, Any]:
        """
        Accept an invitation and create UserTenantRole.

        Called when:
        1. Clerk organizationInvitation.accepted webhook received
        2. First authenticated request detects pending invite

        Args:
            invite_id: Invitation ID to accept
            clerk_user_id: Clerk user ID of the acceptor

        Returns:
            Dict with user_id, tenant_id, role

        Raises:
            InviteNotFoundError: If invitation doesn't exist
            InviteExpiredError: If invitation has expired
            InviteRevokedError: If invitation was revoked
            InviteAlreadyAcceptedError: If already accepted
            UserNotFoundError: If user doesn't exist
        """
        invite = self.get_invite_by_id(invite_id)
        if not invite:
            raise InviteNotFoundError(f"Invitation {invite_id} not found")

        # Check status
        if invite.status == InviteStatus.ACCEPTED:
            raise InviteAlreadyAcceptedError("Invitation already accepted")
        if invite.status == InviteStatus.REVOKED:
            raise InviteRevokedError("Invitation was revoked")
        if invite.status == InviteStatus.EXPIRED or invite.is_expired:
            raise InviteExpiredError("Invitation has expired")

        # Get or create user
        user = self.session.query(User).filter(
            User.clerk_user_id == clerk_user_id
        ).first()

        if not user:
            raise UserNotFoundError(f"User {clerk_user_id} not found")

        # Create role assignment
        user_role = UserTenantRole.create_from_grant(
            user_id=user.id,
            tenant_id=invite.tenant_id,
            role=invite.role,
            granted_by="invite_acceptance",
        )
        self.session.add(user_role)

        # Update invite status
        invite.accept(user.id)

        self.session.flush()

        logger.info(
            "Accepted invitation",
            extra={
                "invite_id": invite_id,
                "user_id": user.id,
                "tenant_id": invite.tenant_id,
                "role": invite.role,
            }
        )

        # Emit audit event
        self._emit_invite_accepted(invite, user.id)

        return {
            "invite_id": invite_id,
            "user_id": user.id,
            "tenant_id": invite.tenant_id,
            "role": invite.role,
        }

    def revoke_invite(
        self,
        invite_id: str,
        revoked_by: str,
    ) -> TenantInvite:
        """
        Revoke a pending invitation.

        Args:
            invite_id: Invitation ID to revoke
            revoked_by: clerk_user_id of revoker

        Returns:
            Updated TenantInvite

        Raises:
            InviteNotFoundError: If invitation doesn't exist
            InvalidStateError: If invitation is not pending
        """
        invite = self.get_invite_by_id(invite_id)
        if not invite:
            raise InviteNotFoundError(f"Invitation {invite_id} not found")

        if invite.status != InviteStatus.PENDING:
            raise InvalidStateError(
                f"Cannot revoke invitation with status {invite.status.value}"
            )

        invite.revoke()

        logger.info(
            "Revoked invitation",
            extra={
                "invite_id": invite_id,
                "tenant_id": invite.tenant_id,
                "revoked_by": revoked_by,
            }
        )

        # Emit audit event
        self._emit_invite_revoked(invite, revoked_by)

        return invite

    def expire_stale_invites(self) -> int:
        """
        Expire all stale pending invitations.

        Called by scheduled job to mark expired invites.

        Returns:
            Number of invites expired
        """
        # Use naive UTC datetime for SQLite compatibility
        now = datetime.utcnow()

        # Find all pending invites that have expired
        stale_invites = self.session.query(TenantInvite).filter(
            TenantInvite.status == InviteStatus.PENDING,
            TenantInvite.expires_at < now,
        ).all()

        count = 0
        for invite in stale_invites:
            invite.mark_expired()
            self._emit_invite_expired(invite)
            count += 1

        # Flush changes to persist status updates
        if count > 0:
            self.session.flush()

        logger.info(f"Expired {count} stale invitations")
        return count

    # =========================================================================
    # Queries
    # =========================================================================

    def get_invite_by_id(self, invite_id: str) -> Optional[TenantInvite]:
        """Get invitation by internal ID."""
        return self.session.query(TenantInvite).filter(
            TenantInvite.id == invite_id
        ).first()

    def get_invite_by_clerk_id(self, clerk_invitation_id: str) -> Optional[TenantInvite]:
        """Get invitation by Clerk invitation ID."""
        return self.session.query(TenantInvite).filter(
            TenantInvite.clerk_invitation_id == clerk_invitation_id
        ).first()

    def _get_pending_invite_by_email(
        self,
        tenant_id: str,
        email: str
    ) -> Optional[TenantInvite]:
        """Get pending invitation by tenant and email."""
        return self.session.query(TenantInvite).filter(
            TenantInvite.tenant_id == tenant_id,
            TenantInvite.email == email,
            TenantInvite.status == InviteStatus.PENDING,
        ).first()

    def list_invites(
        self,
        tenant_id: str,
        status: Optional[str] = None,
        include_expired: bool = False,
    ) -> List[TenantInvite]:
        """
        List invitations for a tenant.

        Args:
            tenant_id: Tenant to list invitations for
            status: Filter by status (pending, accepted, etc.)
            include_expired: Include expired invitations

        Returns:
            List of TenantInvite objects

        Raises:
            TenantNotFoundError: If tenant doesn't exist
        """
        self._get_tenant(tenant_id)  # Verify tenant exists

        query = self.session.query(TenantInvite).filter(
            TenantInvite.tenant_id == tenant_id
        )

        if status:
            query = query.filter(
                TenantInvite.status == InviteStatus(status)
            )

        invites = query.all()

        # Filter expired if not requested
        if not include_expired:
            invites = [inv for inv in invites if not inv.is_expired]

        return invites

    # =========================================================================
    # Private Helpers
    # =========================================================================

    def _get_tenant(self, tenant_id: str) -> Tenant:
        """Get tenant by ID or raise TenantNotFoundError."""
        tenant = self.session.query(Tenant).filter(
            Tenant.id == tenant_id
        ).first()

        if not tenant:
            raise TenantNotFoundError(f"Tenant {tenant_id} not found")

        return tenant

    # =========================================================================
    # Audit Event Emission
    # =========================================================================

    def _emit_invite_sent(self, invite: TenantInvite) -> None:
        """Emit audit event for invitation sent."""
        write_audit_log_sync(
            db=self.session,
            event=AuditEvent(
                action=AuditAction.IDENTITY_INVITE_SENT,
                outcome=AuditOutcome.SUCCESS,
                tenant_id=invite.tenant_id,
                user_id=invite.invited_by or "system",
                correlation_id=self.correlation_id,
                metadata={
                    "invite_id": invite.id,
                    "tenant_id": invite.tenant_id,
                    "role": invite.role,
                    "invited_by": invite.invited_by or "system",
                },
            ),
        )

    def _emit_invite_accepted(self, invite: TenantInvite, user_id: str) -> None:
        """Emit audit event for invitation accepted."""
        write_audit_log_sync(
            db=self.session,
            event=AuditEvent(
                action=AuditAction.IDENTITY_INVITE_ACCEPTED,
                outcome=AuditOutcome.SUCCESS,
                tenant_id=invite.tenant_id,
                user_id=user_id,
                correlation_id=self.correlation_id,
                metadata={
                    "invite_id": invite.id,
                    "tenant_id": invite.tenant_id,
                    "role": invite.role,
                },
            ),
        )

    def _emit_invite_expired(self, invite: TenantInvite) -> None:
        """Emit audit event for invitation expired."""
        write_audit_log_sync(
            db=self.session,
            event=AuditEvent(
                action=AuditAction.IDENTITY_INVITE_EXPIRED,
                outcome=AuditOutcome.SUCCESS,
                tenant_id=invite.tenant_id,
                user_id="system",
                correlation_id=self.correlation_id,
                metadata={
                    "invite_id": invite.id,
                    "tenant_id": invite.tenant_id,
                },
            ),
        )

    def _emit_invite_revoked(self, invite: TenantInvite, revoked_by: str) -> None:
        """Emit audit event for invitation revoked."""
        write_audit_log_sync(
            db=self.session,
            event=AuditEvent(
                action=AuditAction.IDENTITY_INVITE_REVOKED,
                outcome=AuditOutcome.SUCCESS,
                tenant_id=invite.tenant_id,
                user_id=revoked_by,
                correlation_id=self.correlation_id,
                metadata={
                    "invite_id": invite.id,
                    "tenant_id": invite.tenant_id,
                    "revoked_by": revoked_by,
                },
            ),
        )
