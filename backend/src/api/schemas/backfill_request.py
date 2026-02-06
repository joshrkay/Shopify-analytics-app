"""
Pydantic schemas for Admin Backfill Request API.

Story 3.4 - Backfill Request API
"""

from datetime import date, datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator


class SourceSystem(str, Enum):
    """Supported source systems for backfill."""
    SHOPIFY = "shopify"
    FACEBOOK = "facebook"
    GOOGLE = "google"
    TIKTOK = "tiktok"
    PINTEREST = "pinterest"
    SNAPCHAT = "snapchat"
    AMAZON = "amazon"
    KLAVIYO = "klaviyo"
    RECHARGE = "recharge"
    GA4 = "ga4"


class CreateBackfillRequest(BaseModel):
    """Request body for POST /api/v1/admin/backfills."""
    tenant_id: str = Field(
        ...,
        description="Target tenant ID for the backfill",
        min_length=1,
        max_length=255,
        examples=["tenant_abc123"],
    )
    source_system: SourceSystem = Field(
        ...,
        description="Source system to backfill data from",
        examples=["shopify"],
    )
    start_date: date = Field(
        ...,
        description="Start date for backfill (YYYY-MM-DD)",
        examples=["2024-01-01"],
    )
    end_date: date = Field(
        ...,
        description="End date for backfill (YYYY-MM-DD)",
        examples=["2024-03-31"],
    )
    reason: str = Field(
        ...,
        description="Human-readable reason for the backfill request",
        min_length=10,
        max_length=500,
        examples=["Data gap detected after connector migration on 2024-01-15"],
    )

    @model_validator(mode="after")
    def validate_dates(self):
        if self.start_date > self.end_date:
            raise ValueError(
                f"start_date ({self.start_date}) must be before or equal to end_date ({self.end_date})"
            )
        if self.end_date > date.today():
            raise ValueError("end_date cannot be in the future")
        return self


class BackfillRequestResponse(BaseModel):
    """Response model for a backfill request."""
    id: str
    tenant_id: str
    source_system: str
    start_date: str
    end_date: str
    status: str
    reason: str
    requested_by: str
    idempotency_key: str
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


class BackfillRequestCreatedResponse(BaseModel):
    """Response when a backfill request is created or returned (idempotent)."""
    backfill_request: BackfillRequestResponse
    created: bool = Field(
        ..., description="True if newly created, False if existing returned"
    )
    message: str
