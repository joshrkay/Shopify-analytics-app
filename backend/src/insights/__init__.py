"""
AI Insights module for scheduled insight generation.

This module provides:
- Insight detection from aggregated dbt marts
- Natural language summary generation
- Tenant-scoped insight storage

CONSTRAINTS:
- Read-only: No actions executed
- Governed: Only uses pre-aggregated dbt marts (no raw rows, no PII)
- Tenant-isolated: Strict tenant_id scoping
- Scheduled: Daily or hourly cadence only
"""

from src.insights.models import (
    AIInsight,
    AIInsightGenerationLog,
)

__all__ = [
    "AIInsight",
    "AIInsightGenerationLog",
]
