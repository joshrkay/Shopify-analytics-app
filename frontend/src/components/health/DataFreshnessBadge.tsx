/**
 * DataFreshnessBadge Component
 *
 * Compact badge showing data freshness status.
 * Designed for header/navigation placement.
 *
 * Visual states:
 * - Green (success): All data fresh
 * - Yellow (attention): Some data stale
 * - Red (critical): Critical issues
 *
 * Story 9.5 - Data Freshness Indicators
 */

import { Clock, AlertCircle, Loader2 } from 'lucide-react';
import { useFreshnessStatus } from '../../contexts/DataHealthContext';
import { cn } from '../ui/utils';

interface DataFreshnessBadgeProps {
  /**
   * Optional click handler (e.g., navigate to Sync Status page).
   */
  onClick?: () => void;
  /**
   * Show text label alongside badge.
   */
  showLabel?: boolean;
  /**
   * Show only colored dot without time.
   */
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

export function DataFreshnessBadge({
  onClick,
  showLabel = false,
  compact = false,
}: DataFreshnessBadgeProps) {
  const { hasStaleData, hasCriticalIssues, freshnessLabel, loading } =
    useFreshnessStatus();

  if (loading) {
    return (
      <span className="inline-flex items-center" role="status" aria-label="Loading data health">
        <span className="sr-only">Loading data health</span>
        <Loader2 className="h-4 w-4 animate-spin text-gray-500" aria-hidden />
      </span>
    );
  }

  const getTone = (): 'success' | 'attention' | 'critical' => {
    if (hasCriticalIssues) return 'critical';
    if (hasStaleData) return 'attention';
    return 'success';
  };

  const getTooltipContent = (): string => {
    if (hasCriticalIssues) return 'Critical data issues detected';
    if (hasStaleData) return `Data freshness: ${freshnessLabel}`;
    return 'All data is fresh';
  };

  const getBadgeText = (): string => {
    if (compact) return '';
    if (hasCriticalIssues) return '!';
    if (hasStaleData) return freshnessLabel.replace(' ago', '');
    return 'Fresh';
  };

  const tone = getTone();
  const tooltipContent = getTooltipContent();
  const badgeText = getBadgeText();

  const badgeContent = (
    <span className="inline-flex items-center gap-1">
      {showLabel && <span className="text-sm text-gray-700">Data</span>}
      {compact ? (
        hasCriticalIssues ? (
          <AlertCircle className={cn('h-4 w-4', iconToneClass(tone))} aria-hidden />
        ) : (
          <Clock className={cn('h-4 w-4', iconToneClass(tone))} aria-hidden />
        )
      ) : (
        <span
          className={cn(
            'inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium',
            badgeToneClasses(tone),
          )}
        >
          {badgeText}
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

export default DataFreshnessBadge;
