"""
Changelog entry model for Story 9.7.

Provides admin-authored changelog/release notes that are:
- Global (not tenant-scoped) - all users see the same entries
- Versioned with semver format
- Categorized by release type (feature, improvement, fix, etc.)
- Targeted to specific feature areas for contextual badges

SECURITY:
- Write access: ADMIN role only
- Read access: Any authenticated user
"""

from datetime import datetime
from enum import Enum
from typing import Optional, List

from sqlalchemy import (
    Column, String, Text, Boolean, DateTime,
    Index, func
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy import JSON

from src.db_base import Base
from src.models.base import TimestampMixin, generate_uuid


class ReleaseType(str, Enum):
    """Types of changelog releases."""
    FEATURE = "feature"           # New features
    IMPROVEMENT = "improvement"   # Enhancements to existing features
    FIX = "fix"                   # Bug fixes
    DEPRECATION = "deprecation"   # Upcoming removals
    SECURITY = "security"         # Security updates


# Feature areas for contextual badge targeting
FEATURE_AREAS = [
    "dashboard",
    "sync_health",
    "insights",
    "recommendations",
    "approvals",
    "connectors",
    "billing",
    "settings",
    "reports",
    "notifications",
]


class ChangelogEntry(Base, TimestampMixin):
    """
    Admin-authored changelog entry for release notes.

    NOT tenant-scoped - these are global announcements visible to all users.
    Only users with ADMIN role can create/update/delete entries.

    Attributes:
        id: Unique identifier (UUID)
        version: Semver version string (e.g., "2.1.0")
        title: Short title for the entry
        summary: Brief description (shown in lists)
        content: Full markdown content (shown in detail view)
        release_type: Category of the release
        feature_areas: List of feature areas for contextual badges
        is_published: Whether entry is visible to users
        published_at: When entry was published
        documentation_url: Optional link to documentation
        created_by_user_id: Admin user who created the entry
    """
    __tablename__ = "changelog_entries"

    id = Column(String(255), primary_key=True, default=generate_uuid)

    # Version info (semver format, e.g., "2.1.0", "2.1.0-beta.1")
    version = Column(
        String(50),
        nullable=False,
        index=True,
        comment="Semver version string"
    )

    # Content
    title = Column(
        String(500),
        nullable=False,
        comment="Short title for the changelog entry"
    )
    summary = Column(
        Text,
        nullable=False,
        comment="Brief description shown in lists"
    )
    content = Column(
        Text,
        nullable=True,
        comment="Full markdown content for detail view"
    )

    # Categorization
    release_type = Column(
        String(50),
        nullable=False,
        index=True,
        comment="Type: feature, improvement, fix, deprecation, security"
    )

    # Feature targeting for contextual badges
    # Use JSON with JSONB variant for PostgreSQL compatibility
    feature_areas = Column(
        JSON().with_variant(JSONB, "postgresql"),
        nullable=False,
        default=list,
        comment="Feature areas for contextual badges"
    )

    # Visibility
    is_published = Column(
        Boolean,
        nullable=False,
        default=False,
        comment="Whether entry is visible to users"
    )
    published_at = Column(
        DateTime(timezone=True),
        nullable=True,
        comment="When entry was published"
    )

    # Documentation link
    documentation_url = Column(
        String(1000),
        nullable=True,
        comment="Optional link to documentation"
    )

    # Author tracking (admin user ID)
    created_by_user_id = Column(
        String(255),
        nullable=False,
        comment="Admin user who created the entry"
    )

    __table_args__ = (
        Index(
            "ix_changelog_entries_published",
            "is_published", "published_at",
            postgresql_where=(is_published == True)
        ),
        Index("ix_changelog_entries_release_type", "release_type"),
    )

    def __repr__(self) -> str:
        return f"<ChangelogEntry(id={self.id}, version={self.version}, title={self.title[:30]}...)>"

    def publish(self) -> None:
        """Mark entry as published."""
        self.is_published = True
        self.published_at = datetime.utcnow()

    def unpublish(self) -> None:
        """Mark entry as unpublished."""
        self.is_published = False
        self.published_at = None
