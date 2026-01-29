"""
Changelog read status model for Story 9.7.

Tracks which changelog entries a user has seen.

SECURITY:
- Tenant-scoped via TenantScopedMixin
- User-scoped within tenant
- tenant_id from JWT only
"""

from sqlalchemy import (
    Column, String, DateTime, ForeignKey,
    Index, UniqueConstraint, func
)

from src.db_base import Base
from src.models.base import TenantScopedMixin, generate_uuid


class ChangelogReadStatus(Base, TenantScopedMixin):
    """
    Tracks which changelog entries a user has seen.

    Tenant and user scoped - each user has their own read status.

    SECURITY:
    - tenant_id is ONLY from JWT (org_id)
    - NEVER accept tenant_id from client input

    Attributes:
        id: Unique identifier (UUID)
        tenant_id: Tenant identifier from JWT
        user_id: User who read the entry
        changelog_entry_id: The changelog entry that was read
        read_at: When the user read the entry
    """
    __tablename__ = "changelog_read_status"

    id = Column(String(255), primary_key=True, default=generate_uuid)

    # User who read the entry
    user_id = Column(
        String(255),
        nullable=False,
        index=True,
        comment="User who read the entry"
    )

    # The changelog entry that was read
    changelog_entry_id = Column(
        String(255),
        ForeignKey("changelog_entries.id", ondelete="CASCADE"),
        nullable=False,
        comment="The changelog entry that was read"
    )

    # When the user read the entry
    read_at = Column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        comment="When the user read the entry"
    )

    __table_args__ = (
        # Ensure each user can only have one read status per entry
        UniqueConstraint(
            "tenant_id", "user_id", "changelog_entry_id",
            name="uq_changelog_read_tenant_user_entry"
        ),
        # Index for efficient lookup of user's read entries
        Index(
            "ix_changelog_read_tenant_user",
            "tenant_id", "user_id"
        ),
    )

    def __repr__(self) -> str:
        return f"<ChangelogReadStatus(user_id={self.user_id}, entry_id={self.changelog_entry_id})>"
