"""
OAuthCredential model - Secure storage for OAuth credentials.

SECURITY REQUIREMENTS:
- Tokens are encrypted at rest using ENCRYPTION_KEY env var
- No plaintext tokens outside process memory
- Automatic redaction in logs
- Tenant-scoped access only

Retention Policy:
- On disconnect: soft delete, purge after 5 days
- On uninstall: soft delete, purge after 20 days
"""

import uuid
import enum
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import (
    Column, String, DateTime, Text, Boolean, Enum, Index,
    UniqueConstraint, ForeignKey
)
from sqlalchemy.orm import relationship

from src.db_base import Base
from src.models.base import TimestampMixin, TenantScopedMixin


class CredentialStatus(str, enum.Enum):
    """OAuth credential status enumeration."""
    ACTIVE = "active"
    INACTIVE = "inactive"  # Soft-deleted on disconnect
    EXPIRED = "expired"  # Token expired, awaiting refresh
    REVOKED = "revoked"  # Explicitly revoked
    PENDING_DELETION = "pending_deletion"  # Awaiting purge


class CredentialProvider(str, enum.Enum):
    """Supported OAuth providers."""
    SHOPIFY = "shopify"
    GOOGLE_ADS = "google_ads"
    FACEBOOK_ADS = "facebook_ads"
    TIKTOK_ADS = "tiktok_ads"


class OAuthCredential(Base, TimestampMixin, TenantScopedMixin):
    """
    Secure OAuth credential storage.

    SECURITY:
    - access_token_encrypted and refresh_token_encrypted are encrypted at rest
    - Tokens are NEVER exposed in API responses or logs
    - All access is tenant-scoped
    - Metadata (account_name, connector_name) is allowed in logs/audit
    """

    __tablename__ = "oauth_credentials"

    id = Column(
        String(255),
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
        comment="Primary key (UUID)"
    )

    # Provider identification
    provider = Column(
        Enum(CredentialProvider),
        nullable=False,
        comment="OAuth provider (shopify, google_ads, etc.)"
    )
    external_account_id = Column(
        String(255),
        nullable=True,
        comment="External account ID from provider"
    )

    # Encrypted tokens - NEVER log these values
    access_token_encrypted = Column(
        Text,
        nullable=True,
        comment="Encrypted access token - NEVER log plaintext"
    )
    refresh_token_encrypted = Column(
        Text,
        nullable=True,
        comment="Encrypted refresh token - NEVER log plaintext"
    )

    # Token metadata (safe to log)
    token_type = Column(
        String(50),
        default="Bearer",
        comment="Token type (Bearer, etc.)"
    )
    expires_at = Column(
        DateTime(timezone=True),
        nullable=True,
        comment="When the access token expires"
    )
    refresh_token_expires_at = Column(
        DateTime(timezone=True),
        nullable=True,
        comment="When the refresh token expires (if applicable)"
    )
    last_refreshed_at = Column(
        DateTime(timezone=True),
        nullable=True,
        comment="When tokens were last refreshed"
    )

    # Scope management - NOT hardcoded, stored from OAuth response
    scopes = Column(
        Text,
        nullable=True,
        comment="JSON array of granted OAuth scopes"
    )

    # Display metadata (ALLOWED in logs per PII policy)
    account_name = Column(
        String(255),
        nullable=True,
        comment="Display name for the account (allowed in logs)"
    )
    connector_name = Column(
        String(255),
        nullable=True,
        comment="User-friendly connector name (allowed in logs)"
    )

    # Status and lifecycle
    status = Column(
        Enum(CredentialStatus),
        default=CredentialStatus.ACTIVE,
        nullable=False,
        index=True,
        comment="Current credential status"
    )
    is_active = Column(
        Boolean,
        default=True,
        nullable=False,
        comment="Quick check for active credentials"
    )

    # Retention tracking
    disconnected_at = Column(
        DateTime(timezone=True),
        nullable=True,
        comment="When connector was disconnected"
    )
    scheduled_purge_at = Column(
        DateTime(timezone=True),
        nullable=True,
        comment="When encrypted blob will be purged"
    )
    purged_at = Column(
        DateTime(timezone=True),
        nullable=True,
        comment="When tokens were actually purged"
    )

    # Audit trail
    last_used_at = Column(
        DateTime(timezone=True),
        nullable=True,
        comment="When credentials were last used for API call"
    )
    error_count = Column(
        String(10),
        default="0",
        comment="Number of consecutive errors"
    )
    last_error = Column(
        Text,
        nullable=True,
        comment="Last error message (sanitized)"
    )

    # Foreign key to store (optional, for Shopify credentials)
    store_id = Column(
        String(255),
        ForeignKey("shopify_stores.id", ondelete="SET NULL"),
        nullable=True,
        comment="Associated Shopify store (if applicable)"
    )

    # Relationship
    store = relationship("ShopifyStore", backref="oauth_credentials")

    # Table constraints and indexes
    __table_args__ = (
        Index("ix_oauth_credentials_tenant_provider", "tenant_id", "provider"),
        Index("ix_oauth_credentials_tenant_status", "tenant_id", "status"),
        Index("ix_oauth_credentials_scheduled_purge", "scheduled_purge_at"),
        Index("ix_oauth_credentials_expires_at", "expires_at"),
        UniqueConstraint(
            "tenant_id", "provider", "external_account_id",
            name="uq_oauth_credentials_tenant_provider_account"
        ),
    )

    def __repr__(self) -> str:
        """Safe repr - NEVER include token values."""
        return (
            f"<OAuthCredential("
            f"id={self.id}, "
            f"provider={self.provider}, "
            f"account_name={self.account_name}, "
            f"status={self.status})>"
        )

    @property
    def is_token_expired(self) -> bool:
        """Check if access token is expired."""
        if not self.expires_at:
            return False
        return datetime.now(timezone.utc) >= self.expires_at

    @property
    def is_refresh_token_expired(self) -> bool:
        """Check if refresh token is expired."""
        if not self.refresh_token_expires_at:
            return False
        return datetime.now(timezone.utc) >= self.refresh_token_expires_at

    @property
    def can_refresh(self) -> bool:
        """Check if tokens can be refreshed."""
        return (
            self.status == CredentialStatus.ACTIVE and
            self.refresh_token_encrypted is not None and
            not self.is_refresh_token_expired
        )

    @property
    def is_usable(self) -> bool:
        """Check if credentials can be used for API calls."""
        return (
            self.status == CredentialStatus.ACTIVE and
            self.is_active and
            self.access_token_encrypted is not None and
            (not self.is_token_expired or self.can_refresh)
        )

    def to_safe_dict(self) -> dict:
        """
        Return dictionary safe for logging/API responses.
        
        SECURITY: Excludes all token values.
        """
        return {
            "id": self.id,
            "tenant_id": self.tenant_id,
            "provider": self.provider.value if self.provider else None,
            "external_account_id": self.external_account_id,
            "account_name": self.account_name,  # Allowed per PII policy
            "connector_name": self.connector_name,  # Allowed per PII policy
            "status": self.status.value if self.status else None,
            "is_active": self.is_active,
            "expires_at": self.expires_at.isoformat() if self.expires_at else None,
            "last_refreshed_at": self.last_refreshed_at.isoformat() if self.last_refreshed_at else None,
            "last_used_at": self.last_used_at.isoformat() if self.last_used_at else None,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }
