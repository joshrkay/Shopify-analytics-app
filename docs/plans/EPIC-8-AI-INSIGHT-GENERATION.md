# EPIC 8 — AI Insight Generation Implementation Plan

## Story 8.1 — AI Insight Generation (Read-Only Analytics)

**Status**: Planning
**Author**: Claude AI Engineer
**Created**: 2026-01-28
**Branch**: `claude/ai-insight-generation-N3p6j`

---

## Table of Contents

1. [Executive Summary](#1-executive-summary)
2. [Architecture Overview](#2-architecture-overview)
3. [Database Schema](#3-database-schema)
4. [Insight Detection Engine](#4-insight-detection-engine)
5. [Service Layer](#5-service-layer)
6. [Scheduled Job Implementation](#6-scheduled-job-implementation)
7. [Natural Language Generation](#7-natural-language-generation)
8. [Configuration & Thresholds](#8-configuration--thresholds)
9. [Testing Strategy](#9-testing-strategy)
10. [Implementation Phases](#10-implementation-phases)
11. [Security & Compliance](#11-security--compliance)
12. [File Structure](#12-file-structure)

---

## 1. Executive Summary

### Objective
Build a scheduled AI insight generation service that analyzes aggregated dbt marts to produce actionable, natural language insights about performance trends, anomalies, and opportunities.

### Key Principles
- **Read-only**: No actions executed, no external API calls
- **Governed**: Only uses pre-aggregated dbt marts (no raw rows, no PII)
- **Tenant-isolated**: Strict tenant_id scoping on all queries and outputs
- **Deterministic**: Same inputs produce same outputs (for testability)
- **Scheduled**: Daily (default) or hourly (enterprise) cadence

### Input Sources (dbt Marts)
| Mart | Schema | Purpose |
|------|--------|---------|
| `fact_orders` | `analytics` | Revenue, order counts, AOV |
| `fact_ad_spend` | `analytics` | Marketing spend by channel/campaign |
| `fact_campaign_performance` | `analytics` | Campaign metrics (ROAS, CTR, CPA) |

### Output
Structured insights stored in `ai_insights` table with natural language summaries.

---

## 2. Architecture Overview

### System Flow

```
┌─────────────────────────────────────────────────────────────────────────┐
│                        SCHEDULED JOB (Cron)                             │
│                    Daily: 6 AM UTC | Hourly: Enterprise                 │
└─────────────────────────────────┬───────────────────────────────────────┘
                                  │
                                  ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                     INSIGHT ORCHESTRATOR SERVICE                         │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐    │
│  │   Tenant    │  │   Metric    │  │  Insight    │  │   Output    │    │
│  │  Iterator   │──▶  Fetcher   │──▶  Detector   │──▶  Formatter  │    │
│  └─────────────┘  └─────────────┘  └─────────────┘  └─────────────┘    │
└─────────────────────────────────┬───────────────────────────────────────┘
                                  │
        ┌─────────────────────────┼─────────────────────────┐
        │                         │                         │
        ▼                         ▼                         ▼
┌───────────────┐       ┌───────────────┐       ┌───────────────┐
│  fact_orders  │       │ fact_ad_spend │       │ fact_campaign │
│    (mart)     │       │    (mart)     │       │  _performance │
└───────────────┘       └───────────────┘       └───────────────┘
        │                         │                         │
        └─────────────────────────┼─────────────────────────┘
                                  │
                                  ▼
                    ┌───────────────────────┐
                    │     ai_insights       │
                    │   (tenant-scoped)     │
                    └───────────────────────┘
```

### Component Responsibilities

| Component | Responsibility |
|-----------|----------------|
| **Insight Orchestrator** | Coordinates the full insight generation pipeline |
| **Tenant Iterator** | Fetches eligible tenants based on entitlements |
| **Metric Fetcher** | Queries aggregated metrics from dbt marts |
| **Insight Detector** | Applies statistical analysis and threshold rules |
| **Output Formatter** | Generates natural language summaries |
| **Insight Repository** | Persists insights with tenant isolation |

---

## 3. Database Schema

### 3.1 Migration: `ai_insights` Table

**File**: `db/migrations/ai_insights_schema.sql`

```sql
-- AI Insights Schema
-- Stores scheduled, read-only AI-generated insights

CREATE TABLE IF NOT EXISTS ai_insights (
    -- Primary Key
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    -- Tenant Isolation (REQUIRED)
    tenant_id UUID NOT NULL,

    -- Insight Identity
    insight_type VARCHAR(50) NOT NULL,
    insight_category VARCHAR(50) NOT NULL,

    -- Content
    summary TEXT NOT NULL,
    supporting_metrics JSONB NOT NULL DEFAULT '[]',

    -- Scoring
    confidence_score DECIMAL(3,2) NOT NULL CHECK (confidence_score >= 0 AND confidence_score <= 1),
    severity VARCHAR(20) NOT NULL DEFAULT 'info',

    -- Temporal Context
    analysis_period_start DATE NOT NULL,
    analysis_period_end DATE NOT NULL,
    comparison_period_start DATE,
    comparison_period_end DATE,

    -- Metadata
    generated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    generation_cadence VARCHAR(20) NOT NULL DEFAULT 'daily',
    model_version VARCHAR(20) NOT NULL DEFAULT 'v1.0',

    -- Status
    status VARCHAR(20) NOT NULL DEFAULT 'active',
    dismissed_at TIMESTAMP WITH TIME ZONE,
    dismissed_by UUID,

    -- Audit
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),

    -- Constraints
    CONSTRAINT valid_severity CHECK (severity IN ('info', 'warning', 'critical')),
    CONSTRAINT valid_status CHECK (status IN ('active', 'dismissed', 'expired')),
    CONSTRAINT valid_cadence CHECK (generation_cadence IN ('daily', 'hourly')),
    CONSTRAINT valid_insight_type CHECK (insight_type IN (
        'spend_anomaly',
        'roas_change',
        'revenue_spend_divergence',
        'channel_mix_shift',
        'aov_change',
        'conversion_rate_change',
        'cpa_anomaly'
    )),
    CONSTRAINT valid_category CHECK (insight_category IN (
        'anomaly',
        'trend',
        'opportunity',
        'risk'
    ))
);

-- Indexes for efficient querying
CREATE INDEX idx_ai_insights_tenant_id ON ai_insights(tenant_id);
CREATE INDEX idx_ai_insights_tenant_generated ON ai_insights(tenant_id, generated_at DESC);
CREATE INDEX idx_ai_insights_tenant_type ON ai_insights(tenant_id, insight_type);
CREATE INDEX idx_ai_insights_tenant_status ON ai_insights(tenant_id, status) WHERE status = 'active';
CREATE INDEX idx_ai_insights_cadence ON ai_insights(generation_cadence);

-- Row Level Security
ALTER TABLE ai_insights ENABLE ROW LEVEL SECURITY;

CREATE POLICY ai_insights_tenant_isolation ON ai_insights
    FOR ALL
    USING (tenant_id = current_setting('app.current_tenant_id')::uuid);

-- Comments
COMMENT ON TABLE ai_insights IS 'Scheduled AI-generated insights based on aggregated analytics marts';
COMMENT ON COLUMN ai_insights.tenant_id IS 'Tenant identifier for strict isolation';
COMMENT ON COLUMN ai_insights.insight_type IS 'Type of insight detected (spend_anomaly, roas_change, etc.)';
COMMENT ON COLUMN ai_insights.supporting_metrics IS 'JSON array of metrics supporting this insight';
COMMENT ON COLUMN ai_insights.confidence_score IS 'Statistical confidence in the insight (0-1)';
```

### 3.2 Supporting Metrics JSONB Structure

```json
{
  "supporting_metrics": [
    {
      "metric_name": "total_spend",
      "current_value": 15000.00,
      "previous_value": 10000.00,
      "delta_absolute": 5000.00,
      "delta_percent": 50.0,
      "timeframe": "WoW",
      "unit": "USD"
    },
    {
      "metric_name": "roas",
      "current_value": 2.8,
      "previous_value": 3.5,
      "delta_absolute": -0.7,
      "delta_percent": -20.0,
      "timeframe": "WoW",
      "unit": "ratio"
    }
  ]
}
```

### 3.3 Insight Generation Log Table

```sql
-- Tracks each insight generation run for debugging and monitoring
CREATE TABLE IF NOT EXISTS ai_insight_generation_logs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL,
    run_id UUID NOT NULL,
    cadence VARCHAR(20) NOT NULL,
    started_at TIMESTAMP WITH TIME ZONE NOT NULL,
    completed_at TIMESTAMP WITH TIME ZONE,
    status VARCHAR(20) NOT NULL DEFAULT 'running',
    insights_generated INTEGER DEFAULT 0,
    error_message TEXT,
    metrics_analyzed JSONB DEFAULT '{}',
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),

    CONSTRAINT valid_log_status CHECK (status IN ('running', 'completed', 'failed'))
);

CREATE INDEX idx_insight_logs_tenant ON ai_insight_generation_logs(tenant_id);
CREATE INDEX idx_insight_logs_run ON ai_insight_generation_logs(run_id);
```

---

## 4. Insight Detection Engine

### 4.1 Insight Types & Detection Logic

#### 4.1.1 Spend Anomaly Detection

**Definition**: Detect statistically significant changes in marketing spend.

```python
# backend/src/insights/detectors/spend_anomaly.py

@dataclass
class SpendAnomalyDetector(InsightDetector):
    """
    Detects anomalies in marketing spend patterns.

    Triggers:
    - Spend increased/decreased > threshold (default ±15%) WoW
    - Spend outside 2 standard deviations of 4-week rolling average
    """

    insight_type = InsightType.SPEND_ANOMALY

    def detect(self, metrics: TenantMetrics) -> list[InsightCandidate]:
        insights = []

        # Week-over-Week comparison
        wow_delta = self._calculate_wow_delta(
            current=metrics.current_week_spend,
            previous=metrics.previous_week_spend
        )

        if abs(wow_delta.percent) >= self.config.spend_threshold_percent:
            confidence = self._calculate_confidence(
                delta_percent=wow_delta.percent,
                sample_size=metrics.days_with_data,
                std_dev=metrics.spend_std_dev
            )

            insights.append(InsightCandidate(
                insight_type=self.insight_type,
                category=InsightCategory.ANOMALY,
                severity=self._determine_severity(wow_delta.percent),
                confidence_score=confidence,
                metrics=[
                    MetricDelta(
                        metric_name="total_spend",
                        current_value=metrics.current_week_spend,
                        previous_value=metrics.previous_week_spend,
                        delta_absolute=wow_delta.absolute,
                        delta_percent=wow_delta.percent,
                        timeframe="WoW",
                        unit="USD"
                    )
                ]
            ))

        return insights
```

#### 4.1.2 ROAS Change Detection

**Definition**: Detect meaningful changes in Return on Ad Spend.

```python
# backend/src/insights/detectors/roas_change.py

@dataclass
class ROASChangeDetector(InsightDetector):
    """
    Detects significant changes in ROAS (Return on Ad Spend).

    Triggers:
    - ROAS changed > threshold (default ±10%) WoW
    - ROAS dropped below profitability threshold (configurable, default 1.5)
    """

    insight_type = InsightType.ROAS_CHANGE

    def detect(self, metrics: TenantMetrics) -> list[InsightCandidate]:
        insights = []

        current_roas = self._safe_divide(
            metrics.current_week_revenue,
            metrics.current_week_spend
        )
        previous_roas = self._safe_divide(
            metrics.previous_week_revenue,
            metrics.previous_week_spend
        )

        if previous_roas > 0:
            roas_delta_percent = ((current_roas - previous_roas) / previous_roas) * 100

            if abs(roas_delta_percent) >= self.config.roas_threshold_percent:
                # Determine category based on direction
                category = (
                    InsightCategory.RISK if roas_delta_percent < 0
                    else InsightCategory.OPPORTUNITY
                )

                insights.append(InsightCandidate(
                    insight_type=self.insight_type,
                    category=category,
                    severity=self._determine_severity(roas_delta_percent, current_roas),
                    confidence_score=self._calculate_confidence(metrics),
                    metrics=[
                        MetricDelta(
                            metric_name="roas",
                            current_value=round(current_roas, 2),
                            previous_value=round(previous_roas, 2),
                            delta_absolute=round(current_roas - previous_roas, 2),
                            delta_percent=round(roas_delta_percent, 1),
                            timeframe="WoW",
                            unit="ratio"
                        )
                    ]
                ))

        return insights
```

#### 4.1.3 Revenue vs Spend Divergence

**Definition**: Detect when revenue and spend trends diverge.

```python
# backend/src/insights/detectors/revenue_spend_divergence.py

@dataclass
class RevenueSpendDivergenceDetector(InsightDetector):
    """
    Detects divergence between revenue and spend trends.

    Triggers:
    - Spend increased but revenue decreased (inefficiency)
    - Revenue increased but spend decreased (efficiency gain)
    - Divergence > threshold (default 20% difference in direction)
    """

    insight_type = InsightType.REVENUE_SPEND_DIVERGENCE

    def detect(self, metrics: TenantMetrics) -> list[InsightCandidate]:
        insights = []

        spend_delta = self._calculate_delta(
            metrics.current_week_spend,
            metrics.previous_week_spend
        )
        revenue_delta = self._calculate_delta(
            metrics.current_week_revenue,
            metrics.previous_week_revenue
        )

        # Check for divergence (opposite directions or significant magnitude difference)
        is_divergent = (
            (spend_delta.percent > 0 and revenue_delta.percent < 0) or
            (spend_delta.percent < 0 and revenue_delta.percent > 0)
        )

        divergence_magnitude = abs(spend_delta.percent - revenue_delta.percent)

        if is_divergent and divergence_magnitude >= self.config.divergence_threshold_percent:
            # Negative divergence: spending more, earning less
            is_negative = spend_delta.percent > 0 and revenue_delta.percent < 0

            insights.append(InsightCandidate(
                insight_type=self.insight_type,
                category=InsightCategory.RISK if is_negative else InsightCategory.OPPORTUNITY,
                severity="warning" if is_negative else "info",
                confidence_score=self._calculate_confidence(metrics, divergence_magnitude),
                metrics=[
                    MetricDelta(
                        metric_name="total_spend",
                        current_value=metrics.current_week_spend,
                        previous_value=metrics.previous_week_spend,
                        delta_percent=spend_delta.percent,
                        timeframe="WoW",
                        unit="USD"
                    ),
                    MetricDelta(
                        metric_name="total_revenue",
                        current_value=metrics.current_week_revenue,
                        previous_value=metrics.previous_week_revenue,
                        delta_percent=revenue_delta.percent,
                        timeframe="WoW",
                        unit="USD"
                    )
                ]
            ))

        return insights
```

#### 4.1.4 Channel Mix Shift Detection

**Definition**: Detect significant shifts in marketing channel allocation.

```python
# backend/src/insights/detectors/channel_mix_shift.py

@dataclass
class ChannelMixShiftDetector(InsightDetector):
    """
    Detects significant shifts in marketing channel mix.

    Triggers:
    - Channel share changed > threshold (default ±10 percentage points)
    - New channel emerged (>5% share from 0%)
    - Channel dropped off (<2% from >10%)
    """

    insight_type = InsightType.CHANNEL_MIX_SHIFT

    def detect(self, metrics: TenantMetrics) -> list[InsightCandidate]:
        insights = []

        current_mix = self._calculate_channel_mix(metrics.current_week_channel_spend)
        previous_mix = self._calculate_channel_mix(metrics.previous_week_channel_spend)

        for channel, current_share in current_mix.items():
            previous_share = previous_mix.get(channel, 0.0)
            share_delta = current_share - previous_share

            if abs(share_delta) >= self.config.channel_shift_threshold_pp:
                insights.append(InsightCandidate(
                    insight_type=self.insight_type,
                    category=InsightCategory.TREND,
                    severity="info",
                    confidence_score=self._calculate_confidence(
                        current_share, previous_share, metrics.total_spend
                    ),
                    metrics=[
                        MetricDelta(
                            metric_name=f"{channel}_share",
                            current_value=round(current_share * 100, 1),
                            previous_value=round(previous_share * 100, 1),
                            delta_absolute=round(share_delta * 100, 1),
                            delta_percent=None,  # PP change, not percent
                            timeframe="WoW",
                            unit="percentage_points"
                        )
                    ],
                    context={"channel": channel}
                ))

        return insights
```

### 4.2 Statistical Confidence Calculation

```python
# backend/src/insights/stats/confidence.py

class ConfidenceCalculator:
    """
    Calculates statistical confidence for insights.

    Factors:
    - Sample size (days with data)
    - Variance in the metric
    - Magnitude of change relative to historical volatility
    - Data completeness
    """

    @staticmethod
    def calculate(
        delta_percent: float,
        sample_size: int,
        historical_std_dev: float,
        data_completeness: float = 1.0
    ) -> float:
        """
        Returns confidence score between 0 and 1.

        Higher confidence when:
        - Larger sample size
        - Lower historical volatility
        - Change exceeds historical variance
        - Data is complete
        """
        # Base confidence from sample size (7 days = 0.7 base)
        sample_confidence = min(sample_size / 10, 1.0) * 0.4

        # Volatility-adjusted confidence
        if historical_std_dev > 0:
            z_score = abs(delta_percent) / historical_std_dev
            volatility_confidence = min(z_score / 3, 1.0) * 0.4
        else:
            volatility_confidence = 0.3  # Default if no variance data

        # Data completeness factor
        completeness_confidence = data_completeness * 0.2

        total_confidence = (
            sample_confidence +
            volatility_confidence +
            completeness_confidence
        )

        return round(min(max(total_confidence, 0.0), 1.0), 2)
```

### 4.3 Detector Registry

```python
# backend/src/insights/detectors/registry.py

from enum import Enum
from typing import Type

class InsightType(str, Enum):
    SPEND_ANOMALY = "spend_anomaly"
    ROAS_CHANGE = "roas_change"
    REVENUE_SPEND_DIVERGENCE = "revenue_spend_divergence"
    CHANNEL_MIX_SHIFT = "channel_mix_shift"
    AOV_CHANGE = "aov_change"
    CONVERSION_RATE_CHANGE = "conversion_rate_change"
    CPA_ANOMALY = "cpa_anomaly"

class InsightCategory(str, Enum):
    ANOMALY = "anomaly"
    TREND = "trend"
    OPPORTUNITY = "opportunity"
    RISK = "risk"

class DetectorRegistry:
    """Registry of all insight detectors."""

    _detectors: dict[InsightType, Type[InsightDetector]] = {}

    @classmethod
    def register(cls, insight_type: InsightType):
        """Decorator to register a detector."""
        def decorator(detector_cls: Type[InsightDetector]):
            cls._detectors[insight_type] = detector_cls
            return detector_cls
        return decorator

    @classmethod
    def get_all_detectors(cls, config: InsightConfig) -> list[InsightDetector]:
        """Returns instantiated detectors for all registered types."""
        return [
            detector_cls(config)
            for detector_cls in cls._detectors.values()
        ]

    @classmethod
    def get_detector(
        cls,
        insight_type: InsightType,
        config: InsightConfig
    ) -> InsightDetector:
        """Returns a specific detector instance."""
        detector_cls = cls._detectors.get(insight_type)
        if not detector_cls:
            raise ValueError(f"No detector registered for {insight_type}")
        return detector_cls(config)
```

---

## 5. Service Layer

### 5.1 Insight Service (Main Orchestrator)

```python
# backend/src/insights/service.py

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from uuid import UUID, uuid4
import structlog

from src.insights.detectors.registry import DetectorRegistry, InsightType
from src.insights.metrics.fetcher import MetricsFetcher
from src.insights.formatters.summary import SummaryFormatter
from src.insights.repository import InsightRepository
from src.insights.config import InsightConfig
from src.insights.models import Insight, InsightCandidate, TenantMetrics
from src.entitlements.service import EntitlementService

logger = structlog.get_logger()


@dataclass
class InsightGenerationResult:
    """Result of insight generation for a tenant."""
    tenant_id: UUID
    insights_generated: int
    insights: list[Insight]
    duration_ms: int
    errors: list[str]


class InsightService:
    """
    Orchestrates AI insight generation.

    Responsibilities:
    - Fetches aggregated metrics from dbt marts
    - Runs insight detection algorithms
    - Formats natural language summaries
    - Persists insights with tenant isolation
    """

    def __init__(
        self,
        metrics_fetcher: MetricsFetcher,
        insight_repository: InsightRepository,
        summary_formatter: SummaryFormatter,
        entitlement_service: EntitlementService,
        config: InsightConfig
    ):
        self._metrics_fetcher = metrics_fetcher
        self._repository = insight_repository
        self._formatter = summary_formatter
        self._entitlements = entitlement_service
        self._config = config
        self._detectors = DetectorRegistry.get_all_detectors(config)

    async def generate_insights_for_tenant(
        self,
        tenant_id: UUID,
        cadence: str = "daily",
        analysis_date: date | None = None
    ) -> InsightGenerationResult:
        """
        Generate insights for a single tenant.

        Args:
            tenant_id: Tenant to generate insights for
            cadence: 'daily' or 'hourly'
            analysis_date: Date to analyze (defaults to yesterday)

        Returns:
            InsightGenerationResult with generated insights
        """
        start_time = datetime.utcnow()
        errors: list[str] = []
        insights: list[Insight] = []

        analysis_date = analysis_date or (date.today() - timedelta(days=1))

        logger.info(
            "generating_insights",
            tenant_id=str(tenant_id),
            cadence=cadence,
            analysis_date=str(analysis_date)
        )

        try:
            # Check entitlements
            if not await self._check_entitlements(tenant_id, cadence):
                logger.warning(
                    "insight_generation_skipped_no_entitlement",
                    tenant_id=str(tenant_id)
                )
                return InsightGenerationResult(
                    tenant_id=tenant_id,
                    insights_generated=0,
                    insights=[],
                    duration_ms=0,
                    errors=["Tenant not entitled to AI insights"]
                )

            # Fetch aggregated metrics from dbt marts
            metrics = await self._metrics_fetcher.fetch_tenant_metrics(
                tenant_id=tenant_id,
                analysis_date=analysis_date,
                lookback_days=self._config.lookback_days
            )

            if not metrics.has_sufficient_data:
                logger.info(
                    "insight_generation_skipped_insufficient_data",
                    tenant_id=str(tenant_id),
                    days_with_data=metrics.days_with_data
                )
                return InsightGenerationResult(
                    tenant_id=tenant_id,
                    insights_generated=0,
                    insights=[],
                    duration_ms=self._elapsed_ms(start_time),
                    errors=["Insufficient data for analysis"]
                )

            # Run all detectors
            candidates: list[InsightCandidate] = []
            for detector in self._detectors:
                try:
                    detected = detector.detect(metrics)
                    candidates.extend(detected)
                except Exception as e:
                    logger.error(
                        "detector_failed",
                        detector=detector.insight_type,
                        error=str(e)
                    )
                    errors.append(f"Detector {detector.insight_type} failed: {e}")

            # Filter by confidence threshold
            candidates = [
                c for c in candidates
                if c.confidence_score >= self._config.min_confidence_threshold
            ]

            # Deduplicate and prioritize
            candidates = self._deduplicate_and_prioritize(candidates)

            # Generate summaries and create insight records
            for candidate in candidates[:self._config.max_insights_per_run]:
                summary = self._formatter.format_summary(candidate, metrics)

                insight = Insight(
                    id=uuid4(),
                    tenant_id=tenant_id,
                    insight_type=candidate.insight_type.value,
                    insight_category=candidate.category.value,
                    summary=summary,
                    supporting_metrics=[m.to_dict() for m in candidate.metrics],
                    confidence_score=candidate.confidence_score,
                    severity=candidate.severity,
                    analysis_period_start=metrics.current_period_start,
                    analysis_period_end=metrics.current_period_end,
                    comparison_period_start=metrics.previous_period_start,
                    comparison_period_end=metrics.previous_period_end,
                    generation_cadence=cadence,
                    model_version=self._config.model_version
                )

                insights.append(insight)

            # Persist insights
            if insights:
                await self._repository.bulk_create(insights)
                logger.info(
                    "insights_generated",
                    tenant_id=str(tenant_id),
                    count=len(insights)
                )

        except Exception as e:
            logger.exception(
                "insight_generation_failed",
                tenant_id=str(tenant_id),
                error=str(e)
            )
            errors.append(f"Generation failed: {e}")

        return InsightGenerationResult(
            tenant_id=tenant_id,
            insights_generated=len(insights),
            insights=insights,
            duration_ms=self._elapsed_ms(start_time),
            errors=errors
        )

    async def _check_entitlements(self, tenant_id: UUID, cadence: str) -> bool:
        """Check if tenant is entitled to insight generation."""
        # Check base AI insights entitlement
        has_insights = await self._entitlements.check_feature(
            tenant_id, "ai_insights"
        )

        # Hourly cadence requires enterprise entitlement
        if cadence == "hourly":
            has_hourly = await self._entitlements.check_feature(
                tenant_id, "ai_insights_hourly"
            )
            return has_insights and has_hourly

        return has_insights

    def _deduplicate_and_prioritize(
        self,
        candidates: list[InsightCandidate]
    ) -> list[InsightCandidate]:
        """
        Remove duplicate insights and sort by priority.

        Priority order:
        1. Critical severity
        2. Higher confidence
        3. Risk category over others
        """
        # Remove duplicates (same type + similar metrics)
        seen: set[str] = set()
        unique: list[InsightCandidate] = []

        for candidate in candidates:
            key = f"{candidate.insight_type}:{candidate.category}"
            if key not in seen:
                seen.add(key)
                unique.append(candidate)

        # Sort by priority
        severity_order = {"critical": 0, "warning": 1, "info": 2}
        category_order = {"risk": 0, "anomaly": 1, "opportunity": 2, "trend": 3}

        return sorted(
            unique,
            key=lambda c: (
                severity_order.get(c.severity, 2),
                -c.confidence_score,
                category_order.get(c.category.value, 3)
            )
        )

    def _elapsed_ms(self, start: datetime) -> int:
        return int((datetime.utcnow() - start).total_seconds() * 1000)
```

### 5.2 Metrics Fetcher

```python
# backend/src/insights/metrics/fetcher.py

from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from src.database.session import get_async_session


@dataclass
class ChannelSpend:
    """Spend by marketing channel."""
    channel: str
    spend: Decimal


@dataclass
class TenantMetrics:
    """Aggregated metrics for a tenant."""
    tenant_id: UUID

    # Time periods
    current_period_start: date
    current_period_end: date
    previous_period_start: date
    previous_period_end: date

    # Revenue metrics (from fact_orders)
    current_week_revenue: Decimal
    previous_week_revenue: Decimal
    current_week_orders: int
    previous_week_orders: int
    current_week_aov: Decimal
    previous_week_aov: Decimal

    # Spend metrics (from fact_ad_spend)
    current_week_spend: Decimal
    previous_week_spend: Decimal
    current_week_channel_spend: list[ChannelSpend]
    previous_week_channel_spend: list[ChannelSpend]

    # Campaign metrics (from fact_campaign_performance)
    current_week_impressions: int
    current_week_clicks: int
    current_week_conversions: int
    previous_week_conversions: int

    # Statistical context
    spend_std_dev: Decimal
    revenue_std_dev: Decimal
    days_with_data: int

    @property
    def has_sufficient_data(self) -> bool:
        """Check if we have enough data for meaningful analysis."""
        return (
            self.days_with_data >= 5 and
            (self.current_week_spend > 0 or self.current_week_revenue > 0)
        )

    @property
    def current_week_roas(self) -> Decimal:
        if self.current_week_spend > 0:
            return self.current_week_revenue / self.current_week_spend
        return Decimal("0")

    @property
    def previous_week_roas(self) -> Decimal:
        if self.previous_week_spend > 0:
            return self.previous_week_revenue / self.previous_week_spend
        return Decimal("0")


class MetricsFetcher:
    """
    Fetches aggregated metrics from dbt marts.

    IMPORTANT: Only reads from pre-aggregated marts, never raw tables.
    All queries are scoped by tenant_id.
    """

    def __init__(self, session: AsyncSession):
        self._session = session

    async def fetch_tenant_metrics(
        self,
        tenant_id: UUID,
        analysis_date: date,
        lookback_days: int = 28
    ) -> TenantMetrics:
        """
        Fetch all metrics needed for insight detection.

        Sources:
        - analytics.fact_orders: Revenue, orders, AOV
        - analytics.fact_ad_spend: Marketing spend by channel
        - analytics.fact_campaign_performance: Campaign metrics
        """
        current_end = analysis_date
        current_start = analysis_date - timedelta(days=6)  # 7 days
        previous_end = current_start - timedelta(days=1)
        previous_start = previous_end - timedelta(days=6)  # 7 days

        # Fetch revenue metrics from fact_orders
        revenue_metrics = await self._fetch_revenue_metrics(
            tenant_id, current_start, current_end, previous_start, previous_end
        )

        # Fetch spend metrics from fact_ad_spend
        spend_metrics = await self._fetch_spend_metrics(
            tenant_id, current_start, current_end, previous_start, previous_end
        )

        # Fetch campaign metrics from fact_campaign_performance
        campaign_metrics = await self._fetch_campaign_metrics(
            tenant_id, current_start, current_end, previous_start, previous_end
        )

        # Fetch historical variance
        variance = await self._fetch_historical_variance(
            tenant_id, analysis_date, lookback_days
        )

        return TenantMetrics(
            tenant_id=tenant_id,
            current_period_start=current_start,
            current_period_end=current_end,
            previous_period_start=previous_start,
            previous_period_end=previous_end,
            **revenue_metrics,
            **spend_metrics,
            **campaign_metrics,
            **variance
        )

    async def _fetch_revenue_metrics(
        self,
        tenant_id: UUID,
        current_start: date,
        current_end: date,
        previous_start: date,
        previous_end: date
    ) -> dict:
        """Query fact_orders for revenue metrics."""
        query = text("""
            WITH current_period AS (
                SELECT
                    COALESCE(SUM(total_price), 0) as revenue,
                    COUNT(*) as order_count,
                    COALESCE(AVG(total_price), 0) as aov
                FROM analytics.fact_orders
                WHERE tenant_id = :tenant_id
                  AND order_date BETWEEN :current_start AND :current_end
            ),
            previous_period AS (
                SELECT
                    COALESCE(SUM(total_price), 0) as revenue,
                    COUNT(*) as order_count,
                    COALESCE(AVG(total_price), 0) as aov
                FROM analytics.fact_orders
                WHERE tenant_id = :tenant_id
                  AND order_date BETWEEN :previous_start AND :previous_end
            )
            SELECT
                c.revenue as current_revenue,
                c.order_count as current_orders,
                c.aov as current_aov,
                p.revenue as previous_revenue,
                p.order_count as previous_orders,
                p.aov as previous_aov
            FROM current_period c, previous_period p
        """)

        result = await self._session.execute(query, {
            "tenant_id": str(tenant_id),
            "current_start": current_start,
            "current_end": current_end,
            "previous_start": previous_start,
            "previous_end": previous_end
        })
        row = result.fetchone()

        return {
            "current_week_revenue": Decimal(str(row.current_revenue)),
            "previous_week_revenue": Decimal(str(row.previous_revenue)),
            "current_week_orders": row.current_orders,
            "previous_week_orders": row.previous_orders,
            "current_week_aov": Decimal(str(row.current_aov)),
            "previous_week_aov": Decimal(str(row.previous_aov))
        }

    async def _fetch_spend_metrics(
        self,
        tenant_id: UUID,
        current_start: date,
        current_end: date,
        previous_start: date,
        previous_end: date
    ) -> dict:
        """Query fact_ad_spend for spend metrics."""
        # Total spend query
        total_query = text("""
            WITH current_period AS (
                SELECT COALESCE(SUM(spend), 0) as spend
                FROM analytics.fact_ad_spend
                WHERE tenant_id = :tenant_id
                  AND spend_date BETWEEN :current_start AND :current_end
            ),
            previous_period AS (
                SELECT COALESCE(SUM(spend), 0) as spend
                FROM analytics.fact_ad_spend
                WHERE tenant_id = :tenant_id
                  AND spend_date BETWEEN :previous_start AND :previous_end
            )
            SELECT
                c.spend as current_spend,
                p.spend as previous_spend
            FROM current_period c, previous_period p
        """)

        # Channel breakdown query
        channel_query = text("""
            SELECT
                ad_platform as channel,
                SUM(spend) as spend,
                CASE
                    WHEN spend_date BETWEEN :current_start AND :current_end THEN 'current'
                    ELSE 'previous'
                END as period
            FROM analytics.fact_ad_spend
            WHERE tenant_id = :tenant_id
              AND spend_date BETWEEN :previous_start AND :current_end
            GROUP BY ad_platform, period
        """)

        total_result = await self._session.execute(total_query, {
            "tenant_id": str(tenant_id),
            "current_start": current_start,
            "current_end": current_end,
            "previous_start": previous_start,
            "previous_end": previous_end
        })
        total_row = total_result.fetchone()

        channel_result = await self._session.execute(channel_query, {
            "tenant_id": str(tenant_id),
            "current_start": current_start,
            "current_end": current_end,
            "previous_start": previous_start,
            "previous_end": previous_end
        })

        current_channels = []
        previous_channels = []
        for row in channel_result:
            channel_spend = ChannelSpend(
                channel=row.channel,
                spend=Decimal(str(row.spend))
            )
            if row.period == "current":
                current_channels.append(channel_spend)
            else:
                previous_channels.append(channel_spend)

        return {
            "current_week_spend": Decimal(str(total_row.current_spend)),
            "previous_week_spend": Decimal(str(total_row.previous_spend)),
            "current_week_channel_spend": current_channels,
            "previous_week_channel_spend": previous_channels
        }

    async def _fetch_campaign_metrics(
        self,
        tenant_id: UUID,
        current_start: date,
        current_end: date,
        previous_start: date,
        previous_end: date
    ) -> dict:
        """Query fact_campaign_performance for campaign metrics."""
        query = text("""
            WITH current_period AS (
                SELECT
                    COALESCE(SUM(impressions), 0) as impressions,
                    COALESCE(SUM(clicks), 0) as clicks,
                    COALESCE(SUM(conversions), 0) as conversions
                FROM analytics.fact_campaign_performance
                WHERE tenant_id = :tenant_id
                  AND report_date BETWEEN :current_start AND :current_end
            ),
            previous_period AS (
                SELECT
                    COALESCE(SUM(conversions), 0) as conversions
                FROM analytics.fact_campaign_performance
                WHERE tenant_id = :tenant_id
                  AND report_date BETWEEN :previous_start AND :previous_end
            )
            SELECT
                c.impressions,
                c.clicks,
                c.conversions as current_conversions,
                p.conversions as previous_conversions
            FROM current_period c, previous_period p
        """)

        result = await self._session.execute(query, {
            "tenant_id": str(tenant_id),
            "current_start": current_start,
            "current_end": current_end,
            "previous_start": previous_start,
            "previous_end": previous_end
        })
        row = result.fetchone()

        return {
            "current_week_impressions": row.impressions,
            "current_week_clicks": row.clicks,
            "current_week_conversions": row.current_conversions,
            "previous_week_conversions": row.previous_conversions
        }

    async def _fetch_historical_variance(
        self,
        tenant_id: UUID,
        analysis_date: date,
        lookback_days: int
    ) -> dict:
        """Calculate historical variance for statistical context."""
        query = text("""
            WITH daily_metrics AS (
                SELECT
                    spend_date as metric_date,
                    SUM(spend) as daily_spend
                FROM analytics.fact_ad_spend
                WHERE tenant_id = :tenant_id
                  AND spend_date BETWEEN :start_date AND :end_date
                GROUP BY spend_date
            ),
            daily_revenue AS (
                SELECT
                    order_date as metric_date,
                    SUM(total_price) as daily_revenue
                FROM analytics.fact_orders
                WHERE tenant_id = :tenant_id
                  AND order_date BETWEEN :start_date AND :end_date
                GROUP BY order_date
            )
            SELECT
                COALESCE(STDDEV(dm.daily_spend), 0) as spend_std_dev,
                COALESCE(STDDEV(dr.daily_revenue), 0) as revenue_std_dev,
                COUNT(DISTINCT dm.metric_date) as days_with_data
            FROM daily_metrics dm
            LEFT JOIN daily_revenue dr ON dm.metric_date = dr.metric_date
        """)

        result = await self._session.execute(query, {
            "tenant_id": str(tenant_id),
            "start_date": analysis_date - timedelta(days=lookback_days),
            "end_date": analysis_date
        })
        row = result.fetchone()

        return {
            "spend_std_dev": Decimal(str(row.spend_std_dev or 0)),
            "revenue_std_dev": Decimal(str(row.revenue_std_dev or 0)),
            "days_with_data": row.days_with_data or 0
        }
```

### 5.3 Insight Repository

```python
# backend/src/insights/repository.py

from datetime import datetime
from uuid import UUID
from typing import Optional

from sqlalchemy import text, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.insights.models import Insight
from src.repositories.base_repo import BaseRepository


class InsightRepository(BaseRepository[Insight]):
    """
    Repository for AI insights with tenant isolation.

    All operations are scoped to tenant_id.
    """

    def __init__(self, session: AsyncSession, tenant_id: UUID):
        super().__init__(session, tenant_id)
        self._table = "ai_insights"

    async def create(self, insight: Insight) -> Insight:
        """Create a single insight."""
        query = text("""
            INSERT INTO ai_insights (
                id, tenant_id, insight_type, insight_category,
                summary, supporting_metrics, confidence_score, severity,
                analysis_period_start, analysis_period_end,
                comparison_period_start, comparison_period_end,
                generation_cadence, model_version, generated_at
            ) VALUES (
                :id, :tenant_id, :insight_type, :insight_category,
                :summary, :supporting_metrics::jsonb, :confidence_score, :severity,
                :analysis_period_start, :analysis_period_end,
                :comparison_period_start, :comparison_period_end,
                :generation_cadence, :model_version, :generated_at
            )
            RETURNING *
        """)

        await self._session.execute(query, {
            "id": str(insight.id),
            "tenant_id": str(self._tenant_id),
            "insight_type": insight.insight_type,
            "insight_category": insight.insight_category,
            "summary": insight.summary,
            "supporting_metrics": insight.supporting_metrics_json,
            "confidence_score": float(insight.confidence_score),
            "severity": insight.severity,
            "analysis_period_start": insight.analysis_period_start,
            "analysis_period_end": insight.analysis_period_end,
            "comparison_period_start": insight.comparison_period_start,
            "comparison_period_end": insight.comparison_period_end,
            "generation_cadence": insight.generation_cadence,
            "model_version": insight.model_version,
            "generated_at": insight.generated_at or datetime.utcnow()
        })
        await self._session.commit()

        return insight

    async def bulk_create(self, insights: list[Insight]) -> list[Insight]:
        """Create multiple insights in a single transaction."""
        for insight in insights:
            # Ensure tenant_id matches
            if insight.tenant_id != self._tenant_id:
                raise ValueError("Insight tenant_id does not match repository tenant")
            await self.create(insight)

        return insights

    async def get_active_insights(
        self,
        limit: int = 50,
        insight_type: Optional[str] = None
    ) -> list[Insight]:
        """Get active insights for the tenant."""
        query = text("""
            SELECT *
            FROM ai_insights
            WHERE tenant_id = :tenant_id
              AND status = 'active'
              AND (:insight_type IS NULL OR insight_type = :insight_type)
            ORDER BY generated_at DESC
            LIMIT :limit
        """)

        result = await self._session.execute(query, {
            "tenant_id": str(self._tenant_id),
            "insight_type": insight_type,
            "limit": limit
        })

        return [self._row_to_insight(row) for row in result.fetchall()]

    async def dismiss_insight(
        self,
        insight_id: UUID,
        user_id: UUID
    ) -> bool:
        """Dismiss an insight (user action)."""
        query = text("""
            UPDATE ai_insights
            SET status = 'dismissed',
                dismissed_at = :dismissed_at,
                dismissed_by = :dismissed_by
            WHERE id = :insight_id
              AND tenant_id = :tenant_id
              AND status = 'active'
        """)

        result = await self._session.execute(query, {
            "insight_id": str(insight_id),
            "tenant_id": str(self._tenant_id),
            "dismissed_at": datetime.utcnow(),
            "dismissed_by": str(user_id)
        })
        await self._session.commit()

        return result.rowcount > 0

    async def expire_old_insights(self, days: int = 30) -> int:
        """Expire insights older than specified days."""
        query = text("""
            UPDATE ai_insights
            SET status = 'expired'
            WHERE tenant_id = :tenant_id
              AND status = 'active'
              AND generated_at < NOW() - INTERVAL ':days days'
        """)

        result = await self._session.execute(query, {
            "tenant_id": str(self._tenant_id),
            "days": days
        })
        await self._session.commit()

        return result.rowcount
```

---

## 6. Scheduled Job Implementation

### 6.1 Daily Insight Generation Job

```python
# backend/src/jobs/insight_generation.py

import asyncio
from datetime import date, datetime, timedelta
from uuid import uuid4
import structlog

from src.database.session import get_async_session
from src.insights.service import InsightService
from src.insights.metrics.fetcher import MetricsFetcher
from src.insights.formatters.summary import SummaryFormatter
from src.insights.repository import InsightRepository
from src.insights.config import InsightConfig, load_insight_config
from src.entitlements.service import EntitlementService
from src.platform.tenant_context import get_all_active_tenants

logger = structlog.get_logger()


class InsightGenerationJob:
    """
    Scheduled job for generating AI insights.

    Runs:
    - Daily at 6 AM UTC (all entitled tenants)
    - Hourly (enterprise tenants only)
    """

    def __init__(self, cadence: str = "daily"):
        self.cadence = cadence
        self.run_id = uuid4()
        self.config = load_insight_config()

    async def run(self, analysis_date: date | None = None) -> dict:
        """
        Execute insight generation for all eligible tenants.

        Returns summary of generation results.
        """
        start_time = datetime.utcnow()
        analysis_date = analysis_date or (date.today() - timedelta(days=1))

        logger.info(
            "insight_generation_job_started",
            run_id=str(self.run_id),
            cadence=self.cadence,
            analysis_date=str(analysis_date)
        )

        results = {
            "run_id": str(self.run_id),
            "cadence": self.cadence,
            "analysis_date": str(analysis_date),
            "started_at": start_time.isoformat(),
            "tenants_processed": 0,
            "total_insights_generated": 0,
            "tenant_results": [],
            "errors": []
        }

        try:
            # Get all eligible tenants
            tenants = await self._get_eligible_tenants()

            logger.info(
                "eligible_tenants_found",
                run_id=str(self.run_id),
                tenant_count=len(tenants)
            )

            # Process each tenant
            for tenant_id in tenants:
                try:
                    tenant_result = await self._process_tenant(
                        tenant_id,
                        analysis_date
                    )
                    results["tenant_results"].append({
                        "tenant_id": str(tenant_id),
                        "insights_generated": tenant_result.insights_generated,
                        "duration_ms": tenant_result.duration_ms,
                        "errors": tenant_result.errors
                    })
                    results["total_insights_generated"] += tenant_result.insights_generated
                    results["tenants_processed"] += 1

                except Exception as e:
                    logger.exception(
                        "tenant_processing_failed",
                        run_id=str(self.run_id),
                        tenant_id=str(tenant_id),
                        error=str(e)
                    )
                    results["errors"].append({
                        "tenant_id": str(tenant_id),
                        "error": str(e)
                    })

        except Exception as e:
            logger.exception(
                "insight_generation_job_failed",
                run_id=str(self.run_id),
                error=str(e)
            )
            results["errors"].append({"error": str(e)})

        end_time = datetime.utcnow()
        results["completed_at"] = end_time.isoformat()
        results["duration_seconds"] = (end_time - start_time).total_seconds()

        logger.info(
            "insight_generation_job_completed",
            run_id=str(self.run_id),
            tenants_processed=results["tenants_processed"],
            total_insights=results["total_insights_generated"],
            duration_seconds=results["duration_seconds"]
        )

        return results

    async def _get_eligible_tenants(self) -> list:
        """Get tenants eligible for insight generation."""
        async with get_async_session() as session:
            entitlement_service = EntitlementService(session)

            # Get all active tenants
            all_tenants = await get_all_active_tenants(session)

            # Filter by entitlement
            eligible = []
            for tenant_id in all_tenants:
                feature = (
                    "ai_insights_hourly" if self.cadence == "hourly"
                    else "ai_insights"
                )
                if await entitlement_service.check_feature(tenant_id, feature):
                    eligible.append(tenant_id)

            return eligible

    async def _process_tenant(
        self,
        tenant_id,
        analysis_date: date
    ):
        """Process insight generation for a single tenant."""
        async with get_async_session() as session:
            # Initialize services
            metrics_fetcher = MetricsFetcher(session)
            repository = InsightRepository(session, tenant_id)
            formatter = SummaryFormatter()
            entitlement_service = EntitlementService(session)

            service = InsightService(
                metrics_fetcher=metrics_fetcher,
                insight_repository=repository,
                summary_formatter=formatter,
                entitlement_service=entitlement_service,
                config=self.config
            )

            return await service.generate_insights_for_tenant(
                tenant_id=tenant_id,
                cadence=self.cadence,
                analysis_date=analysis_date
            )


# Entry points for cron jobs
async def run_daily_insights():
    """Entry point for daily cron job."""
    job = InsightGenerationJob(cadence="daily")
    return await job.run()


async def run_hourly_insights():
    """Entry point for hourly cron job (enterprise only)."""
    job = InsightGenerationJob(cadence="hourly")
    return await job.run()


if __name__ == "__main__":
    # CLI invocation
    import sys

    cadence = sys.argv[1] if len(sys.argv) > 1 else "daily"

    if cadence == "hourly":
        asyncio.run(run_hourly_insights())
    else:
        asyncio.run(run_daily_insights())
```

### 6.2 Render Cron Configuration

Add to `render.yaml`:

```yaml
# Daily insight generation - 6 AM UTC
- type: cron
  name: shopify-analytics-daily-insights
  runtime: docker
  dockerfilePath: ./docker/worker.Dockerfile
  dockerContext: .
  schedule: "0 6 * * *"
  envVars:
    - fromGroup: shopify-analytics-env
  buildCommand: ""
  startCommand: python -m src.jobs.insight_generation daily

# Hourly insight generation (enterprise) - top of every hour
- type: cron
  name: shopify-analytics-hourly-insights
  runtime: docker
  dockerfilePath: ./docker/worker.Dockerfile
  dockerContext: .
  schedule: "0 * * * *"
  envVars:
    - fromGroup: shopify-analytics-env
  buildCommand: ""
  startCommand: python -m src.jobs.insight_generation hourly
```

---

## 7. Natural Language Generation

### 7.1 Summary Formatter

```python
# backend/src/insights/formatters/summary.py

from dataclasses import dataclass
from decimal import Decimal
from typing import Optional

from src.insights.detectors.registry import InsightType, InsightCategory
from src.insights.models import InsightCandidate, TenantMetrics


@dataclass
class SummaryTemplate:
    """Template for insight summaries."""
    positive: str
    negative: str
    neutral: str


class SummaryFormatter:
    """
    Generates natural language summaries for insights.

    Summaries are:
    - 1-2 sentences maximum
    - Data-driven (include specific numbers)
    - Actionable where possible
    - Deterministic (same inputs = same outputs)
    """

    TEMPLATES: dict[InsightType, SummaryTemplate] = {
        InsightType.SPEND_ANOMALY: SummaryTemplate(
            positive="Marketing spend increased {delta_percent}% week-over-week to ${current_value:,.0f}. Review campaign budgets to ensure this aligns with your growth targets.",
            negative="Marketing spend dropped {delta_percent}% week-over-week to ${current_value:,.0f}. This may impact reach and conversions if unintentional.",
            neutral="Marketing spend changed by {delta_percent}% week-over-week to ${current_value:,.0f}."
        ),
        InsightType.ROAS_CHANGE: SummaryTemplate(
            positive="ROAS improved {delta_percent}% to {current_value:.1f}x, generating ${revenue:,.0f} from ${spend:,.0f} in ad spend. Your campaigns are becoming more efficient.",
            negative="ROAS declined {delta_percent}% to {current_value:.1f}x. Consider reviewing underperforming campaigns or adjusting targeting.",
            neutral="ROAS is {current_value:.1f}x, {direction} {delta_percent}% from last week."
        ),
        InsightType.REVENUE_SPEND_DIVERGENCE: SummaryTemplate(
            positive="Revenue grew {revenue_delta}% while spend decreased {spend_delta}%, indicating improved marketing efficiency.",
            negative="Spend increased {spend_delta}% but revenue declined {revenue_delta}%. Review campaign performance to identify inefficiencies.",
            neutral="Revenue and spend are diverging: revenue {revenue_direction} {revenue_delta}% while spend {spend_direction} {spend_delta}%."
        ),
        InsightType.CHANNEL_MIX_SHIFT: SummaryTemplate(
            positive="{channel} now represents {current_share}% of spend (up {delta}pp). Monitor performance to validate this increased investment.",
            negative="{channel} dropped to {current_share}% of spend (down {delta}pp). Ensure this reduction is intentional.",
            neutral="{channel} shifted from {previous_share}% to {current_share}% of total spend."
        ),
        InsightType.AOV_CHANGE: SummaryTemplate(
            positive="Average order value increased {delta_percent}% to ${current_value:,.2f}. Customers are spending more per order.",
            negative="Average order value decreased {delta_percent}% to ${current_value:,.2f}. Consider upselling strategies or bundle offers.",
            neutral="Average order value is ${current_value:,.2f}, {direction} {delta_percent}% from last week."
        ),
        InsightType.CONVERSION_RATE_CHANGE: SummaryTemplate(
            positive="Conversion rate improved {delta_percent}% to {current_value:.2f}%. Your funnel is converting more visitors into customers.",
            negative="Conversion rate dropped {delta_percent}% to {current_value:.2f}%. Review landing pages and checkout flow for friction.",
            neutral="Conversion rate is {current_value:.2f}%, {direction} {delta_percent}% week-over-week."
        ),
        InsightType.CPA_ANOMALY: SummaryTemplate(
            positive="Cost per acquisition improved {delta_percent}% to ${current_value:,.2f}. You're acquiring customers more efficiently.",
            negative="Cost per acquisition increased {delta_percent}% to ${current_value:,.2f}. Review targeting and ad creative to reduce acquisition costs.",
            neutral="Cost per acquisition is ${current_value:,.2f}, {direction} {delta_percent}% from last week."
        )
    }

    def format_summary(
        self,
        candidate: InsightCandidate,
        metrics: TenantMetrics
    ) -> str:
        """
        Generate a natural language summary for an insight candidate.

        Returns a 1-2 sentence summary with specific metrics.
        """
        template = self.TEMPLATES.get(candidate.insight_type)
        if not template:
            return self._format_generic(candidate)

        # Get the primary metric
        primary_metric = candidate.metrics[0] if candidate.metrics else None
        if not primary_metric:
            return self._format_generic(candidate)

        # Determine sentiment
        delta = primary_metric.delta_percent or 0

        # For some metrics, negative delta is actually positive (CPA, spend anomaly when decreasing intentionally)
        is_positive_direction = self._is_positive_change(
            candidate.insight_type,
            delta
        )

        # Select appropriate template
        if is_positive_direction:
            template_str = template.positive
        elif delta < 0:
            template_str = template.negative
        else:
            template_str = template.neutral

        # Format with actual values
        try:
            return self._apply_template(
                template_str,
                candidate,
                metrics,
                primary_metric
            )
        except (KeyError, ValueError):
            return self._format_generic(candidate)

    def _is_positive_change(
        self,
        insight_type: InsightType,
        delta: float
    ) -> bool:
        """Determine if a change is positive based on insight type."""
        # These metrics are better when they go down
        lower_is_better = {
            InsightType.CPA_ANOMALY,
        }

        # These metrics are better when they go up
        higher_is_better = {
            InsightType.ROAS_CHANGE,
            InsightType.AOV_CHANGE,
            InsightType.CONVERSION_RATE_CHANGE,
        }

        if insight_type in lower_is_better:
            return delta < 0
        elif insight_type in higher_is_better:
            return delta > 0
        else:
            # Neutral - magnitude matters more than direction
            return abs(delta) < 5  # Small changes are "neutral"

    def _apply_template(
        self,
        template: str,
        candidate: InsightCandidate,
        metrics: TenantMetrics,
        primary_metric
    ) -> str:
        """Apply values to template string."""
        format_values = {
            "delta_percent": abs(primary_metric.delta_percent or 0),
            "current_value": float(primary_metric.current_value or 0),
            "previous_value": float(primary_metric.previous_value or 0),
            "delta": abs(primary_metric.delta_absolute or 0),
            "direction": "up" if (primary_metric.delta_percent or 0) > 0 else "down",
            "revenue": float(metrics.current_week_revenue),
            "spend": float(metrics.current_week_spend),
        }

        # Handle channel-specific formatting
        if candidate.insight_type == InsightType.CHANNEL_MIX_SHIFT:
            context = candidate.context or {}
            format_values.update({
                "channel": context.get("channel", "Unknown"),
                "current_share": float(primary_metric.current_value or 0),
                "previous_share": float(primary_metric.previous_value or 0),
            })

        # Handle divergence-specific formatting
        if candidate.insight_type == InsightType.REVENUE_SPEND_DIVERGENCE:
            if len(candidate.metrics) >= 2:
                spend_metric = candidate.metrics[0]
                revenue_metric = candidate.metrics[1]
                format_values.update({
                    "spend_delta": abs(spend_metric.delta_percent or 0),
                    "revenue_delta": abs(revenue_metric.delta_percent or 0),
                    "spend_direction": "up" if (spend_metric.delta_percent or 0) > 0 else "down",
                    "revenue_direction": "up" if (revenue_metric.delta_percent or 0) > 0 else "down",
                })

        return template.format(**format_values)

    def _format_generic(self, candidate: InsightCandidate) -> str:
        """Fallback generic formatting."""
        type_name = candidate.insight_type.value.replace("_", " ").title()

        if candidate.metrics:
            metric = candidate.metrics[0]
            return (
                f"{type_name} detected: {metric.metric_name} changed "
                f"{metric.delta_percent:+.1f}% {metric.timeframe}."
            )

        return f"{type_name} detected based on recent performance data."
```

---

## 8. Configuration & Thresholds

### 8.1 Configuration Schema

```python
# backend/src/insights/config.py

from dataclasses import dataclass, field
from pathlib import Path
import json
from typing import Optional


@dataclass
class InsightThresholds:
    """Configurable thresholds for insight detection."""

    # Spend anomaly
    spend_threshold_percent: float = 15.0  # ±15% WoW
    spend_std_dev_multiplier: float = 2.0  # Outside 2 std devs

    # ROAS change
    roas_threshold_percent: float = 10.0  # ±10% WoW
    roas_profitability_threshold: float = 1.5  # Alert if below

    # Revenue/spend divergence
    divergence_threshold_percent: float = 20.0  # 20% difference

    # Channel mix shift
    channel_shift_threshold_pp: float = 10.0  # 10 percentage points

    # AOV change
    aov_threshold_percent: float = 10.0  # ±10% WoW

    # Conversion rate
    conversion_threshold_percent: float = 15.0  # ±15% WoW

    # CPA anomaly
    cpa_threshold_percent: float = 20.0  # ±20% WoW


@dataclass
class InsightConfig:
    """Full configuration for insight generation."""

    # Thresholds
    thresholds: InsightThresholds = field(default_factory=InsightThresholds)

    # General settings
    min_confidence_threshold: float = 0.5  # Minimum confidence to emit
    max_insights_per_run: int = 10  # Cap insights per tenant per run
    lookback_days: int = 28  # Historical data for variance
    min_days_with_data: int = 5  # Minimum data requirement

    # Model version (for tracking)
    model_version: str = "v1.0"

    # Feature flags
    enabled_insight_types: list[str] = field(default_factory=lambda: [
        "spend_anomaly",
        "roas_change",
        "revenue_spend_divergence",
        "channel_mix_shift"
    ])


def load_insight_config(config_path: Optional[Path] = None) -> InsightConfig:
    """
    Load insight configuration from file or environment.

    Priority:
    1. Explicit config file path
    2. config/insights.json
    3. Default values
    """
    if config_path and config_path.exists():
        return _load_from_file(config_path)

    default_path = Path("config/insights.json")
    if default_path.exists():
        return _load_from_file(default_path)

    return InsightConfig()


def _load_from_file(path: Path) -> InsightConfig:
    """Load config from JSON file."""
    with open(path) as f:
        data = json.load(f)

    thresholds = InsightThresholds(**data.get("thresholds", {}))

    return InsightConfig(
        thresholds=thresholds,
        min_confidence_threshold=data.get("min_confidence_threshold", 0.5),
        max_insights_per_run=data.get("max_insights_per_run", 10),
        lookback_days=data.get("lookback_days", 28),
        min_days_with_data=data.get("min_days_with_data", 5),
        model_version=data.get("model_version", "v1.0"),
        enabled_insight_types=data.get("enabled_insight_types", [])
    )
```

### 8.2 Configuration File

```json
// config/insights.json
{
  "thresholds": {
    "spend_threshold_percent": 15.0,
    "spend_std_dev_multiplier": 2.0,
    "roas_threshold_percent": 10.0,
    "roas_profitability_threshold": 1.5,
    "divergence_threshold_percent": 20.0,
    "channel_shift_threshold_pp": 10.0,
    "aov_threshold_percent": 10.0,
    "conversion_threshold_percent": 15.0,
    "cpa_threshold_percent": 20.0
  },
  "min_confidence_threshold": 0.5,
  "max_insights_per_run": 10,
  "lookback_days": 28,
  "min_days_with_data": 5,
  "model_version": "v1.0",
  "enabled_insight_types": [
    "spend_anomaly",
    "roas_change",
    "revenue_spend_divergence",
    "channel_mix_shift"
  ]
}
```

---

## 9. Testing Strategy

### 9.1 Unit Tests

```python
# backend/src/tests/insights/test_detectors.py

import pytest
from decimal import Decimal
from datetime import date
from uuid import uuid4

from src.insights.detectors.spend_anomaly import SpendAnomalyDetector
from src.insights.detectors.roas_change import ROASChangeDetector
from src.insights.detectors.revenue_spend_divergence import RevenueSpendDivergenceDetector
from src.insights.detectors.registry import InsightType, InsightCategory
from src.insights.config import InsightConfig, InsightThresholds
from src.insights.metrics.fetcher import TenantMetrics, ChannelSpend


@pytest.fixture
def config():
    """Default test configuration."""
    return InsightConfig(
        thresholds=InsightThresholds(
            spend_threshold_percent=15.0,
            roas_threshold_percent=10.0,
            divergence_threshold_percent=20.0
        )
    )


@pytest.fixture
def base_metrics():
    """Base metrics fixture for tests."""
    return TenantMetrics(
        tenant_id=uuid4(),
        current_period_start=date(2026, 1, 20),
        current_period_end=date(2026, 1, 26),
        previous_period_start=date(2026, 1, 13),
        previous_period_end=date(2026, 1, 19),
        current_week_revenue=Decimal("50000"),
        previous_week_revenue=Decimal("50000"),
        current_week_orders=500,
        previous_week_orders=500,
        current_week_aov=Decimal("100"),
        previous_week_aov=Decimal("100"),
        current_week_spend=Decimal("10000"),
        previous_week_spend=Decimal("10000"),
        current_week_channel_spend=[],
        previous_week_channel_spend=[],
        current_week_impressions=100000,
        current_week_clicks=5000,
        current_week_conversions=500,
        previous_week_conversions=500,
        spend_std_dev=Decimal("1000"),
        revenue_std_dev=Decimal("5000"),
        days_with_data=7
    )


class TestSpendAnomalyDetector:
    """Tests for spend anomaly detection."""

    def test_no_anomaly_when_within_threshold(self, config, base_metrics):
        """Should not detect anomaly when spend change is within threshold."""
        detector = SpendAnomalyDetector(config)

        # 10% increase (below 15% threshold)
        base_metrics.current_week_spend = Decimal("11000")

        insights = detector.detect(base_metrics)

        assert len(insights) == 0

    def test_detects_significant_spend_increase(self, config, base_metrics):
        """Should detect anomaly when spend increases significantly."""
        detector = SpendAnomalyDetector(config)

        # 25% increase (above 15% threshold)
        base_metrics.current_week_spend = Decimal("12500")

        insights = detector.detect(base_metrics)

        assert len(insights) == 1
        assert insights[0].insight_type == InsightType.SPEND_ANOMALY
        assert insights[0].category == InsightCategory.ANOMALY
        assert insights[0].metrics[0].delta_percent == pytest.approx(25.0, rel=0.1)

    def test_detects_significant_spend_decrease(self, config, base_metrics):
        """Should detect anomaly when spend decreases significantly."""
        detector = SpendAnomalyDetector(config)

        # 20% decrease
        base_metrics.current_week_spend = Decimal("8000")

        insights = detector.detect(base_metrics)

        assert len(insights) == 1
        assert insights[0].metrics[0].delta_percent == pytest.approx(-20.0, rel=0.1)

    def test_deterministic_output(self, config, base_metrics):
        """Same inputs should produce same outputs."""
        detector = SpendAnomalyDetector(config)

        base_metrics.current_week_spend = Decimal("12500")

        insights_1 = detector.detect(base_metrics)
        insights_2 = detector.detect(base_metrics)

        assert len(insights_1) == len(insights_2)
        assert insights_1[0].confidence_score == insights_2[0].confidence_score
        assert insights_1[0].metrics[0].delta_percent == insights_2[0].metrics[0].delta_percent


class TestROASChangeDetector:
    """Tests for ROAS change detection."""

    def test_no_insight_when_roas_stable(self, config, base_metrics):
        """Should not detect when ROAS is stable."""
        detector = ROASChangeDetector(config)

        # ROAS stays at 5.0 (50k revenue / 10k spend)
        insights = detector.detect(base_metrics)

        assert len(insights) == 0

    def test_detects_roas_improvement(self, config, base_metrics):
        """Should detect significant ROAS improvement."""
        detector = ROASChangeDetector(config)

        # Current: 60k/10k = 6.0 ROAS
        # Previous: 50k/10k = 5.0 ROAS (20% improvement)
        base_metrics.current_week_revenue = Decimal("60000")

        insights = detector.detect(base_metrics)

        assert len(insights) == 1
        assert insights[0].insight_type == InsightType.ROAS_CHANGE
        assert insights[0].category == InsightCategory.OPPORTUNITY

    def test_detects_roas_decline(self, config, base_metrics):
        """Should detect significant ROAS decline."""
        detector = ROASChangeDetector(config)

        # Current: 40k/10k = 4.0 ROAS
        # Previous: 50k/10k = 5.0 ROAS (20% decline)
        base_metrics.current_week_revenue = Decimal("40000")

        insights = detector.detect(base_metrics)

        assert len(insights) == 1
        assert insights[0].category == InsightCategory.RISK

    def test_handles_zero_spend(self, config, base_metrics):
        """Should handle zero spend gracefully."""
        detector = ROASChangeDetector(config)

        base_metrics.current_week_spend = Decimal("0")
        base_metrics.previous_week_spend = Decimal("0")

        insights = detector.detect(base_metrics)

        # Should not crash, may or may not produce insight
        assert isinstance(insights, list)


class TestRevenueSpendDivergenceDetector:
    """Tests for revenue/spend divergence detection."""

    def test_no_divergence_when_aligned(self, config, base_metrics):
        """Should not detect when revenue and spend move together."""
        detector = RevenueSpendDivergenceDetector(config)

        # Both up 20%
        base_metrics.current_week_revenue = Decimal("60000")
        base_metrics.current_week_spend = Decimal("12000")

        insights = detector.detect(base_metrics)

        assert len(insights) == 0

    def test_detects_negative_divergence(self, config, base_metrics):
        """Should detect when spend up but revenue down."""
        detector = RevenueSpendDivergenceDetector(config)

        # Spend up 30%, revenue down 10%
        base_metrics.current_week_spend = Decimal("13000")
        base_metrics.current_week_revenue = Decimal("45000")

        insights = detector.detect(base_metrics)

        assert len(insights) == 1
        assert insights[0].insight_type == InsightType.REVENUE_SPEND_DIVERGENCE
        assert insights[0].category == InsightCategory.RISK

    def test_detects_positive_divergence(self, config, base_metrics):
        """Should detect when revenue up but spend down."""
        detector = RevenueSpendDivergenceDetector(config)

        # Spend down 20%, revenue up 15%
        base_metrics.current_week_spend = Decimal("8000")
        base_metrics.current_week_revenue = Decimal("57500")

        insights = detector.detect(base_metrics)

        assert len(insights) == 1
        assert insights[0].category == InsightCategory.OPPORTUNITY


class TestConfidenceCalculation:
    """Tests for statistical confidence scoring."""

    def test_higher_confidence_with_more_data(self, config, base_metrics):
        """More days of data should increase confidence."""
        detector = SpendAnomalyDetector(config)

        base_metrics.current_week_spend = Decimal("12500")  # 25% increase

        base_metrics.days_with_data = 3
        insights_low_data = detector.detect(base_metrics)

        base_metrics.days_with_data = 14
        insights_high_data = detector.detect(base_metrics)

        assert insights_high_data[0].confidence_score >= insights_low_data[0].confidence_score

    def test_higher_confidence_with_lower_volatility(self, config, base_metrics):
        """Lower historical volatility should increase confidence."""
        detector = SpendAnomalyDetector(config)

        base_metrics.current_week_spend = Decimal("12500")

        base_metrics.spend_std_dev = Decimal("5000")  # High volatility
        insights_volatile = detector.detect(base_metrics)

        base_metrics.spend_std_dev = Decimal("500")  # Low volatility
        insights_stable = detector.detect(base_metrics)

        assert insights_stable[0].confidence_score >= insights_volatile[0].confidence_score
```

### 9.2 Integration Tests

```python
# backend/src/tests/insights/test_service_integration.py

import pytest
from datetime import date, timedelta
from uuid import uuid4
from decimal import Decimal

from src.insights.service import InsightService
from src.insights.config import InsightConfig


@pytest.fixture
async def insight_service(test_db_session, mock_entitlements):
    """Create insight service with test dependencies."""
    from src.insights.metrics.fetcher import MetricsFetcher
    from src.insights.formatters.summary import SummaryFormatter
    from src.insights.repository import InsightRepository

    tenant_id = uuid4()

    return InsightService(
        metrics_fetcher=MetricsFetcher(test_db_session),
        insight_repository=InsightRepository(test_db_session, tenant_id),
        summary_formatter=SummaryFormatter(),
        entitlement_service=mock_entitlements,
        config=InsightConfig()
    ), tenant_id


@pytest.mark.integration
class TestInsightServiceIntegration:
    """Integration tests for the insight service."""

    async def test_full_insight_generation_flow(
        self,
        insight_service,
        seed_test_data
    ):
        """Test complete insight generation pipeline."""
        service, tenant_id = insight_service

        # Seed test data with known anomalies
        await seed_test_data(
            tenant_id=tenant_id,
            current_week_spend=Decimal("15000"),  # 50% increase
            previous_week_spend=Decimal("10000"),
            current_week_revenue=Decimal("50000"),
            previous_week_revenue=Decimal("50000")
        )

        result = await service.generate_insights_for_tenant(
            tenant_id=tenant_id,
            cadence="daily",
            analysis_date=date.today() - timedelta(days=1)
        )

        assert result.insights_generated > 0
        assert len(result.errors) == 0

        # Should detect spend anomaly
        spend_insights = [
            i for i in result.insights
            if i.insight_type == "spend_anomaly"
        ]
        assert len(spend_insights) == 1

    async def test_insights_persisted_correctly(
        self,
        insight_service,
        seed_test_data,
        test_db_session
    ):
        """Test that insights are correctly persisted."""
        service, tenant_id = insight_service

        await seed_test_data(tenant_id=tenant_id)

        result = await service.generate_insights_for_tenant(
            tenant_id=tenant_id,
            cadence="daily"
        )

        # Verify persistence
        from src.insights.repository import InsightRepository
        repo = InsightRepository(test_db_session, tenant_id)

        stored_insights = await repo.get_active_insights()

        assert len(stored_insights) == result.insights_generated

    async def test_tenant_isolation(
        self,
        insight_service,
        seed_test_data,
        test_db_session
    ):
        """Test that insights are properly tenant-isolated."""
        service, tenant_id = insight_service
        other_tenant_id = uuid4()

        await seed_test_data(tenant_id=tenant_id)
        await seed_test_data(tenant_id=other_tenant_id)

        # Generate insights for one tenant
        await service.generate_insights_for_tenant(tenant_id=tenant_id)

        # Other tenant should have no insights
        from src.insights.repository import InsightRepository
        other_repo = InsightRepository(test_db_session, other_tenant_id)
        other_insights = await other_repo.get_active_insights()

        assert len(other_insights) == 0
```

### 9.3 Test Fixtures and Factories

```python
# backend/src/tests/insights/conftest.py

import pytest
from datetime import date, timedelta
from decimal import Decimal
from uuid import uuid4

from sqlalchemy import text


@pytest.fixture
async def seed_test_data(test_db_session):
    """Factory fixture to seed test data."""

    async def _seed(
        tenant_id,
        current_week_spend=Decimal("10000"),
        previous_week_spend=Decimal("10000"),
        current_week_revenue=Decimal("50000"),
        previous_week_revenue=Decimal("50000")
    ):
        today = date.today()
        current_start = today - timedelta(days=7)
        previous_start = today - timedelta(days=14)

        # Seed fact_ad_spend
        for i in range(7):
            spend_date = current_start + timedelta(days=i)
            await test_db_session.execute(text("""
                INSERT INTO analytics.fact_ad_spend
                (tenant_id, spend_date, ad_platform, spend)
                VALUES (:tenant_id, :spend_date, 'meta', :spend)
            """), {
                "tenant_id": str(tenant_id),
                "spend_date": spend_date,
                "spend": float(current_week_spend / 7)
            })

        for i in range(7):
            spend_date = previous_start + timedelta(days=i)
            await test_db_session.execute(text("""
                INSERT INTO analytics.fact_ad_spend
                (tenant_id, spend_date, ad_platform, spend)
                VALUES (:tenant_id, :spend_date, 'meta', :spend)
            """), {
                "tenant_id": str(tenant_id),
                "spend_date": spend_date,
                "spend": float(previous_week_spend / 7)
            })

        # Seed fact_orders
        for i in range(7):
            order_date = current_start + timedelta(days=i)
            await test_db_session.execute(text("""
                INSERT INTO analytics.fact_orders
                (tenant_id, order_date, total_price, order_id)
                VALUES (:tenant_id, :order_date, :price, :order_id)
            """), {
                "tenant_id": str(tenant_id),
                "order_date": order_date,
                "price": float(current_week_revenue / 7),
                "order_id": str(uuid4())
            })

        for i in range(7):
            order_date = previous_start + timedelta(days=i)
            await test_db_session.execute(text("""
                INSERT INTO analytics.fact_orders
                (tenant_id, order_date, total_price, order_id)
                VALUES (:tenant_id, :order_date, :price, :order_id)
            """), {
                "tenant_id": str(tenant_id),
                "order_date": order_date,
                "price": float(previous_week_revenue / 7),
                "order_id": str(uuid4())
            })

        await test_db_session.commit()

    return _seed


@pytest.fixture
def mock_entitlements():
    """Mock entitlement service for tests."""
    from unittest.mock import AsyncMock

    mock = AsyncMock()
    mock.check_feature.return_value = True

    return mock
```

---

## 10. Implementation Phases

### Phase 1: Foundation (Days 1-3)
| Task | Description | Files |
|------|-------------|-------|
| 1.1 | Create database migration | `db/migrations/ai_insights_schema.sql` |
| 1.2 | Define data models | `backend/src/insights/models.py` |
| 1.3 | Create configuration schema | `backend/src/insights/config.py`, `config/insights.json` |
| 1.4 | Implement base detector interface | `backend/src/insights/detectors/base.py` |
| 1.5 | Implement detector registry | `backend/src/insights/detectors/registry.py` |

### Phase 2: Metrics & Detection (Days 4-7)
| Task | Description | Files |
|------|-------------|-------|
| 2.1 | Implement metrics fetcher | `backend/src/insights/metrics/fetcher.py` |
| 2.2 | Implement spend anomaly detector | `backend/src/insights/detectors/spend_anomaly.py` |
| 2.3 | Implement ROAS change detector | `backend/src/insights/detectors/roas_change.py` |
| 2.4 | Implement divergence detector | `backend/src/insights/detectors/revenue_spend_divergence.py` |
| 2.5 | Implement channel mix detector | `backend/src/insights/detectors/channel_mix_shift.py` |
| 2.6 | Implement confidence calculator | `backend/src/insights/stats/confidence.py` |

### Phase 3: Service Layer (Days 8-10)
| Task | Description | Files |
|------|-------------|-------|
| 3.1 | Implement summary formatter | `backend/src/insights/formatters/summary.py` |
| 3.2 | Implement insight repository | `backend/src/insights/repository.py` |
| 3.3 | Implement main insight service | `backend/src/insights/service.py` |
| 3.4 | Add entitlement integration | `backend/src/entitlements/rules.py` (update) |

### Phase 4: Scheduling & Jobs (Days 11-12)
| Task | Description | Files |
|------|-------------|-------|
| 4.1 | Implement generation job | `backend/src/jobs/insight_generation.py` |
| 4.2 | Configure render cron jobs | `render.yaml` (update) |
| 4.3 | Add logging and monitoring | `backend/src/insights/monitoring.py` |

### Phase 5: API & Testing (Days 13-15)
| Task | Description | Files |
|------|-------------|-------|
| 5.1 | Create insights API endpoint | `backend/src/api/routes/insights.py` |
| 5.2 | Write unit tests | `backend/src/tests/insights/test_*.py` |
| 5.3 | Write integration tests | `backend/src/tests/insights/test_service_integration.py` |
| 5.4 | Documentation | `docs/insights/README.md` |

---

## 11. Security & Compliance

### 11.1 Data Access Controls

| Control | Implementation |
|---------|----------------|
| **Tenant Isolation** | All queries filtered by `tenant_id` from JWT |
| **No Raw Data** | Only aggregated marts accessed |
| **No PII** | Metrics are aggregated, no customer-level data |
| **No Cross-Tenant** | Repository pattern enforces tenant boundary |
| **Read-Only** | Service only reads marts, writes to `ai_insights` |
| **No External APIs** | No LLM calls, external services |

### 11.2 Audit Trail

```python
# All insight generations are logged with:
{
    "event": "insight_generated",
    "tenant_id": "uuid",
    "insight_id": "uuid",
    "insight_type": "spend_anomaly",
    "confidence_score": 0.85,
    "generated_at": "2026-01-28T06:00:00Z",
    "model_version": "v1.0"
}
```

### 11.3 Rate Limiting

- Daily insights: 1 run per tenant per day
- Hourly insights: 1 run per tenant per hour (enterprise only)
- Maximum 10 insights per run per tenant

---

## 12. File Structure

```
backend/src/
├── insights/
│   ├── __init__.py
│   ├── config.py                    # Configuration & thresholds
│   ├── models.py                    # Data models (Insight, InsightCandidate, etc.)
│   ├── service.py                   # Main orchestrator service
│   ├── repository.py                # Data access layer
│   ├── monitoring.py                # Logging & metrics
│   │
│   ├── detectors/
│   │   ├── __init__.py
│   │   ├── base.py                  # Base detector interface
│   │   ├── registry.py              # Detector registry & enums
│   │   ├── spend_anomaly.py         # Spend anomaly detection
│   │   ├── roas_change.py           # ROAS change detection
│   │   ├── revenue_spend_divergence.py
│   │   └── channel_mix_shift.py
│   │
│   ├── metrics/
│   │   ├── __init__.py
│   │   └── fetcher.py               # Metrics aggregation from marts
│   │
│   ├── stats/
│   │   ├── __init__.py
│   │   └── confidence.py            # Statistical confidence calculation
│   │
│   └── formatters/
│       ├── __init__.py
│       └── summary.py               # Natural language generation
│
├── jobs/
│   └── insight_generation.py        # Scheduled job implementation
│
├── api/routes/
│   └── insights.py                  # API endpoints
│
└── tests/insights/
    ├── __init__.py
    ├── conftest.py                  # Test fixtures
    ├── test_detectors.py            # Detector unit tests
    ├── test_confidence.py           # Statistical tests
    ├── test_formatter.py            # Summary generation tests
    └── test_service_integration.py  # Integration tests

config/
└── insights.json                    # Threshold configuration

db/migrations/
└── ai_insights_schema.sql           # Database schema

docs/
└── plans/
    └── EPIC-8-AI-INSIGHT-GENERATION.md  # This document
```

---

## Appendix A: API Endpoint Specification

### GET /api/insights

**Description**: Retrieve active insights for the authenticated tenant.

**Request**:
```
GET /api/insights?limit=20&insight_type=spend_anomaly
Authorization: Bearer <jwt>
```

**Response**:
```json
{
  "insights": [
    {
      "id": "uuid",
      "insight_type": "spend_anomaly",
      "insight_category": "anomaly",
      "summary": "Marketing spend increased 25% week-over-week to $12,500...",
      "supporting_metrics": [...],
      "confidence_score": 0.85,
      "severity": "warning",
      "analysis_period_start": "2026-01-20",
      "analysis_period_end": "2026-01-26",
      "generated_at": "2026-01-27T06:00:00Z",
      "status": "active"
    }
  ],
  "total": 5,
  "limit": 20,
  "offset": 0
}
```

### POST /api/insights/{id}/dismiss

**Description**: Dismiss an insight (user action).

**Request**:
```
POST /api/insights/uuid/dismiss
Authorization: Bearer <jwt>
```

**Response**:
```json
{
  "success": true,
  "dismissed_at": "2026-01-28T10:30:00Z"
}
```

---

## Appendix B: Entitlement Configuration

Add to `config/plans.json`:

```json
{
  "features": {
    "ai_insights": {
      "description": "AI-generated performance insights",
      "plans": ["growth", "scale", "enterprise"]
    },
    "ai_insights_hourly": {
      "description": "Hourly AI insight generation",
      "plans": ["enterprise"]
    }
  }
}
```

---

## Summary

This plan provides a complete implementation blueprint for the AI Insight Generation service, covering:

- **Architecture**: Multi-tenant, scheduled insight generation from dbt marts
- **Detection**: Statistical anomaly detection with configurable thresholds
- **Output**: Natural language summaries with confidence scores
- **Security**: Strict tenant isolation, no PII, read-only analytics
- **Testing**: Comprehensive unit and integration tests for determinism
- **Operations**: Cron-based scheduling with logging and monitoring

The implementation follows existing codebase patterns and integrates with the entitlements system for feature gating.
