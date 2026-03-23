import { API_BASE_URL, createHeadersAsync, handleResponse } from './apiUtils';

export interface ApiKeySummary {
  id: string;
  name: string;
  key_prefix: string;
  created_at: string;
  last_used_at: string | null;
  expires_at: string | null;
  revoked_at: string | null;
  is_active: boolean;
}

export interface ApiKeyListResponse {
  keys: ApiKeySummary[];
}

export interface ApiKeyCreateRequest {
  name: string;
  expires_in_days?: number;
}

export interface ApiKeyCreateResponse {
  key: ApiKeySummary;
  plaintext_key: string;
}

export interface AiInsightsSettings {
  enabled: boolean;
  model: 'gpt-4.1-mini' | 'gpt-4.1' | 'gpt-5-mini';
  cadence: 'daily' | 'weekly';
  include_recommendations: boolean;
  max_insights_per_run: number;
}

export interface AiInsightsSettingsResponse {
  settings: AiInsightsSettings;
  entitled: boolean;
  entitlement_reason: string | null;
}

export async function fetchApiKeys(): Promise<ApiKeyListResponse> {
  const response = await fetch(`${API_BASE_URL}/api/settings/api-keys`, {
    method: 'GET',
    headers: await createHeadersAsync(),
  });

  return handleResponse<ApiKeyListResponse>(response);
}

export async function createApiKey(payload: ApiKeyCreateRequest): Promise<ApiKeyCreateResponse> {
  const response = await fetch(`${API_BASE_URL}/api/settings/api-keys`, {
    method: 'POST',
    headers: await createHeadersAsync(),
    body: JSON.stringify(payload),
  });

  return handleResponse<ApiKeyCreateResponse>(response);
}

export async function revokeApiKey(id: string): Promise<void> {
  const response = await fetch(`${API_BASE_URL}/api/settings/api-keys/${id}`, {
    method: 'DELETE',
    headers: await createHeadersAsync(),
  });

  if (!response.ok) {
    await handleResponse<void>(response);
  }
}

export async function fetchAiInsightsSettings(): Promise<AiInsightsSettingsResponse> {
  const response = await fetch(`${API_BASE_URL}/api/settings/ai-insights`, {
    method: 'GET',
    headers: await createHeadersAsync(),
  });

  return handleResponse<AiInsightsSettingsResponse>(response);
}

export async function updateAiInsightsSettings(payload: AiInsightsSettings): Promise<AiInsightsSettingsResponse> {
  const response = await fetch(`${API_BASE_URL}/api/settings/ai-insights`, {
    method: 'PUT',
    headers: await createHeadersAsync(),
    body: JSON.stringify(payload),
  });

  return handleResponse<AiInsightsSettingsResponse>(response);
}
