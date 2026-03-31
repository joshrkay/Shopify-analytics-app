/**
 * NotificationBadge Component
 *
 * Generic badge component for displaying notification counts.
 * Used for insights, changelog, and other notification indicators.
 *
 * Consolidates duplicate logic from InsightBadge and ChangelogBadge.
 */

import { useState, useEffect, useCallback } from 'react';
import { Loader2 } from 'lucide-react';
import { cn } from '../ui/utils';

interface NotificationBadgeProps {
  /**
   * Function to fetch the count. Should return a Promise<number>.
   */
  fetchCount: () => Promise<number>;
  /**
   * Optional click handler when badge is clicked.
   */
  onClick?: () => void;
  /**
   * Refresh interval in milliseconds. Set to 0 to disable auto-refresh.
   * Default: 60000 (1 minute)
   */
  refreshInterval?: number;
  /**
   * Show text label alongside count.
   */
  showLabel?: boolean;
  /**
   * Custom label text.
   */
  label?: string;
  /**
   * Tooltip text template. Use {count} as placeholder for the count.
   * Default: "{count} new item(s)"
   */
  tooltipTemplate?: string;
  /**
   * Badge tone.
   * Default: "attention"
   */
  tone?: 'info' | 'success' | 'warning' | 'critical' | 'attention';
  /**
   * Singular noun for tooltip (e.g., "insight", "update").
   */
  singularNoun?: string;
  /**
   * Plural noun for tooltip (e.g., "insights", "updates").
   */
  pluralNoun?: string;
}

function toneClasses(
  tone: 'info' | 'success' | 'warning' | 'critical' | 'attention',
): string {
  switch (tone) {
    case 'success':
      return 'border border-emerald-200 bg-emerald-50 text-emerald-800';
    case 'warning':
    case 'attention':
      return 'border border-amber-200 bg-amber-50 text-amber-800';
    case 'critical':
      return 'border border-red-200 bg-red-50 text-red-800';
    case 'info':
      return 'border border-blue-200 bg-blue-50 text-blue-800';
  }
}

export function NotificationBadge({
  fetchCount,
  onClick,
  refreshInterval = 60000,
  showLabel = false,
  label = 'Notifications',
  tone = 'attention',
  singularNoun = 'item',
  pluralNoun = 'items',
}: NotificationBadgeProps) {
  const [count, setCount] = useState<number | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState(false);

  const loadCount = useCallback(async () => {
    try {
      const unreadCount = await fetchCount();
      setCount(unreadCount);
      setError(false);
    } catch (err) {
      console.error('Failed to fetch notification count:', err);
      setError(true);
    } finally {
      setIsLoading(false);
    }
  }, [fetchCount]);

  useEffect(() => {
    loadCount();

    if (refreshInterval > 0) {
      const interval = setInterval(loadCount, refreshInterval);
      return () => clearInterval(interval);
    }
  }, [loadCount, refreshInterval]);

  if (isLoading && count === null) {
    if (showLabel) {
      return (
        <span className="inline-flex items-center gap-1">
          <span className="text-sm text-gray-700">{label}</span>
          <Loader2 className="h-4 w-4 animate-spin text-gray-500" aria-hidden />
        </span>
      );
    }
    return <Loader2 className="h-4 w-4 animate-spin text-gray-500" aria-hidden />;
  }

  if (error || count === null || count === 0) {
    if (showLabel) {
      return (
        <span className="text-sm text-gray-500">{label}</span>
      );
    }
    return null;
  }

  const displayCount = count > 99 ? '99+' : count.toString();
  const tooltipText = `${count} ${count === 1 ? singularNoun : pluralNoun}`;

  const badge = (
    <span
      className={cn(
        'inline-flex min-w-[1.25rem] items-center justify-center rounded-full px-1.5 py-0.5 text-xs font-medium',
        toneClasses(tone),
      )}
    >
      {displayCount}
    </span>
  );

  const badgeContent = showLabel ? (
    <span className="inline-flex items-center gap-1">
      <span className="text-sm text-gray-600">{label}</span>
      {badge}
    </span>
  ) : (
    badge
  );

  if (onClick) {
    return (
      <button
        type="button"
        title={tooltipText}
        onClick={onClick}
        className="inline-flex border-0 bg-transparent p-0 cursor-pointer"
        aria-label={tooltipText}
      >
        {badgeContent}
      </button>
    );
  }

  return (
    <span title={tooltipText} className="inline-flex">
      {badgeContent}
    </span>
  );
}

export default NotificationBadge;
