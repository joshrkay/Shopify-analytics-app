"""
Platform credentials model for storing encrypted API credentials.

Stores encrypted credentials for external platforms (Meta, Google, Shopify)
with tenant isolation and status tracking.

SECURITY:
- Credentials are encrypted at rest using AES-256-GCM
- tenant_id is ONLY extracted from JWT, never from client input
- Supports credential rotation and revocation
- Audit trail via timestamps

Story 8.5 - Action Execution (Scoped & Reversible)
"""

import enum
import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import (
    Column,
    String,
    Enum,
    DateTime,
    LargeBinary,
    Index,
    Boolean,
    Text,
    UniqueConstraint,
)

from src.db_base import Base
from src.models.base import TimestampMixin, TenantScopedMixin


class PlatformType(str, enum.Enum):
    """Supported external platforms."""
    META = "meta"
    GOOGLE = "google"
    SHOPIFY = "shopify"


class CredentialStatus(str, enum.Enum):
    """Status of stored credentials."""
    ACTIVE = "active"          # Credentials are valid and usable
    EXPIRED = "expired"        # OAuth tokens have expired
    REVOKED = "revoked"        # Access has been revoked by user
    INVALID = "invalid"        # Credentials failed validation
    PENDING = "pending"        # Awaiting initial validation


class PlatformCredential(Base, TimestampMixin, TenantScopedMixin):
    """
    Stores encrypted credentials for external platform APIs.

    Each tenant can have one active credential record per platform.
    Credentials are encrypted using AES-256-GCM before storage.

    SECURITY:
    - tenant_id from TenantScopedMixin ensures isolation
    - tenant_id is ONLY extracted from JWT, never from client input
    - encrypted_data contains the actual API credentials
    - encryption_nonce is the unique nonce used for AES-GCM encryption
    - Never log or expose encrypted_data in plaintext
    """

    __tablename__ = "platform_credentials"

    id = Column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
        comment="Primary key (UUID)"
    )

    # Platform identification
    platform = Column(
        Enum(PlatformType),
        nullable=False,
        index=True,
        comment="External platform type (meta, google, shopify)"
    )

    # Status tracking
    status = Column(
        Enum(CredentialStatus),
        default=CredentialStatus.PENDING,
        nullable=False,
        index=True,
        comment="Current credential status"
    )

    # Encrypted credential data (AES-256-GCM encrypted JSON)
    encrypted_data = Column(
        LargeBinary,
        nullable=False,
        comment="AES-256-GCM encrypted credential JSON"
    )

    # Encryption nonce (12 bytes for AES-GCM)
    encryption_nonce = Column(
        LargeBinary(12),
        nullable=False,
        comment="Unique nonce for AES-GCM encryption"
    )

    # Authentication tag (16 bytes for AES-GCM)
    auth_tag = Column(
        LargeBinary(16),
        nullable=False,
        comment="Authentication tag for AES-GCM"
    )

    # Optional metadata
    label = Column(
        String(255),
        nullable=True,
        comment="User-friendly label for this credential set"
    )

    # Validation tracking
    last_validated_at = Column(
        DateTime(timezone=True),
        nullable=True,
        comment="When credentials were last validated via API"
    )

    validation_error = Column(
        Text,
        nullable=True,
        comment="Last validation error message if any"
    )

    # Expiration tracking for OAuth tokens
    expires_at = Column(
        DateTime(timezone=True),
        nullable=True,
        comment="When OAuth access token expires (if applicable)"
    )

    # Revocation tracking
    revoked_at = Column(
        DateTime(timezone=True),
        nullable=True,
        comment="When credentials were revoked"
    )

    revoked_by = Column(
        String(255),
        nullable=True,
        comment="User ID who revoked the credentials"
    )

    # Table constraints
    __table_args__ = (
        # Each tenant can have only one active credential per platform
        UniqueConstraint(
            "tenant_id",
            "platform",
            name="uq_tenant_platform_credential"
        ),
        # Index for looking up active credentials
        Index(
            "ix_platform_credentials_tenant_active",
            "tenant_id",
            "platform",
            "status",
        ),
        # Index for finding expired credentials
        Index(
            "ix_platform_credentials_expires",
            "expires_at",
            postgresql_where=(status == CredentialStatus.ACTIVE)
        ),
    )

    def __repr__(self) -> str:
        return (
            f"<PlatformCredential("
            f"id={self.id}, "
            f"tenant_id={self.tenant_id}, "
            f"platform={self.platform.value if self.platform else None}, "
            f"status={self.status.value if self.status else None}"
            f")>"
        )

    # ==========================================================================
    # Status checks
    # ==========================================================================

    @property
    def is_active(self) -> bool:
        """Check if credential is active and usable."""
        return self.status == CredentialStatus.ACTIVE

    @property
    def is_expired(self) -> bool:
        """Check if credential has expired."""
        if self.status == CredentialStatus.EXPIRED:
            return True
        if self.expires_at and datetime.now(timezone.utc) > self.expires_at:
            return True
        return False

    @property
    def is_revoked(self) -> bool:
        """Check if credential has been revoked."""
        return self.status == CredentialStatus.REVOKED

    @property
    def needs_reauth(self) -> bool:
        """Check if credential needs re-authentication."""
        return self.status in (
            CredentialStatus.EXPIRED,
            CredentialStatus.REVOKED,
            CredentialStatus.INVALID,
        )

    # ==========================================================================
    # Status transitions
    # ==========================================================================

    def mark_active(self, validated_at: Optional[datetime] = None) -> None:
        """Mark credential as active after successful validation."""
        self.status = CredentialStatus.ACTIVE
        self.last_validated_at = validated_at or datetime.now(timezone.utc)
        self.validation_error = None

    def mark_expired(self) -> None:
        """Mark credential as expired."""
        self.status = CredentialStatus.EXPIRED

    def mark_invalid(self, error: str) -> None:
        """Mark credential as invalid with error message."""
        self.status = CredentialStatus.INVALID
        self.validation_error = error
        self.last_validated_at = datetime.now(timezone.utc)

    def mark_revoked(self, user_id: Optional[str] = None) -> None:
        """Mark credential as revoked."""
        self.status = CredentialStatus.REVOKED
        self.revoked_at = datetime.now(timezone.utc)
        self.revoked_by = user_id

    def update_expiration(self, expires_at: datetime) -> None:
        """Update the expiration time for OAuth tokens."""
        self.expires_at = expires_at
