"""
Audit API schemas for Story 8.7.

Pydantic models for audit log queries and responses.
"""

from datetime import datetime
from typing import Optional, Any

from pydantic import BaseModel, Field


class AuditLogEntry(BaseModel):
    """Single audit log entry."""

    id: str
    tenant_id: str
    user_id: str
    action: str
    timestamp: datetime
    ip_address: Optional[str] = None
    user_agent: Optional[str] = None
    resource_type: Optional[str] = None
    resource_id: Optional[str] = None
    event_metadata: dict[str, Any] = Field(default_factory=dict)
    correlation_id: Optional[str] = None


class AuditLogsResponse(BaseModel):
    """Response for audit log queries."""

    logs: list[AuditLogEntry]
    total: int
    has_more: bool


class AuditSummaryResponse(BaseModel):
    """Summary statistics for audit logs."""

    total_events: int
    by_action: dict[str, int]
    by_severity: dict[str, int]
    by_resource_type: dict[str, int]


class SafetyEventEntry(BaseModel):
    """Single safety event entry."""

    id: str
    tenant_id: str
    event_type: str
    operation_type: str
    entity_id: Optional[str] = None
    action_id: Optional[str] = None
    reason: str
    metadata: dict[str, Any] = Field(default_factory=dict)
    correlation_id: Optional[str] = None
    created_at: datetime


class SafetyEventsResponse(BaseModel):
    """Response for safety event queries."""

    events: list[SafetyEventEntry]
    total: int
    has_more: bool


class SafetyStatusResponse(BaseModel):
    """Current safety system status."""

    rate_limit_status: dict[str, Any]
    active_cooldowns: int
    kill_switch_active: bool
    recent_blocked_count: int
