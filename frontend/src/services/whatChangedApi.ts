/**
 * What Changed API Service
 *
 * Handles API calls for the "What Changed?" debug panel:
 * - Getting summary data for panel header
 * - Getting data freshness status
 * - Listing recent syncs
 * - Listing AI action activity
 * - Listing connector status changes
 *
 * Story 9.8 - "What Changed?" Debug Panel
 */

import type {
  DataChangeEvent,
  ChangeEventsListResponse,
  WhatChangedSummary,
  DataFreshness,
  RecentSync,
  RecentSyncsResponse,
  AIActionSummary,
  AIActionsResponse,
  ConnectorStatusChange,
  ConnectorStatusChangesResponse,
  ChangeEventsFilters,
} from '../types/whatChanged';

const API_BASE_URL = import.meta.env.VITE_API_URL || '';

/**
 * Get the current JWT token from localStorage.
 */
function getAuthToken(): string | null {
  return localStorage.getItem('jwt_token') || localStorage.getItem('auth_token');
}

/**
 * Create headers with authentication.
 */
function createHeaders(): HeadersInit {
  const token = getAuthToken();
  const headers: HeadersInit = {
    'Content-Type': 'application/json',
  };
  if (token) {
    headers['Authorization'] = `Bearer ${token}`;
  }
  return headers;
}

/**
 * Handle API response and throw on error.
 */
async function handleResponse<T>(response: Response): Promise<T> {
  if (!response.ok) {
    const errorData = await response.json().catch(() => ({}));
    const error = new Error(errorData.detail || `API error: ${response.status}`);
    (error as Error & { status: number; detail: string }).status = response.status;
    (error as Error & { status: number; detail: string }).detail = errorData.detail;
    throw error;
  }
  return response.json();
}

/**
 * Build query string from filters.
 */
function buildQueryString(filters: ChangeEventsFilters): string {
  const params = new URLSearchParams();

  if (filters.event_type) {
    params.append('event_type', filters.event_type);
  }
  if (filters.connector_id) {
    params.append('connector_id', filters.connector_id);
  }
  if (filters.metric) {
    params.append('metric', filters.metric);
  }
  if (filters.days !== undefined) {
    params.append('days', String(filters.days));
  }
  if (filters.limit !== undefined) {
    params.append('limit', String(filters.limit));
  }
  if (filters.offset !== undefined) {
    params.append('offset', String(filters.offset));
  }

  const queryString = params.toString();
  return queryString ? `?${queryString}` : '';
}

/**
 * List data change events with optional filtering.
 *
 * @param filters - Optional filters for events
 * @returns List of events with pagination info
 */
export async function listChangeEvents(
  filters: ChangeEventsFilters = {}
): Promise<ChangeEventsListResponse> {
  const queryString = buildQueryString(filters);
  const response = await fetch(`${API_BASE_URL}/api/what-changed${queryString}`, {
    method: 'GET',
    headers: createHeaders(),
  });
  return handleResponse<ChangeEventsListResponse>(response);
}

/**
 * Get summary for the debug panel header.
 *
 * @param days - Number of days to look back (default 7)
 * @returns Summary with freshness, counts, and last updated
 */
export async function getSummary(days: number = 7): Promise<WhatChangedSummary> {
  const params = new URLSearchParams();
  params.append('days', String(days));

  const response = await fetch(
    `${API_BASE_URL}/api/what-changed/summary?${params.toString()}`,
    {
      method: 'GET',
      headers: createHeaders(),
    }
  );
  return handleResponse<WhatChangedSummary>(response);
}

/**
 * Get data freshness status.
 *
 * @returns Overall freshness and per-connector breakdown
 */
export async function getFreshnessStatus(): Promise<DataFreshness> {
  const response = await fetch(`${API_BASE_URL}/api/what-changed/freshness`, {
    method: 'GET',
    headers: createHeaders(),
  });
  return handleResponse<DataFreshness>(response);
}

/**
 * Get recent sync activity.
 *
 * @param days - Number of days to look back (default 7)
 * @param limit - Maximum syncs to return (default 20)
 * @returns List of recent syncs
 */
export async function getRecentSyncs(
  days: number = 7,
  limit: number = 20
): Promise<RecentSyncsResponse> {
  const params = new URLSearchParams();
  params.append('days', String(days));
  params.append('limit', String(limit));

  const response = await fetch(
    `${API_BASE_URL}/api/what-changed/recent-syncs?${params.toString()}`,
    {
      method: 'GET',
      headers: createHeaders(),
    }
  );
  return handleResponse<RecentSyncsResponse>(response);
}

/**
 * Get recent AI action activity.
 *
 * @param days - Number of days to look back (default 7)
 * @param limit - Maximum actions to return (default 20)
 * @returns List of AI action summaries
 */
export async function getAIActions(
  days: number = 7,
  limit: number = 20
): Promise<AIActionsResponse> {
  const params = new URLSearchParams();
  params.append('days', String(days));
  params.append('limit', String(limit));

  const response = await fetch(
    `${API_BASE_URL}/api/what-changed/ai-actions?${params.toString()}`,
    {
      method: 'GET',
      headers: createHeaders(),
    }
  );
  return handleResponse<AIActionsResponse>(response);
}

/**
 * Get recent connector status changes.
 *
 * @param days - Number of days to look back (default 7)
 * @returns List of connector status changes
 */
export async function getConnectorStatusChanges(
  days: number = 7
): Promise<ConnectorStatusChangesResponse> {
  const params = new URLSearchParams();
  params.append('days', String(days));

  const response = await fetch(
    `${API_BASE_URL}/api/what-changed/connector-status?${params.toString()}`,
    {
      method: 'GET',
      headers: createHeaders(),
    }
  );
  return handleResponse<ConnectorStatusChangesResponse>(response);
}

/**
 * Check if there are any critical issues.
 *
 * Convenience function for showing alerts.
 *
 * @returns True if there are critical events in the last 24 hours
 */
export async function hasCriticalIssues(): Promise<boolean> {
  const summary = await getSummary(1);
  return (
    summary.data_freshness.overall_status === 'critical' ||
    summary.open_incidents_count > 0
  );
}

/**
 * Get count of recent changes.
 *
 * Convenience function for badge displays.
 *
 * @param days - Number of days to look back (default 7)
 * @returns Number of change events
 */
export async function getRecentChangesCount(days: number = 7): Promise<number> {
  const events = await listChangeEvents({ days, limit: 1 });
  return events.total;
}
