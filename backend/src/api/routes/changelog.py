"""
Changelog API routes for Story 9.7.

Public endpoints for viewing changelog entries and managing read status.
Available to all authenticated users.

SECURITY:
- tenant_id from JWT only
- user_id from JWT only
- Read-only access to changelog entries
- Write access only for read status (marking as read)

Story 9.7 - In-App Changelog & Release Notes
"""

import logging
from typing import Optional

from fastapi import APIRouter, Request, HTTPException, status, Depends, Query

from src.platform.tenant_context import get_tenant_context
from src.database.session import get_db_session
from src.services.changelog_service import ChangelogService
from src.api.schemas.changelog import (
    ChangelogEntryResponse,
    ChangelogListResponse,
    ChangelogUnreadCountResponse,
    ChangelogMarkReadResponse,
)


logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/changelog", tags=["changelog"])


# =============================================================================
# Public Changelog Routes (any authenticated user)
# =============================================================================


@router.get(
    "",
    response_model=ChangelogListResponse,
)
async def list_changelog_entries(
    request: Request,
    db_session=Depends(get_db_session),
    release_type: Optional[str] = Query(
        None,
        description="Filter by release type (feature, improvement, fix, deprecation, security)"
    ),
    feature_area: Optional[str] = Query(
        None,
        description="Filter by feature area for contextual display"
    ),
    include_read: bool = Query(
        True,
        description="Include already-read entries"
    ),
    limit: int = Query(50, le=100, description="Maximum entries to return"),
    offset: int = Query(0, ge=0, description="Offset for pagination"),
):
    """
    List published changelog entries.

    Returns paginated changelog entries with read status for the current user.
    Entries are sorted by published_at descending (newest first).
    """
    tenant_ctx = get_tenant_context(request)

    service = ChangelogService(
        db_session=db_session,
        tenant_id=tenant_ctx.tenant_id,
        user_id=tenant_ctx.user_id,
    )

    entries, total, unread_count = service.get_published_entries(
        release_type=release_type,
        feature_area=feature_area,
        include_read=include_read,
        limit=limit,
        offset=offset,
    )

    has_more = offset + len(entries) < total

    return ChangelogListResponse(
        entries=[
            ChangelogEntryResponse(**entry)
            for entry in entries
        ],
        total=total,
        has_more=has_more,
        unread_count=unread_count,
    )


@router.get(
    "/unread/count",
    response_model=ChangelogUnreadCountResponse,
)
async def get_unread_count(
    request: Request,
    db_session=Depends(get_db_session),
    feature_area: Optional[str] = Query(
        None,
        description="Filter by feature area"
    ),
):
    """
    Get count of unread changelog entries.

    Useful for displaying badges in the UI.
    """
    tenant_ctx = get_tenant_context(request)

    service = ChangelogService(
        db_session=db_session,
        tenant_id=tenant_ctx.tenant_id,
        user_id=tenant_ctx.user_id,
    )

    result = service.get_unread_count(feature_area=feature_area)

    return ChangelogUnreadCountResponse(
        count=result["count"],
        by_feature_area=result["by_feature_area"],
    )


@router.get(
    "/feature/{feature_area}",
    response_model=ChangelogListResponse,
)
async def get_entries_for_feature(
    request: Request,
    feature_area: str,
    db_session=Depends(get_db_session),
    limit: int = Query(5, le=20, description="Maximum entries to return"),
):
    """
    Get recent unread changelog entries for a specific feature area.

    Used for contextual badges/banners near changed features.
    Returns only unread entries.
    """
    tenant_ctx = get_tenant_context(request)

    service = ChangelogService(
        db_session=db_session,
        tenant_id=tenant_ctx.tenant_id,
        user_id=tenant_ctx.user_id,
    )

    entries = service.get_entries_for_feature(
        feature_area=feature_area,
        limit=limit,
    )

    return ChangelogListResponse(
        entries=[
            ChangelogEntryResponse(**entry)
            for entry in entries
        ],
        total=len(entries),
        has_more=False,
        unread_count=len(entries),
    )


@router.get(
    "/{entry_id}",
    response_model=ChangelogEntryResponse,
)
async def get_changelog_entry(
    request: Request,
    entry_id: str,
    db_session=Depends(get_db_session),
):
    """
    Get a single changelog entry.

    Returns the entry with read status for the current user.
    """
    tenant_ctx = get_tenant_context(request)

    service = ChangelogService(
        db_session=db_session,
        tenant_id=tenant_ctx.tenant_id,
        user_id=tenant_ctx.user_id,
    )

    entry = service.get_entry(entry_id)

    if not entry:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Changelog entry not found",
        )

    return ChangelogEntryResponse(**entry)


@router.post(
    "/{entry_id}/read",
    response_model=ChangelogMarkReadResponse,
)
async def mark_entry_as_read(
    request: Request,
    entry_id: str,
    db_session=Depends(get_db_session),
):
    """
    Mark a changelog entry as read for the current user.
    """
    tenant_ctx = get_tenant_context(request)

    service = ChangelogService(
        db_session=db_session,
        tenant_id=tenant_ctx.tenant_id,
        user_id=tenant_ctx.user_id,
    )

    success = service.mark_as_read(entry_id)

    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Changelog entry not found",
        )

    # Get updated unread count
    db_session.commit()

    # Get updated unread count
    result = service.get_unread_count()

    return ChangelogMarkReadResponse(
        marked_count=1,
        unread_count=result["count"],
    )


@router.post(
    "/read-all",
    response_model=ChangelogMarkReadResponse,
)
async def mark_all_as_read(
    request: Request,
    db_session=Depends(get_db_session),
):
    """
    Mark all changelog entries as read for the current user.
    """
    tenant_ctx = get_tenant_context(request)

    service = ChangelogService(
        db_session=db_session,
        tenant_id=tenant_ctx.tenant_id,
        user_id=tenant_ctx.user_id,
    )

    count = service.mark_all_as_read()

    db_session.commit()

    return ChangelogMarkReadResponse(
        marked_count=count,
        unread_count=0,
    )
