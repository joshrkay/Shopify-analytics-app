"""
Notification preference model for user notification settings.

Allows users to control which notifications they receive
and through which channels.

Story 9.2 - Notification Preferences (prepared in Story 9.1)
"""

import uuid

from sqlalchemy import Column, String, Boolean, Enum, UniqueConstraint, Index

from src.db_base import Base
from src.models.base import TimestampMixin, TenantScopedMixin
from src.models.notification import NotificationEventType


class NotificationPreference(Base, TimestampMixin, TenantScopedMixin):
    """
    User notification preferences.

    Controls which event types are enabled for which channels.
    NULL user_id represents tenant default.
    """

    __tablename__ = "notification_preferences"

    id = Column(
        String(255),
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
    )

    user_id = Column(String(255), nullable=True, index=True)
    event_type = Column(Enum(NotificationEventType, values_callable=lambda enum_cls: [e.value for e in enum_cls]), nullable=False)

    in_app_enabled = Column(Boolean, nullable=False, default=True)
    email_enabled = Column(Boolean, nullable=False, default=True)

    __table_args__ = (
        UniqueConstraint(
            "tenant_id", "user_id", "event_type",
            name="uq_notification_pref_user_event"
        ),
        Index("ix_notification_prefs_tenant_user", "tenant_id", "user_id"),
    )

    def __repr__(self) -> str:
        return (
            f"<NotificationPreference(tenant_id={self.tenant_id}, "
            f"user_id={self.user_id}, event_type={self.event_type.value if self.event_type else None})>"
        )
