/**
 * Changelog types for Story 9.7 - In-App Changelog & Release Notes
 *
 * Provides type definitions for changelog entries and read status tracking.
 */

// =============================================================================
// Enum Types
// =============================================================================

/**
 * Types of changelog releases.
 */
export type ReleaseType = 'feature' | 'improvement' | 'fix' | 'deprecation' | 'security';

/**
 * Feature areas for contextual badge targeting.
 */
export type FeatureArea =
  | 'dashboard'
  | 'sync_health'
  | 'insights'
  | 'recommendations'
  | 'approvals'
  | 'connectors'
  | 'billing'
  | 'settings'
  | 'reports'
  | 'notifications';

// =============================================================================
// Data Interfaces
// =============================================================================

/**
 * A changelog entry as returned by the API.
 */
export interface ChangelogEntry {
  id: string;
  version: string;
  title: string;
  summary: string;
  content?: string;
  release_type: ReleaseType;
  feature_areas: FeatureArea[];
  published_at?: string;
  documentation_url?: string;
  is_read: boolean;
}

/**
 * Admin view of a changelog entry with additional metadata.
 */
export interface ChangelogAdminEntry extends ChangelogEntry {
  is_published: boolean;
  created_by_user_id: string;
  created_at: string;
  updated_at: string;
}

// =============================================================================
// Response Interfaces
// =============================================================================

/**
 * Response for changelog list queries.
 */
export interface ChangelogListResponse {
  entries: ChangelogEntry[];
  total: number;
  has_more: boolean;
  unread_count: number;
}

/**
 * Response for admin changelog list queries.
 */
export interface ChangelogAdminListResponse {
  entries: ChangelogAdminEntry[];
  total: number;
  has_more: boolean;
}

/**
 * Response for unread count query.
 */
export interface ChangelogUnreadCountResponse {
  count: number;
  by_feature_area: Record<string, number>;
}

/**
 * Response after marking entries as read.
 */
export interface ChangelogMarkReadResponse {
  marked_count: number;
  unread_count: number;
}

// =============================================================================
// Request/Filter Interfaces
// =============================================================================

/**
 * Filters for changelog list queries.
 */
export interface ChangelogFilters {
  release_type?: ReleaseType;
  feature_area?: FeatureArea;
  include_read?: boolean;
  limit?: number;
  offset?: number;
}

/**
 * Request to create a new changelog entry (admin only).
 */
export interface ChangelogCreateRequest {
  version: string;
  title: string;
  summary: string;
  content?: string;
  release_type: ReleaseType;
  feature_areas?: FeatureArea[];
  documentation_url?: string;
}

/**
 * Request to update a changelog entry (admin only).
 */
export interface ChangelogUpdateRequest {
  version?: string;
  title?: string;
  summary?: string;
  content?: string;
  release_type?: ReleaseType;
  feature_areas?: FeatureArea[];
  documentation_url?: string;
}

// =============================================================================
// Utility Functions
// =============================================================================

/**
 * Get human-readable label for a release type.
 */
export function getReleaseTypeLabel(type: ReleaseType): string {
  const labels: Record<ReleaseType, string> = {
    feature: 'New Feature',
    improvement: 'Improvement',
    fix: 'Bug Fix',
    deprecation: 'Deprecation',
    security: 'Security',
  };
  return labels[type] || type;
}

/**
 * Get badge tone for a release type (for Polaris Badge).
 */
export function getReleaseTypeTone(
  type: ReleaseType
): 'info' | 'success' | 'warning' | 'critical' | 'attention' | undefined {
  const tones: Record<ReleaseType, 'info' | 'success' | 'warning' | 'critical' | 'attention' | undefined> = {
    feature: 'success',
    improvement: 'info',
    fix: 'attention',
    deprecation: 'warning',
    security: 'critical',
  };
  return tones[type];
}

/**
 * Get icon name for a release type.
 */
export function getReleaseTypeIcon(type: ReleaseType): string {
  const icons: Record<ReleaseType, string> = {
    feature: 'StarFilledIcon',
    improvement: 'ArrowUpIcon',
    fix: 'WrenchIcon',
    deprecation: 'AlertCircleIcon',
    security: 'LockIcon',
  };
  return icons[type] || 'InfoIcon';
}

/**
 * Get human-readable label for a feature area.
 */
export function getFeatureAreaLabel(area: FeatureArea): string {
  const labels: Record<FeatureArea, string> = {
    dashboard: 'Dashboard',
    sync_health: 'Sync Health',
    insights: 'AI Insights',
    recommendations: 'Recommendations',
    approvals: 'Approvals',
    connectors: 'Connectors',
    billing: 'Billing',
    settings: 'Settings',
    reports: 'Reports',
    notifications: 'Notifications',
  };
  return labels[area] || area;
}

/**
 * Format a date string for display.
 */
export function formatChangelogDate(dateString?: string): string {
  if (!dateString) return '';
  const date = new Date(dateString);
  return date.toLocaleDateString('en-US', {
    year: 'numeric',
    month: 'short',
    day: 'numeric',
  });
}

/**
 * Group changelog entries by version.
 */
export function groupEntriesByVersion(entries: ChangelogEntry[]): Map<string, ChangelogEntry[]> {
  const grouped = new Map<string, ChangelogEntry[]>();
  for (const entry of entries) {
    const existing = grouped.get(entry.version) || [];
    existing.push(entry);
    grouped.set(entry.version, existing);
  }
  return grouped;
}
