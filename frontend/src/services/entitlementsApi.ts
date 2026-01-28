/**
 * Entitlements API Service
 *
 * Handles API calls for feature entitlements and billing state.
 * Supports both feature-based and category-based entitlements.
 */

const API_BASE_URL = import.meta.env.VITE_API_URL || '/api/v1';

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
    throw new Error(errorData.detail || `API error: ${response.status}`);
  }
  return response.json();
}

/**
 * Feature entitlement information.
 */
export interface FeatureEntitlement {
  feature: string;
  is_entitled: boolean;
  billing_state: string;
  plan_id: string | null;
  plan_name: string | null;
  reason: string | null;
  required_plan: string | null;
  grace_period_ends_on: string | null;
}

/**
 * Category entitlement information.
 */
export interface CategoryEntitlement {
  category: string;
  is_entitled: boolean;
  billing_state: string;
  plan_id: string | null;
  reason: string | null;
  action_required: string | null;
  is_degraded_access: boolean;
}

/**
 * Premium category types.
 */
export type PremiumCategory = 'exports' | 'ai' | 'heavy_recompute';

/**
 * Complete entitlements response.
 */
export interface EntitlementsResponse {
  billing_state: 'active' | 'past_due' | 'grace_period' | 'canceled' | 'expired' | 'none';
  plan_id: string | null;
  plan_name: string | null;
  features: Record<string, FeatureEntitlement>;
  categories: Record<PremiumCategory, CategoryEntitlement>;
  grace_period_days_remaining: number | null;
  current_period_end: string | null;
}

/**
 * Fetch current entitlements for the tenant.
 */
export async function fetchEntitlements(): Promise<EntitlementsResponse> {
  const response = await fetch(`${API_BASE_URL}/billing/entitlements`, {
    method: 'GET',
    headers: createHeaders(),
  });

  return handleResponse<EntitlementsResponse>(response);
}

/**
 * Check if a specific feature is entitled.
 */
export function isFeatureEntitled(
  entitlements: EntitlementsResponse | null,
  feature: string
): boolean {
  if (!entitlements) {
    return false;
  }

  const featureEntitlement = entitlements.features[feature];
  return featureEntitlement?.is_entitled ?? false;
}

/**
 * Check if a specific category is entitled.
 */
export function isCategoryEntitled(
  entitlements: EntitlementsResponse | null,
  category: PremiumCategory
): boolean {
  if (!entitlements) {
    return false;
  }

  const categoryEntitlement = entitlements.categories[category];
  return categoryEntitlement?.is_entitled ?? false;
}

/**
 * Get category entitlement information.
 */
export function getCategoryEntitlement(
  entitlements: EntitlementsResponse | null,
  category: PremiumCategory
): CategoryEntitlement | null {
  if (!entitlements) {
    return null;
  }

  return entitlements.categories[category] || null;
}

/**
 * Get billing state from entitlements.
 */
export function getBillingState(
  entitlements: EntitlementsResponse | null
): EntitlementsResponse['billing_state'] {
  return entitlements?.billing_state ?? 'none';
}

/**
 * Check if billing state allows read-only access.
 */
export function isReadOnlyAccess(
  entitlements: EntitlementsResponse | null
): boolean {
  const state = getBillingState(entitlements);
  return state === 'grace_period' || state === 'canceled' || state === 'expired';
}

/**
 * Get billing action required.
 */
export function getBillingActionRequired(
  entitlements: EntitlementsResponse | null,
  category?: PremiumCategory
): string | null {
  if (!entitlements) {
    return 'upgrade';
  }

  if (category) {
    const categoryEntitlement = entitlements.categories[category];
    return categoryEntitlement?.action_required || null;
  }

  // Default action based on billing state
  const state = entitlements.billing_state;
  if (state === 'expired' || state === 'canceled') {
    return 'update_payment';
  }
  if (state === 'past_due' || state === 'grace_period') {
    return 'update_payment';
  }
  if (state === 'none') {
    return 'upgrade';
  }

  return null;
}
