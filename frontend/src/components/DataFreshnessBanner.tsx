/**
 * DataFreshnessBanner Component
 *
 * Displays a merchant-visible banner communicating data freshness status.
 * Only renders for STALE or UNAVAILABLE states; returns null when data is fresh.
 * All copy is sourced from freshness_copy.ts to keep text centralized.
 */

import { X } from 'lucide-react';
import type { DataFreshnessState } from '../utils/freshness_copy';
import {
  getFreshnessBannerTone,
  getFreshnessBannerTitle,
  getFreshnessBannerMessage,
  getFreshnessTooltip,
} from '../utils/freshness_copy';
import { cn } from './ui/utils';

interface DataFreshnessBannerProps {
  /** Current data freshness state. */
  state: DataFreshnessState;
  /** Optional backend reason code that refines the banner message. */
  reason?: string;
  /** Optional list of friendly source names affected (e.g. ["Shopify Orders", "Facebook Ads"]). */
  affectedSources?: string[];
  /** Optional dismiss handler passed to Banner's onDismiss. */
  onDismiss?: () => void;
  /** Optional retry handler; renders a "Retry" action button for unavailable state. */
  onRetry?: () => void;
}

const shell: Record<'info' | 'warning' | 'critical', string> = {
  info: 'border-l-4 border-blue-500 bg-blue-50',
  warning: 'border-l-4 border-amber-500 bg-amber-50',
  critical: 'border-l-4 border-red-500 bg-red-50',
};

/**
 * DataFreshnessBanner renders a banner for stale or unavailable data states.
 * Returns null when state is 'fresh' since no banner is needed.
 */
export function DataFreshnessBanner({
  state,
  reason,
  affectedSources,
  onDismiss,
  onRetry,
}: DataFreshnessBannerProps) {
  if (state === 'fresh') {
    return null;
  }

  const tone = getFreshnessBannerTone(state);
  const title = getFreshnessBannerTitle(state);
  const message = getFreshnessBannerMessage(state, reason);
  const tooltipContent = getFreshnessTooltip(state, reason);

  const showRetry = state === 'unavailable' && onRetry;

  return (
    <div className={cn('relative rounded-r-md pr-10', shell[tone])} role="alert">
      {onDismiss && (
        <button
          type="button"
          className="absolute right-2 top-2 rounded p-1 text-gray-600 hover:bg-black/5"
          aria-label="Dismiss"
          onClick={onDismiss}
        >
          <X className="h-4 w-4" aria-hidden />
        </button>
      )}
      <div className="p-4">
        <p className="font-semibold text-gray-900">{title}</p>
        <div className="mt-2 space-y-2 text-sm text-gray-800">
          <p>{message}</p>
          {affectedSources && affectedSources.length > 0 && (
            <p>
              <span className="font-semibold">Affected:</span>{' '}
              {affectedSources.join(', ')}
            </p>
          )}
          <p>
            <span
              title={tooltipContent}
              className="cursor-help text-gray-600 underline decoration-dotted"
            >
              Why am I seeing this?
            </span>
          </p>
          {showRetry && (
            <button
              type="button"
              className="rounded-md bg-white px-3 py-1.5 text-sm font-medium text-gray-900 shadow ring-1 ring-inset ring-gray-300 hover:bg-gray-50"
              onClick={onRetry}
            >
              Retry
            </button>
          )}
        </div>
      </div>
    </div>
  );
}
