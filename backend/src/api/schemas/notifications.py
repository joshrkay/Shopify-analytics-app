"""
Pydantic schemas for Notifications API (Story 9.1).

Request and response models for notification endpoints.

Story 9.1 - Notification Framework (Events → Channels)
"""

from typing import Optional, List
from datetime import datetime

from pydantic import BaseModel, Field


class NotificationResponse(BaseModel):
    """Response model for a single notification."""

    id: str = Field(..., description="Unique notification identifier")
    event_type: str = Field(..., description="Type of event that triggered notification")
    importance: str = Field(..., description="Importance level: important or routine")
    title: str = Field(..., description="Notification title")
    message: str = Field(..., description="Notification body message")
    action_url: Optional[str] = Field(None, description="Deep link URL to relevant page")

    entity_type: Optional[str] = Field(None, description="Type of related entity")
    entity_id: Optional[str] = Field(None, description="ID of related entity")

    status: str = Field(..., description="Delivery status: pending, delivered, read")
    created_at: datetime = Field(..., description="When notification was created")
    read_at: Optional[datetime] = Field(None, description="When notification was read")

    class Config:
        from_attributes = True


class NotificationListResponse(BaseModel):
    """Response model for notification list."""

    notifications: List[NotificationResponse] = Field(..., description="List of notifications")
    total: int = Field(..., description="Total count of matching notifications")
    unread_count: int = Field(..., description="Count of unread notifications")


class UnreadCountResponse(BaseModel):
    """Response model for unread count."""

    count: int = Field(..., description="Number of unread notifications")


class MarkReadResponse(BaseModel):
    """Response model for marking notification as read."""

    success: bool = Field(..., description="Whether operation succeeded")


class MarkAllReadResponse(BaseModel):
    """Response model for marking all notifications as read."""

    marked_count: int = Field(..., description="Number of notifications marked as read")


class NotificationPreferenceItem(BaseModel):
    """A single per-event-type preference row."""

    event_type: str = Field(..., description="Event type identifier")
    in_app_enabled: bool = Field(..., description="Whether in-app notifications are enabled")
    email_enabled: bool = Field(..., description="Whether email notifications are enabled")


class NotificationPreferencesResponse(BaseModel):
    """Response model for notification preferences list."""

    preferences: List[NotificationPreferenceItem]


class NotificationPreferencesUpdateRequest(BaseModel):
    """Request model for upserting notification preferences."""

    preferences: List[NotificationPreferenceItem]
