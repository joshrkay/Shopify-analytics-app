/**
 * Attribution API Service
 *
 * Fetches UTM last-click attribution data for the Attribution dashboard.
 * Both endpoints are available on every plan (no custom_reports gate).
 *
 * Backend routes (backend/src/api/routes/attribution.py):
 *   GET /api/attribution/summary?timeframe=
 *   GET /api/attribution/orders?timeframe=&platform=&limit=&offset=
 */

import { API_BASE_URL, createHeadersAsync, handleResponse } from './apiUtils';

// ---------------------------------------------------------------------------
// Types (mirror Pydantic models in attribution.py)
// ---------------------------------------------------------------------------

export interface TopCampaign {
  campaign_name: string;
  platform: string | null;
  revenue: number;
  orders: number;
  spend: number;
  roas: number | null;
}

export interface ChannelRoas {
  platform: string;
  gross_roas: number;
  revenue: number;
  spend: number;
}

export interface AttributionSummaryResponse {
  attributed_orders: number;
  unattributed_orders: number;
  attribution_rate: number;
  total_attributed_revenue: number;
  top_campaigns: TopCampaign[];
  channel_roas: ChannelRoas[];
}

export interface AttributedOrder {
  order_id: string;
  order_name: string | null;
  order_number: string | null;
  revenue: number;
  currency: string;
  created_at: string;
  utm_source: string | null;
  utm_medium: string | null;
  utm_campaign: string | null;
  platform: string | null;
  attribution_status: string;
}

export interface AttributedOrdersResponse {
  orders: AttributedOrder[];
  total: number;
  has_more: boolean;
}

export interface AttributedOrdersParams {
  timeframe?: string;
  platform?: string | null;
  limit?: number;
  offset?: number;
}

// ---------------------------------------------------------------------------
// API functions
// ---------------------------------------------------------------------------

/**
 * Aggregated attribution KPIs: rate, revenue, top campaigns, channel ROAS.
 *
 * @param timeframe - One of: 7days, thisWeek, 30days, thisMonth, 90days, thisQuarter
 */
export async function getAttributionSummary(
  timeframe: string,
): Promise<AttributionSummaryResponse> {
  const headers = await createHeadersAsync();
  const response = await fetch(
    `${API_BASE_URL}/api/attribution/summary?timeframe=${encodeURIComponent(timeframe)}`,
    { method: 'GET', headers },
  );
  return handleResponse<AttributionSummaryResponse>(response);
}

/**
 * Paginated list of orders with UTM attribution fields.
 *
 * @param params - timeframe, platform filter, limit, offset
 */
export async function getAttributedOrders(
  params: AttributedOrdersParams = {},
): Promise<AttributedOrdersResponse> {
  const { timeframe = '30days', platform, limit = 50, offset = 0 } = params;
  const headers = await createHeadersAsync();
  const query = new URLSearchParams({
    timeframe,
    limit: String(limit),
    offset: String(offset),
  });
  if (platform) query.set('platform', platform);
  const response = await fetch(
    `${API_BASE_URL}/api/attribution/orders?${query}`,
    { method: 'GET', headers },
  );
  return handleResponse<AttributedOrdersResponse>(response);
}
