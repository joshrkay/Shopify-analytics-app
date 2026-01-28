"""
Notifications API routes for Story 9.1.

Provides endpoints for:
- Listing notifications
- Getting unread count
- Marking notifications as read

SECURITY:
- All routes require valid tenant context from JWT
- Notifications are tenant-scoped and user-scoped
- Users can only see their own notifications

Story 9.1 - Notification Framework (Events → Channels)
"""

import logging
from typing import Optional

from fastapi import APIRouter, Request, HTTPException, status, Depends, Query

from src.platform.tenant_context import get_tenant_context
from src.database.session import get_db_session
from src.models.notification import (
    Notification,
    NotificationEventType,
    NotificationStatus,
)
from src.services.notification_service import NotificationService
from src.api.schemas.notifications import (
    NotificationResponse,
    NotificationListResponse,
    UnreadCountResponse,
    MarkReadResponse,
    MarkAllReadResponse,
)


logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/notifications", tags=["notifications"])


def _notification_to_response(notification: Notification) -> NotificationResponse:
    """Convert Notification model to response model."""
    return NotificationResponse(
        id=notification.id,
        event_type=notification.event_type.value if notification.event_type else "",
        importance=notification.importance.value if notification.importance else "",
        title=notification.title,
        message=notification.message,
        action_url=notification.action_url,
        entity_type=notification.entity_type,
        entity_id=notification.entity_id,
        status=notification.status.value if notification.status else "",
        created_at=notification.created_at,
        read_at=notification.read_at,
    )


@router.get(
    "",
    response_model=NotificationListResponse,
)
async def list_notifications(
    request: Request,
    db_session=Depends(get_db_session),
    status_filter: Optional[str] = Query(
        None, alias="status", description="Filter by status"
    ),
    event_type: Optional[str] = Query(
        None, description="Filter by event type"
    ),
    limit: int = Query(50, le=100, description="Maximum notifications to return"),
    offset: int = Query(0, ge=0, description="Offset for pagination"),
):
    """
    List notifications for the current user.

    Notifications are sorted by created_at (newest first).

    SECURITY: Only returns notifications for the authenticated user.
    """
    tenant_ctx = get_tenant_context(request)

    service = NotificationService(db_session, tenant_ctx.tenant_id)

    # Parse filters
    parsed_status = None
    if status_filter:
        try:
            parsed_status = NotificationStatus(status_filter)
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid status: {status_filter}",
            )

    parsed_event_type = None
    if event_type:
        try:
            parsed_event_type = NotificationEventType(event_type)
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid event type: {event_type}",
            )

    notifications, total = service.get_notifications(
        user_id=tenant_ctx.user_id,
        event_type=parsed_event_type,
        status=parsed_status,
        limit=limit,
        offset=offset,
    )

    unread_count = service.get_unread_count(tenant_ctx.user_id)

    return NotificationListResponse(
        notifications=[_notification_to_response(n) for n in notifications],
        total=total,
        unread_count=unread_count,
    )


@router.get(
    "/unread/count",
    response_model=UnreadCountResponse,
)
async def get_unread_count(
    request: Request,
    db_session=Depends(get_db_session),
):
    """
    Get count of unread notifications for the current user.

    SECURITY: Only counts notifications for the authenticated user.
    """
    tenant_ctx = get_tenant_context(request)

    service = NotificationService(db_session, tenant_ctx.tenant_id)
    count = service.get_unread_count(tenant_ctx.user_id)

    return UnreadCountResponse(count=count)


@router.get(
    "/{notification_id}",
    response_model=NotificationResponse,
)
async def get_notification(
    request: Request,
    notification_id: str,
    db_session=Depends(get_db_session),
):
    """
    Get a single notification by ID.

    SECURITY: Only returns notification if it belongs to the authenticated user.
    """
    tenant_ctx = get_tenant_context(request)

    notification = (
        db_session.query(Notification)
        .filter(
            Notification.id == notification_id,
            Notification.tenant_id == tenant_ctx.tenant_id,
            Notification.user_id == tenant_ctx.user_id,
        )
        .first()
    )

    if not notification:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Notification not found",
        )

    return _notification_to_response(notification)


@router.patch(
    "/{notification_id}/read",
    response_model=MarkReadResponse,
)
async def mark_as_read(
    request: Request,
    notification_id: str,
    db_session=Depends(get_db_session),
):
    """
    Mark a notification as read.

    SECURITY: Only allows marking notifications owned by the authenticated user.
    """
    tenant_ctx = get_tenant_context(request)

    service = NotificationService(db_session, tenant_ctx.tenant_id)
    success = service.mark_as_read(notification_id, tenant_ctx.user_id)

    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Notification not found",
        )

    db_session.commit()

    return MarkReadResponse(success=True)


@router.post(
    "/read-all",
    response_model=MarkAllReadResponse,
)
async def mark_all_as_read(
    request: Request,
    db_session=Depends(get_db_session),
):
    """
    Mark all notifications as read for the current user.

    SECURITY: Only marks notifications owned by the authenticated user.
    """
    tenant_ctx = get_tenant_context(request)

    service = NotificationService(db_session, tenant_ctx.tenant_id)
    count = service.mark_all_as_read(tenant_ctx.user_id)

    db_session.commit()

    logger.info(
        "All notifications marked as read",
        extra={
            "tenant_id": tenant_ctx.tenant_id,
            "user_id": tenant_ctx.user_id,
            "count": count,
        },
    )

    return MarkAllReadResponse(marked_count=count)
