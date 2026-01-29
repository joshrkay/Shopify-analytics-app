/**
 * Changelog API Service
 *
 * Handles API calls for changelog entries:
 * - Listing changelog entries with filtering
 * - Getting unread count for badges
 * - Marking entries as read
 * - Getting entries for specific feature areas (contextual badges)
 *
 * Story 9.7 - In-App Changelog & Release Notes
 */

import type {
  ChangelogEntry,
  ChangelogListResponse,
  ChangelogUnreadCountResponse,
  ChangelogMarkReadResponse,
  ChangelogFilters,
  FeatureArea,
} from '../types/changelog';

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
function buildQueryString(filters: ChangelogFilters): string {
  const params = new URLSearchParams();

  if (filters.release_type) {
    params.append('release_type', filters.release_type);
  }
  if (filters.feature_area) {
    params.append('feature_area', filters.feature_area);
  }
  if (filters.include_read !== undefined) {
    params.append('include_read', String(filters.include_read));
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
 * List published changelog entries with optional filtering.
 *
 * @param filters - Optional filters for entries
 * @returns List of entries with pagination info and unread count
 */
export async function listChangelog(
  filters: ChangelogFilters = {}
): Promise<ChangelogListResponse> {
  const queryString = buildQueryString(filters);
  const response = await fetch(`${API_BASE_URL}/api/changelog${queryString}`, {
    method: 'GET',
    headers: createHeaders(),
  });
  return handleResponse<ChangelogListResponse>(response);
}

/**
 * Get a single changelog entry by ID.
 *
 * @param entryId - The changelog entry ID
 * @returns The changelog entry details
 */
export async function getChangelogEntry(entryId: string): Promise<ChangelogEntry> {
  const response = await fetch(`${API_BASE_URL}/api/changelog/${entryId}`, {
    method: 'GET',
    headers: createHeaders(),
  });
  return handleResponse<ChangelogEntry>(response);
}

/**
 * Get unread changelog count.
 *
 * Useful for badge displays.
 *
 * @param featureArea - Optional filter by feature area
 * @returns Unread count and breakdown by feature area
 */
export async function getUnreadCount(
  featureArea?: FeatureArea
): Promise<ChangelogUnreadCountResponse> {
  const params = new URLSearchParams();
  if (featureArea) {
    params.append('feature_area', featureArea);
  }
  const queryString = params.toString();
  const url = `${API_BASE_URL}/api/changelog/unread/count${queryString ? `?${queryString}` : ''}`;

  const response = await fetch(url, {
    method: 'GET',
    headers: createHeaders(),
  });
  return handleResponse<ChangelogUnreadCountResponse>(response);
}

/**
 * Get changelog entries for a specific feature area.
 *
 * Used for contextual banners near changed features.
 *
 * @param featureArea - The feature area to filter by
 * @param limit - Maximum entries to return (default 5)
 * @returns List of unread entries for the feature area
 */
export async function getEntriesForFeature(
  featureArea: FeatureArea,
  limit: number = 5
): Promise<ChangelogListResponse> {
  const params = new URLSearchParams();
  params.append('limit', String(limit));

  const response = await fetch(
    `${API_BASE_URL}/api/changelog/feature/${featureArea}?${params.toString()}`,
    {
      method: 'GET',
      headers: createHeaders(),
    }
  );
  return handleResponse<ChangelogListResponse>(response);
}

/**
 * Mark a changelog entry as read.
 *
 * @param entryId - The entry ID to mark as read
 * @returns Response with updated counts
 */
export async function markAsRead(entryId: string): Promise<ChangelogMarkReadResponse> {
  const response = await fetch(`${API_BASE_URL}/api/changelog/${entryId}/read`, {
    method: 'POST',
    headers: createHeaders(),
  });
  return handleResponse<ChangelogMarkReadResponse>(response);
}

/**
 * Mark all changelog entries as read.
 *
 * @returns Response with count of entries marked
 */
export async function markAllAsRead(): Promise<ChangelogMarkReadResponse> {
  const response = await fetch(`${API_BASE_URL}/api/changelog/read-all`, {
    method: 'POST',
    headers: createHeaders(),
  });
  return handleResponse<ChangelogMarkReadResponse>(response);
}

/**
 * Get simple unread count number.
 *
 * Convenience function for badge components.
 *
 * @param featureArea - Optional filter by feature area
 * @returns Number of unread entries
 */
export async function getUnreadCountNumber(featureArea?: FeatureArea): Promise<number> {
  const result = await getUnreadCount(featureArea);
  return result.count;
}
