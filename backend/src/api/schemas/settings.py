"""Pydantic schemas for settings API endpoints."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator


class ApiKeySummary(BaseModel):
    id: str
    name: str
    key_prefix: str
    created_at: datetime
    last_used_at: datetime | None = None
    expires_at: datetime | None = None
    revoked_at: datetime | None = None
    is_active: bool


class ApiKeyListResponse(BaseModel):
    keys: list[ApiKeySummary]


class ApiKeyCreateRequest(BaseModel):
    name: str = Field(..., min_length=3, max_length=120)
    expires_in_days: int | None = Field(default=None, ge=1, le=365)

    @field_validator("name")
    @classmethod
    def normalize_name(cls, value: str) -> str:
        normalized = value.strip()
        if len(normalized) < 3:
            raise ValueError("name must be at least 3 non-space characters")
        return normalized


class ApiKeyCreateResponse(BaseModel):
    key: ApiKeySummary
    plaintext_key: str


class AiInsightsSettings(BaseModel):
    enabled: bool = True
    model: Literal["gpt-4.1-mini", "gpt-4.1", "gpt-5-mini"] = "gpt-4.1-mini"
    cadence: Literal["daily", "weekly"] = "weekly"
    include_recommendations: bool = True
    max_insights_per_run: int = Field(default=5, ge=1, le=20)


class AiInsightsSettingsResponse(BaseModel):
    settings: AiInsightsSettings
    entitled: bool
    entitlement_reason: str | None = None
