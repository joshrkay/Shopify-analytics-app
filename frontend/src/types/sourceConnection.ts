/**
 * Source Connection Types
 *
 * Extended type definitions for connection wizard, OAuth flow, and sync configuration.
 * Complements the base Source types in sources.ts.
 *
 * Phase 3 — Subphase 3.1: Extended Type Definitions
 */

import type { SourcePlatform, SourceAuthType, SourceStatus } from './sources';

// =============================================================================
// Catalog Types (Available Platforms)
// =============================================================================

/**
 * Definition of an available data source platform that can be connected.
 * Used in the connection wizard to display platform options.
 */
export interface DataSourceDefinition {
  id: string;
  platform: SourcePlatform;
  displayName: string;
  description: string;
  authType: SourceAuthType;
  logoUrl?: string;
  category: 'ecommerce' | 'ads' | 'email' | 'sms';
  isEnabled: boolean;
}

// =============================================================================
// Connection Wizard Flow State
// =============================================================================

/**
 * Step in the connection wizard flow
 */
export type ConnectionStep = 'select' | 'configure' | 'authenticate' | 'test' | 'complete';

/**
 * State of the connection wizard
 */
export interface ConnectionWizardState {
  step: ConnectionStep;
  selectedPlatform: DataSourceDefinition | null;
  configuration: Record<string, any>;
  testResult: ConnectionTestResult | null;
  error: string | null;
}

/**
 * Result of connection test
 */
export interface ConnectionTestResult {
  success: boolean;
  message: string;
  details?: Record<string, any>;
}

// =============================================================================
// OAuth Flow Types
// =============================================================================

/**
 * Response from initiating OAuth flow
 */
export interface OAuthInitiateResponse {
  authorization_url: string;
  state: string; // CSRF token
  connection_id?: string; // Optional: for tracking the connection being created
}

/**
 * Parameters from OAuth callback redirect
 */
export interface OAuthCallbackParams {
  code: string;
  state: string;
}

/**
 * An ad account discovered from the platform immediately after OAuth.
 * Returned when the backend needs the user to select an account before
 * the Airbyte source can be created (e.g. Meta Ads).
 */
export interface DiscoveredAccount {
  id: string;    // Platform-specific ID, e.g. 'act_123456789'
  name: string;  // Human-readable account name
}

/**
 * Response from completing OAuth flow
 */
export interface OAuthCompleteResponse {
  success: boolean;
  connection_id: string;
  message: string;
  error?: string;
  /** True when account selection is required before the connection can be created. */
  needs_account_selection?: boolean;
  /** Accounts available for selection (set when needs_account_selection is true). */
  discovered_accounts?: DiscoveredAccount[];
  /** Opaque token identifying the stored pending OAuth state in Redis. */
  pending_token?: string;
}

// =============================================================================
// Sync Configuration Types
// =============================================================================

/**
 * Sync frequency options
 */
export type SyncFrequency = 'hourly' | 'six_hourly' | 'daily' | 'weekly';

/**
 * Sync configuration for a data source connection
 */
export interface SyncConfig {
  start_date: string; // ISO date format (YYYY-MM-DD)
  sync_frequency: SyncFrequency;
  enabled_streams?: string[]; // Optional: specific data streams to sync
}

/**
 * Request to update sync configuration
 */
export interface UpdateSyncConfigRequest {
  sync_frequency?: SyncFrequency;
  enabled_streams?: string[];
}

// =============================================================================
// API Response Types
// =============================================================================

/**
 * Response from catalog endpoint
 */
export interface CatalogResponse {
  sources: DataSourceDefinition[];
  total: number;
}

// =============================================================================
// Extended Connection Types (Subphase 3.2)
// =============================================================================

/**
 * Extended data source connection with health and sync progress fields.
 * Merges Source base data with SourceHealthResponse fields from /api/data-health.
 */
export interface DataSourceConnection {
  id: string;
  platform: SourcePlatform;
  displayName: string;
  authType: SourceAuthType;
  status: SourceStatus;
  isEnabled: boolean;
  lastSyncAt: string | null;
  lastSyncStatus: string | null;
  freshnessStatus: string | null;
  minutesSinceSync: number | null;
  isStale: boolean;
  isHealthy: boolean;
  warningMessage: string | null;
  syncFrequencyMinutes: number | null;
  expectedNextSyncAt: string | null;
}

/**
 * Sync progress information from /api/sync/state/{connectionId}.
 */
export interface SyncProgress {
  connectionId: string;
  status: string;
  lastSyncAt: string | null;
  lastSyncStatus: string | null;
  isEnabled: boolean;
  canSync: boolean;
}

/**
 * Detailed sync progress with percentage, stream, and message data.
 * Returned by getSyncProgressDetailed for the wizard progress bar.
 */
export interface DetailedSyncProgress extends SyncProgress {
  percentComplete: number;
  currentStream: string | null;
  message: string | null;
}

/**
 * Global sync settings for the tenant.
 */
export interface GlobalSyncSettings {
  defaultFrequency: SyncFrequency;
  pauseAllSyncs: boolean;
  maxConcurrentSyncs: number;
}

/**
 * Connected account information from ad platform connections.
 */
export interface ConnectedAccount {
  id: string;
  platform: string;
  accountId: string;
  accountName: string;
  connectionId: string;
  airbyteConnectionId: string;
  status: string;
  isEnabled: boolean;
  lastSyncAt: string | null;
  lastSyncStatus: string | null;
}

/**
 * Result from completing the OAuth callback flow.
 */
export type OAuthCallbackResult = OAuthCompleteResponse;

// =============================================================================
// 6-Step Connect Source Wizard Types (Subphase 3.4/3.5)
// =============================================================================

/**
 * Step in the 6-step connect source wizard.
 */
export type WizardStep = 'intro' | 'oauth' | 'accounts' | 'syncConfig' | 'syncing' | 'success';

/**
 * Metadata about each wizard step for the step indicator.
 */
export interface WizardStepMeta {
  key: WizardStep;
  label: string;
  order: number;
}

/**
 * Account option for the account selection step.
 */
export interface AccountOption {
  id: string;
  accountId: string;
  accountName: string;
  platform: string;
  isEnabled: boolean;
  last30dSpend: number | null;
}

/**
 * Sync configuration collected during the wizard.
 */
export interface WizardSyncConfig {
  historicalRange: '30d' | '90d' | '365d' | 'all';
  frequency: SyncFrequency;
  enabledMetrics: string[];
}

/**
 * Full state object for the 6-step connect source wizard.
 */
export interface ConnectSourceWizardState {
  step: WizardStep;
  platform: DataSourceDefinition | null;
  connectionId: string | null;
  oauthState: string | null;
  accounts: AccountOption[];
  selectedAccountIds: string[];
  syncConfig: WizardSyncConfig;
  syncProgress: DetailedSyncProgress | null;
  error: string | null;
  loading: boolean;
  /** Set when the OAuth callback requires account selection (e.g. Meta Ads). */
  pendingToken: string | null;
}
