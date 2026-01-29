"""
Changelog API schemas for Story 9.7.

Pydantic models for changelog entries and read status.

SECURITY:
- Admin-only write operations
- Any authenticated user can read
"""

from datetime import datetime
from typing import Optional, List

from pydantic import BaseModel, Field, field_validator


class ChangelogEntryResponse(BaseModel):
    """Single changelog entry for display."""

    id: str
    version: str
    title: str
    summary: str
    content: Optional[str] = None
    release_type: str
    feature_areas: List[str] = Field(default_factory=list)
    published_at: Optional[datetime] = None
    documentation_url: Optional[str] = None
    is_read: bool = False  # Populated per-user


class ChangelogListResponse(BaseModel):
    """Response for changelog list queries."""

    entries: List[ChangelogEntryResponse]
    total: int
    has_more: bool
    unread_count: int


class ChangelogUnreadCountResponse(BaseModel):
    """Response for unread count query."""

    count: int
    by_feature_area: dict[str, int] = Field(default_factory=dict)


class ChangelogCreateRequest(BaseModel):
    """Request to create a new changelog entry (admin only)."""

    version: str = Field(..., min_length=1, max_length=50)
    title: str = Field(..., min_length=1, max_length=500)
    summary: str = Field(..., min_length=1)
    content: Optional[str] = None
    release_type: str = Field(..., pattern=r"^(feature|improvement|fix|deprecation|security)$")
    feature_areas: List[str] = Field(default_factory=list)
    documentation_url: Optional[str] = Field(None, max_length=1000)

    @field_validator("feature_areas")
    @classmethod
    def validate_feature_areas(cls, v: List[str]) -> List[str]:
        """Validate feature areas are from allowed list."""
        from src.models.changelog_entry import FEATURE_AREAS
        invalid = set(v) - set(FEATURE_AREAS)
        if invalid:
            raise ValueError(f"Invalid feature areas: {invalid}. Allowed: {FEATURE_AREAS}")
        return v


class ChangelogUpdateRequest(BaseModel):
    """Request to update a changelog entry (admin only)."""

    version: Optional[str] = Field(None, min_length=1, max_length=50)
    title: Optional[str] = Field(None, min_length=1, max_length=500)
    summary: Optional[str] = Field(None, min_length=1)
    content: Optional[str] = None
    release_type: Optional[str] = Field(None, pattern=r"^(feature|improvement|fix|deprecation|security)$")
    feature_areas: Optional[List[str]] = None
    documentation_url: Optional[str] = Field(None, max_length=1000)

    @field_validator("feature_areas")
    @classmethod
    def validate_feature_areas(cls, v: Optional[List[str]]) -> Optional[List[str]]:
        """Validate feature areas are from allowed list."""
        if v is None:
            return v
        from src.models.changelog_entry import FEATURE_AREAS
        invalid = set(v) - set(FEATURE_AREAS)
        if invalid:
            raise ValueError(f"Invalid feature areas: {invalid}. Allowed: {FEATURE_AREAS}")
        return v


class ChangelogAdminEntryResponse(BaseModel):
    """
    Changelog entry for admin view.

    Includes additional fields not shown to regular users.
    """

    id: str
    version: str
    title: str
    summary: str
    content: Optional[str] = None
    release_type: str
    feature_areas: List[str] = Field(default_factory=list)
    is_published: bool
    published_at: Optional[datetime] = None
    documentation_url: Optional[str] = None
    created_by_user_id: str
    created_at: datetime
    updated_at: datetime


class ChangelogAdminListResponse(BaseModel):
    """Response for admin changelog list queries."""

    entries: List[ChangelogAdminEntryResponse]
    total: int
    has_more: bool


class ChangelogMarkReadRequest(BaseModel):
    """Request to mark entries as read."""

    entry_ids: List[str] = Field(default_factory=list)


class ChangelogMarkReadResponse(BaseModel):
    """Response after marking entries as read."""

    marked_count: int
    unread_count: int
