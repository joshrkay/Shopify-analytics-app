"""
Admin Changelog API routes for Story 9.7.

Admin-only endpoints for managing changelog entries.
Requires ADMIN_SYSTEM_CONFIG permission.

SECURITY:
- Requires ADMIN role with ADMIN_SYSTEM_CONFIG permission
- Write operations create audit trail via logging
- tenant_id from JWT only (for audit tracking)

Story 9.7 - In-App Changelog & Release Notes
"""

import logging
from typing import Optional

from fastapi import APIRouter, Request, HTTPException, status, Depends, Query

from src.platform.tenant_context import get_tenant_context
from src.database.session import get_db_session
from src.services.changelog_service import ChangelogService
from src.constants.permissions import roles_have_permission, Permission
from src.api.schemas.changelog import (
    ChangelogCreateRequest,
    ChangelogUpdateRequest,
    ChangelogAdminEntryResponse,
    ChangelogAdminListResponse,
)


logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/admin/changelog", tags=["admin", "changelog"])


def require_admin_permission(request: Request) -> None:
    """
    Require ADMIN_SYSTEM_CONFIG permission for admin changelog operations.

    Raises 403 if user doesn't have required permission.
    """
    tenant_ctx = get_tenant_context(request)

    if not roles_have_permission(tenant_ctx.roles, Permission.ADMIN_SYSTEM_CONFIG):
        logger.warning(
            "Unauthorized admin changelog access attempt",
            extra={
                "tenant_id": tenant_ctx.tenant_id,
                "user_id": tenant_ctx.user_id,
                "roles": tenant_ctx.roles,
            },
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin permission required for changelog management",
        )


# =============================================================================
# Admin Changelog Routes (requires ADMIN_SYSTEM_CONFIG)
# =============================================================================


@router.get(
    "",
    response_model=ChangelogAdminListResponse,
)
async def list_all_entries(
    request: Request,
    db_session=Depends(get_db_session),
    include_unpublished: bool = Query(True, description="Include unpublished entries"),
    limit: int = Query(50, le=100, description="Maximum entries to return"),
    offset: int = Query(0, ge=0, description="Offset for pagination"),
):
    """
    List all changelog entries (including unpublished).

    Admin view with full entry details.
    """
    require_admin_permission(request)
    tenant_ctx = get_tenant_context(request)

    service = ChangelogService(
        db_session=db_session,
        tenant_id=tenant_ctx.tenant_id,
        user_id=tenant_ctx.user_id,
    )

    entries, total = service.get_all_entries_admin(
        include_unpublished=include_unpublished,
        limit=limit,
        offset=offset,
    )

    has_more = offset + len(entries) < total

    return ChangelogAdminListResponse(
        entries=[
            ChangelogAdminEntryResponse(
                id=entry.id,
                version=entry.version,
                title=entry.title,
                summary=entry.summary,
                content=entry.content,
                release_type=entry.release_type,
                feature_areas=entry.feature_areas or [],
                is_published=entry.is_published,
                published_at=entry.published_at,
                documentation_url=entry.documentation_url,
                created_by_user_id=entry.created_by_user_id,
                created_at=entry.created_at,
                updated_at=entry.updated_at,
            )
            for entry in entries
        ],
        total=total,
        has_more=has_more,
    )


@router.get(
    "/{entry_id}",
    response_model=ChangelogAdminEntryResponse,
)
async def get_entry_admin(
    request: Request,
    entry_id: str,
    db_session=Depends(get_db_session),
):
    """
    Get a single changelog entry (admin view).

    Returns full entry details including unpublished.
    """
    require_admin_permission(request)
    tenant_ctx = get_tenant_context(request)

    service = ChangelogService(
        db_session=db_session,
        tenant_id=tenant_ctx.tenant_id,
        user_id=tenant_ctx.user_id,
    )

    entry = service.get_entry_admin(entry_id)

    if not entry:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Changelog entry not found",
        )

    return ChangelogAdminEntryResponse(
        id=entry.id,
        version=entry.version,
        title=entry.title,
        summary=entry.summary,
        content=entry.content,
        release_type=entry.release_type,
        feature_areas=entry.feature_areas or [],
        is_published=entry.is_published,
        published_at=entry.published_at,
        documentation_url=entry.documentation_url,
        created_by_user_id=entry.created_by_user_id,
        created_at=entry.created_at,
        updated_at=entry.updated_at,
    )


@router.post(
    "",
    response_model=ChangelogAdminEntryResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_entry(
    request: Request,
    body: ChangelogCreateRequest,
    db_session=Depends(get_db_session),
):
    """
    Create a new changelog entry.

    Entry is created as unpublished by default.
    """
    require_admin_permission(request)
    tenant_ctx = get_tenant_context(request)

    service = ChangelogService(
        db_session=db_session,
        tenant_id=tenant_ctx.tenant_id,
        user_id=tenant_ctx.user_id,
    )

    entry = service.create_entry(
        version=body.version,
        title=body.title,
        summary=body.summary,
        release_type=body.release_type,
        content=body.content,
        feature_areas=body.feature_areas,
        documentation_url=body.documentation_url,
    )

    db_session.commit()

    logger.info(
        "Admin created changelog entry",
        extra={
            "entry_id": entry.id,
            "version": entry.version,
            "created_by": tenant_ctx.user_id,
        },
    )

    return ChangelogAdminEntryResponse(
        id=entry.id,
        version=entry.version,
        title=entry.title,
        summary=entry.summary,
        content=entry.content,
        release_type=entry.release_type,
        feature_areas=entry.feature_areas or [],
        is_published=entry.is_published,
        published_at=entry.published_at,
        documentation_url=entry.documentation_url,
        created_by_user_id=entry.created_by_user_id,
        created_at=entry.created_at,
        updated_at=entry.updated_at,
    )


@router.put(
    "/{entry_id}",
    response_model=ChangelogAdminEntryResponse,
)
async def update_entry(
    request: Request,
    entry_id: str,
    body: ChangelogUpdateRequest,
    db_session=Depends(get_db_session),
):
    """
    Update a changelog entry.
    """
    require_admin_permission(request)
    tenant_ctx = get_tenant_context(request)

    service = ChangelogService(
        db_session=db_session,
        tenant_id=tenant_ctx.tenant_id,
        user_id=tenant_ctx.user_id,
    )

    entry = service.update_entry(
        entry_id=entry_id,
        version=body.version,
        title=body.title,
        summary=body.summary,
        release_type=body.release_type,
        content=body.content,
        feature_areas=body.feature_areas,
        documentation_url=body.documentation_url,
    )

    if not entry:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Changelog entry not found",
        )

    db_session.commit()

    logger.info(
        "Admin updated changelog entry",
        extra={
            "entry_id": entry_id,
            "updated_by": tenant_ctx.user_id,
        },
    )

    return ChangelogAdminEntryResponse(
        id=entry.id,
        version=entry.version,
        title=entry.title,
        summary=entry.summary,
        content=entry.content,
        release_type=entry.release_type,
        feature_areas=entry.feature_areas or [],
        is_published=entry.is_published,
        published_at=entry.published_at,
        documentation_url=entry.documentation_url,
        created_by_user_id=entry.created_by_user_id,
        created_at=entry.created_at,
        updated_at=entry.updated_at,
    )


@router.delete(
    "/{entry_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_entry(
    request: Request,
    entry_id: str,
    db_session=Depends(get_db_session),
):
    """
    Delete a changelog entry.
    """
    require_admin_permission(request)
    tenant_ctx = get_tenant_context(request)

    service = ChangelogService(
        db_session=db_session,
        tenant_id=tenant_ctx.tenant_id,
        user_id=tenant_ctx.user_id,
    )

    success = service.delete_entry(entry_id)

    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Changelog entry not found",
        )

    db_session.commit()

    logger.info(
        "Admin deleted changelog entry",
        extra={
            "entry_id": entry_id,
            "deleted_by": tenant_ctx.user_id,
        },
    )


@router.post(
    "/{entry_id}/publish",
    response_model=ChangelogAdminEntryResponse,
)
async def publish_entry(
    request: Request,
    entry_id: str,
    db_session=Depends(get_db_session),
):
    """
    Publish a changelog entry.

    Makes the entry visible to all users.
    """
    require_admin_permission(request)
    tenant_ctx = get_tenant_context(request)

    service = ChangelogService(
        db_session=db_session,
        tenant_id=tenant_ctx.tenant_id,
        user_id=tenant_ctx.user_id,
    )

    entry = service.publish_entry(entry_id)

    if not entry:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Changelog entry not found",
        )

    db_session.commit()

    logger.info(
        "Admin published changelog entry",
        extra={
            "entry_id": entry_id,
            "published_by": tenant_ctx.user_id,
        },
    )

    return ChangelogAdminEntryResponse(
        id=entry.id,
        version=entry.version,
        title=entry.title,
        summary=entry.summary,
        content=entry.content,
        release_type=entry.release_type,
        feature_areas=entry.feature_areas or [],
        is_published=entry.is_published,
        published_at=entry.published_at,
        documentation_url=entry.documentation_url,
        created_by_user_id=entry.created_by_user_id,
        created_at=entry.created_at,
        updated_at=entry.updated_at,
    )


@router.post(
    "/{entry_id}/unpublish",
    response_model=ChangelogAdminEntryResponse,
)
async def unpublish_entry(
    request: Request,
    entry_id: str,
    db_session=Depends(get_db_session),
):
    """
    Unpublish a changelog entry.

    Hides the entry from regular users.
    """
    require_admin_permission(request)
    tenant_ctx = get_tenant_context(request)

    service = ChangelogService(
        db_session=db_session,
        tenant_id=tenant_ctx.tenant_id,
        user_id=tenant_ctx.user_id,
    )

    entry = service.unpublish_entry(entry_id)

    if not entry:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Changelog entry not found",
        )

    db_session.commit()

    logger.info(
        "Admin unpublished changelog entry",
        extra={
            "entry_id": entry_id,
            "unpublished_by": tenant_ctx.user_id,
        },
    )

    return ChangelogAdminEntryResponse(
        id=entry.id,
        version=entry.version,
        title=entry.title,
        summary=entry.summary,
        content=entry.content,
        release_type=entry.release_type,
        feature_areas=entry.feature_areas or [],
        is_published=entry.is_published,
        published_at=entry.published_at,
        documentation_url=entry.documentation_url,
        created_by_user_id=entry.created_by_user_id,
        created_at=entry.created_at,
        updated_at=entry.updated_at,
    )
