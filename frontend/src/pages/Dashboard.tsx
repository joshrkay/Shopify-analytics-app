/**
 * Analytics Overview Page
 *
 * Matches the Figma "Analytics Overview" design.
 * Data sourced from:
 *   - GET /api/datasets/kpi-summary?timeframe=30days   → aggregate KPIs
 *   - GET /api/datasets/channel-breakdown?metric=revenue&timeframe=30days → per-channel bar chart
 *   - GET /api/channels/{platform}/metrics?timeframe=30days → channel table rows
 *
 * Loading strategy: 3 independent data groups (KPI, breakdown, channel metrics)
 * each with their own loading/error/retry state. One section failing does not
 * crash the others.
 */

import { useState, useEffect, useCallback } from 'react';
import {
  DollarSign,
  TrendingUp,
  ShoppingCart,
  MousePointerClick,
  Calendar,
  X,
  AlertTriangle,
  RefreshCw,
} from 'lucide-react';
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ResponsiveContainer,
} from 'recharts';
import { MetricCard } from '../components/MetricCard';
import { ChannelTable, type ChannelRow } from '../components/ChannelTable';
import { PerformanceChart, type DailyDataPoint } from '../components/PerformanceChart';
import {
  getKpiSummary,
  getChannelBreakdown,
  getChannelMetrics,
  type KpiSummaryResponse,
  type ChannelBreakdownSummary,
  type ChannelMetricsResponse,
} from '../services/kpiApi';

// Channel key → platform API name mapping
const CHANNEL_PLATFORMS: { key: string; displayName: string; platform: string }[] = [
  { key: 'google', displayName: 'Google Ads', platform: 'google_ads' },
  { key: 'facebook', displayName: 'Facebook Ads', platform: 'facebook_ads' },
  { key: 'instagram', displayName: 'Instagram Ads', platform: 'instagram_ads' },
  { key: 'tiktok', displayName: 'TikTok Ads', platform: 'tiktok_ads' },
  { key: 'pinterest', displayName: 'Pinterest Ads', platform: 'pinterest_ads' },
  { key: 'twitter', displayName: 'Twitter Ads', platform: 'twitter_ads' },
  { key: 'organic', displayName: 'Organic', platform: 'organic' },
];

type DrillDownMetric = 'revenue' | 'spend' | 'roas' | 'conversions' | 'clicks' | 'ctr' | 'conversionRate';

interface DrillDownModalProps {
  isOpen: boolean;
  title: string;
  onClose: () => void;
  children: React.ReactNode;
}

function DrillDownModal({ isOpen, title, onClose, children }: DrillDownModalProps) {
  if (!isOpen) return null;
  return (
    <div className="fixed inset-0 bg-black/50 z-50 flex items-center justify-center p-4">
      <div className="bg-white rounded-xl shadow-xl w-full max-w-2xl max-h-[80vh] flex flex-col">
        <div className="flex items-center justify-between p-6 border-b border-gray-200">
          <h2 className="text-lg font-semibold text-gray-900">{title}</h2>
          <button onClick={onClose} className="p-2 hover:bg-gray-100 rounded-lg transition-colors">
            <X className="w-5 h-5 text-gray-500" />
          </button>
        </div>
        <div className="flex-1 overflow-auto p-6">{children}</div>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Skeleton components
// ---------------------------------------------------------------------------

function ChartSkeleton() {
  return (
    <div className="h-[350px] bg-gray-100 rounded-lg animate-pulse flex items-end justify-around p-6 gap-4">
      {[65, 45, 80, 35, 55, 70, 50].map((h, i) => (
        <div key={i} className="bg-gray-200 rounded-t w-full" style={{ height: `${h}%` }} />
      ))}
    </div>
  );
}

function TableSkeleton() {
  return (
    <div className="bg-white rounded-lg border border-gray-200 overflow-hidden">
      <div className="bg-gray-50 px-4 py-3">
        <div className="h-4 w-48 bg-gray-200 rounded animate-pulse" />
      </div>
      {Array.from({ length: 7 }).map((_, i) => (
        <div key={i} className="px-4 py-3 border-t border-gray-100 flex gap-6">
          <div className="h-4 w-28 bg-gray-200 rounded animate-pulse" />
          <div className="h-4 w-20 bg-gray-200 rounded animate-pulse" />
          <div className="h-4 w-20 bg-gray-200 rounded animate-pulse" />
          <div className="h-4 w-16 bg-gray-200 rounded animate-pulse" />
          <div className="h-4 w-20 bg-gray-200 rounded animate-pulse" />
          <div className="h-4 w-16 bg-gray-200 rounded animate-pulse" />
        </div>
      ))}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Inline error banner for a section
// ---------------------------------------------------------------------------

function SectionError({ message, onRetry }: { message: string; onRetry: () => void }) {
  return (
    <div className="bg-amber-50 border border-amber-200 rounded-lg p-4 flex items-center justify-between">
      <div className="flex items-center gap-3">
        <AlertTriangle className="w-5 h-5 text-amber-600 flex-shrink-0" />
        <p className="text-amber-800 text-sm">{message}</p>
      </div>
      <button
        onClick={onRetry}
        className="flex items-center gap-1.5 px-3 py-1.5 text-sm font-medium text-amber-700 bg-amber-100 hover:bg-amber-200 rounded-lg transition-colors"
      >
        <RefreshCw className="w-3.5 h-3.5" />
        Retry
      </button>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Main component
// ---------------------------------------------------------------------------

export function Dashboard() {
  // Group 1: KPI Summary
  const [kpi, setKpi] = useState<KpiSummaryResponse | null>(null);
  const [kpiLoading, setKpiLoading] = useState(true);
  const [kpiError, setKpiError] = useState<string | null>(null);

  // Group 2: Channel Breakdown (bar chart)
  const [channelBreakdown, setChannelBreakdown] = useState<ChannelBreakdownSummary | null>(null);
  const [breakdownLoading, setBreakdownLoading] = useState(true);
  const [breakdownError, setBreakdownError] = useState<string | null>(null);

  // Group 3: Channel Metrics (table + secondary KPIs)
  const [channelMetrics, setChannelMetrics] = useState<ChannelMetricsResponse[]>([]);
  const [metricsLoading, setMetricsLoading] = useState(true);
  const [metricsError, setMetricsError] = useState<string | null>(null);

  // Daily trend (derived from channel metrics)
  const [dailyTrend, setDailyTrend] = useState<DailyDataPoint[]>([]);

  // Drill-down modal
  const [drillDown, setDrillDown] = useState<{ open: boolean; metric: DrillDownMetric; title: string }>({
    open: false,
    metric: 'revenue',
    title: '',
  });

  // ---- Data fetching functions (independent per group) ----

  const loadKpi = useCallback(async (cancelled = { current: false }) => {
    setKpiLoading(true);
    setKpiError(null);
    try {
      const data = await getKpiSummary('30days');
      if (!cancelled.current) {
        setKpi(data);
      }
    } catch (err) {
      if (!cancelled.current) {
        setKpiError(err instanceof Error ? err.message : 'Failed to load KPI data');
      }
    } finally {
      if (!cancelled.current) {
        setKpiLoading(false);
      }
    }
  }, []);

  const loadBreakdown = useCallback(async (cancelled = { current: false }) => {
    setBreakdownLoading(true);
    setBreakdownError(null);
    try {
      const data = await getChannelBreakdown('revenue', '30days');
      if (!cancelled.current) {
        setChannelBreakdown(data);
      }
    } catch (err) {
      if (!cancelled.current) {
        setBreakdownError(err instanceof Error ? err.message : 'Failed to load channel comparison');
      }
    } finally {
      if (!cancelled.current) {
        setBreakdownLoading(false);
      }
    }
  }, []);

  const loadMetrics = useCallback(async (cancelled = { current: false }) => {
    setMetricsLoading(true);
    setMetricsError(null);
    try {
      const results = await Promise.all(
        CHANNEL_PLATFORMS.map((ch) =>
          getChannelMetrics(ch.platform, '30days').catch(() => null),
        ),
      );
      if (cancelled.current) return;

      const valid = results.filter((r): r is ChannelMetricsResponse => r !== null);
      setChannelMetrics(valid);

      if (valid.length === 0) {
        setMetricsError('Failed to load channel metrics');
      } else {
        setMetricsError(null);
      }

      // Build daily trend from successful channel data
      const dateMap: Record<string, { date: string; revenue: number; spend: number }> = {};
      valid.forEach((ch) => {
        ch.daily_trend?.forEach((point) => {
          if (!dateMap[point.date]) {
            dateMap[point.date] = { date: point.date, revenue: 0, spend: 0 };
          }
          dateMap[point.date].revenue += point.revenue;
        });
      });
      setDailyTrend(Object.values(dateMap).sort((a, b) => a.date.localeCompare(b.date)));
    } catch (err) {
      if (!cancelled.current) {
        setMetricsError(err instanceof Error ? err.message : 'Failed to load channel metrics');
      }
    } finally {
      if (!cancelled.current) {
        setMetricsLoading(false);
      }
    }
  }, []);

  // Initial data load — all 3 groups fire in parallel
  useEffect(() => {
    const cancelled = { current: false };
    loadKpi(cancelled);
    loadBreakdown(cancelled);
    loadMetrics(cancelled);
    return () => { cancelled.current = true; };
  }, [loadKpi, loadBreakdown, loadMetrics]);

  // ---- Derived data ----

  const channelTableRows: ChannelRow[] = channelMetrics.map((ch) => {
    const platform = CHANNEL_PLATFORMS.find((p) => p.platform === ch.platform);
    return {
      channel: platform?.displayName ?? ch.display_name,
      spend: ch.spend,
      revenue: ch.revenue,
      roas: ch.roas,
      conversions: ch.orders,
      ctr: ch.ctr,
      cpc: ch.clicks > 0 ? ch.spend / ch.clicks : 0,
      conversionRate: ch.conversion_rate,
    };
  });
  const channelKeys = channelMetrics.map((ch) => {
    const platform = CHANNEL_PLATFORMS.find((p) => p.platform === ch.platform);
    return platform?.key ?? ch.platform;
  });

  const barChartData = (channelBreakdown?.bar_chart ?? []).map((item) => ({
    name: item.channel,
    Revenue: item.revenue,
    Spend: item.spend,
  }));

  const openDrillDown = (metric: DrillDownMetric, title: string) => {
    setDrillDown({ open: true, metric, title });
  };

  return (
    <div className="p-4 md:p-8">
      {/* Header */}
      <div className="mb-6 md:mb-8">
        <div className="flex flex-col md:flex-row md:items-center md:justify-between gap-4">
          <div>
            <h1 className="text-2xl md:text-3xl font-semibold text-gray-900">Analytics Overview</h1>
            <p className="text-gray-600 mt-1 text-sm md:text-base">
              Track performance across all advertising channels
            </p>
          </div>
          <div className="flex items-center gap-2 bg-white px-4 py-2 rounded-lg border border-gray-200 w-fit">
            <Calendar className="w-4 h-4 text-gray-500" />
            <span className="text-sm text-gray-700">Last 30 days</span>
          </div>
        </div>
      </div>

      {/* Inline error / loading state — page shell always renders */}
      {loading && (
        <div className="flex items-center gap-3 mb-6 bg-blue-50 border border-blue-200 rounded-lg px-4 py-3">
          <div className="w-4 h-4 border-2 border-blue-600 border-t-transparent rounded-full animate-spin shrink-0" />
          <span className="text-sm text-blue-700">Loading analytics…</span>
        </div>
      )}
      {error && !loading && (
        <div className="flex items-center justify-between mb-6 bg-red-50 border border-red-200 rounded-lg px-4 py-3">
          <div>
            <p className="text-sm font-medium text-red-700">Failed to load analytics</p>
            <p className="text-xs text-red-600 mt-0.5">{error}</p>
          </div>
          <button
            onClick={loadData}
            className="ml-4 shrink-0 px-3 py-1.5 bg-red-600 text-white rounded-lg hover:bg-red-700 transition-colors text-xs font-medium"
          >
            Retry
          </button>
        </div>
      )}

      {/* Primary KPI Cards */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4 md:gap-6 mb-6 md:mb-8">
        <MetricCard
          title="Total Revenue"
          value={kpi?.total_revenue.value ?? 0}
          change={kpi?.total_revenue.change_pct ?? undefined}
          icon={DollarSign}
          iconColor="green"
          formatValue
          isLoading={kpiLoading}
          onClick={kpi ? () => openDrillDown('revenue', 'Total Revenue Breakdown') : undefined}
        />
        <MetricCard
          title="Total Ad Spend"
          value={kpi?.total_ad_spend.value ?? 0}
          change={kpi?.total_ad_spend.change_pct ?? undefined}
          icon={TrendingUp}
          iconColor="red"
          formatValue
          isLoading={kpiLoading}
          onClick={kpi ? () => openDrillDown('spend', 'Total Ad Spend Breakdown') : undefined}
        />
        <MetricCard
          title="Average ROAS"
          value={kpi ? `${(kpi.average_roas.value ?? 0).toFixed(2)}x` : '—'}
          change={kpi?.average_roas.change_pct ?? undefined}
          icon={TrendingUp}
          iconColor="purple"
          isLoading={kpiLoading}
          onClick={kpi ? () => openDrillDown('roas', 'ROAS by Channel') : undefined}
        />
        <MetricCard
          title="Total Conversions"
          value={kpi ? (kpi.total_conversions.value ?? 0).toLocaleString() : '—'}
          change={kpi?.total_conversions.change_pct ?? undefined}
          icon={ShoppingCart}
          iconColor="blue"
          isLoading={kpiLoading}
          onClick={kpi ? () => openDrillDown('conversions', 'Total Conversions Breakdown') : undefined}
        />
      </div>

      {/* ================================================================= */}
      {/* Section 1b: Revenue & Spend Trends (from channel metrics data)     */}
      {/* ================================================================= */}
      <div className="bg-white rounded-lg p-4 md:p-6 shadow-sm border border-gray-200 mb-6 md:mb-8">
        <h2 className="text-base md:text-lg font-semibold text-gray-900 mb-4">Revenue & Spend Trends</h2>
        {metricsLoading ? (
          <div className="h-64 flex items-center justify-center">
            <div className="w-6 h-6 border-3 border-blue-600 border-t-transparent rounded-full animate-spin" />
          </div>
        ) : dailyTrend.length > 0 ? (
          <PerformanceChart data={dailyTrend} type="area" dataKeys={['revenue']} colors={['#3b82f6']} />
        ) : (
          <div className="h-64 flex items-center justify-center text-gray-400">
            No trend data available
          </div>
        )}
      </div>

      {/* ================================================================= */}
      {/* Section 2: Channel Comparison Bar Chart                            */}
      {/* ================================================================= */}
      {breakdownError && !breakdownLoading && (
        <div className="mb-4">
          <SectionError message={breakdownError} onRetry={() => loadBreakdown()} />
        </div>
      )}
      <div className="bg-white rounded-lg p-4 md:p-6 shadow-sm border border-gray-200 mb-6 md:mb-8">
        <h2 className="text-base md:text-lg font-semibold text-gray-900 mb-4">Channel Comparison</h2>
        {breakdownLoading ? (
          <ChartSkeleton />
        ) : barChartData.length > 0 ? (
          <ResponsiveContainer width="100%" height={350}>
            <BarChart data={barChartData}>
              <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" />
              <XAxis
                dataKey="name"
                tick={{ fill: '#6b7280', fontSize: 12 }}
                tickMargin={8}
              />
              <YAxis
                tick={{ fill: '#6b7280', fontSize: 12 }}
                tickFormatter={(value) => `$${(value / 1000).toFixed(0)}k`}
              />
              <Tooltip
                contentStyle={{
                  backgroundColor: 'white',
                  border: '1px solid #e5e7eb',
                  borderRadius: '8px',
                  padding: '12px',
                }}
                formatter={(value: number, name: string) => [`$${value.toLocaleString()}`, name]}
              />
              <Legend wrapperStyle={{ paddingTop: '20px' }} iconType="circle" />
              <Bar dataKey="Revenue" fill="#3b82f6" radius={[8, 8, 0, 0]} />
              <Bar dataKey="Spend" fill="#10b981" radius={[8, 8, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        ) : (
          <div className="h-64 flex items-center justify-center text-gray-400">
            No channel data available
          </div>
        )}
      </div>

      {/* ================================================================= */}
      {/* Section 3: Secondary KPI Cards (from channel metrics)              */}
      {/* ================================================================= */}
      {metricsError && !metricsLoading && (
        <div className="mb-4">
          <SectionError message={metricsError} onRetry={() => loadMetrics()} />
        </div>
      )}
      <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 gap-4 md:gap-6 mb-6 md:mb-8">
        <MetricCard
          title="Total Clicks"
          value={channelMetrics.reduce((s, c) => s + c.clicks, 0).toLocaleString()}
          icon={MousePointerClick}
          iconColor="blue"
          isLoading={metricsLoading}
          onClick={channelMetrics.length > 0 ? () => openDrillDown('clicks', 'Total Clicks Breakdown') : undefined}
        />
        <MetricCard
          title="Avg CTR"
          value={
            channelMetrics.length > 0
              ? `${(channelMetrics.reduce((s, c) => s + c.ctr, 0) / channelMetrics.length).toFixed(2)}%`
              : '—'
          }
          icon={TrendingUp}
          iconColor="orange"
          isLoading={metricsLoading}
          onClick={channelMetrics.length > 0 ? () => openDrillDown('ctr', 'CTR by Channel') : undefined}
        />
        <MetricCard
          title="Avg Conv. Rate"
          value={
            channelMetrics.length > 0
              ? `${(channelMetrics.reduce((s, c) => s + c.conversion_rate, 0) / channelMetrics.length).toFixed(2)}%`
              : '—'
          }
          icon={ShoppingCart}
          iconColor="green"
          isLoading={metricsLoading}
          onClick={channelMetrics.length > 0 ? () => openDrillDown('conversionRate', 'Conversion Rate by Channel') : undefined}
        />
      </div>

      {/* ================================================================= */}
      {/* Section 3b: Channel Performance Table                              */}
      {/* ================================================================= */}
      <div className="mb-6 md:mb-8">
        <h2 className="text-base md:text-lg font-semibold text-gray-900 mb-4">Channel Performance</h2>
        <div className="overflow-x-auto -mx-4 md:mx-0">
          <div className="inline-block min-w-full align-middle px-4 md:px-0">
            {metricsLoading ? (
              <TableSkeleton />
            ) : channelTableRows.length > 0 ? (
              <ChannelTable channels={channelTableRows} channelKeys={channelKeys} />
            ) : (
              <div className="bg-white rounded-lg border border-gray-200 p-8 text-center text-gray-400">
                No channel data available
              </div>
            )}
          </div>
        </div>
      </div>

      {/* Drill Down Modal */}
      <DrillDownModal
        isOpen={drillDown.open}
        title={drillDown.title}
        onClose={() => setDrillDown((d) => ({ ...d, open: false }))}
      >
        <div className="space-y-3">
          {channelMetrics.map((ch) => {
            const platform = CHANNEL_PLATFORMS.find((p) => p.platform === ch.platform);
            const key = platform?.displayName ?? ch.display_name;
            let metricValue: string;
            switch (drillDown.metric) {
              case 'revenue':
                metricValue = `$${ch.revenue.toLocaleString('en-US', { minimumFractionDigits: 0, maximumFractionDigits: 0 })}`;
                break;
              case 'spend':
                metricValue = `$${ch.spend.toLocaleString('en-US', { minimumFractionDigits: 0, maximumFractionDigits: 0 })}`;
                break;
              case 'roas':
                metricValue = `${ch.roas.toFixed(2)}x`;
                break;
              case 'conversions':
                metricValue = ch.orders.toLocaleString();
                break;
              case 'clicks':
                metricValue = ch.clicks.toLocaleString();
                break;
              case 'ctr':
                metricValue = `${ch.ctr.toFixed(2)}%`;
                break;
              case 'conversionRate':
                metricValue = `${ch.conversion_rate.toFixed(2)}%`;
                break;
              default:
                metricValue = '—';
            }
            return (
              <div key={ch.platform} className="flex items-center justify-between p-3 bg-gray-50 rounded-lg">
                <span className="font-medium text-gray-900">{key}</span>
                <span className="text-gray-700">{metricValue}</span>
              </div>
            );
          })}
          {channelMetrics.length === 0 && (
            <div className="text-center text-gray-400 py-4">No channel data available</div>
          )}
        </div>
      </DrillDownModal>
    </div>
  );
}
