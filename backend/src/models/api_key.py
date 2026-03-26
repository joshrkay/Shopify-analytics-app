"""API key model for tenant-scoped programmatic access settings."""

import uuid

from sqlalchemy import Column, String, Boolean, DateTime

from src.db_base import Base
from src.models.base import TimestampMixin, TenantScopedMixin


class ApiKey(Base, TenantScopedMixin, TimestampMixin):
    """Stores hashed API keys and metadata for a tenant."""

    __tablename__ = "api_keys"

    id = Column(String(255), primary_key=True, default=lambda: str(uuid.uuid4()))
    name = Column(String(120), nullable=False)
    key_prefix = Column(String(20), nullable=False)
    key_hash = Column(String(128), nullable=False)
    created_by_user_id = Column(String(255), nullable=False)
    last_used_at = Column(DateTime(timezone=True), nullable=True)
    expires_at = Column(DateTime(timezone=True), nullable=True)
    revoked_at = Column(DateTime(timezone=True), nullable=True)
    is_active = Column(Boolean, nullable=False, default=True)
