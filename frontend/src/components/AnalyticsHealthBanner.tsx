/**
 * Analytics Health Banner
 *
 * Banner displayed when analytics is temporarily unavailable.
 * Does NOT leak error details to users - only shows a generic message.
 * Emits audit events to backend for incident tracking (fire-and-forget).
 *
 * Phase 4 - Fallback UX
 */

import React, { useEffect, useRef } from 'react';
import { Loader2 } from 'lucide-react';
import { API_BASE_URL } from '../services/apiUtils';
import type { AccessSurface } from '../types/embed';

export interface AnalyticsHealthBannerProps {
  /** Retry callback */
  onRetry: () => void;
  /** Show spinner on retry button while retrying */
  isRetrying?: boolean;
  /** Error type for audit logging - NOT displayed to user */
  errorType?: string;
  /** Access surface for audit logging */
  accessSurface?: AccessSurface;
}

/**
 * Report a health incident to the backend.
 * Fire-and-forget: does not await response and does not throw on failure.
 */
function reportHealthIncident(errorType: string, accessSurface: string): void {
  try {
    fetch(`${API_BASE_URL}/embed/health/incident`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        error_type: errorType,
        access_surface: accessSurface,
      }),
    }).catch(() => {
      // Silently ignore - fire-and-forget
    });
  } catch {
    // Silently ignore - fire-and-forget
  }
}

/**
 * AnalyticsHealthBanner Component
 *
 * Displays a warning banner when analytics is temporarily unavailable.
 * Provides a retry button and reports incidents to backend audit log.
 */
export const AnalyticsHealthBanner: React.FC<AnalyticsHealthBannerProps> = ({
  onRetry,
  isRetrying = false,
  errorType = 'unknown',
  accessSurface = 'shopify_embed',
}) => {
  const incidentReportedRef = useRef(false);

  useEffect(() => {
    if (!incidentReportedRef.current) {
      incidentReportedRef.current = true;
      reportHealthIncident(errorType, accessSurface);
    }
  }, [errorType, accessSurface]);

  return (
    <div
      className="border-l-4 border-amber-500 bg-amber-50 text-gray-900"
      role="status"
    >
      <div className="p-4">
        <p className="font-semibold">Analytics temporarily unavailable</p>
        <p className="mt-2 text-sm">We&apos;re retrying. You can also try manually.</p>
        <div className="mt-3 flex flex-wrap items-center gap-2">
          {isRetrying && (
            <Loader2 className="h-4 w-4 animate-spin text-gray-600" aria-hidden />
          )}
          <button
            type="button"
            onClick={onRetry}
            disabled={isRetrying}
            className="rounded-md bg-white px-3 py-1.5 text-sm font-medium text-gray-900 shadow ring-1 ring-inset ring-gray-300 hover:bg-gray-50 disabled:cursor-not-allowed disabled:opacity-60"
          >
            {isRetrying ? 'Retrying...' : 'Retry'}
          </button>
        </div>
      </div>
    </div>
  );
};

export default AnalyticsHealthBanner;
