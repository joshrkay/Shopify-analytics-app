/**
 * Integration Card Component
 *
 * Displays a data source platform in the catalog/browse grid on the sources page.
 * Shows platform name, description, and a Connect button.
 * Already-connected platforms show a "Connected" badge.
 *
 * Phase 3 — Subphase 3.3: Source Catalog Page
 */

import { Box, BlockStack, InlineStack, Text, Badge, Button } from '@shopify/polaris';
import type { DataSourceDefinition } from '../../types/sourceConnection';

interface IntegrationCardProps {
  platform: DataSourceDefinition;
  isConnected: boolean;
  onConnect: (platform: DataSourceDefinition) => void;
}

export function IntegrationCard({ platform, isConnected, onConnect }: IntegrationCardProps) {
  return (
    <Box
      background="bg-surface"
      borderColor="border"
      borderWidth="025"
      borderRadius="200"
      padding="400"
    >
      <BlockStack gap="300">
        <InlineStack align="space-between" blockAlign="center">
          <Text as="h3" variant="headingMd" fontWeight="semibold">
            {platform.displayName}
          </Text>
          {isConnected && <Badge tone="success">Connected</Badge>}
        </InlineStack>

        <Text as="p" variant="bodySm" tone="subdued">
          {platform.description}
        </Text>

        <Button
          onClick={() => onConnect(platform)}
          disabled={isConnected || !platform.isEnabled}
          fullWidth
        >
          {isConnected ? 'Connected' : platform.isEnabled ? 'Connect \u2192' : 'Coming Soon'}
        </Button>
      </BlockStack>
    </Box>
  );
}
