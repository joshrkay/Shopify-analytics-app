/**
 * DataHealthBanner Component
 *
 * Displays a merchant-visible banner for DELAYED or UNAVAILABLE health states.
 * Returns null when health is HEALTHY (no banner needed).
 *
 * All copy is sourced from data_health_copy.ts for consistency.
 * Tooltips explain impact, never cause.
 *
 * Story 4.3 - Merchant Data Health Trust Layer
 */

import { X } from 'lucide-react';
import type { MerchantHealthState } from '../../utils/data_health_copy';
import {
  getMerchantHealthBannerTone,
  getMerchantHealthBannerTitle,
  getMerchantHealthBannerMessage,
  getMerchantHealthTooltip,
} from '../../utils/data_health_copy';
import { cn } from '../ui/utils';

interface DataHealthBannerProps {
  /** Current merchant health state. */
  healthState: MerchantHealthState;
  /** Optional dismiss handler. */
  onDismiss?: () => void;
  /** Optional handler to show support CTA (for UNAVAILABLE state). */
  onContactSupport?: () => void;
}

const shell: Record<'info' | 'warning' | 'critical', string> = {
  info: 'border-l-4 border-blue-500 bg-blue-50',
  warning: 'border-l-4 border-amber-500 bg-amber-50',
  critical: 'border-l-4 border-red-500 bg-red-50',
};

/**
 * DataHealthBanner renders a banner for DELAYED or UNAVAILABLE states.
 * Returns null when state is 'healthy'.
 */
export function DataHealthBanner({
  healthState,
  onDismiss,
  onContactSupport,
}: DataHealthBannerProps) {
  if (healthState === 'healthy') {
    return null;
  }

  const tone = getMerchantHealthBannerTone(healthState);
  const title = getMerchantHealthBannerTitle(healthState);
  const message = getMerchantHealthBannerMessage(healthState);
  const tooltipContent = getMerchantHealthTooltip(healthState);

  const showContact = healthState === 'unavailable' && onContactSupport;

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
          <p>
            <span title={tooltipContent} className="cursor-help text-gray-600 underline decoration-dotted">
              Why am I seeing this?
            </span>
          </p>
          {showContact && (
            <button
              type="button"
              className="text-sm font-medium text-blue-700"
              onClick={onContactSupport}
            >
              Contact Support
            </button>
          )}
        </div>
      </div>
    </div>
  );
}

export default DataHealthBanner;
