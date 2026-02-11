/**
 * Source Normalizer
 *
 * Maps both legacy API shapes (Shopify ingestion + ad platform connections)
 * and the new unified /api/sources response to the Source type.
 *
 * Story 2.1.1 — Unified Source domain model
 */

import type { Source, SourcePlatform, SourceAuthType, SourceStatus } from '../types/sources';

// =============================================================================
// Auth type mapping (platform key -> auth type)
// =============================================================================

const PLATFORM_AUTH_TYPES: Record<string, SourceAuthType> = {
  shopify: 'oauth',
  meta_ads: 'oauth',
  google_ads: 'oauth',
  tiktok_ads: 'oauth',
  snapchat_ads: 'oauth',
  klaviyo: 'api_key',
  shopify_email: 'oauth',
  attentive: 'api_key',
  postscript: 'api_key',
  smsbump: 'api_key',
};

// =============================================================================
// Legacy API Shape: Shopify Ingestion Status
// =============================================================================

export interface ShopifyIngestionStatus {
  connection_id: string;
  connection_name: string;
  status: string;
  is_enabled: boolean;
  can_sync: boolean;
  last_sync_at: string | null;
  last_sync_status: string | null;
}

/**
 * Normalize a Shopify ingestion status response to a unified Source.
 */
export function normalizeShopifySource(raw: ShopifyIngestionStatus): Source {
  return {
    id: raw.connection_id,
    platform: 'shopify',
    displayName: raw.connection_name,
    authType: 'oauth',
    status: raw.status as SourceStatus,
    isEnabled: raw.is_enabled,
    lastSyncAt: raw.last_sync_at,
    lastSyncStatus: raw.last_sync_status,
  };
}

// =============================================================================
// Legacy API Shape: Ad Platform Connection Summary
// =============================================================================

export interface AdConnectionSummary {
  id: string;
  platform: string;
  account_id: string;
  account_name: string;
  connection_id: string;
  airbyte_connection_id: string;
  status: string;
  is_enabled: boolean;
  last_sync_at: string | null;
  last_sync_status: string | null;
}

/**
 * Normalize an ad platform connection summary to a unified Source.
 */
export function normalizeAdSource(raw: AdConnectionSummary): Source {
  const platform = raw.platform as SourcePlatform;
  const authType = PLATFORM_AUTH_TYPES[platform] ?? 'api_key';

  return {
    id: raw.id,
    platform,
    displayName: raw.account_name,
    authType,
    status: raw.status as SourceStatus,
    isEnabled: raw.is_enabled,
    lastSyncAt: raw.last_sync_at,
    lastSyncStatus: raw.last_sync_status,
  };
}

// =============================================================================
// Unified API Shape: /api/sources response
// =============================================================================

export interface RawApiSource {
  id: string;
  platform: string;
  display_name: string;
  auth_type: string;
  status: string;
  is_enabled: boolean;
  last_sync_at: string | null;
  last_sync_status: string | null;
}

/**
 * Normalize a unified API source response (snake_case) to a Source (camelCase).
 */
export function normalizeApiSource(raw: RawApiSource): Source {
  return {
    id: raw.id,
    platform: raw.platform as SourcePlatform,
    displayName: raw.display_name,
    authType: raw.auth_type as SourceAuthType,
    status: raw.status as SourceStatus,
    isEnabled: raw.is_enabled,
    lastSyncAt: raw.last_sync_at,
    lastSyncStatus: raw.last_sync_status,
  };
}
