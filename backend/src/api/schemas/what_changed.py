"""
What Changed API schemas for Story 9.8.

Pydantic models for the "What Changed?" debug panel.

SECURITY:
- Read-only endpoints only
- No raw logs, credentials, or sensitive data
- All data is merchant-safe aggregated summaries
"""

from datetime import datetime
from typing import Optional, List

from pydantic import BaseModel, Field


class DataChangeEventResponse(BaseModel):
    """Single data change event for display."""

    id: str
    event_type: str
    title: str
    description: str
    affected_metrics: List[str] = Field(default_factory=list)
    affected_connector_name: Optional[str] = None
    impact_summary: Optional[str] = None
    affected_date_start: Optional[datetime] = None
    affected_date_end: Optional[datetime] = None
    occurred_at: datetime


class ChangeEventsListResponse(BaseModel):
    """Response for change events list queries."""

    events: List[DataChangeEventResponse]
    total: int
    has_more: bool


class ConnectorFreshnessStatus(BaseModel):
    """Freshness status for a single connector."""

    connector_id: str
    connector_name: str
    status: str  # "fresh", "stale", "critical", "error"
    last_sync_at: Optional[datetime] = None
    minutes_since_sync: Optional[int] = None
    source_type: Optional[str] = None


class FreshnessStatusResponse(BaseModel):
    """Overall data freshness status."""

    overall_status: str  # "fresh", "stale", "critical"
    last_sync_at: Optional[datetime] = None
    hours_since_sync: Optional[int] = None
    connectors: List[ConnectorFreshnessStatus] = Field(default_factory=list)


class RecentSyncResponse(BaseModel):
    """Recent sync information."""

    sync_id: str
    connector_id: str
    connector_name: str
    source_type: Optional[str] = None
    status: str  # "success", "failed", "running"
    started_at: datetime
    completed_at: Optional[datetime] = None
    rows_synced: Optional[int] = None
    duration_seconds: Optional[float] = None
    error_message: Optional[str] = None  # Sanitized, no sensitive data


class RecentSyncsListResponse(BaseModel):
    """Response for recent syncs query."""

    syncs: List[RecentSyncResponse]
    total: int


class AIActionSummaryResponse(BaseModel):
    """Summary of an AI action taken."""

    action_id: str
    action_type: str
    status: str  # "approved", "rejected", "executed", "pending"
    target_name: str  # Sanitized target description
    target_platform: Optional[str] = None
    performed_at: datetime
    performed_by: Optional[str] = None  # "Admin user" or similar, not email


class AIActionsListResponse(BaseModel):
    """Response for AI actions query."""

    actions: List[AIActionSummaryResponse]
    total: int


class ConnectorStatusChangeResponse(BaseModel):
    """Connector status change information."""

    connector_id: str
    connector_name: str
    previous_status: str
    new_status: str
    changed_at: datetime
    reason: Optional[str] = None  # Sanitized reason


class ConnectorStatusChangesResponse(BaseModel):
    """Response for connector status changes query."""

    changes: List[ConnectorStatusChangeResponse]
    total: int


class WhatChangedSummaryResponse(BaseModel):
    """
    Summary for the debug panel header.

    Provides at-a-glance overview of recent changes.
    """

    data_freshness: FreshnessStatusResponse
    recent_syncs_count: int
    recent_ai_actions_count: int
    open_incidents_count: int
    metric_changes_count: int
    last_updated: datetime


class MetricVersionChangeResponse(BaseModel):
    """Information about a metric version change."""

    metric_name: str
    previous_version: Optional[str] = None
    new_version: str
    change_description: str
    changed_at: datetime
    affected_date_range_start: Optional[datetime] = None
    affected_date_range_end: Optional[datetime] = None


class MetricChangesListResponse(BaseModel):
    """Response for metric version changes query."""

    changes: List[MetricVersionChangeResponse]
    total: int
