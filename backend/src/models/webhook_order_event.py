"""
WebhookOrderEvent model — stores real-time order data from Shopify webhooks.

Provides immediate access to order data (including UTM attribution params)
without waiting for the 60-minute Airbyte sync cycle.
"""

import uuid

from sqlalchemy import Column, String, DateTime, Numeric, Text, Index
from sqlalchemy.dialects.postgresql import JSONB

from src.db_base import Base
from src.models.base import TimestampMixin, TenantScopedMixin


class WebhookOrderEvent(Base, TimestampMixin, TenantScopedMixin):
    """
    Order data received via Shopify orders/create and orders/updated webhooks.

    Enables real-time attribution and dashboards instead of waiting for Airbyte.
    """

    __tablename__ = "webhook_order_events"

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
    shopify_order_id = Column(
        String(255),
        nullable=False,
        comment="Shopify order ID (numeric string or GID)",
    )
    order_name = Column(
        String(255),
        nullable=True,
        comment="Shopify order name (e.g., #1001)",
    )
    order_number = Column(
        String(50),
        nullable=True,
        comment="Shopify order number",
    )
    total_price = Column(
        Numeric(12, 2),
        nullable=True,
        comment="Total order price including tax",
    )
    subtotal_price = Column(
        Numeric(12, 2),
        nullable=True,
        comment="Subtotal before tax",
    )
    currency = Column(
        String(10),
        nullable=True,
        comment="Order currency code",
    )
    financial_status = Column(
        String(50),
        nullable=True,
        comment="Financial status (paid, pending, refunded, etc.)",
    )
    fulfillment_status = Column(
        String(50),
        nullable=True,
        comment="Fulfillment status (fulfilled, unfulfilled, etc.)",
    )

    # UTM attribution fields extracted from note_attributes
    utm_source = Column(String(255), nullable=True)
    utm_medium = Column(String(255), nullable=True)
    utm_campaign = Column(String(500), nullable=True)
    utm_term = Column(String(500), nullable=True)
    utm_content = Column(String(500), nullable=True)

    # Raw data
    note_attributes_json = Column(
        JSONB,
        nullable=True,
        comment="Raw note_attributes array from Shopify order",
    )
    raw_payload = Column(
        JSONB,
        nullable=True,
        comment="Full webhook payload for debugging/reprocessing",
    )

    # Event metadata
    event_type = Column(
        String(20),
        nullable=False,
        comment="Webhook event type: created or updated",
    )
    order_created_at = Column(
        DateTime(timezone=True),
        nullable=True,
        comment="When the order was created in Shopify",
    )
    received_at = Column(
        DateTime(timezone=True),
        nullable=False,
        comment="When the webhook was received",
    )

    __table_args__ = (
        Index("ix_webhook_order_events_tenant_order", "tenant_id", "shopify_order_id"),
        Index("ix_webhook_order_events_tenant_received", "tenant_id", "received_at"),
    )

    def __repr__(self) -> str:
        return (
            f"<WebhookOrderEvent(id={self.id}, order={self.order_name}, "
            f"event_type={self.event_type})>"
        )
