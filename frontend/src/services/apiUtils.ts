/**
 * Shared API Utilities
 *
 * Common functions for API service modules:
 * - Authentication token handling
 * - HTTP headers creation
 * - Response handling with error extraction
 * - Query string building
 */

export const API_BASE_URL = import.meta.env.VITE_API_URL || '';

/**
 * API error with status and detail information.
 */
export interface ApiError extends Error {
  status: number;
  detail: string;
}

/**
 * Get the current JWT token from localStorage.
 * Checks both possible token keys for compatibility.
 */
export function getAuthToken(): string | null {
  return localStorage.getItem('jwt_token') || localStorage.getItem('auth_token');
}

/**
 * Set the JWT token in localStorage.
 */
export function setAuthToken(token: string): void {
  localStorage.setItem('jwt_token', token);
}

/**
 * Create headers with authentication.
 */
export function createHeaders(): HeadersInit {
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
 * Extracts error details from the response body.
 */
export async function handleResponse<T>(response: Response): Promise<T> {
  if (!response.ok) {
    const errorData = await response.json().catch(() => ({}));
    const error = new Error(errorData.detail || `API error: ${response.status}`) as ApiError;
    error.status = response.status;
    error.detail = errorData.detail;
    throw error;
  }
  return response.json();
}

/**
 * Build query string from a filters object.
 * Handles undefined values and converts booleans/numbers to strings.
 */
export function buildQueryString(filters: Record<string, unknown>): string {
  const params = new URLSearchParams();

  for (const [key, value] of Object.entries(filters)) {
    if (value !== undefined && value !== null) {
      params.append(key, String(value));
    }
  }

  const queryString = params.toString();
  return queryString ? `?${queryString}` : '';
}
