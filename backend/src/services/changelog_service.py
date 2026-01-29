"""
Changelog service for Story 9.7.

Handles changelog entry management and read status tracking.

SECURITY:
- Write operations require ADMIN role (enforced at route level)
- Read operations available to any authenticated user
- tenant_id from JWT only for read status
"""

import logging
from datetime import datetime, timezone
from typing import Optional, List, Tuple

from sqlalchemy.orm import Session
from sqlalchemy import func, and_, or_

from src.models.changelog_entry import ChangelogEntry, ReleaseType, FEATURE_AREAS
from src.models.changelog_read_status import ChangelogReadStatus


logger = logging.getLogger(__name__)


class ChangelogService:
    """
    Service for managing changelog entries and read status.

    Handles:
    - CRUD operations for changelog entries (admin only)
    - Read status tracking per user
    - Unread count calculations
    - Feature area filtering for contextual badges
    """

    def __init__(self, db_session: Session, tenant_id: str, user_id: str):
        """
        Initialize changelog service.

        Args:
            db_session: Database session
            tenant_id: Tenant identifier (from JWT)
            user_id: User identifier (from JWT)
        """
        if not tenant_id:
            raise ValueError("tenant_id is required")
        if not user_id:
            raise ValueError("user_id is required")

        self.db = db_session
        self.tenant_id = tenant_id
        self.user_id = user_id

    # =========================================================================
    # Public Read Operations (any authenticated user)
    # =========================================================================

    def get_published_entries(
        self,
        release_type: Optional[str] = None,
        feature_area: Optional[str] = None,
        include_read: bool = True,
        limit: int = 50,
        offset: int = 0,
    ) -> Tuple[List[dict], int, int]:
        """
        Get published changelog entries with read status.

        Args:
            release_type: Filter by release type (optional)
            feature_area: Filter by feature area (optional)
            include_read: Include already-read entries (default True)
            limit: Maximum results
            offset: Pagination offset

        Returns:
            Tuple of (entries_with_read_status, total_count, unread_count)
        """
        # Build base query for published entries
        query = self.db.query(ChangelogEntry).filter(
            ChangelogEntry.is_published == True
        )

        if release_type:
            query = query.filter(ChangelogEntry.release_type == release_type)

        if feature_area:
            # Filter by feature area in JSONB array
            query = query.filter(
                ChangelogEntry.feature_areas.contains([feature_area])
            )

        # Get user's read entries
        read_entry_ids = set(
            r[0] for r in self.db.query(ChangelogReadStatus.changelog_entry_id)
            .filter(
                ChangelogReadStatus.tenant_id == self.tenant_id,
                ChangelogReadStatus.user_id == self.user_id,
            )
            .all()
        )

        # Get total count
        total = query.count()

        # Calculate unread count
        unread_count = query.filter(
            ~ChangelogEntry.id.in_(read_entry_ids) if read_entry_ids else True
        ).count()

        # Apply include_read filter
        if not include_read and read_entry_ids:
            query = query.filter(~ChangelogEntry.id.in_(read_entry_ids))

        # Get paginated results
        entries = (
            query
            .order_by(ChangelogEntry.published_at.desc())
            .offset(offset)
            .limit(limit)
            .all()
        )

        # Build response with read status
        result = []
        for entry in entries:
            result.append({
                "id": entry.id,
                "version": entry.version,
                "title": entry.title,
                "summary": entry.summary,
                "content": entry.content,
                "release_type": entry.release_type,
                "feature_areas": entry.feature_areas or [],
                "published_at": entry.published_at,
                "documentation_url": entry.documentation_url,
                "is_read": entry.id in read_entry_ids,
            })

        return result, total, unread_count

    def get_entry(self, entry_id: str) -> Optional[dict]:
        """
        Get a single published changelog entry with read status.

        Args:
            entry_id: Changelog entry ID

        Returns:
            Entry dict with read status or None if not found
        """
        entry = (
            self.db.query(ChangelogEntry)
            .filter(
                ChangelogEntry.id == entry_id,
                ChangelogEntry.is_published == True,
            )
            .first()
        )

        if not entry:
            return None

        # Check if user has read this entry
        is_read = (
            self.db.query(ChangelogReadStatus)
            .filter(
                ChangelogReadStatus.tenant_id == self.tenant_id,
                ChangelogReadStatus.user_id == self.user_id,
                ChangelogReadStatus.changelog_entry_id == entry_id,
            )
            .first()
        ) is not None

        return {
            "id": entry.id,
            "version": entry.version,
            "title": entry.title,
            "summary": entry.summary,
            "content": entry.content,
            "release_type": entry.release_type,
            "feature_areas": entry.feature_areas or [],
            "published_at": entry.published_at,
            "documentation_url": entry.documentation_url,
            "is_read": is_read,
        }

    def get_unread_count(self, feature_area: Optional[str] = None) -> dict:
        """
        Get count of unread changelog entries.

        Args:
            feature_area: Optional filter by feature area

        Returns:
            Dict with total count and count by feature area
        """
        # Get user's read entry IDs
        read_entry_ids = set(
            r[0] for r in self.db.query(ChangelogReadStatus.changelog_entry_id)
            .filter(
                ChangelogReadStatus.tenant_id == self.tenant_id,
                ChangelogReadStatus.user_id == self.user_id,
            )
            .all()
        )

        # Build base query for published entries
        base_query = self.db.query(ChangelogEntry).filter(
            ChangelogEntry.is_published == True
        )

        if read_entry_ids:
            base_query = base_query.filter(
                ~ChangelogEntry.id.in_(read_entry_ids)
            )

        # Get total unread count
        if feature_area:
            total_count = base_query.filter(
                ChangelogEntry.feature_areas.contains([feature_area])
            ).count()
            return {"count": total_count, "by_feature_area": {feature_area: total_count}}

        total_count = base_query.count()

        # Get count by feature area
        by_feature_area = {}
        for area in FEATURE_AREAS:
            area_count = base_query.filter(
                ChangelogEntry.feature_areas.contains([area])
            ).count()
            if area_count > 0:
                by_feature_area[area] = area_count

        return {"count": total_count, "by_feature_area": by_feature_area}

    def get_entries_for_feature(
        self,
        feature_area: str,
        limit: int = 5,
    ) -> List[dict]:
        """
        Get recent unread entries for a specific feature area.

        Used for contextual badges/banners.

        Args:
            feature_area: Feature area to filter by
            limit: Maximum results

        Returns:
            List of unread entries for the feature area
        """
        # Get user's read entry IDs
        read_entry_ids = set(
            r[0] for r in self.db.query(ChangelogReadStatus.changelog_entry_id)
            .filter(
                ChangelogReadStatus.tenant_id == self.tenant_id,
                ChangelogReadStatus.user_id == self.user_id,
            )
            .all()
        )

        # Query unread entries for feature area
        query = self.db.query(ChangelogEntry).filter(
            ChangelogEntry.is_published == True,
            ChangelogEntry.feature_areas.contains([feature_area]),
        )

        if read_entry_ids:
            query = query.filter(~ChangelogEntry.id.in_(read_entry_ids))

        entries = (
            query
            .order_by(ChangelogEntry.published_at.desc())
            .limit(limit)
            .all()
        )

        return [
            {
                "id": entry.id,
                "version": entry.version,
                "title": entry.title,
                "summary": entry.summary,
                "release_type": entry.release_type,
                "published_at": entry.published_at,
                "is_read": False,
            }
            for entry in entries
        ]

    def mark_as_read(self, entry_id: str) -> bool:
        """
        Mark a changelog entry as read for the current user.

        Args:
            entry_id: Changelog entry ID

        Returns:
            True if successful, False if entry not found
        """
        # Verify entry exists and is published
        entry = (
            self.db.query(ChangelogEntry)
            .filter(
                ChangelogEntry.id == entry_id,
                ChangelogEntry.is_published == True,
            )
            .first()
        )

        if not entry:
            return False

        # Check if already read
        existing = (
            self.db.query(ChangelogReadStatus)
            .filter(
                ChangelogReadStatus.tenant_id == self.tenant_id,
                ChangelogReadStatus.user_id == self.user_id,
                ChangelogReadStatus.changelog_entry_id == entry_id,
            )
            .first()
        )

        if existing:
            return True  # Already read

        # Create read status
        read_status = ChangelogReadStatus(
            tenant_id=self.tenant_id,
            user_id=self.user_id,
            changelog_entry_id=entry_id,
        )
        self.db.add(read_status)
        self.db.flush()

        logger.info(
            "Changelog entry marked as read",
            extra={
                "tenant_id": self.tenant_id,
                "user_id": self.user_id,
                "entry_id": entry_id,
            },
        )

        return True

    def mark_all_as_read(self) -> int:
        """
        Mark all published changelog entries as read for the current user.

        Returns:
            Count of entries marked as read
        """
        # Get user's already-read entry IDs
        read_entry_ids = set(
            r[0] for r in self.db.query(ChangelogReadStatus.changelog_entry_id)
            .filter(
                ChangelogReadStatus.tenant_id == self.tenant_id,
                ChangelogReadStatus.user_id == self.user_id,
            )
            .all()
        )

        # Get all published entry IDs that haven't been read
        unread_query = self.db.query(ChangelogEntry.id).filter(
            ChangelogEntry.is_published == True
        )

        if read_entry_ids:
            unread_query = unread_query.filter(
                ~ChangelogEntry.id.in_(read_entry_ids)
            )

        unread_ids = [r[0] for r in unread_query.all()]

        # Create read status for each unread entry
        count = 0
        for entry_id in unread_ids:
            read_status = ChangelogReadStatus(
                tenant_id=self.tenant_id,
                user_id=self.user_id,
                changelog_entry_id=entry_id,
            )
            self.db.add(read_status)
            count += 1

        self.db.flush()

        logger.info(
            "All changelog entries marked as read",
            extra={
                "tenant_id": self.tenant_id,
                "user_id": self.user_id,
                "count": count,
            },
        )

        return count

    # =========================================================================
    # Admin Operations (requires ADMIN role, enforced at route level)
    # =========================================================================

    def create_entry(
        self,
        version: str,
        title: str,
        summary: str,
        release_type: str,
        content: Optional[str] = None,
        feature_areas: Optional[List[str]] = None,
        documentation_url: Optional[str] = None,
    ) -> ChangelogEntry:
        """
        Create a new changelog entry (admin only).

        Args:
            version: Semver version string
            title: Entry title
            summary: Brief description
            release_type: Type of release
            content: Full markdown content (optional)
            feature_areas: List of feature areas (optional)
            documentation_url: Link to docs (optional)

        Returns:
            Created ChangelogEntry
        """
        entry = ChangelogEntry(
            version=version,
            title=title,
            summary=summary,
            release_type=release_type,
            content=content,
            feature_areas=feature_areas or [],
            documentation_url=documentation_url,
            created_by_user_id=self.user_id,
        )
        self.db.add(entry)
        self.db.flush()

        logger.info(
            "Changelog entry created",
            extra={
                "entry_id": entry.id,
                "version": version,
                "release_type": release_type,
                "created_by": self.user_id,
            },
        )

        return entry

    def update_entry(
        self,
        entry_id: str,
        version: Optional[str] = None,
        title: Optional[str] = None,
        summary: Optional[str] = None,
        release_type: Optional[str] = None,
        content: Optional[str] = None,
        feature_areas: Optional[List[str]] = None,
        documentation_url: Optional[str] = None,
    ) -> Optional[ChangelogEntry]:
        """
        Update a changelog entry (admin only).

        Args:
            entry_id: Entry ID to update
            Other args: Fields to update (optional)

        Returns:
            Updated ChangelogEntry or None if not found
        """
        entry = self.db.query(ChangelogEntry).filter(
            ChangelogEntry.id == entry_id
        ).first()

        if not entry:
            return None

        if version is not None:
            entry.version = version
        if title is not None:
            entry.title = title
        if summary is not None:
            entry.summary = summary
        if release_type is not None:
            entry.release_type = release_type
        if content is not None:
            entry.content = content
        if feature_areas is not None:
            entry.feature_areas = feature_areas
        if documentation_url is not None:
            entry.documentation_url = documentation_url

        self.db.flush()

        logger.info(
            "Changelog entry updated",
            extra={
                "entry_id": entry_id,
                "updated_by": self.user_id,
            },
        )

        return entry

    def delete_entry(self, entry_id: str) -> bool:
        """
        Delete a changelog entry (admin only).

        Args:
            entry_id: Entry ID to delete

        Returns:
            True if deleted, False if not found
        """
        entry = self.db.query(ChangelogEntry).filter(
            ChangelogEntry.id == entry_id
        ).first()

        if not entry:
            return False

        self.db.delete(entry)
        self.db.flush()

        logger.info(
            "Changelog entry deleted",
            extra={
                "entry_id": entry_id,
                "deleted_by": self.user_id,
            },
        )

        return True

    def publish_entry(self, entry_id: str) -> Optional[ChangelogEntry]:
        """
        Publish a changelog entry (admin only).

        Args:
            entry_id: Entry ID to publish

        Returns:
            Updated ChangelogEntry or None if not found
        """
        entry = self.db.query(ChangelogEntry).filter(
            ChangelogEntry.id == entry_id
        ).first()

        if not entry:
            return None

        entry.publish()
        self.db.flush()

        logger.info(
            "Changelog entry published",
            extra={
                "entry_id": entry_id,
                "published_by": self.user_id,
            },
        )

        return entry

    def unpublish_entry(self, entry_id: str) -> Optional[ChangelogEntry]:
        """
        Unpublish a changelog entry (admin only).

        Args:
            entry_id: Entry ID to unpublish

        Returns:
            Updated ChangelogEntry or None if not found
        """
        entry = self.db.query(ChangelogEntry).filter(
            ChangelogEntry.id == entry_id
        ).first()

        if not entry:
            return None

        entry.unpublish()
        self.db.flush()

        logger.info(
            "Changelog entry unpublished",
            extra={
                "entry_id": entry_id,
                "unpublished_by": self.user_id,
            },
        )

        return entry

    def get_all_entries_admin(
        self,
        include_unpublished: bool = True,
        limit: int = 50,
        offset: int = 0,
    ) -> Tuple[List[ChangelogEntry], int]:
        """
        Get all changelog entries for admin view (admin only).

        Args:
            include_unpublished: Include unpublished entries
            limit: Maximum results
            offset: Pagination offset

        Returns:
            Tuple of (entries, total_count)
        """
        query = self.db.query(ChangelogEntry)

        if not include_unpublished:
            query = query.filter(ChangelogEntry.is_published == True)

        total = query.count()

        entries = (
            query
            .order_by(ChangelogEntry.created_at.desc())
            .offset(offset)
            .limit(limit)
            .all()
        )

        return entries, total

    def get_entry_admin(self, entry_id: str) -> Optional[ChangelogEntry]:
        """
        Get a single changelog entry for admin view (admin only).

        Args:
            entry_id: Changelog entry ID

        Returns:
            ChangelogEntry or None if not found
        """
        return self.db.query(ChangelogEntry).filter(
            ChangelogEntry.id == entry_id
        ).first()
