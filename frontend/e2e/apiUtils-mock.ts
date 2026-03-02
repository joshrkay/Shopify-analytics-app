/**
 * Mock replacement for services/apiUtils.
 * Provides stubs for auth token management and API request utilities
 * so page components can render without a live backend or Clerk session.
 */

export const API_BASE_URL = '';

export class ApiError extends Error {
  status: number;
  constructor(message: string, status = 500) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
  }
}

export function isApiError(err: unknown): err is ApiError {
  return err instanceof ApiError;
}

export function isProvisioningError(_err: unknown): boolean {
  return false;
}

export function setTokenProvider(): void {}
export async function getAuthTokenAsync(): Promise<string | null> {
  return 'mock-jwt-token';
}
export function getAuthToken(): string | null {
  return 'mock-jwt-token';
}
export function setAuthToken(): void {}
export function clearAuthToken(): void {}

export async function createHeadersAsync(): Promise<HeadersInit> {
  return {
    'Content-Type': 'application/json',
    Authorization: 'Bearer mock-jwt-token',
  };
}

export function createHeaders(): HeadersInit {
  return {
    'Content-Type': 'application/json',
    Authorization: 'Bearer mock-jwt-token',
  };
}

export async function fetchWithRetry(
  input: RequestInfo | URL,
  init?: RequestInit,
): Promise<Response> {
  return fetch(input, init);
}

export function isBackendDown(): boolean {
  return false;
}

export function resetCircuitBreaker(): void {}

export async function handleResponse<T>(response: Response): Promise<T> {
  if (!response.ok) {
    throw new ApiError(`HTTP ${response.status}`, response.status);
  }
  return response.json() as Promise<T>;
}

export function buildQueryString<T extends object>(filters: T): string {
  const params = new URLSearchParams();
  for (const [key, value] of Object.entries(filters)) {
    if (value !== undefined && value !== null && value !== '') {
      params.append(key, String(value));
    }
  }
  const str = params.toString();
  return str ? `?${str}` : '';
}

export function getErrorStatus(err: unknown): number | null {
  if (isApiError(err)) return err.status;
  return null;
}

export function getErrorMessage(err: unknown, fallback: string): string {
  if (err instanceof Error) return err.message;
  return fallback;
}
