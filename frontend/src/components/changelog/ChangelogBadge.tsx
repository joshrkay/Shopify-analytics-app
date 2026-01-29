/**
 * ChangelogBadge Component
 *
 * Displays a badge showing the count of unread changelog entries.
 * Auto-refreshes at a configurable interval.
 *
 * Story 9.7 - In-App Changelog & Release Notes
 */

import { useState, useEffect, useCallback } from 'react';
import { Badge, Tooltip, InlineStack, Text, Spinner } from '@shopify/polaris';
import { getUnreadCountNumber } from '../../services/changelogApi';
import type { FeatureArea } from '../../types/changelog';

interface ChangelogBadgeProps {
  onClick?: () => void;
  refreshInterval?: number;
  showLabel?: boolean;
  label?: string;
  featureArea?: FeatureArea;
}

export function ChangelogBadge({
  onClick,
  refreshInterval = 60000,
  showLabel = false,
  label = "What's New",
  featureArea,
}: ChangelogBadgeProps) {
  const [count, setCount] = useState<number | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState(false);

  const fetchCount = useCallback(async () => {
    try {
      const unreadCount = await getUnreadCountNumber(featureArea);
      setCount(unreadCount);
      setError(false);
    } catch (err) {
      console.error('Failed to fetch changelog count:', err);
      setError(true);
    } finally {
      setIsLoading(false);
    }
  }, [featureArea]);

  useEffect(() => {
    fetchCount();

    // Set up auto-refresh
    const intervalId = setInterval(fetchCount, refreshInterval);

    return () => clearInterval(intervalId);
  }, [fetchCount, refreshInterval]);

  // Don't show anything if loading initially
  if (isLoading && count === null) {
    return showLabel ? (
      <InlineStack gap="100" blockAlign="center">
        <Text as="span" variant="bodySm">
          {label}
        </Text>
        <Spinner size="small" />
      </InlineStack>
    ) : null;
  }

  // Don't show if error or no unread items
  if (error || count === null || count === 0) {
    return showLabel ? (
      <Text as="span" variant="bodySm" tone="subdued">
        {label}
      </Text>
    ) : null;
  }

  const badge = (
    <Badge tone="attention">
      {count > 99 ? '99+' : count}
    </Badge>
  );

  const content = showLabel ? (
    <InlineStack gap="100" blockAlign="center">
      <Text as="span" variant="bodySm">
        {label}
      </Text>
      {badge}
    </InlineStack>
  ) : (
    badge
  );

  if (onClick) {
    return (
      <Tooltip content={`${count} new update${count === 1 ? '' : 's'}`}>
        <button
          type="button"
          onClick={onClick}
          style={{
            background: 'none',
            border: 'none',
            padding: 0,
            cursor: 'pointer',
          }}
        >
          {content}
        </button>
      </Tooltip>
    );
  }

  return (
    <Tooltip content={`${count} new update${count === 1 ? '' : 's'}`}>
      {content}
    </Tooltip>
  );
}

export default ChangelogBadge;
