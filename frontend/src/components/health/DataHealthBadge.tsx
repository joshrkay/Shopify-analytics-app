/**
 * DataHealthBadge Component
 *
 * Compact badge showing the merchant-facing data health state.
 * Designed for placement near dashboards and in the app header.
 *
 * Visual states:
 * - Green (success): HEALTHY - all features enabled
 * - Yellow (attention): DELAYED - some data updating
 * - Red (critical): UNAVAILABLE - data temporarily unavailable
 *
 * Story 4.3 - Merchant Data Health Trust Layer
 */

import { CheckCircle, Clock, AlertCircle, Loader2 } from 'lucide-react';
import type { MerchantHealthState } from '../../utils/data_health_copy';
import {
  getMerchantHealthLabel,
  getMerchantHealthTooltip,
  getMerchantHealthBadgeTone,
} from '../../utils/data_health_copy';
import { cn } from '../ui/utils';

interface DataHealthBadgeProps {
  /** Current merchant health state. Null while loading. */
  healthState: MerchantHealthState | null;
  /** Whether data is currently loading. */
  loading?: boolean;
  /** Optional click handler (e.g., navigate to health details). */
  onClick?: () => void;
  /** Show text label alongside badge. */
  showLabel?: boolean;
  /** Show only colored icon without text. */
  compact?: boolean;
}

function badgeToneClasses(tone: 'success' | 'attention' | 'critical'): string {
  switch (tone) {
    case 'success':
      return 'border border-emerald-200 bg-emerald-50 text-emerald-800';
    case 'attention':
      return 'border border-amber-200 bg-amber-50 text-amber-800';
    case 'critical':
      return 'border border-red-200 bg-red-50 text-red-800';
  }
}

function iconToneClass(tone: 'success' | 'attention' | 'critical'): string {
  switch (tone) {
    case 'success':
      return 'text-emerald-600';
    case 'attention':
      return 'text-amber-600';
    case 'critical':
      return 'text-red-600';
  }
}

export function DataHealthBadge({
  healthState,
  loading = false,
  onClick,
  showLabel = false,
  compact = false,
}: DataHealthBadgeProps) {
  if (loading || healthState === null) {
    return (
      <span className="inline-flex items-center" role="status" aria-label="Loading data health">
        <span className="sr-only">Loading data health</span>
        <Loader2 className="h-4 w-4 animate-spin text-gray-500" aria-hidden />
      </span>
    );
  }

  const tone = getMerchantHealthBadgeTone(healthState);
  const label = getMerchantHealthLabel(healthState);
  const tooltipContent = getMerchantHealthTooltip(healthState);

  const IconComponent =
    healthState === 'healthy'
      ? CheckCircle
      : healthState === 'delayed'
        ? Clock
        : AlertCircle;

  const badgeContent = (
    <span className="inline-flex items-center gap-1">
      {showLabel && <span className="text-sm text-gray-700">Data</span>}
      {compact ? (
        <IconComponent className={cn('h-4 w-4', iconToneClass(tone))} aria-hidden />
      ) : (
        <span
          className={cn(
            'inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium',
            badgeToneClasses(tone),
          )}
        >
          {label}
        </span>
      )}
    </span>
  );

  if (onClick) {
    return (
      <button
        type="button"
        onClick={onClick}
        title={tooltipContent}
        className="inline-flex border-0 bg-transparent p-0 cursor-pointer"
        aria-label={tooltipContent}
      >
        {badgeContent}
      </button>
    );
  }

  return (
    <span title={tooltipContent} className="inline-flex">
      {badgeContent}
    </span>
  );
}

export default DataHealthBadge;
