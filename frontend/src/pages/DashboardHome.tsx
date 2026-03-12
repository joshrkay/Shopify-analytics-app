/**
 * DashboardHome Page
 *
 * Native dashboard home page with:
 * - Metric summary cards (insights count, recommendations count, data health)
 * - Timeframe selector
 * - Recent insights table
 * - Recommendations overview
 * - Data health status
 * - Empty state for new users
 * - Error state when APIs fail (distinct from empty state)
 *
 * Wires to existing APIs: insightsApi, recommendationsApi, syncHealthApi.
 *
 * Phase 1 — Dashboard Home
 */

import { useState, useEffect, useCallback } from 'react';
import {
  Page,
  Card,
  Text,
  BlockStack,
  InlineStack,
  InlineGrid,
  Badge,
  DataTable,
  Spinner,
  Banner,
  EmptyState,
  Button,
} from '@shopify/polaris';
import { useNavigate } from 'react-router-dom';
import { listInsights, getUnreadInsightsCount } from '../services/insightsApi';
import { listRecommendations, getActiveRecommendationsCount } from '../services/recommendationsApi';
import { getCompactHealth } from '../services/syncHealthApi';
import type { Insight } from '../types/insights';
import type { Recommendation } from '../types/recommendations';
import type { CompactHealth } from '../services/syncHealthApi';
import { getInsightTypeLabel } from '../types/insights';
import { getRecommendationTypeLabel } from '../types/recommendations';

interface DashboardMetrics {
  unreadInsights: number;
  activeRecommendations: number;
  healthScore: number;
  healthStatus: 'healthy' | 'degraded' | 'critical';
}

export function DashboardHome() {
  const navigate = useNavigate();
  const [metrics, setMetrics] = useState<DashboardMetrics | null>(null);
  const [insights, setInsights] = useState<Insight[]>([]);
  const [recommendations, setRecommendations] = useState<Recommendation[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [apiFailures, setApiFailures] = useState(0);

  const loadData = useCallback(async () => {
    let cancelled = false;

    try {
      setLoading(true);
      setError(null);

      let failedCalls = 0;

      const [
        unreadCount,
        activeRecCount,
        health,
        insightsResponse,
        recsResponse,
      ] = await Promise.all([
        getUnreadInsightsCount().catch(() => { failedCalls++; return 0; }),
        getActiveRecommendationsCount().catch(() => { failedCalls++; return 0; }),
        getCompactHealth().catch((): CompactHealth => {
          failedCalls++;
          return {
            overall_status: 'healthy',
            health_score: 100,
            stale_count: 0,
            critical_count: 0,
            has_blocking_issues: false,
            oldest_sync_minutes: null,
            last_checked_at: new Date().toISOString(),
          };
        }),
        listInsights({ limit: 5, include_dismissed: false }).catch(() => {
          failedCalls++;
          return { insights: [], total: 0, has_more: false };
        }),
        listRecommendations({ limit: 5, include_dismissed: false }).catch(() => {
          failedCalls++;
          return { recommendations: [], total: 0, has_more: false };
        }),
      ]);

      if (cancelled) return;

      setApiFailures(failedCalls);
      setMetrics({
        unreadInsights: unreadCount,
        activeRecommendations: activeRecCount,
        healthScore: health.health_score,
        healthStatus: health.overall_status,
      });
      setInsights(insightsResponse.insights);
      setRecommendations(recsResponse.recommendations);
    } catch (err) {
      if (!cancelled) {
        setError(err instanceof Error ? err.message : 'Failed to load dashboard data');
      }
    } finally {
      if (!cancelled) {
        setLoading(false);
      }
    }

    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    loadData();
  }, [loadData]);

  if (loading) {
    return (
      <Page title="Home">
        <div style={{ display: 'flex', justifyContent: 'center', padding: 80 }}>
          <Spinner size="large" />
        </div>
      </Page>
    );
  }

  if (error) {
    return (
      <Page title="Home">
        <Banner tone="critical" title="Failed to load dashboard">
          <p>{error}</p>
        </Banner>
      </Page>
    );
  }

  const hasData = metrics && (metrics.unreadInsights > 0 || metrics.activeRecommendations > 0 || insights.length > 0);

  // API failures masquerading as empty — show error state with retry + fallback CTA
  if (!hasData && !loading && apiFailures > 0) {
    return (
      <Page title="Home">
        <BlockStack gap="400">
          <Banner
            tone="critical"
            title="Unable to load dashboard data"
            action={{ content: 'Retry', onAction: () => loadData() }}
          >
            <p>
              We couldn't reach the server to load your dashboard. Please check
              your connection and try again.
            </p>
          </Banner>
          <Card>
            <EmptyState
              heading="Or connect your data sources"
              image=""
            >
              <p>
                If you haven't connected data sources yet, start here to begin
                seeing insights and recommendations.
              </p>
              <Button variant="primary" onClick={() => navigate('/data-sources')}>
                Connect data sources
              </Button>
            </EmptyState>
          </Card>
        </BlockStack>
      </Page>
    );
  }

  // Genuine empty state — no API failures, just no data yet
  if (!hasData && !loading) {
    return (
      <Page title="Home">
        <Card>
          <EmptyState
            heading="Welcome to your analytics dashboard"
            image=""
          >
            <p>
              Connect your data sources to start seeing insights, recommendations,
              and performance metrics here.
            </p>
            <Button variant="primary" onClick={() => navigate('/data-sources')}>
              Connect data sources
            </Button>
          </EmptyState>
        </Card>
      </Page>
    );
  }

  const healthBadgeTone = metrics?.healthStatus === 'healthy'
    ? 'success'
    : metrics?.healthStatus === 'degraded'
      ? 'attention'
      : 'critical';

  const healthLabel = metrics?.healthStatus === 'healthy'
    ? 'Healthy'
    : metrics?.healthStatus === 'degraded'
      ? 'Degraded'
      : 'Critical';

  // Build insights table rows
  const insightRows = insights.map((insight) => [
    getInsightTypeLabel(insight.insight_type),
    insight.summary.length > 80 ? `${insight.summary.slice(0, 80)}...` : insight.summary,
    insight.severity,
    insight.timeframe,
  ]);

  // Build recommendations table rows
  const recRows = recommendations.map((rec) => [
    getRecommendationTypeLabel(rec.recommendation_type),
    rec.recommendation_text.length > 80 ? `${rec.recommendation_text.slice(0, 80)}...` : rec.recommendation_text,
    rec.priority,
    rec.estimated_impact,
  ]);

  return (
    <Page title="Home">
      <BlockStack gap="600">
        {/* Warning banner when some calls failed but we have partial data */}
        {apiFailures > 0 && (
          <Banner
            tone="warning"
            title="Some data couldn't be loaded"
            action={{ content: 'Retry', onAction: () => loadData() }}
          >
            <p>Some dashboard metrics may be incomplete or showing default values.</p>
          </Banner>
        )}

        {/* Metric summary cards */}
        <InlineGrid columns={{ xs: 1, sm: 2, md: 3 }} gap="400">
          <Card>
            <BlockStack gap="200">
              <Text as="p" variant="bodySm" tone="subdued">Unread Insights</Text>
              <Text as="p" variant="heading2xl">{metrics?.unreadInsights ?? 0}</Text>
              {(metrics?.unreadInsights ?? 0) > 0 && (
                <Button variant="plain" onClick={() => navigate('/insights')}>View all</Button>
              )}
            </BlockStack>
          </Card>
          <Card>
            <BlockStack gap="200">
              <Text as="p" variant="bodySm" tone="subdued">Active Recommendations</Text>
              <Text as="p" variant="heading2xl">{metrics?.activeRecommendations ?? 0}</Text>
              {(metrics?.activeRecommendations ?? 0) > 0 && (
                <Button variant="plain" onClick={() => navigate('/insights')}>Review</Button>
              )}
            </BlockStack>
          </Card>
          <Card>
            <BlockStack gap="200">
              <Text as="p" variant="bodySm" tone="subdued">Data Health</Text>
              <InlineStack gap="200" blockAlign="center">
                <Text as="p" variant="heading2xl">{metrics?.healthScore ?? 0}%</Text>
                <Badge tone={healthBadgeTone}>{healthLabel}</Badge>
              </InlineStack>
              <Button variant="plain" onClick={() => navigate('/data-sources')}>Details</Button>
            </BlockStack>
          </Card>
        </InlineGrid>

        {/* Recent insights table */}
        {insights.length > 0 && (
          <Card>
            <BlockStack gap="400">
              <InlineStack align="space-between" blockAlign="center">
                <Text as="h2" variant="headingMd">Recent Insights</Text>
                <Button variant="plain" onClick={() => navigate('/insights')}>View all</Button>
              </InlineStack>
              <DataTable
                columnContentTypes={['text', 'text', 'text', 'text']}
                headings={['Type', 'Summary', 'Severity', 'Timeframe']}
                rows={insightRows}
                hoverable
              />
            </BlockStack>
          </Card>
        )}

        {/* Recommendations table */}
        {recommendations.length > 0 && (
          <Card>
            <BlockStack gap="400">
              <InlineStack align="space-between" blockAlign="center">
                <Text as="h2" variant="headingMd">Recommendations</Text>
                <Button variant="plain" onClick={() => navigate('/insights')}>View all</Button>
              </InlineStack>
              <DataTable
                columnContentTypes={['text', 'text', 'text', 'text']}
                headings={['Type', 'Description', 'Priority', 'Impact']}
                rows={recRows}
                hoverable
              />
            </BlockStack>
          </Card>
        )}
      </BlockStack>
    </Page>
  );
}

export default DashboardHome;
