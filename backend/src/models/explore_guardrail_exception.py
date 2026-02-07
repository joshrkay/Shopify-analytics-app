"""
Explore guardrail exception model.

Tracks time-boxed, approval-based bypasses for Explore guardrails.
RLS, tenant isolation, and PII restrictions are never bypassed.
"""

import uuid
from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, String, Text, Index
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy import JSON

from src.db_base import Base


DatasetNamesType = ARRAY(String).with_variant(JSON, "sqlite")


class ExploreGuardrailException(Base):
    """Database model for Explore guardrail bypass exceptions."""

    __tablename__ = "explore_guardrail_exceptions"

    id = Column(
        String(255),
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
        comment="Primary key (UUID)"
    )

    user_id = Column(
        String(255),
        nullable=False,
        index=True,
        comment="Target user ID (internal user UUID)"
    )

    approved_by = Column(
        String(255),
        nullable=True,
        index=True,
        comment="Approver user ID"
    )

    dataset_names = Column(
        DatasetNamesType,
        nullable=False,
        comment="Datasets covered by the bypass"
    )

    expires_at = Column(
        DateTime(timezone=True),
        nullable=True,
        index=True,
        comment="Bypass expiration timestamp"
    )

    reason = Column(
        Text,
        nullable=False,
        comment="Reason for guardrail bypass"
    )

    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        comment="Creation timestamp"
    )

    __table_args__ = (
        Index(
            "idx_explore_guardrail_user_expires",
            "user_id",
            "expires_at",
        ),
    )

    def __repr__(self) -> str:
        return (
            f"<ExploreGuardrailException("
            f"id={self.id}, "
            f"user_id={self.user_id}, "
            f"approved_by={self.approved_by}, "
            f"expires_at={self.expires_at}"
            f")>"
        )
