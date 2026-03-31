/**
 * DashboardFreshnessIndicator Component
 *
 * Shows data freshness summary within dashboard context.
 * More detailed than header badge.
 *
 * Variants:
 * - compact: Inline text with icon
 * - detailed: Shows stale count
 *
 * Story 9.5 - Freshness visible where analytics appear
 */

import { Clock, CheckCircle, AlertCircle } from 'lucide-react';
import { useFreshnessStatus } from '../../contexts/DataHealthContext';
import { cn } from '../ui/utils';

interface DashboardFreshnessIndicatorProps {
  /**
   * Display variant.
   * - compact: Just icon + text
   * - detailed: Icon + text + stale count badge
   */
  variant?: 'compact' | 'detailed';
}

export function DashboardFreshnessIndicator({
  variant = 'compact',
}: DashboardFreshnessIndicatorProps) {
  const { status, hasStaleData, hasCriticalIssues, freshnessLabel, loading } =
    useFreshnessStatus();

  if (loading) {
    return (
      <span className="inline-flex items-center gap-1">
        <Clock className="h-4 w-4 text-gray-400" aria-hidden />
        <span className="text-sm text-gray-500">Checking data freshness...</span>
      </span>
    );
  }

  const IconComponent = hasCriticalIssues
    ? AlertCircle
    : hasStaleData
      ? Clock
      : CheckCircle;

  const tone: 'success' | 'caution' | 'critical' = hasCriticalIssues
    ? 'critical'
    : hasStaleData
      ? 'caution'
      : 'success';

  const iconClass =
    tone === 'critical'
      ? 'text-red-600'
      : tone === 'caution'
        ? 'text-amber-600'
        : 'text-emerald-600';

  const textClass =
    tone === 'success' ? 'text-emerald-700' : 'text-sm text-gray-600';

  const text = hasCriticalIssues
    ? 'Data issues detected'
    : hasStaleData
      ? `Last sync: ${freshnessLabel}`
      : 'All data fresh';

  if (variant === 'compact') {
    return (
      <span className="inline-flex items-center gap-1">
        <IconComponent className={cn('h-4 w-4', iconClass)} aria-hidden />
        <span className={cn('text-sm', textClass)}>{text}</span>
      </span>
    );
  }

  return (
    <span className="inline-flex flex-wrap items-center gap-2">
      <IconComponent className={cn('h-4 w-4', iconClass)} aria-hidden />
      <span className={cn('text-sm', textClass)}>{text}</span>
      {hasStaleData && status === 'degraded' && (
        <span className="inline-flex rounded-full border border-amber-200 bg-amber-50 px-2 py-0.5 text-xs font-medium text-amber-800">
          Some data delayed
        </span>
      )}
      {hasCriticalIssues && (
        <span className="inline-flex rounded-full border border-red-200 bg-red-50 px-2 py-0.5 text-xs font-medium text-red-800">
          Action required
        </span>
      )}
    </span>
  );
}

export default DashboardFreshnessIndicator;
