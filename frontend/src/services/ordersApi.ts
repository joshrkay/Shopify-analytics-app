/**
 * Orders API Service
 *
 * Fetches paginated Shopify orders with UTM attribution overlay.
 * Available on every plan (no custom_reports gate).
 *
 * Backend route (backend/src/api/routes/orders.py):
 *   GET /api/orders?timeframe=&limit=&offset=
 */

import { API_BASE_URL, createHeadersAsync, handleResponse } from './apiUtils';

// ---------------------------------------------------------------------------
// Types (mirror Pydantic models in orders.py)
// ---------------------------------------------------------------------------

export interface Order {
  order_id: string;
  order_number: string | null;
  order_name: string | null;
  revenue: number;
  currency: string;
  financial_status: string | null;
  created_at: string;
  utm_source: string | null;
  utm_medium: string | null;
  utm_campaign: string | null;
  platform: string | null;
}

export interface OrdersListResponse {
  orders: Order[];
  total: number;
  has_more: boolean;
}

export interface GetOrdersParams {
  timeframe?: string;
  limit?: number;
  offset?: number;
}

// ---------------------------------------------------------------------------
// API functions
// ---------------------------------------------------------------------------

/**
 * Paginated Shopify order list with UTM attribution overlay.
 *
 * @param params - timeframe, limit, offset
 */
export async function getOrders(
  params: GetOrdersParams = {},
): Promise<OrdersListResponse> {
  const { timeframe = '30days', limit = 50, offset = 0 } = params;
  const headers = await createHeadersAsync();
  const query = new URLSearchParams({
    timeframe,
    limit: String(limit),
    offset: String(offset),
  });
  const response = await fetch(
    `${API_BASE_URL}/api/orders?${query}`,
    { method: 'GET', headers },
  );
  return handleResponse<OrdersListResponse>(response);
}
