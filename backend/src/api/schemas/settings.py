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


class BrandingSettings(BaseModel):
    brand_name: str | None = Field(default=None, max_length=255)
    logo_url: str | None = Field(default=None, max_length=2048)
    accent_color: str | None = Field(default=None, max_length=7)
    email_footer_text: str | None = Field(default=None, max_length=500)

    @field_validator("logo_url")
    @classmethod
    def validate_logo_url(cls, value: str | None) -> str | None:
        if value is None or value == "":
            return None
        if not value.startswith("https://"):
            raise ValueError("Logo URL must use HTTPS")
        return value

    @field_validator("accent_color")
    @classmethod
    def validate_accent_color(cls, value: str | None) -> str | None:
        if value is None or value == "":
            return None
        import re
        if not re.match(r'^#[0-9a-fA-F]{6}$', value):
            raise ValueError("Accent color must be a valid hex color (e.g. #4CAF50)")
        return value


class BrandingSettingsResponse(BaseModel):
    brand_name: str
    logo_url: str | None = None
    accent_color: str
    email_footer_text: str | None = None


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
