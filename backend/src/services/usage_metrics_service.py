"""Usage metrics aggregation for billing endpoints."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from src.ingestion.jobs.models import IngestionJob, JobStatus
from src.models.llm_routing import LLMUsageLog
from src.models.subscription import Subscription


_BYTES_PER_GB = 1024 * 1024 * 1024


@dataclass(frozen=True)
class BillingPeriod:
    """Billing period boundaries used for usage aggregation."""

    start: datetime
    end: datetime


@dataclass(frozen=True)
class UsageMetrics:
    """Aggregated usage values for the current billing period."""

    storage_used_gb: float
    ai_requests_used: int


class UsageMetricsService:
    """Compute tenant usage metrics from authoritative pipeline sources."""

    def __init__(self, db_session: Session, tenant_id: str):
        self.db = db_session
        self.tenant_id = tenant_id

    def get_current_billing_period(self) -> BillingPeriod:
        """
        Resolve billing period from subscription metadata.

        Fallback is current UTC calendar month when no subscription period exists.
        """
        subscription = (
            self.db.query(Subscription)
            .filter(Subscription.tenant_id == self.tenant_id)
            .order_by(Subscription.created_at.desc())
            .first()
        )

        if subscription and subscription.current_period_start and subscription.current_period_end:
            return BillingPeriod(
                start=subscription.current_period_start,
                end=subscription.current_period_end,
            )

        now = datetime.now(timezone.utc)
        month_start = datetime(now.year, now.month, 1, tzinfo=timezone.utc)
        if now.month == 12:
            next_month_start = datetime(now.year + 1, 1, 1, tzinfo=timezone.utc)
        else:
            next_month_start = datetime(now.year, now.month + 1, 1, tzinfo=timezone.utc)

        return BillingPeriod(start=month_start, end=next_month_start)

    def get_usage_for_period(self, period: BillingPeriod) -> UsageMetrics:
        """
        Aggregate usage for a tenant within a billing period.

        Authoritative sources:
        - Storage: successful ingestion jobs (job_metadata.bytes_synced)
        - AI requests: LLM usage log rows
        """
        ingestion_jobs = (
            self.db.query(IngestionJob)
            .filter(
                IngestionJob.tenant_id == self.tenant_id,
                IngestionJob.status == JobStatus.SUCCESS,
                IngestionJob.completed_at.isnot(None),
                IngestionJob.completed_at >= period.start,
                IngestionJob.completed_at < period.end,
            )
            .all()
        )

        total_bytes = 0
        for job in ingestion_jobs:
            metadata = job.job_metadata or {}
            if isinstance(metadata, dict):
                raw_bytes = metadata.get("bytes_synced", 0)
                try:
                    total_bytes += max(0, int(raw_bytes or 0))
                except (TypeError, ValueError):
                    continue

        ai_requests_used = (
            self.db.query(LLMUsageLog)
            .filter(
                LLMUsageLog.tenant_id == self.tenant_id,
                LLMUsageLog.created_at >= period.start,
                LLMUsageLog.created_at < period.end,
            )
            .count()
        )

        return UsageMetrics(
            storage_used_gb=round(total_bytes / _BYTES_PER_GB, 4),
            ai_requests_used=ai_requests_used,
        )
