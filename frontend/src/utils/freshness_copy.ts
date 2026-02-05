/**
 * freshness_copy.ts
 *
 * Centralized copy/text utilities for data freshness indicators.
 * All merchant-visible text for freshness states lives here, not in components.
 * This keeps copy consistent across banners, badges, tooltips, and any other
 * surfaces that communicate data freshness to the merchant.
 */

/**
 * Possible data freshness states for analytics data sources.
 * - 'fresh': All data is current and up to date.
 * - 'stale': Data is behind but still partially usable.
 * - 'unavailable': Data cannot be displayed at this time.
 */
export type DataFreshnessState = 'fresh' | 'stale' | 'unavailable';

/**
 * Returns a short, human-friendly label for the given freshness state.
 * Suitable for badges and inline status indicators.
 */
export function getFreshnessLabel(state: DataFreshnessState): string {
  switch (state) {
    case 'fresh':
      return 'Up to date';
    case 'stale':
      return 'Data delayed';
    case 'unavailable':
      return 'Data temporarily unavailable';
  }
}

/**
 * Returns the banner title for the given freshness state.
 * Returns an empty string for 'fresh' since no banner should be shown.
 */
export function getFreshnessBannerTitle(state: DataFreshnessState): string {
  switch (state) {
    case 'fresh':
      return '';
    case 'stale':
      return 'Data Update in Progress';
    case 'unavailable':
      return 'Data Temporarily Unavailable';
  }
}

/**
 * Returns the banner body message for the given freshness state and optional reason.
 * Messages are written in plain English without timestamps so they remain accurate
 * regardless of when the merchant reads them.
 *
 * @param state - The current data freshness state.
 * @param reason - Optional backend reason code (e.g. 'sla_exceeded', 'sync_failed',
 *   'grace_window_exceeded', 'never_synced') that refines the message.
 */
export function getFreshnessBannerMessage(
  state: DataFreshnessState,
  reason?: string,
): string {
  if (state === 'stale') {
    switch (reason) {
      case 'sla_exceeded':
        return 'Your data is being updated and may not reflect the very latest changes. This is normal and updates typically complete within a few hours.';
      case 'sync_failed':
        return 'A recent data update encountered an issue. Our team has been notified and your data will be refreshed shortly.';
      default:
        return 'Some of your data is being refreshed. You can still use the app, but some numbers may not be fully current.';
    }
  }

  if (state === 'unavailable') {
    switch (reason) {
      case 'grace_window_exceeded':
        return 'Your data is temporarily unavailable while we process updates. This usually resolves automatically. If this persists, please contact support.';
      case 'sync_failed':
        return 'We\'re experiencing difficulties updating your data. Our team is working on it. Please try again in a few minutes.';
      case 'never_synced':
        return 'Your data sources are being set up for the first time. This may take a few minutes to complete.';
      default:
        return 'Your data is temporarily unavailable. Please try again in a few minutes.';
    }
  }

  // 'fresh' state should not display a banner message, but return empty for safety.
  return '';
}

/**
 * Returns tooltip text for the given freshness state.
 * Provides a brief, reassuring explanation in one to two sentences.
 *
 * @param state - The current data freshness state.
 * @param _reason - Reserved for future use; currently unused.
 */
export function getFreshnessTooltip(
  state: DataFreshnessState,
  _reason?: string,
): string {
  switch (state) {
    case 'fresh':
      return 'All your data sources are current and up to date.';
    case 'stale':
      return 'Your data is being updated. Some information may be slightly behind.';
    case 'unavailable':
      return 'Your data is temporarily unavailable while updates are processed.';
  }
}

/**
 * Returns the Polaris Badge tone for the given freshness state.
 * Maps freshness states to the Badge component's tone prop values.
 */
export function getFreshnessBadgeTone(
  state: DataFreshnessState,
): 'success' | 'attention' | 'critical' {
  switch (state) {
    case 'fresh':
      return 'success';
    case 'stale':
      return 'attention';
    case 'unavailable':
      return 'critical';
  }
}

/**
 * Returns the Polaris Banner tone for the given freshness state.
 * The 'fresh' state maps to 'info' for type safety, though a banner
 * should not be rendered in that state.
 */
export function getFreshnessBannerTone(
  state: DataFreshnessState,
): 'info' | 'warning' | 'critical' {
  switch (state) {
    case 'fresh':
      return 'info';
    case 'stale':
      return 'warning';
    case 'unavailable':
      return 'critical';
  }
}
