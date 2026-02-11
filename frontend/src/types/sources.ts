/**
 * Unified Source types for the Data Sources page.
 *
 * Story 2.1.1 — Unified Source domain model
 */

export type SourcePlatform =
  | 'shopify'
  | 'meta_ads'
  | 'google_ads'
  | 'tiktok_ads'
  | 'snapchat_ads'
  | 'klaviyo'
  | 'shopify_email'
  | 'attentive'
  | 'postscript'
  | 'smsbump';

export type SourceAuthType = 'oauth' | 'api_key';

export type SourceStatus = 'active' | 'pending' | 'inactive' | 'failed' | 'deleted';

export interface Source {
  id: string;
  platform: SourcePlatform;
  displayName: string;
  authType: SourceAuthType;
  status: SourceStatus;
  isEnabled: boolean;
  lastSyncAt: string | null;
  lastSyncStatus: string | null;
}

export interface SourceListResponse {
  sources: Source[];
  total: number;
}

export const PLATFORM_DISPLAY_NAMES: Record<string, string> = {
  shopify: 'Shopify',
  meta_ads: 'Meta Ads',
  google_ads: 'Google Ads',
  tiktok_ads: 'TikTok Ads',
  snapchat_ads: 'Snapchat Ads',
  klaviyo: 'Klaviyo',
  shopify_email: 'Shopify Email',
  attentive: 'Attentive',
  postscript: 'Postscript',
  smsbump: 'SMSBump',
};
