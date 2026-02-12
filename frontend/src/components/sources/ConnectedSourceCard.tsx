/**
 * Connected Source Card Component
 *
 * Displays a connected data source with status indicator, sync info, and action buttons.
 * Extracted from the inline rendering in DataSources.tsx for reuse and testability.
 *
 * Phase 3 — Subphase 3.3: Source Catalog Page
 */

import { Box, BlockStack, InlineStack, Text, Badge, Button } from '@shopify/polaris';
import type { Source, SourceStatus } from '../../types/sources';
import { PLATFORM_DISPLAY_NAMES } from '../../types/sources';

interface ConnectedSourceCardProps {
  source: Source;
  onManage: (source: Source) => void;
  onDisconnect: (source: Source) => void;
  onTestConnection: (source: Source) => void;
  testing?: boolean;
}

function getStatusBadge(status: SourceStatus) {
  switch (status) {
    case 'active':
      return <Badge tone="success">Active</Badge>;
    case 'pending':
      return <Badge tone="attention">Pending</Badge>;
    case 'failed':
      return <Badge tone="critical">Error</Badge>;
    case 'inactive':
      return <Badge>Inactive</Badge>;
    default:
      return <Badge>{status}</Badge>;
  }
}

function formatRelativeTime(dateString: string | null): string {
  if (!dateString) {
    return 'Never synced';
  }
  const date = new Date(dateString);
  const now = new Date();
  const diffMs = now.getTime() - date.getTime();
  const diffMinutes = Math.floor(diffMs / 60_000);

  if (diffMinutes < 1) return 'Just now';
  if (diffMinutes < 60) return `${diffMinutes} minute${diffMinutes === 1 ? '' : 's'} ago`;
  const diffHours = Math.floor(diffMinutes / 60);
  if (diffHours < 24) return `${diffHours} hour${diffHours === 1 ? '' : 's'} ago`;
  const diffDays = Math.floor(diffHours / 24);
  return `${diffDays} day${diffDays === 1 ? '' : 's'} ago`;
}

export function ConnectedSourceCard({
  source,
  onManage,
  onDisconnect,
  onTestConnection,
  testing = false,
}: ConnectedSourceCardProps) {
  return (
    <Box
      background="bg-surface"
      borderColor="border"
      borderWidth="025"
      borderRadius="200"
      padding="300"
    >
      <InlineStack align="space-between" blockAlign="center" wrap={false}>
        <BlockStack gap="100">
          <Text as="span" variant="bodyMd" fontWeight="semibold">
            {source.displayName}
          </Text>
          <Text as="span" variant="bodySm" tone="subdued">
            {PLATFORM_DISPLAY_NAMES[source.platform] ?? source.platform}
          </Text>
        </BlockStack>

        <InlineStack gap="400" blockAlign="center">
          <BlockStack gap="100" inlineAlign="end">
            <Text as="span" variant="bodySm" tone="subdued">
              Last sync: {formatRelativeTime(source.lastSyncAt)}
            </Text>
          </BlockStack>

          {getStatusBadge(source.status)}

          <InlineStack gap="200">
            <Button variant="plain" onClick={() => onManage(source)}>
              Manage
            </Button>
            <Button
              variant="plain"
              onClick={() => onTestConnection(source)}
              loading={testing}
            >
              Test
            </Button>
            <Button
              variant="plain"
              tone="critical"
              onClick={() => onDisconnect(source)}
            >
              Disconnect
            </Button>
          </InlineStack>
        </InlineStack>
      </InlineStack>
    </Box>
  );
}
