"""
TenantInvite model for Clerk-backed invitation flow.

TenantInvite stores pending and historical invitations for users to join
tenants. Integrates with Clerk organization invitations via webhooks.

Lifecycle:
1. Admin creates invite via API or Clerk sends organizationInvitation.created
2. Local TenantInvite record created with status=pending
3. User accepts via Clerk -> organizationInvitation.accepted webhook
4. InviteService.accept_invite() creates UserTenantRole, marks accepted
5. Expired invites marked by scheduled job

SECURITY:
- Invites expire after 30 days by default
- Duplicate pending invites for same email+tenant blocked
- Only pending invites can be accepted/revoked
"""

import uuid
import enum
from datetime import datetime, timezone, timedelta
from typing import TYPE_CHECKING, Optional

from sqlalchemy import Column, String, Boolean, DateTime, Index, ForeignKey, Enum as SAEnum
from sqlalchemy.orm import relationship

from src.db_base import Base
from src.models.base import TimestampMixin

if TYPE_CHECKING:
    from src.models.user import User
    from src.models.tenant import Tenant


class InviteStatus(str, enum.Enum):
    """Invitation lifecycle status."""
    PENDING = "pending"       # Awaiting response
    ACCEPTED = "accepted"     # Invitation accepted, UserTenantRole created
    EXPIRED = "expired"       # Expired without response
    REVOKED = "revoked"       # Revoked by admin


class TenantInvite(Base, TimestampMixin):
    """
    Pending or historical invitation for a user to join a tenant.

    Created when:
    1. Admin manually invites via API (POST /api/tenants/{id}/invites)
    2. Clerk organizationInvitation.created webhook received

    Lifecycle:
    - PENDING: Awaiting user response
    - ACCEPTED: User accepted via Clerk -> UserTenantRole created
    - EXPIRED: expiration time passed without action
    - REVOKED: Admin revoked the invitation
    """

    __tablename__ = "tenant_invites"

    # Primary Key
    id = Column(
        String(255),
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
        comment="Internal UUID primary key"
    )

    # External reference from Clerk
    clerk_invitation_id = Column(
        String(255),
        nullable=True,
        unique=True,
        index=True,
        comment="Clerk invitation ID (from organizationInvitation webhook)"
    )

    # Tenant being joined
    tenant_id = Column(
        String(255),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="Tenant this invitation is for"
    )

    # Invitee info
    email = Column(
        String(255),
        nullable=False,
        index=True,
        comment="Email address of invitee"
    )

    # Role to be assigned upon acceptance
    role = Column(
        String(50),
        nullable=False,
        default="MERCHANT_VIEWER",
        comment="Role to grant upon acceptance"
    )

    # Status tracking
    status = Column(
        SAEnum(InviteStatus, name="invite_status", create_constraint=True),
        nullable=False,
        default=InviteStatus.PENDING,
        index=True,
        comment="Current invitation status"
    )

    # Timestamps
    invited_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        comment="When invitation was created"
    )

    expires_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc) + timedelta(days=30),
        comment="When invitation expires (default 30 days)"
    )

    # Audit trail
    invited_by = Column(
        String(255),
        nullable=True,
        comment="clerk_user_id of person who invited (null for Clerk webhook)"
    )

    # Acceptance tracking
    accepted_at = Column(
        DateTime(timezone=True),
        nullable=True,
        comment="When invitation was accepted"
    )

    accepted_by_user_id = Column(
        String(255),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
        comment="Internal user ID of acceptor"
    )

    # Relationships
    tenant = relationship("Tenant", lazy="joined")
    accepted_by_user = relationship("User", lazy="joined")

    # Indexes
    __table_args__ = (
        Index("ix_tenant_invites_tenant_email", "tenant_id", "email"),
        Index("ix_tenant_invites_tenant_status", "tenant_id", "status"),
        Index("ix_tenant_invites_expires_at", "expires_at"),
    )

    def __repr__(self) -> str:
        return (
            f"<TenantInvite(id={self.id}, email={self.email}, "
            f"tenant_id={self.tenant_id}, status={self.status.value})>"
        )

    @property
    def is_expired(self) -> bool:
        """Check if invitation has expired based on expires_at."""
        if self.status != InviteStatus.PENDING:
            return False
        return datetime.now(timezone.utc) > self.expires_at

    @property
    def is_actionable(self) -> bool:
        """Check if invitation can still be accepted/rejected."""
        return (
            self.status == InviteStatus.PENDING and
            not self.is_expired
        )

    def accept(self, user_id: str) -> None:
        """
        Mark invitation as accepted.

        Args:
            user_id: Internal user ID of the acceptor
        """
        self.status = InviteStatus.ACCEPTED
        self.accepted_at = datetime.now(timezone.utc)
        self.accepted_by_user_id = user_id

    def mark_expired(self) -> None:
        """Mark invitation as expired."""
        self.status = InviteStatus.EXPIRED

    def revoke(self) -> None:
        """Mark invitation as revoked."""
        self.status = InviteStatus.REVOKED

    @classmethod
    def create_invite(
        cls,
        tenant_id: str,
        email: str,
        role: str = "MERCHANT_VIEWER",
        invited_by: Optional[str] = None,
        expires_in_days: int = 30,
        clerk_invitation_id: Optional[str] = None,
    ) -> "TenantInvite":
        """
        Factory method for creating a new invite.

        Args:
            tenant_id: Target tenant ID
            email: Invitee email address
            role: Role to grant on acceptance
            invited_by: clerk_user_id of inviter (null for webhook)
            expires_in_days: Days until expiration
            clerk_invitation_id: Clerk invitation ID (from webhook)

        Returns:
            New TenantInvite instance
        """
        now = datetime.now(timezone.utc)
        return cls(
            tenant_id=tenant_id,
            email=email,
            role=role,
            status=InviteStatus.PENDING,
            invited_by=invited_by,
            invited_at=now,
            expires_at=now + timedelta(days=expires_in_days),
            clerk_invitation_id=clerk_invitation_id,
        )
