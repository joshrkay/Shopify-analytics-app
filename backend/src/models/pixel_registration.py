"""
PixelRegistration model — tracks Web Pixel deployments per store.

Records when a Web Pixel is registered/unregistered via the Shopify
GraphQL Admin API, linking the Shopify pixel GID to the tenant.
"""

import uuid

from sqlalchemy import Column, String, Index

from src.db_base import Base
from src.models.base import TimestampMixin, TenantScopedMixin


class PixelRegistration(Base, TimestampMixin, TenantScopedMixin):
    """
    Tracks Web Pixel registrations for merchant stores.

    Each store can have at most one active pixel registration.
    """

    __tablename__ = "pixel_registrations"

    id = Column(
        String(255),
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
        comment="Primary key (UUID)",
    )
    shop_domain = Column(
        String(255),
        nullable=False,
        comment="Shopify store domain",
    )
    pixel_id = Column(
        String(255),
        unique=True,
        nullable=True,
        comment="Opaque pixel identifier (from Shopify webPixelCreate)",
    )
    shopify_pixel_gid = Column(
        String(255),
        nullable=True,
        comment="Shopify GraphQL ID for the registered pixel (gid://shopify/WebPixel/...)",
    )
    status = Column(
        String(50),
        nullable=False,
        default="active",
        comment="Registration status: active, inactive, deleted",
    )

    __table_args__ = (
        Index("ix_pixel_registrations_tenant_id", "tenant_id"),
        Index("ix_pixel_registrations_shop_domain", "shop_domain"),
    )

    def __repr__(self) -> str:
        return (
            f"<PixelRegistration(id={self.id}, shop={self.shop_domain}, "
            f"status={self.status})>"
        )
