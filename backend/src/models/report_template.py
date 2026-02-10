"""
Report Template model.

System-defined templates that can be instantiated into user dashboards.
Templates use abstract chart types that are mapped to current Superset
viz_type plugins at instantiation time.

Phase 2C - Template System Backend
"""

import enum

from sqlalchemy import (
    Column, String, Text, Boolean, Integer, Enum, Index,
)

from src.db_base import Base
from src.models.base import TimestampMixin, generate_uuid

try:
    from sqlalchemy.types import JSON as JSONType
except ImportError:
    from sqlalchemy import Text as JSONType


class TemplateCategory(str, enum.Enum):
    """Categories for organizing templates in the gallery."""

    REVENUE = "revenue"
    MARKETING = "marketing"
    PRODUCT = "product"
    CUSTOMER = "customer"
    OPERATIONS = "operations"


class ReportTemplate(Base, TimestampMixin):
    """
    System-defined report template.

    Templates are admin-managed and can be instantiated into user dashboards.
    Uses abstract chart types (line, bar, etc.) that the instantiation
    service maps to current Superset viz_type plugins.

    is_active=False hides from gallery but does not affect existing
    dashboards created from this template.
    """

    __tablename__ = "report_templates"

    id = Column(String(255), primary_key=True, default=generate_uuid)
    name = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    category = Column(
        Enum(TemplateCategory),
        nullable=False,
        index=True,
        comment="Template category for gallery organization",
    )
    thumbnail_url = Column(String(500), nullable=True)
    min_billing_tier = Column(
        String(50),
        nullable=False,
        default="free",
        comment="Minimum billing tier required to use this template",
    )
    is_active = Column(
        Boolean,
        nullable=False,
        default=True,
        index=True,
        comment="False hides from gallery; existing instantiations unaffected",
    )
    config_json = Column(
        JSONType,
        nullable=False,
        comment="Template config with abstract chart types and report definitions",
    )
    version = Column(
        Integer,
        nullable=False,
        default=1,
        comment="Template version for forward compatibility",
    )

    __table_args__ = (
        Index("ix_report_template_active_category", "is_active", "category"),
    )
