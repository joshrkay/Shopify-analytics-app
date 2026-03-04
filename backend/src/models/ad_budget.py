"""
Ad Budget model for budget pacing tracking.

Stores monthly ad spend budgets per platform per tenant.
Used by the Budget Pacing page to show spend vs budget progress.

SECURITY: Tenant isolation via TenantScopedMixin + RLS policy.
"""

import uuid

from sqlalchemy import Column, String, BigInteger, Date, Boolean, Index

from src.db_base import Base
from src.models.base import TimestampMixin, TenantScopedMixin


class AdBudget(Base, TimestampMixin, TenantScopedMixin):
    """Monthly ad spend budget per platform."""

    __tablename__ = "ad_budgets"

    id = Column(
        String(255),
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
    )

    source_platform = Column(String(100), nullable=False, index=True)
    budget_monthly_cents = Column(BigInteger, nullable=False)
    start_date = Column(Date, nullable=False)
    end_date = Column(Date, nullable=True)
    enabled = Column(Boolean, nullable=False, default=True)

    __table_args__ = (
        Index("ix_ad_budget_tenant_platform", "tenant_id", "source_platform"),
    )

    def __repr__(self) -> str:
        return (
            f"<AdBudget(id={self.id}, platform={self.source_platform}, "
            f"budget=${self.budget_monthly_cents / 100:.2f})>"
        )
