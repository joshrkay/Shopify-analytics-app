/**
 * KPI API Service
 *
 * Fetches pre-aggregated KPI metrics for the Overview dashboard.
 * All three endpoints are available on every plan (no custom_reports gate).
 *
 * Backend routes (backend/src/api/routes/datasets.py):
 *   GET /api/datasets/kpi-summary?timeframe=
 *   GET /api/datasets/channel-breakdown?metric=&timeframe=
 *   GET /api/datasets/channel-breakdown/{channel}?timeframe=
 */

import { API_BASE_URL, createHeadersAsync, handleResponse } from './apiUtils';

// ---------------------------------------------------------------------------
// Types (mirror Pydantic models in datasets.py)
// ---------------------------------------------------------------------------

export interface KpiMetric {
  value: number;
  change_pct: number | null;
}

export interface ChannelBar {
  channel: string;
  revenue: number;
  spend: number;
}

export interface KpiSummaryResponse {
  total_revenue: KpiMetric;
  total_ad_spend: KpiMetric;
  average_roas: KpiMetric;
  total_conversions: KpiMetric;
  revenue_by_channel: ChannelBar[];
  active_channels: number;
}

export interface ChannelBreakdownRow {
  rank: number;
  channel: string;
  display_name: string;
  value: number;
  pct_of_total: number;
}

export interface ChannelBreakdownSummary {
  total: number;
  active_channels: number;
  bar_chart: ChannelBar[];
  pie_chart: ChannelBreakdownRow[];
  table: ChannelBreakdownRow[];
}

export interface DailyTrendPoint {
  date: string;
  revenue: number;
}

export interface ProductRow {
  rank: number;
  product_name: string;
  revenue: number;
  units_sold: number;
  avg_price: number;
  pct_of_channel: number;
}

export interface ChannelDrilldownResponse {
  channel: string;
  display_name: string;
  total_revenue: number;
  unique_products: number;
  daily_trend: DailyTrendPoint[];
  products: ProductRow[];
}

// ---------------------------------------------------------------------------
// API functions
// ---------------------------------------------------------------------------

/**
 * Aggregated KPI metrics for the Overview dashboard.
 *
 * @param timeframe - One of: 7days, thisWeek, 30days, thisMonth, 90days, thisQuarter
 */
export async function getKpiSummary(timeframe: string): Promise<KpiSummaryResponse> {
  const headers = await createHeadersAsync();
  const response = await fetch(
    `${API_BASE_URL}/api/datasets/kpi-summary?timeframe=${encodeURIComponent(timeframe)}`,
    { method: 'GET', headers },
  );
  return handleResponse<KpiSummaryResponse>(response);
}

/**
 * Per-channel breakdown for a given metric.
 *
 * @param metric   - One of: revenue, spend, roas, conversions
 * @param timeframe - Same values as getKpiSummary
 */
export async function getChannelBreakdown(
  metric: string,
  timeframe: string,
): Promise<ChannelBreakdownSummary> {
  const headers = await createHeadersAsync();
  const params = new URLSearchParams({ metric, timeframe });
  const response = await fetch(
    `${API_BASE_URL}/api/datasets/channel-breakdown?${params}`,
    { method: 'GET', headers },
  );
  return handleResponse<ChannelBreakdownSummary>(response);
}

/**
 * Channel drill-down: daily trend + top products for one channel.
 *
 * @param channel  - Platform key, e.g. "meta_ads", "google_ads", "organic"
 * @param timeframe - Same values as getKpiSummary
 */
export async function getChannelDrilldown(
  channel: string,
  timeframe: string,
): Promise<ChannelDrilldownResponse> {
  const headers = await createHeadersAsync();
  const response = await fetch(
    `${API_BASE_URL}/api/datasets/channel-breakdown/${encodeURIComponent(channel)}?timeframe=${encodeURIComponent(timeframe)}`,
    { method: 'GET', headers },
  );
  return handleResponse<ChannelDrilldownResponse>(response);
}
