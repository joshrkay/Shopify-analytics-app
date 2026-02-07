"""
Pydantic schemas for Explore guardrail bypass API (Story 5.4).
"""

from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, Field, field_validator


class CreateGuardrailBypassRequest(BaseModel):
    """Request to create a guardrail bypass (pending approval)."""
    user_id: str = Field(..., description="Target user ID (internal UUID)")
    dataset_names: List[str] = Field(..., min_length=1, description="Datasets covered")
    reason: str = Field(..., min_length=10, description="Reason for bypass request")
    requested_duration_minutes: int = Field(
        60,
        ge=1,
        le=60,
        description="Requested duration in minutes (max 60)",
    )

    @field_validator("dataset_names")
    @classmethod
    def _validate_dataset_names(cls, value: List[str]) -> List[str]:
        cleaned = [name.strip() for name in value if name and name.strip()]
        if not cleaned:
            raise ValueError("dataset_names must include at least one dataset")
        return cleaned


class ApproveGuardrailBypassRequest(BaseModel):
    """Request to approve a pending bypass."""
    duration_minutes: int = Field(
        ...,
        ge=1,
        le=60,
        description="Approved duration in minutes (max 60)",
    )


class GuardrailBypassResponse(BaseModel):
    """Response representing a guardrail bypass exception."""
    id: str
    user_id: str
    approved_by: Optional[str]
    dataset_names: List[str]
    expires_at: Optional[str]
    reason: str
    created_at: datetime


class GuardrailBypassListResponse(BaseModel):
    """List response for active bypasses."""
    exceptions: List[GuardrailBypassResponse]
    total: int


class GuardrailBypassRequestCreatedResponse(BaseModel):
    """Response for a created bypass request."""
    exception: GuardrailBypassResponse
    created: bool
    message: str
