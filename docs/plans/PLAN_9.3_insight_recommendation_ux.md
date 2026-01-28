# PLAN: Story 9.3 — Insight & Recommendation UX

**Version:** 1.0.0
**Date:** 2026-01-28
**Status:** Draft
**Story:** 9.3 - Insight Feed + Contextual Surfacing

---

## Table of Contents

1. [Overview](#1-overview)
2. [Architecture](#2-architecture)
3. [API Endpoints](#3-api-endpoints)
4. [Frontend Services](#4-frontend-services)
5. [UI Components](#5-ui-components)
6. [Page Structure](#6-page-structure)
7. [State Management](#7-state-management)
8. [Testing Plan](#8-testing-plan)
9. [Implementation Checklist](#9-implementation-checklist)

---

## 1. Overview

### 1.1 Purpose

Build UI surfaces for AI insights and recommendations that are:
- **Visible but not interruptive** - Users notice them when relevant
- **Contextual** - Appear where users already work (dashboards, campaign views)
- **Read-only** - Display only, no direct actions from insight cards
- **Dismissible but recoverable** - Users can hide and restore insights

### 1.2 User Story

> As a user, I want insights in a feed and inline on dashboards so that I notice them when they matter.

### 1.3 Requirements

| Requirement | Description |
|-------------|-------------|
| Central Insights Feed | Dedicated page listing all insights with filtering |
| Contextual Badges | Badge counts on navigation/dashboard indicating unread insights |
| Inline Dashboard Surfacing | Insight panel embedded within Analytics page |
| Read-only Display | Insights are informational, no action buttons |
| Dismissible | Users can dismiss insights to hide them |
| Recoverable | Dismissed insights can be viewed and restored |

### 1.4 Design Principles

1. **Non-interruptive** - No modals, no forced attention
2. **Progressive disclosure** - Summary first, details on demand
3. **Tenant isolation** - All data scoped via JWT tenant_id
4. **Entitlement gated** - AI_INSIGHTS feature required
5. **Performance** - Efficient polling, minimal re-renders

---

## 2. Architecture

### 2.1 Component Diagram

```
┌─────────────────────────────────────────────────────────────────────────┐
│                          Insight & Recommendation UX                     │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                          │
│  ┌─────────────────────────────────────────────────────────────────┐    │
│  │                        Navigation Bar                            │    │
│  │  ┌──────────────────┐                                            │    │
│  │  │ Insights (Badge) │  ← Unread count from /api/insights/summary │    │
│  │  └──────────────────┘                                            │    │
│  └─────────────────────────────────────────────────────────────────┘    │
│                                                                          │
│  ┌──────────────────────────┐    ┌──────────────────────────────────┐   │
│  │     Insights Page        │    │        Analytics Page             │   │
│  │                          │    │                                   │   │
│  │  ┌────────────────────┐  │    │  ┌─────────────────────────────┐ │   │
│  │  │   Filter Bar       │  │    │  │   Dashboard Selector        │ │   │
│  │  │ [Type] [Severity]  │  │    │  └─────────────────────────────┘ │   │
│  │  │ [Show Dismissed]   │  │    │                                   │   │
│  │  └────────────────────┘  │    │  ┌─────────────────────────────┐ │   │
│  │                          │    │  │   InsightsSummaryPanel      │ │   │
│  │  ┌────────────────────┐  │    │  │   (collapsed by default)    │ │   │
│  │  │   InsightCard      │  │    │  │   "3 new insights"          │ │   │
│  │  │   - Summary        │  │    │  └─────────────────────────────┘ │   │
│  │  │   - Severity Badge │  │    │                                   │   │
│  │  │   - Why It Matters │  │    │  ┌─────────────────────────────┐ │   │
│  │  │   - Metrics        │  │    │  │   Superset Dashboard        │ │   │
│  │  │   - [Dismiss]      │  │    │  │   (iframe)                  │ │   │
│  │  └────────────────────┘  │    │  └─────────────────────────────┘ │   │
│  │                          │    │                                   │   │
│  │  ┌────────────────────┐  │    └──────────────────────────────────┘   │
│  │  │   InsightCard      │  │                                           │
│  │  │   ...              │  │                                           │
│  │  └────────────────────┘  │                                           │
│  │                          │                                           │
│  │  ┌────────────────────┐  │                                           │
│  │  │   Load More        │  │                                           │
│  │  └────────────────────┘  │                                           │
│  └──────────────────────────┘                                           │
│                                                                          │
└─────────────────────────────────────────────────────────────────────────┘
```

### 2.2 Data Flow

```
┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
│   Backend API   │────▶│  Frontend       │────▶│   UI Components │
│                 │     │  Services       │     │                 │
│ /api/insights   │     │ insightsApi.ts  │     │ InsightCard     │
│ /api/recommend- │     │ recommendationsA│     │ InsightFeed     │
│   ations        │     │   pi.ts         │     │ InsightBadge    │
└─────────────────┘     └─────────────────┘     └─────────────────┘
         │                      │                       │
         │                      │                       │
         ▼                      ▼                       ▼
┌─────────────────────────────────────────────────────────────────┐
│                         React Context                            │
│  InsightsContext: { insights, unreadCount, loading, actions }   │
└─────────────────────────────────────────────────────────────────┘
```

---

## 3. API Endpoints

### 3.1 Existing Endpoints (No Changes Required)

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/insights` | List insights with pagination & filters |
| GET | `/api/insights/{id}` | Get single insight |
| PATCH | `/api/insights/{id}/read` | Mark as read |
| PATCH | `/api/insights/{id}/dismiss` | Dismiss insight |
| POST | `/api/insights/batch/read` | Batch mark as read |
| GET | `/api/recommendations` | List recommendations |
| GET | `/api/recommendations/{id}` | Get single recommendation |
| PATCH | `/api/recommendations/{id}/dismiss` | Dismiss recommendation |

### 3.2 New Endpoints

#### 3.2.1 GET `/api/insights/summary`

Returns aggregated counts for badge display.

**Purpose:** Efficient endpoint for navigation badge - single query instead of full list.

**Response:**
```json
{
  "total_unread": 5,
  "total_active": 12,
  "by_severity": {
    "critical": 1,
    "warning": 2,
    "info": 2
  },
  "by_type": {
    "spend_anomaly": 2,
    "roas_change": 1,
    "cac_anomaly": 2
  }
}
```

**Implementation:** `backend/src/api/routes/insights.py`

```python
class InsightsSummaryResponse(BaseModel):
    """Summary counts for badge display."""
    total_unread: int
    total_active: int
    by_severity: dict[str, int]
    by_type: dict[str, int]


@router.get(
    "/summary",
    response_model=InsightsSummaryResponse,
)
async def get_insights_summary(
    request: Request,
    db_session=Depends(check_ai_insights_entitlement),
):
    """
    Get aggregated insight counts for badge display.

    Efficient endpoint that returns counts without full insight data.
    Used for navigation badges and dashboard summary panels.

    SECURITY: Scoped to authenticated tenant.
    """
    tenant_ctx = get_tenant_context(request)

    # Count unread, non-dismissed
    total_unread = (
        db_session.query(func.count(AIInsight.id))
        .filter(
            AIInsight.tenant_id == tenant_ctx.tenant_id,
            AIInsight.is_read == 0,
            AIInsight.is_dismissed == 0,
        )
        .scalar()
    )

    # Count all active (non-dismissed)
    total_active = (
        db_session.query(func.count(AIInsight.id))
        .filter(
            AIInsight.tenant_id == tenant_ctx.tenant_id,
            AIInsight.is_dismissed == 0,
        )
        .scalar()
    )

    # Count by severity (active only)
    severity_counts = (
        db_session.query(AIInsight.severity, func.count(AIInsight.id))
        .filter(
            AIInsight.tenant_id == tenant_ctx.tenant_id,
            AIInsight.is_dismissed == 0,
            AIInsight.is_read == 0,
        )
        .group_by(AIInsight.severity)
        .all()
    )

    # Count by type (active only)
    type_counts = (
        db_session.query(AIInsight.insight_type, func.count(AIInsight.id))
        .filter(
            AIInsight.tenant_id == tenant_ctx.tenant_id,
            AIInsight.is_dismissed == 0,
            AIInsight.is_read == 0,
        )
        .group_by(AIInsight.insight_type)
        .all()
    )

    return InsightsSummaryResponse(
        total_unread=total_unread or 0,
        total_active=total_active or 0,
        by_severity={s.value: c for s, c in severity_counts if s},
        by_type={t.value: c for t, c in type_counts if t},
    )
```

#### 3.2.2 PATCH `/api/insights/{id}/restore`

Restores a dismissed insight.

**Purpose:** Allow users to undo dismiss action.

**Response:**
```json
{
  "status": "ok",
  "insight_id": "abc-123"
}
```

**Implementation:**

```python
@router.patch(
    "/{insight_id}/restore",
    response_model=InsightActionResponse,
)
async def restore_insight(
    request: Request,
    insight_id: str,
    db_session=Depends(check_ai_insights_entitlement),
):
    """
    Restore a dismissed insight (undismiss).

    Makes the insight visible again in the default list.

    SECURITY: Only restores insight if it belongs to the authenticated tenant.
    """
    tenant_ctx = get_tenant_context(request)

    insight = (
        db_session.query(AIInsight)
        .filter(
            AIInsight.id == insight_id,
            AIInsight.tenant_id == tenant_ctx.tenant_id,
        )
        .first()
    )

    if not insight:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Insight not found",
        )

    insight.is_dismissed = 0
    db_session.commit()

    logger.info(
        "Insight restored",
        extra={
            "tenant_id": tenant_ctx.tenant_id,
            "insight_id": insight_id,
        },
    )

    return InsightActionResponse(status="ok", insight_id=insight_id)
```

#### 3.2.3 GET `/api/recommendations/summary`

Returns aggregated counts for recommendations.

**Response:**
```json
{
  "total_pending": 3,
  "total_active": 8,
  "by_priority": {
    "high": 1,
    "medium": 2,
    "low": 0
  }
}
```

#### 3.2.4 PATCH `/api/recommendations/{id}/restore`

Restores a dismissed recommendation.

---

## 4. Frontend Services

### 4.1 File: `frontend/src/services/insightsApi.ts`

```typescript
/**
 * Insights API Service
 *
 * Provides typed API client for AI insights endpoints.
 * All requests include JWT auth header automatically via fetch wrapper.
 */

import { fetchWithAuth } from './apiClient';

// =============================================================================
// Types
// =============================================================================

export type InsightType =
  | 'spend_anomaly'
  | 'roas_change'
  | 'revenue_vs_spend_divergence'
  | 'channel_mix_shift'
  | 'cac_anomaly'
  | 'aov_change';

export type InsightSeverity = 'info' | 'warning' | 'critical';

export interface SupportingMetric {
  metric: string;
  previous: number | null;
  current: number | null;
  change: number | null;
  change_pct: number | null;
}

export interface Insight {
  insight_id: string;
  insight_type: InsightType;
  severity: InsightSeverity;
  summary: string;
  why_it_matters: string | null;
  supporting_metrics: SupportingMetric[];
  timeframe: string;
  confidence_score: number;
  platform: string | null;
  campaign_id: string | null;
  currency: string | null;
  generated_at: string;
  is_read: boolean;
  is_dismissed: boolean;
}

export interface InsightsListResponse {
  insights: Insight[];
  total: number;
  has_more: boolean;
}

export interface InsightsSummary {
  total_unread: number;
  total_active: number;
  by_severity: Record<InsightSeverity, number>;
  by_type: Record<InsightType, number>;
}

export interface InsightsListParams {
  insight_type?: InsightType;
  severity?: InsightSeverity;
  include_dismissed?: boolean;
  include_read?: boolean;
  limit?: number;
  offset?: number;
}

// =============================================================================
// API Functions
// =============================================================================

const BASE_URL = '/api/insights';

/**
 * Fetch insights summary for badge display.
 */
export async function getInsightsSummary(): Promise<InsightsSummary> {
  const response = await fetchWithAuth(`${BASE_URL}/summary`);
  if (!response.ok) {
    throw new Error(`Failed to fetch insights summary: ${response.status}`);
  }
  return response.json();
}

/**
 * List insights with optional filters.
 */
export async function listInsights(
  params: InsightsListParams = {}
): Promise<InsightsListResponse> {
  const searchParams = new URLSearchParams();

  if (params.insight_type) searchParams.set('insight_type', params.insight_type);
  if (params.severity) searchParams.set('severity', params.severity);
  if (params.include_dismissed !== undefined) {
    searchParams.set('include_dismissed', String(params.include_dismissed));
  }
  if (params.include_read !== undefined) {
    searchParams.set('include_read', String(params.include_read));
  }
  if (params.limit) searchParams.set('limit', String(params.limit));
  if (params.offset) searchParams.set('offset', String(params.offset));

  const url = searchParams.toString()
    ? `${BASE_URL}?${searchParams}`
    : BASE_URL;

  const response = await fetchWithAuth(url);
  if (!response.ok) {
    throw new Error(`Failed to fetch insights: ${response.status}`);
  }
  return response.json();
}

/**
 * Get single insight by ID.
 */
export async function getInsight(insightId: string): Promise<Insight> {
  const response = await fetchWithAuth(`${BASE_URL}/${insightId}`);
  if (!response.ok) {
    throw new Error(`Failed to fetch insight: ${response.status}`);
  }
  return response.json();
}

/**
 * Mark insight as read.
 */
export async function markInsightRead(
  insightId: string
): Promise<{ status: string; insight_id: string }> {
  const response = await fetchWithAuth(`${BASE_URL}/${insightId}/read`, {
    method: 'PATCH',
  });
  if (!response.ok) {
    throw new Error(`Failed to mark insight read: ${response.status}`);
  }
  return response.json();
}

/**
 * Dismiss an insight.
 */
export async function dismissInsight(
  insightId: string
): Promise<{ status: string; insight_id: string }> {
  const response = await fetchWithAuth(`${BASE_URL}/${insightId}/dismiss`, {
    method: 'PATCH',
  });
  if (!response.ok) {
    throw new Error(`Failed to dismiss insight: ${response.status}`);
  }
  return response.json();
}

/**
 * Restore a dismissed insight.
 */
export async function restoreInsight(
  insightId: string
): Promise<{ status: string; insight_id: string }> {
  const response = await fetchWithAuth(`${BASE_URL}/${insightId}/restore`, {
    method: 'PATCH',
  });
  if (!response.ok) {
    throw new Error(`Failed to restore insight: ${response.status}`);
  }
  return response.json();
}

/**
 * Batch mark insights as read.
 */
export async function markInsightsReadBatch(
  insightIds: string[]
): Promise<{ status: string; updated: number }> {
  const response = await fetchWithAuth(`${BASE_URL}/batch/read`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(insightIds),
  });
  if (!response.ok) {
    throw new Error(`Failed to batch mark insights read: ${response.status}`);
  }
  return response.json();
}

// =============================================================================
// Display Helpers
// =============================================================================

/**
 * Get human-readable insight type label.
 */
export function getInsightTypeLabel(type: InsightType): string {
  const labels: Record<InsightType, string> = {
    spend_anomaly: 'Spend Anomaly',
    roas_change: 'ROAS Change',
    revenue_vs_spend_divergence: 'Revenue vs Spend Divergence',
    channel_mix_shift: 'Channel Mix Shift',
    cac_anomaly: 'CAC Anomaly',
    aov_change: 'AOV Change',
  };
  return labels[type] || type;
}

/**
 * Get Polaris Badge tone for severity.
 */
export function getSeverityBadgeTone(
  severity: InsightSeverity
): 'info' | 'warning' | 'critical' {
  const tones: Record<InsightSeverity, 'info' | 'warning' | 'critical'> = {
    info: 'info',
    warning: 'warning',
    critical: 'critical',
  };
  return tones[severity] || 'info';
}

/**
 * Format metric change for display.
 */
export function formatMetricChange(
  change: number | null,
  changePct: number | null
): string {
  if (change === null && changePct === null) return 'N/A';

  const parts: string[] = [];

  if (change !== null) {
    const sign = change >= 0 ? '+' : '';
    parts.push(`${sign}${change.toLocaleString()}`);
  }

  if (changePct !== null) {
    const sign = changePct >= 0 ? '+' : '';
    parts.push(`(${sign}${changePct.toFixed(1)}%)`);
  }

  return parts.join(' ');
}

/**
 * Format relative time for insight.
 */
export function formatInsightTime(generatedAt: string): string {
  const date = new Date(generatedAt);
  const now = new Date();
  const diffMs = now.getTime() - date.getTime();
  const diffMins = Math.floor(diffMs / 60000);
  const diffHours = Math.floor(diffMins / 60);
  const diffDays = Math.floor(diffHours / 24);

  if (diffMins < 60) return `${diffMins}m ago`;
  if (diffHours < 24) return `${diffHours}h ago`;
  if (diffDays < 7) return `${diffDays}d ago`;
  return date.toLocaleDateString();
}
```

### 4.2 File: `frontend/src/services/recommendationsApi.ts`

```typescript
/**
 * Recommendations API Service
 *
 * Provides typed API client for AI recommendations endpoints.
 */

import { fetchWithAuth } from './apiClient';

// =============================================================================
// Types
// =============================================================================

export type RecommendationType =
  | 'increase_budget'
  | 'decrease_budget'
  | 'pause_campaign'
  | 'reallocate_spend'
  | 'investigate_anomaly';

export type RecommendationPriority = 'low' | 'medium' | 'high';
export type EstimatedImpact = 'minimal' | 'moderate' | 'significant';
export type RiskLevel = 'low' | 'medium' | 'high';

export interface Recommendation {
  recommendation_id: string;
  related_insight_id: string;
  recommendation_type: RecommendationType;
  priority: RecommendationPriority;
  recommendation_text: string;
  rationale: string | null;
  estimated_impact: EstimatedImpact;
  risk_level: RiskLevel;
  confidence_score: number;
  affected_entity: string | null;
  affected_entity_type: string | null;
  currency: string | null;
  generated_at: string;
  is_accepted: boolean;
  is_dismissed: boolean;
}

export interface RecommendationsListResponse {
  recommendations: Recommendation[];
  total: number;
  has_more: boolean;
}

export interface RecommendationsSummary {
  total_pending: number;
  total_active: number;
  by_priority: Record<RecommendationPriority, number>;
}

export interface RecommendationsListParams {
  recommendation_type?: RecommendationType;
  priority?: RecommendationPriority;
  risk_level?: RiskLevel;
  related_insight_id?: string;
  include_dismissed?: boolean;
  include_accepted?: boolean;
  limit?: number;
  offset?: number;
}

// =============================================================================
// API Functions
// =============================================================================

const BASE_URL = '/api/recommendations';

/**
 * Fetch recommendations summary.
 */
export async function getRecommendationsSummary(): Promise<RecommendationsSummary> {
  const response = await fetchWithAuth(`${BASE_URL}/summary`);
  if (!response.ok) {
    throw new Error(`Failed to fetch recommendations summary: ${response.status}`);
  }
  return response.json();
}

/**
 * List recommendations with optional filters.
 */
export async function listRecommendations(
  params: RecommendationsListParams = {}
): Promise<RecommendationsListResponse> {
  const searchParams = new URLSearchParams();

  if (params.recommendation_type) {
    searchParams.set('recommendation_type', params.recommendation_type);
  }
  if (params.priority) searchParams.set('priority', params.priority);
  if (params.risk_level) searchParams.set('risk_level', params.risk_level);
  if (params.related_insight_id) {
    searchParams.set('related_insight_id', params.related_insight_id);
  }
  if (params.include_dismissed !== undefined) {
    searchParams.set('include_dismissed', String(params.include_dismissed));
  }
  if (params.include_accepted !== undefined) {
    searchParams.set('include_accepted', String(params.include_accepted));
  }
  if (params.limit) searchParams.set('limit', String(params.limit));
  if (params.offset) searchParams.set('offset', String(params.offset));

  const url = searchParams.toString()
    ? `${BASE_URL}?${searchParams}`
    : BASE_URL;

  const response = await fetchWithAuth(url);
  if (!response.ok) {
    throw new Error(`Failed to fetch recommendations: ${response.status}`);
  }
  return response.json();
}

/**
 * Get single recommendation by ID.
 */
export async function getRecommendation(
  recommendationId: string
): Promise<Recommendation> {
  const response = await fetchWithAuth(`${BASE_URL}/${recommendationId}`);
  if (!response.ok) {
    throw new Error(`Failed to fetch recommendation: ${response.status}`);
  }
  return response.json();
}

/**
 * Mark recommendation as accepted.
 */
export async function acceptRecommendation(
  recommendationId: string
): Promise<{ status: string; recommendation_id: string }> {
  const response = await fetchWithAuth(
    `${BASE_URL}/${recommendationId}/accept`,
    { method: 'PATCH' }
  );
  if (!response.ok) {
    throw new Error(`Failed to accept recommendation: ${response.status}`);
  }
  return response.json();
}

/**
 * Dismiss a recommendation.
 */
export async function dismissRecommendation(
  recommendationId: string
): Promise<{ status: string; recommendation_id: string }> {
  const response = await fetchWithAuth(
    `${BASE_URL}/${recommendationId}/dismiss`,
    { method: 'PATCH' }
  );
  if (!response.ok) {
    throw new Error(`Failed to dismiss recommendation: ${response.status}`);
  }
  return response.json();
}

/**
 * Restore a dismissed recommendation.
 */
export async function restoreRecommendation(
  recommendationId: string
): Promise<{ status: string; recommendation_id: string }> {
  const response = await fetchWithAuth(
    `${BASE_URL}/${recommendationId}/restore`,
    { method: 'PATCH' }
  );
  if (!response.ok) {
    throw new Error(`Failed to restore recommendation: ${response.status}`);
  }
  return response.json();
}

// =============================================================================
// Display Helpers
// =============================================================================

/**
 * Get Polaris Badge tone for priority.
 */
export function getPriorityBadgeTone(
  priority: RecommendationPriority
): 'info' | 'warning' | 'critical' {
  const tones: Record<RecommendationPriority, 'info' | 'warning' | 'critical'> = {
    low: 'info',
    medium: 'warning',
    high: 'critical',
  };
  return tones[priority] || 'info';
}

/**
 * Get Polaris Badge tone for risk level.
 */
export function getRiskBadgeTone(
  risk: RiskLevel
): 'success' | 'warning' | 'critical' {
  const tones: Record<RiskLevel, 'success' | 'warning' | 'critical'> = {
    low: 'success',
    medium: 'warning',
    high: 'critical',
  };
  return tones[risk] || 'success';
}
```

---

## 5. UI Components

### 5.1 InsightCard Component

**File:** `frontend/src/components/InsightCard.tsx`

```typescript
/**
 * Insight Card Component
 *
 * Displays a single AI insight in a card format.
 * Features:
 * - Severity badge with color coding
 * - Summary with "why it matters" expansion
 * - Supporting metrics with change indicators
 * - Dismiss/Restore actions
 * - Read tracking on expand
 */

import React, { useState, useCallback } from 'react';
import {
  Card,
  BlockStack,
  InlineStack,
  Text,
  Badge,
  Button,
  Collapsible,
  Box,
  Icon,
  Divider,
} from '@shopify/polaris';
import {
  AlertCircleIcon,
  InfoIcon,
  ChevronDownIcon,
  ChevronUpIcon,
  XIcon,
  RefreshIcon,
} from '@shopify/polaris-icons';

import type { Insight } from '../services/insightsApi';
import {
  getSeverityBadgeTone,
  getInsightTypeLabel,
  formatMetricChange,
  formatInsightTime,
} from '../services/insightsApi';

interface InsightCardProps {
  insight: Insight;
  onDismiss?: (insightId: string) => void;
  onRestore?: (insightId: string) => void;
  onRead?: (insightId: string) => void;
  showRestoreButton?: boolean;
}

const InsightCard: React.FC<InsightCardProps> = ({
  insight,
  onDismiss,
  onRestore,
  onRead,
  showRestoreButton = false,
}) => {
  const [expanded, setExpanded] = useState(false);

  // Mark as read when expanded for first time
  const handleToggleExpand = useCallback(() => {
    const newExpanded = !expanded;
    setExpanded(newExpanded);

    if (newExpanded && !insight.is_read && onRead) {
      onRead(insight.insight_id);
    }
  }, [expanded, insight.insight_id, insight.is_read, onRead]);

  // Get severity icon
  const getSeverityIcon = () => {
    switch (insight.severity) {
      case 'critical':
        return <Icon source={AlertCircleIcon} tone="critical" />;
      case 'warning':
        return <Icon source={AlertCircleIcon} tone="caution" />;
      default:
        return <Icon source={InfoIcon} tone="info" />;
    }
  };

  // Determine card background based on severity and read state
  const getCardBackground = () => {
    if (insight.is_dismissed) return 'bg-surface-secondary';
    if (!insight.is_read) {
      if (insight.severity === 'critical') return 'bg-surface-critical';
      if (insight.severity === 'warning') return 'bg-surface-warning';
    }
    return 'bg-surface';
  };

  return (
    <Box
      background={getCardBackground()}
      borderColor={!insight.is_read ? 'border-emphasis' : 'border'}
      borderWidth="025"
      borderRadius="200"
      padding="300"
    >
      <BlockStack gap="300">
        {/* Header Row */}
        <InlineStack align="space-between" blockAlign="start">
          <InlineStack gap="200" blockAlign="center">
            {getSeverityIcon()}
            <BlockStack gap="050">
              <Text
                as="span"
                variant="bodyMd"
                fontWeight={insight.is_read ? 'regular' : 'semibold'}
              >
                {insight.summary}
              </Text>
              <InlineStack gap="100">
                <Text as="span" variant="bodySm" tone="subdued">
                  {getInsightTypeLabel(insight.insight_type)}
                </Text>
                <Text as="span" variant="bodySm" tone="subdued">
                  •
                </Text>
                <Text as="span" variant="bodySm" tone="subdued">
                  {formatInsightTime(insight.generated_at)}
                </Text>
              </InlineStack>
            </BlockStack>
          </InlineStack>

          <InlineStack gap="100">
            <Badge tone={getSeverityBadgeTone(insight.severity)}>
              {insight.severity.toUpperCase()}
            </Badge>
            {!insight.is_read && (
              <Badge tone="attention">New</Badge>
            )}
          </InlineStack>
        </InlineStack>

        {/* Expand/Collapse Actions */}
        <InlineStack align="space-between">
          <Button
            variant="plain"
            onClick={handleToggleExpand}
            icon={expanded ? ChevronUpIcon : ChevronDownIcon}
          >
            {expanded ? 'Show less' : 'Show details'}
          </Button>

          <InlineStack gap="200">
            {showRestoreButton && insight.is_dismissed && onRestore && (
              <Button
                variant="plain"
                icon={RefreshIcon}
                onClick={() => onRestore(insight.insight_id)}
              >
                Restore
              </Button>
            )}
            {!insight.is_dismissed && onDismiss && (
              <Button
                variant="plain"
                icon={XIcon}
                onClick={() => onDismiss(insight.insight_id)}
              >
                Dismiss
              </Button>
            )}
          </InlineStack>
        </InlineStack>

        {/* Collapsible Details */}
        <Collapsible
          open={expanded}
          id={`insight-${insight.insight_id}-details`}
        >
          <BlockStack gap="300">
            <Divider />

            {/* Why It Matters */}
            {insight.why_it_matters && (
              <BlockStack gap="100">
                <Text as="h4" variant="headingSm">
                  Why it matters
                </Text>
                <Text as="p" variant="bodyMd">
                  {insight.why_it_matters}
                </Text>
              </BlockStack>
            )}

            {/* Supporting Metrics */}
            {insight.supporting_metrics.length > 0 && (
              <BlockStack gap="200">
                <Text as="h4" variant="headingSm">
                  Supporting metrics
                </Text>
                <Box
                  background="bg-surface-secondary"
                  padding="200"
                  borderRadius="100"
                >
                  <BlockStack gap="200">
                    {insight.supporting_metrics.map((metric, idx) => (
                      <InlineStack
                        key={idx}
                        align="space-between"
                        blockAlign="center"
                      >
                        <Text as="span" variant="bodySm">
                          {metric.metric}
                        </Text>
                        <InlineStack gap="200">
                          {metric.previous !== null && (
                            <Text as="span" variant="bodySm" tone="subdued">
                              {metric.previous.toLocaleString()}
                            </Text>
                          )}
                          <Text as="span" variant="bodySm">
                            →
                          </Text>
                          {metric.current !== null && (
                            <Text as="span" variant="bodySm" fontWeight="medium">
                              {metric.current.toLocaleString()}
                            </Text>
                          )}
                          <Text
                            as="span"
                            variant="bodySm"
                            tone={
                              (metric.change_pct ?? 0) >= 0 ? 'success' : 'critical'
                            }
                          >
                            {formatMetricChange(metric.change, metric.change_pct)}
                          </Text>
                        </InlineStack>
                      </InlineStack>
                    ))}
                  </BlockStack>
                </Box>
              </BlockStack>
            )}

            {/* Metadata */}
            <InlineStack gap="400" wrap>
              <BlockStack gap="050">
                <Text as="span" variant="bodySm" tone="subdued">
                  Timeframe
                </Text>
                <Text as="span" variant="bodySm">
                  {insight.timeframe}
                </Text>
              </BlockStack>

              <BlockStack gap="050">
                <Text as="span" variant="bodySm" tone="subdued">
                  Confidence
                </Text>
                <Text as="span" variant="bodySm">
                  {(insight.confidence_score * 100).toFixed(0)}%
                </Text>
              </BlockStack>

              {insight.platform && (
                <BlockStack gap="050">
                  <Text as="span" variant="bodySm" tone="subdued">
                    Platform
                  </Text>
                  <Text as="span" variant="bodySm">
                    {insight.platform.replace('_', ' ').toUpperCase()}
                  </Text>
                </BlockStack>
              )}
            </InlineStack>
          </BlockStack>
        </Collapsible>
      </BlockStack>
    </Box>
  );
};

export default InsightCard;
```

### 5.2 InsightBadge Component

**File:** `frontend/src/components/InsightBadge.tsx`

```typescript
/**
 * Insight Badge Component
 *
 * Displays unread insight count as a navigation badge.
 * Used in navigation items to indicate new insights.
 */

import React from 'react';
import { Badge, InlineStack, Text } from '@shopify/polaris';

interface InsightBadgeProps {
  count: number;
  hasCritical?: boolean;
}

const InsightBadge: React.FC<InsightBadgeProps> = ({
  count,
  hasCritical = false,
}) => {
  if (count === 0) return null;

  const displayCount = count > 99 ? '99+' : String(count);
  const tone = hasCritical ? 'critical' : 'attention';

  return (
    <Badge tone={tone} size="small">
      {displayCount}
    </Badge>
  );
};

export default InsightBadge;
```

### 5.3 InsightsSummaryPanel Component

**File:** `frontend/src/components/InsightsSummaryPanel.tsx`

```typescript
/**
 * Insights Summary Panel Component
 *
 * Compact panel showing insight summary for dashboard embedding.
 * Shows unread count with breakdown by severity.
 * Expandable to show recent insights inline.
 */

import React, { useState, useEffect } from 'react';
import {
  Card,
  BlockStack,
  InlineStack,
  Text,
  Badge,
  Button,
  Collapsible,
  SkeletonBodyText,
  Link,
} from '@shopify/polaris';
import { ChevronDownIcon, ChevronUpIcon } from '@shopify/polaris-icons';

import type { Insight, InsightsSummary } from '../services/insightsApi';
import {
  getInsightsSummary,
  listInsights,
  getSeverityBadgeTone,
} from '../services/insightsApi';
import InsightCard from './InsightCard';

interface InsightsSummaryPanelProps {
  onNavigateToFeed?: () => void;
  onDismiss?: (insightId: string) => void;
  onRead?: (insightId: string) => void;
  maxPreviewInsights?: number;
}

const InsightsSummaryPanel: React.FC<InsightsSummaryPanelProps> = ({
  onNavigateToFeed,
  onDismiss,
  onRead,
  maxPreviewInsights = 3,
}) => {
  const [summary, setSummary] = useState<InsightsSummary | null>(null);
  const [recentInsights, setRecentInsights] = useState<Insight[]>([]);
  const [expanded, setExpanded] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Fetch summary and recent insights
  useEffect(() => {
    const fetchData = async () => {
      try {
        setLoading(true);
        const [summaryData, insightsData] = await Promise.all([
          getInsightsSummary(),
          listInsights({
            include_read: false,
            limit: maxPreviewInsights,
          }),
        ]);
        setSummary(summaryData);
        setRecentInsights(insightsData.insights);
      } catch (err) {
        console.error('Failed to fetch insights summary:', err);
        setError('Unable to load insights');
      } finally {
        setLoading(false);
      }
    };

    fetchData();
  }, [maxPreviewInsights]);

  // Don't render if no insights
  if (!loading && summary?.total_unread === 0) {
    return null;
  }

  // Loading state
  if (loading) {
    return (
      <Card>
        <SkeletonBodyText lines={2} />
      </Card>
    );
  }

  // Error state
  if (error) {
    return null; // Fail silently for non-critical feature
  }

  const hasCritical = (summary?.by_severity?.critical ?? 0) > 0;

  return (
    <Card>
      <BlockStack gap="300">
        {/* Summary Header */}
        <InlineStack align="space-between" blockAlign="center">
          <InlineStack gap="200" blockAlign="center">
            <Text as="h3" variant="headingMd">
              AI Insights
            </Text>
            <Badge tone={hasCritical ? 'critical' : 'attention'}>
              {summary?.total_unread} new
            </Badge>
          </InlineStack>

          <InlineStack gap="200">
            {summary?.by_severity?.critical && (
              <Badge tone="critical">
                {summary.by_severity.critical} critical
              </Badge>
            )}
            {summary?.by_severity?.warning && (
              <Badge tone="warning">
                {summary.by_severity.warning} warning
              </Badge>
            )}
          </InlineStack>
        </InlineStack>

        {/* Expand Toggle */}
        {recentInsights.length > 0 && (
          <Button
            variant="plain"
            onClick={() => setExpanded(!expanded)}
            icon={expanded ? ChevronUpIcon : ChevronDownIcon}
            fullWidth
            textAlign="left"
          >
            {expanded ? 'Hide recent insights' : 'Show recent insights'}
          </Button>
        )}

        {/* Collapsible Recent Insights */}
        <Collapsible open={expanded} id="insights-summary-recent">
          <BlockStack gap="200">
            {recentInsights.map((insight) => (
              <InsightCard
                key={insight.insight_id}
                insight={insight}
                onDismiss={onDismiss}
                onRead={onRead}
              />
            ))}

            {summary && summary.total_unread > maxPreviewInsights && (
              <InlineStack align="center">
                <Link onClick={onNavigateToFeed}>
                  View all {summary.total_unread} insights →
                </Link>
              </InlineStack>
            )}
          </BlockStack>
        </Collapsible>

        {/* View All Link (when collapsed) */}
        {!expanded && onNavigateToFeed && (
          <InlineStack align="end">
            <Link onClick={onNavigateToFeed}>View all insights →</Link>
          </InlineStack>
        )}
      </BlockStack>
    </Card>
  );
};

export default InsightsSummaryPanel;
```

### 5.4 RecommendationCard Component

**File:** `frontend/src/components/RecommendationCard.tsx`

```typescript
/**
 * Recommendation Card Component
 *
 * Displays a single AI recommendation in a card format.
 * Features:
 * - Priority and risk badges
 * - Recommendation text with rationale
 * - Impact estimation
 * - Accept/Dismiss actions (advisory only)
 */

import React, { useState, useCallback } from 'react';
import {
  Card,
  BlockStack,
  InlineStack,
  Text,
  Badge,
  Button,
  Collapsible,
  Box,
  Divider,
} from '@shopify/polaris';
import {
  ChevronDownIcon,
  ChevronUpIcon,
  CheckIcon,
  XIcon,
  RefreshIcon,
} from '@shopify/polaris-icons';

import type { Recommendation } from '../services/recommendationsApi';
import {
  getPriorityBadgeTone,
  getRiskBadgeTone,
} from '../services/recommendationsApi';

interface RecommendationCardProps {
  recommendation: Recommendation;
  onAccept?: (recommendationId: string) => void;
  onDismiss?: (recommendationId: string) => void;
  onRestore?: (recommendationId: string) => void;
  showRestoreButton?: boolean;
}

const RecommendationCard: React.FC<RecommendationCardProps> = ({
  recommendation,
  onAccept,
  onDismiss,
  onRestore,
  showRestoreButton = false,
}) => {
  const [expanded, setExpanded] = useState(false);

  return (
    <Box
      background={recommendation.is_dismissed ? 'bg-surface-secondary' : 'bg-surface'}
      borderColor="border"
      borderWidth="025"
      borderRadius="200"
      padding="300"
    >
      <BlockStack gap="300">
        {/* Header */}
        <InlineStack align="space-between" blockAlign="start">
          <BlockStack gap="100">
            <Text as="span" variant="bodyMd" fontWeight="semibold">
              {recommendation.recommendation_text}
            </Text>
            {recommendation.affected_entity && (
              <Text as="span" variant="bodySm" tone="subdued">
                {recommendation.affected_entity_type}: {recommendation.affected_entity}
              </Text>
            )}
          </BlockStack>

          <InlineStack gap="100">
            <Badge tone={getPriorityBadgeTone(recommendation.priority)}>
              {recommendation.priority.toUpperCase()}
            </Badge>
            <Badge tone={getRiskBadgeTone(recommendation.risk_level)}>
              Risk: {recommendation.risk_level}
            </Badge>
          </InlineStack>
        </InlineStack>

        {/* Actions */}
        <InlineStack align="space-between">
          <Button
            variant="plain"
            onClick={() => setExpanded(!expanded)}
            icon={expanded ? ChevronUpIcon : ChevronDownIcon}
          >
            {expanded ? 'Show less' : 'Show rationale'}
          </Button>

          <InlineStack gap="200">
            {showRestoreButton && recommendation.is_dismissed && onRestore && (
              <Button
                variant="plain"
                icon={RefreshIcon}
                onClick={() => onRestore(recommendation.recommendation_id)}
              >
                Restore
              </Button>
            )}
            {!recommendation.is_dismissed && !recommendation.is_accepted && (
              <>
                {onAccept && (
                  <Button
                    variant="plain"
                    icon={CheckIcon}
                    onClick={() => onAccept(recommendation.recommendation_id)}
                  >
                    Acknowledge
                  </Button>
                )}
                {onDismiss && (
                  <Button
                    variant="plain"
                    icon={XIcon}
                    onClick={() => onDismiss(recommendation.recommendation_id)}
                  >
                    Dismiss
                  </Button>
                )}
              </>
            )}
            {recommendation.is_accepted && (
              <Badge tone="success">Acknowledged</Badge>
            )}
          </InlineStack>
        </InlineStack>

        {/* Collapsible Details */}
        <Collapsible
          open={expanded}
          id={`recommendation-${recommendation.recommendation_id}-details`}
        >
          <BlockStack gap="300">
            <Divider />

            {/* Rationale */}
            {recommendation.rationale && (
              <BlockStack gap="100">
                <Text as="h4" variant="headingSm">
                  Rationale
                </Text>
                <Text as="p" variant="bodyMd">
                  {recommendation.rationale}
                </Text>
              </BlockStack>
            )}

            {/* Impact & Risk */}
            <InlineStack gap="400" wrap>
              <BlockStack gap="050">
                <Text as="span" variant="bodySm" tone="subdued">
                  Estimated Impact
                </Text>
                <Text as="span" variant="bodySm">
                  {recommendation.estimated_impact.charAt(0).toUpperCase() +
                    recommendation.estimated_impact.slice(1)}
                </Text>
              </BlockStack>

              <BlockStack gap="050">
                <Text as="span" variant="bodySm" tone="subdued">
                  Confidence
                </Text>
                <Text as="span" variant="bodySm">
                  {(recommendation.confidence_score * 100).toFixed(0)}%
                </Text>
              </BlockStack>
            </InlineStack>

            {/* Advisory Notice */}
            <Box
              background="bg-surface-info"
              padding="200"
              borderRadius="100"
            >
              <Text as="p" variant="bodySm" tone="subdued">
                This is an advisory recommendation. Acknowledging does not
                execute any action automatically.
              </Text>
            </Box>
          </BlockStack>
        </Collapsible>
      </BlockStack>
    </Box>
  );
};

export default RecommendationCard;
```

### 5.5 InsightsEmptyState Component

**File:** `frontend/src/components/InsightsEmptyState.tsx`

```typescript
/**
 * Insights Empty State Component
 *
 * Displayed when there are no insights to show.
 */

import React from 'react';
import { EmptyState, Text } from '@shopify/polaris';

interface InsightsEmptyStateProps {
  showDismissed?: boolean;
}

const InsightsEmptyState: React.FC<InsightsEmptyStateProps> = ({
  showDismissed = false,
}) => {
  return (
    <EmptyState
      heading={showDismissed ? 'No dismissed insights' : 'No insights yet'}
      image="https://cdn.shopify.com/s/files/1/0262/4071/2726/files/emptystate-files.png"
    >
      <Text as="p" variant="bodyMd" tone="subdued">
        {showDismissed
          ? "You haven't dismissed any insights. Dismissed insights will appear here."
          : 'AI insights will appear here as patterns are detected in your data. Check back after your next data sync.'}
      </Text>
    </EmptyState>
  );
};

export default InsightsEmptyState;
```

---

## 6. Page Structure

### 6.1 Insights Page

**File:** `frontend/src/pages/Insights.tsx`

```typescript
/**
 * Insights Page
 *
 * Central feed for all AI insights and recommendations.
 * Features:
 * - Tabbed view (Insights | Recommendations | Dismissed)
 * - Filtering by type and severity
 * - Infinite scroll pagination
 * - Mark all as read
 */

import React, { useState, useEffect, useCallback } from 'react';
import {
  Page,
  Layout,
  Card,
  Tabs,
  BlockStack,
  InlineStack,
  Select,
  Checkbox,
  Button,
  Spinner,
  Banner,
} from '@shopify/polaris';

import {
  listInsights,
  markInsightRead,
  dismissInsight,
  restoreInsight,
  markInsightsReadBatch,
  type Insight,
  type InsightType,
  type InsightSeverity,
} from '../services/insightsApi';
import {
  listRecommendations,
  acceptRecommendation,
  dismissRecommendation,
  restoreRecommendation,
  type Recommendation,
} from '../services/recommendationsApi';

import InsightCard from '../components/InsightCard';
import RecommendationCard from '../components/RecommendationCard';
import InsightsEmptyState from '../components/InsightsEmptyState';
import FeatureGate from '../components/FeatureGate';

const ITEMS_PER_PAGE = 20;

const Insights: React.FC = () => {
  // Tab state
  const [selectedTab, setSelectedTab] = useState(0);

  // Filter state
  const [typeFilter, setTypeFilter] = useState<InsightType | ''>('');
  const [severityFilter, setSeverityFilter] = useState<InsightSeverity | ''>('');

  // Data state
  const [insights, setInsights] = useState<Insight[]>([]);
  const [recommendations, setRecommendations] = useState<Recommendation[]>([]);
  const [dismissedInsights, setDismissedInsights] = useState<Insight[]>([]);

  // Pagination state
  const [hasMore, setHasMore] = useState(false);
  const [offset, setOffset] = useState(0);

  // Loading state
  const [loading, setLoading] = useState(true);
  const [loadingMore, setLoadingMore] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Fetch data based on selected tab
  const fetchData = useCallback(async (isLoadMore = false) => {
    try {
      if (isLoadMore) {
        setLoadingMore(true);
      } else {
        setLoading(true);
        setOffset(0);
      }

      const currentOffset = isLoadMore ? offset : 0;

      if (selectedTab === 0) {
        // Insights tab
        const response = await listInsights({
          insight_type: typeFilter || undefined,
          severity: severityFilter || undefined,
          include_dismissed: false,
          limit: ITEMS_PER_PAGE,
          offset: currentOffset,
        });

        if (isLoadMore) {
          setInsights((prev) => [...prev, ...response.insights]);
        } else {
          setInsights(response.insights);
        }
        setHasMore(response.has_more);
        setOffset(currentOffset + response.insights.length);
      } else if (selectedTab === 1) {
        // Recommendations tab
        const response = await listRecommendations({
          include_dismissed: false,
          limit: ITEMS_PER_PAGE,
          offset: currentOffset,
        });

        if (isLoadMore) {
          setRecommendations((prev) => [...prev, ...response.recommendations]);
        } else {
          setRecommendations(response.recommendations);
        }
        setHasMore(response.has_more);
        setOffset(currentOffset + response.recommendations.length);
      } else {
        // Dismissed tab
        const response = await listInsights({
          include_dismissed: true,
          limit: ITEMS_PER_PAGE,
          offset: currentOffset,
        });

        // Filter to only dismissed
        const dismissed = response.insights.filter((i) => i.is_dismissed);

        if (isLoadMore) {
          setDismissedInsights((prev) => [...prev, ...dismissed]);
        } else {
          setDismissedInsights(dismissed);
        }
        setHasMore(response.has_more);
        setOffset(currentOffset + dismissed.length);
      }

      setError(null);
    } catch (err) {
      console.error('Failed to fetch data:', err);
      setError('Failed to load insights. Please try again.');
    } finally {
      setLoading(false);
      setLoadingMore(false);
    }
  }, [selectedTab, typeFilter, severityFilter, offset]);

  // Initial load and tab/filter change
  useEffect(() => {
    fetchData(false);
  }, [selectedTab, typeFilter, severityFilter]);

  // Handlers
  const handleDismissInsight = async (insightId: string) => {
    try {
      await dismissInsight(insightId);
      setInsights((prev) => prev.filter((i) => i.insight_id !== insightId));
    } catch (err) {
      console.error('Failed to dismiss insight:', err);
    }
  };

  const handleRestoreInsight = async (insightId: string) => {
    try {
      await restoreInsight(insightId);
      setDismissedInsights((prev) =>
        prev.filter((i) => i.insight_id !== insightId)
      );
    } catch (err) {
      console.error('Failed to restore insight:', err);
    }
  };

  const handleReadInsight = async (insightId: string) => {
    try {
      await markInsightRead(insightId);
      setInsights((prev) =>
        prev.map((i) =>
          i.insight_id === insightId ? { ...i, is_read: true } : i
        )
      );
    } catch (err) {
      console.error('Failed to mark insight read:', err);
    }
  };

  const handleMarkAllRead = async () => {
    const unreadIds = insights
      .filter((i) => !i.is_read)
      .map((i) => i.insight_id);

    if (unreadIds.length === 0) return;

    try {
      await markInsightsReadBatch(unreadIds);
      setInsights((prev) =>
        prev.map((i) => ({ ...i, is_read: true }))
      );
    } catch (err) {
      console.error('Failed to mark all as read:', err);
    }
  };

  const handleDismissRecommendation = async (recommendationId: string) => {
    try {
      await dismissRecommendation(recommendationId);
      setRecommendations((prev) =>
        prev.filter((r) => r.recommendation_id !== recommendationId)
      );
    } catch (err) {
      console.error('Failed to dismiss recommendation:', err);
    }
  };

  const handleAcceptRecommendation = async (recommendationId: string) => {
    try {
      await acceptRecommendation(recommendationId);
      setRecommendations((prev) =>
        prev.map((r) =>
          r.recommendation_id === recommendationId
            ? { ...r, is_accepted: true }
            : r
        )
      );
    } catch (err) {
      console.error('Failed to accept recommendation:', err);
    }
  };

  // Tab configuration
  const tabs = [
    { id: 'insights', content: 'Insights', panelID: 'insights-panel' },
    { id: 'recommendations', content: 'Recommendations', panelID: 'recommendations-panel' },
    { id: 'dismissed', content: 'Dismissed', panelID: 'dismissed-panel' },
  ];

  // Filter options
  const typeOptions = [
    { label: 'All types', value: '' },
    { label: 'Spend Anomaly', value: 'spend_anomaly' },
    { label: 'ROAS Change', value: 'roas_change' },
    { label: 'Revenue vs Spend', value: 'revenue_vs_spend_divergence' },
    { label: 'Channel Mix Shift', value: 'channel_mix_shift' },
    { label: 'CAC Anomaly', value: 'cac_anomaly' },
    { label: 'AOV Change', value: 'aov_change' },
  ];

  const severityOptions = [
    { label: 'All severities', value: '' },
    { label: 'Critical', value: 'critical' },
    { label: 'Warning', value: 'warning' },
    { label: 'Info', value: 'info' },
  ];

  const unreadCount = insights.filter((i) => !i.is_read).length;

  return (
    <FeatureGate feature="AI_INSIGHTS">
      <Page
        title="AI Insights"
        subtitle="AI-generated insights and recommendations from your data"
        primaryAction={
          selectedTab === 0 && unreadCount > 0
            ? {
                content: `Mark all as read (${unreadCount})`,
                onAction: handleMarkAllRead,
              }
            : undefined
        }
      >
        <Layout>
          <Layout.Section>
            <Card padding="0">
              <Tabs tabs={tabs} selected={selectedTab} onSelect={setSelectedTab}>
                <Card.Section>
                  {/* Filters (Insights tab only) */}
                  {selectedTab === 0 && (
                    <BlockStack gap="400">
                      <InlineStack gap="300">
                        <Select
                          label="Type"
                          labelInline
                          options={typeOptions}
                          value={typeFilter}
                          onChange={(value) =>
                            setTypeFilter(value as InsightType | '')
                          }
                        />
                        <Select
                          label="Severity"
                          labelInline
                          options={severityOptions}
                          value={severityFilter}
                          onChange={(value) =>
                            setSeverityFilter(value as InsightSeverity | '')
                          }
                        />
                      </InlineStack>
                    </BlockStack>
                  )}
                </Card.Section>

                <Card.Section>
                  {/* Error Banner */}
                  {error && (
                    <Banner tone="critical" onDismiss={() => setError(null)}>
                      {error}
                    </Banner>
                  )}

                  {/* Loading State */}
                  {loading && (
                    <BlockStack gap="400" inlineAlign="center">
                      <Spinner size="large" />
                    </BlockStack>
                  )}

                  {/* Insights Tab Content */}
                  {!loading && selectedTab === 0 && (
                    <BlockStack gap="300">
                      {insights.length === 0 ? (
                        <InsightsEmptyState />
                      ) : (
                        <>
                          {insights.map((insight) => (
                            <InsightCard
                              key={insight.insight_id}
                              insight={insight}
                              onDismiss={handleDismissInsight}
                              onRead={handleReadInsight}
                            />
                          ))}

                          {hasMore && (
                            <InlineStack align="center">
                              <Button
                                onClick={() => fetchData(true)}
                                loading={loadingMore}
                              >
                                Load more
                              </Button>
                            </InlineStack>
                          )}
                        </>
                      )}
                    </BlockStack>
                  )}

                  {/* Recommendations Tab Content */}
                  {!loading && selectedTab === 1 && (
                    <BlockStack gap="300">
                      {recommendations.length === 0 ? (
                        <InsightsEmptyState />
                      ) : (
                        <>
                          {recommendations.map((rec) => (
                            <RecommendationCard
                              key={rec.recommendation_id}
                              recommendation={rec}
                              onAccept={handleAcceptRecommendation}
                              onDismiss={handleDismissRecommendation}
                            />
                          ))}

                          {hasMore && (
                            <InlineStack align="center">
                              <Button
                                onClick={() => fetchData(true)}
                                loading={loadingMore}
                              >
                                Load more
                              </Button>
                            </InlineStack>
                          )}
                        </>
                      )}
                    </BlockStack>
                  )}

                  {/* Dismissed Tab Content */}
                  {!loading && selectedTab === 2 && (
                    <BlockStack gap="300">
                      {dismissedInsights.length === 0 ? (
                        <InsightsEmptyState showDismissed />
                      ) : (
                        <>
                          {dismissedInsights.map((insight) => (
                            <InsightCard
                              key={insight.insight_id}
                              insight={insight}
                              onRestore={handleRestoreInsight}
                              showRestoreButton
                            />
                          ))}

                          {hasMore && (
                            <InlineStack align="center">
                              <Button
                                onClick={() => fetchData(true)}
                                loading={loadingMore}
                              >
                                Load more
                              </Button>
                            </InlineStack>
                          )}
                        </>
                      )}
                    </BlockStack>
                  )}
                </Card.Section>
              </Tabs>
            </Card>
          </Layout.Section>
        </Layout>
      </Page>
    </FeatureGate>
  );
};

export default Insights;
```

### 6.2 Analytics Page Update

Add `InsightsSummaryPanel` to the Analytics page.

**File:** `frontend/src/pages/Analytics.tsx` (Update)

```typescript
// Add import
import InsightsSummaryPanel from '../components/InsightsSummaryPanel';
import { useNavigate } from 'react-router-dom';

// Inside component, before the return:
const navigate = useNavigate();

const handleNavigateToInsights = () => {
  navigate('/insights');
};

// Add to Layout, before the dashboard selector:
<Layout.Section>
  <InsightsSummaryPanel
    onNavigateToFeed={handleNavigateToInsights}
  />
</Layout.Section>
```

---

## 7. State Management

### 7.1 InsightsContext (Optional Enhancement)

For apps needing global insight state (badge counts across pages), create a context.

**File:** `frontend/src/contexts/InsightsContext.tsx`

```typescript
/**
 * Insights Context
 *
 * Provides global access to insight summary data.
 * Used for navigation badges and cross-page state.
 */

import React, {
  createContext,
  useContext,
  useState,
  useEffect,
  useCallback,
  ReactNode,
} from 'react';
import {
  getInsightsSummary,
  type InsightsSummary,
} from '../services/insightsApi';

interface InsightsContextValue {
  summary: InsightsSummary | null;
  loading: boolean;
  error: string | null;
  refresh: () => Promise<void>;
}

const InsightsContext = createContext<InsightsContextValue | undefined>(
  undefined
);

interface InsightsProviderProps {
  children: ReactNode;
  pollInterval?: number; // ms, default 60000 (1 minute)
}

export const InsightsProvider: React.FC<InsightsProviderProps> = ({
  children,
  pollInterval = 60000,
}) => {
  const [summary, setSummary] = useState<InsightsSummary | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    try {
      const data = await getInsightsSummary();
      setSummary(data);
      setError(null);
    } catch (err) {
      console.error('Failed to fetch insights summary:', err);
      setError('Failed to load insights');
    } finally {
      setLoading(false);
    }
  }, []);

  // Initial fetch
  useEffect(() => {
    refresh();
  }, [refresh]);

  // Polling
  useEffect(() => {
    if (pollInterval <= 0) return;

    const interval = setInterval(refresh, pollInterval);
    return () => clearInterval(interval);
  }, [refresh, pollInterval]);

  return (
    <InsightsContext.Provider value={{ summary, loading, error, refresh }}>
      {children}
    </InsightsContext.Provider>
  );
};

export function useInsights(): InsightsContextValue {
  const context = useContext(InsightsContext);
  if (context === undefined) {
    throw new Error('useInsights must be used within InsightsProvider');
  }
  return context;
}
```

### 7.2 Usage in Navigation

```typescript
// In navigation component
import { useInsights } from '../contexts/InsightsContext';
import InsightBadge from '../components/InsightBadge';

const Navigation: React.FC = () => {
  const { summary } = useInsights();

  return (
    <nav>
      <NavItem to="/analytics">Analytics</NavItem>
      <NavItem to="/insights">
        Insights
        <InsightBadge
          count={summary?.total_unread ?? 0}
          hasCritical={(summary?.by_severity?.critical ?? 0) > 0}
        />
      </NavItem>
    </nav>
  );
};
```

---

## 8. Testing Plan

### 8.1 Backend Tests

**File:** `backend/tests/api/test_insights_summary.py`

```python
"""Tests for insights summary endpoint."""

import pytest
from fastapi.testclient import TestClient


class TestInsightsSummaryEndpoint:
    """Test GET /api/insights/summary."""

    def test_summary_returns_counts(
        self, client: TestClient, auth_headers: dict, db_session
    ):
        """Summary returns correct unread and severity counts."""
        # Create test insights with different severities
        # ... setup code ...

        response = client.get("/api/insights/summary", headers=auth_headers)

        assert response.status_code == 200
        data = response.json()
        assert "total_unread" in data
        assert "total_active" in data
        assert "by_severity" in data
        assert "by_type" in data

    def test_summary_excludes_dismissed(
        self, client: TestClient, auth_headers: dict, db_session
    ):
        """Summary excludes dismissed insights from counts."""
        # ... test code ...

    def test_summary_requires_entitlement(
        self, client: TestClient, free_tier_headers: dict
    ):
        """Summary requires AI_INSIGHTS entitlement."""
        response = client.get("/api/insights/summary", headers=free_tier_headers)
        assert response.status_code == 402


class TestRestoreInsightEndpoint:
    """Test PATCH /api/insights/{id}/restore."""

    def test_restore_dismissed_insight(
        self, client: TestClient, auth_headers: dict, dismissed_insight
    ):
        """Restore makes dismissed insight visible again."""
        response = client.patch(
            f"/api/insights/{dismissed_insight.id}/restore",
            headers=auth_headers,
        )

        assert response.status_code == 200
        assert response.json()["status"] == "ok"

        # Verify insight is no longer dismissed
        # ... verification code ...

    def test_restore_not_found(
        self, client: TestClient, auth_headers: dict
    ):
        """Restore returns 404 for non-existent insight."""
        response = client.patch(
            "/api/insights/nonexistent-id/restore",
            headers=auth_headers,
        )
        assert response.status_code == 404
```

### 8.2 Frontend Tests

**File:** `frontend/src/components/__tests__/InsightCard.test.tsx`

```typescript
import { render, screen, fireEvent } from '@testing-library/react';
import { PolarisTestProvider } from '@shopify/polaris';
import InsightCard from '../InsightCard';
import type { Insight } from '../../services/insightsApi';

const mockInsight: Insight = {
  insight_id: 'test-123',
  insight_type: 'spend_anomaly',
  severity: 'warning',
  summary: 'Spend increased by 25% this week',
  why_it_matters: 'Unusual spending pattern detected',
  supporting_metrics: [
    {
      metric: 'Ad Spend',
      previous: 1000,
      current: 1250,
      change: 250,
      change_pct: 25,
    },
  ],
  timeframe: 'Last 7 days',
  confidence_score: 0.85,
  platform: 'meta_ads',
  campaign_id: null,
  currency: 'USD',
  generated_at: new Date().toISOString(),
  is_read: false,
  is_dismissed: false,
};

describe('InsightCard', () => {
  it('renders insight summary', () => {
    render(
      <PolarisTestProvider>
        <InsightCard insight={mockInsight} />
      </PolarisTestProvider>
    );

    expect(screen.getByText(mockInsight.summary)).toBeInTheDocument();
  });

  it('shows New badge for unread insights', () => {
    render(
      <PolarisTestProvider>
        <InsightCard insight={mockInsight} />
      </PolarisTestProvider>
    );

    expect(screen.getByText('New')).toBeInTheDocument();
  });

  it('calls onDismiss when dismiss button clicked', () => {
    const onDismiss = jest.fn();
    render(
      <PolarisTestProvider>
        <InsightCard insight={mockInsight} onDismiss={onDismiss} />
      </PolarisTestProvider>
    );

    fireEvent.click(screen.getByText('Dismiss'));
    expect(onDismiss).toHaveBeenCalledWith(mockInsight.insight_id);
  });

  it('expands to show details on click', () => {
    render(
      <PolarisTestProvider>
        <InsightCard insight={mockInsight} />
      </PolarisTestProvider>
    );

    fireEvent.click(screen.getByText('Show details'));
    expect(screen.getByText('Why it matters')).toBeInTheDocument();
    expect(screen.getByText(mockInsight.why_it_matters!)).toBeInTheDocument();
  });

  it('calls onRead when expanded for first time', () => {
    const onRead = jest.fn();
    render(
      <PolarisTestProvider>
        <InsightCard insight={mockInsight} onRead={onRead} />
      </PolarisTestProvider>
    );

    fireEvent.click(screen.getByText('Show details'));
    expect(onRead).toHaveBeenCalledWith(mockInsight.insight_id);
  });
});
```

### 8.3 Integration Tests

**File:** `frontend/src/pages/__tests__/Insights.integration.test.tsx`

```typescript
import { render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { PolarisTestProvider } from '@shopify/polaris';
import Insights from '../Insights';
import * as insightsApi from '../../services/insightsApi';

jest.mock('../../services/insightsApi');

describe('Insights Page Integration', () => {
  beforeEach(() => {
    jest.clearAllMocks();
  });

  it('loads and displays insights', async () => {
    const mockInsights = [
      {
        insight_id: '1',
        insight_type: 'spend_anomaly',
        severity: 'warning',
        summary: 'Test insight 1',
        supporting_metrics: [],
        timeframe: 'Last 7 days',
        confidence_score: 0.9,
        generated_at: new Date().toISOString(),
        is_read: false,
        is_dismissed: false,
      },
    ];

    (insightsApi.listInsights as jest.Mock).mockResolvedValue({
      insights: mockInsights,
      total: 1,
      has_more: false,
    });

    render(
      <MemoryRouter>
        <PolarisTestProvider>
          <Insights />
        </PolarisTestProvider>
      </MemoryRouter>
    );

    await waitFor(() => {
      expect(screen.getByText('Test insight 1')).toBeInTheDocument();
    });
  });

  it('shows empty state when no insights', async () => {
    (insightsApi.listInsights as jest.Mock).mockResolvedValue({
      insights: [],
      total: 0,
      has_more: false,
    });

    render(
      <MemoryRouter>
        <PolarisTestProvider>
          <Insights />
        </PolarisTestProvider>
      </MemoryRouter>
    );

    await waitFor(() => {
      expect(screen.getByText('No insights yet')).toBeInTheDocument();
    });
  });
});
```

---

## 9. Implementation Checklist

### Phase 1: Backend API Extensions

- [ ] Add `InsightsSummaryResponse` schema to `backend/src/api/routes/insights.py`
- [ ] Implement `GET /api/insights/summary` endpoint
- [ ] Implement `PATCH /api/insights/{id}/restore` endpoint
- [ ] Add `RecommendationsSummaryResponse` schema to `backend/src/api/routes/recommendations.py`
- [ ] Implement `GET /api/recommendations/summary` endpoint
- [ ] Implement `PATCH /api/recommendations/{id}/restore` endpoint
- [ ] Write unit tests for new endpoints
- [ ] Run backend test suite

### Phase 2: Frontend API Services

- [ ] Create `frontend/src/services/insightsApi.ts`
- [ ] Create `frontend/src/services/recommendationsApi.ts`
- [ ] Add `fetchWithAuth` wrapper if not exists
- [ ] Write unit tests for API services

### Phase 3: UI Components

- [ ] Create `frontend/src/components/InsightCard.tsx`
- [ ] Create `frontend/src/components/InsightBadge.tsx`
- [ ] Create `frontend/src/components/InsightsSummaryPanel.tsx`
- [ ] Create `frontend/src/components/RecommendationCard.tsx`
- [ ] Create `frontend/src/components/InsightsEmptyState.tsx`
- [ ] Write component unit tests
- [ ] Verify Polaris styling consistency

### Phase 4: Pages & Routing

- [ ] Create `frontend/src/pages/Insights.tsx`
- [ ] Add route for `/insights` in router configuration
- [ ] Update `frontend/src/pages/Analytics.tsx` to include `InsightsSummaryPanel`
- [ ] Write page integration tests

### Phase 5: State Management (Optional)

- [ ] Create `frontend/src/contexts/InsightsContext.tsx`
- [ ] Wrap app with `InsightsProvider`
- [ ] Add `InsightBadge` to navigation
- [ ] Configure polling interval

### Phase 6: QA & Polish

- [ ] Manual testing of all user flows
- [ ] Test entitlement gating (free tier blocked)
- [ ] Test tenant isolation (multi-tenant)
- [ ] Test pagination (large data sets)
- [ ] Test dismiss/restore flow
- [ ] Accessibility audit (keyboard nav, screen readers)
- [ ] Performance profiling (rendering, API calls)

---

## Appendix A: File Structure

```
backend/
├── src/
│   └── api/
│       └── routes/
│           ├── insights.py          # Updated with summary + restore
│           └── recommendations.py   # Updated with summary + restore
└── tests/
    └── api/
        ├── test_insights_summary.py
        └── test_recommendations_summary.py

frontend/
├── src/
│   ├── components/
│   │   ├── InsightCard.tsx
│   │   ├── InsightBadge.tsx
│   │   ├── InsightsSummaryPanel.tsx
│   │   ├── RecommendationCard.tsx
│   │   ├── InsightsEmptyState.tsx
│   │   └── __tests__/
│   │       ├── InsightCard.test.tsx
│   │       └── RecommendationCard.test.tsx
│   ├── contexts/
│   │   └── InsightsContext.tsx
│   ├── pages/
│   │   ├── Analytics.tsx            # Updated
│   │   ├── Insights.tsx             # New
│   │   └── __tests__/
│   │       └── Insights.integration.test.tsx
│   └── services/
│       ├── insightsApi.ts           # New
│       └── recommendationsApi.ts    # New
└── package.json
```

---

## Appendix B: API Contract Summary

| Method | Endpoint | New/Existing | Purpose |
|--------|----------|--------------|---------|
| GET | `/api/insights` | Existing | List insights |
| GET | `/api/insights/{id}` | Existing | Get single insight |
| PATCH | `/api/insights/{id}/read` | Existing | Mark as read |
| PATCH | `/api/insights/{id}/dismiss` | Existing | Dismiss insight |
| POST | `/api/insights/batch/read` | Existing | Batch mark as read |
| **GET** | **`/api/insights/summary`** | **New** | **Aggregated counts** |
| **PATCH** | **`/api/insights/{id}/restore`** | **New** | **Restore dismissed** |
| GET | `/api/recommendations` | Existing | List recommendations |
| GET | `/api/recommendations/{id}` | Existing | Get single recommendation |
| PATCH | `/api/recommendations/{id}/accept` | Existing | Mark as accepted |
| PATCH | `/api/recommendations/{id}/dismiss` | Existing | Dismiss recommendation |
| **GET** | **`/api/recommendations/summary`** | **New** | **Aggregated counts** |
| **PATCH** | **`/api/recommendations/{id}/restore`** | **New** | **Restore dismissed** |

---

**Document End**
