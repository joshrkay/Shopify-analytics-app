import { API_BASE_URL, createHeadersAsync, handleResponse } from './apiUtils';

export interface BrandingSettings {
  brand_name: string;
  logo_url: string | null;
  accent_color: string;
  email_footer_text: string | null;
}

export interface BrandingSettingsUpdate {
  brand_name?: string | null;
  logo_url?: string | null;
  accent_color?: string | null;
  email_footer_text?: string | null;
}

export async function getBrandingSettings(): Promise<BrandingSettings> {
  const headers = await createHeadersAsync();
  const response = await fetch(`${API_BASE_URL}/api/settings/branding`, { headers });
  return handleResponse<BrandingSettings>(response);
}

export async function updateBrandingSettings(
  settings: BrandingSettingsUpdate,
): Promise<BrandingSettings> {
  const headers = await createHeadersAsync();
  const response = await fetch(`${API_BASE_URL}/api/settings/branding`, {
    method: 'PUT',
    headers: { ...headers, 'Content-Type': 'application/json' },
    body: JSON.stringify(settings),
  });
  return handleResponse<BrandingSettings>(response);
}
