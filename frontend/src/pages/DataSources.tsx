/**
 * Data Sources Page
 *
 * Displays all connected data sources (Shopify + ad platforms) in a unified list.
 * Each source shows: platform name, status badge, auth type, and last sync time.
 *
 * Story 2.1.1 — Unified Source domain model
 */

import { useState, useEffect, useCallback } from 'react';
import {
  Page,
  Layout,
  Card,
  Banner,
  SkeletonPage,
  SkeletonBodyText,
  BlockStack,
  InlineStack,
  Text,
  Badge,
  EmptyState,
  Box,
} from '@shopify/polaris';
import { RefreshIcon } from '@shopify/polaris-icons';

import { listSources } from '../services/sourcesApi';
import { PLATFORM_DISPLAY_NAMES } from '../types/sources';
import type { Source, SourceStatus } from '../types/sources';

function getStatusBadge(status: SourceStatus) {
  switch (status) {
    case 'active':
      return <Badge tone="success">Active</Badge>;
    case 'pending':
      return <Badge tone="attention">Pending</Badge>;
    case 'failed':
      return <Badge tone="critical">Failed</Badge>;
    case 'inactive':
      return <Badge>Inactive</Badge>;
    default:
      return <Badge>{status}</Badge>;
  }
}

function formatLastSync(lastSyncAt: string | null): string {
  if (!lastSyncAt) {
    return 'Never synced';
  }
  const date = new Date(lastSyncAt);
  return date.toLocaleString();
}

function formatAuthType(authType: string): string {
  switch (authType) {
    case 'oauth':
      return 'OAuth';
    case 'api_key':
      return 'API Key';
    default:
      return authType;
  }
}

export default function DataSources() {
  const [sources, setSources] = useState<Source[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [refreshing, setRefreshing] = useState(false);

  const loadSources = useCallback(async (showRefreshing = false) => {
    if (showRefreshing) {
      setRefreshing(true);
    } else {
      setLoading(true);
    }
    setError(null);

    try {
      const data = await listSources();
      setSources(data);
    } catch (err) {
      console.error('Failed to load data sources:', err);
      setError('Failed to load data sources. Please try again.');
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, []);

  useEffect(() => {
    let cancelled = false;

    async function load() {
      try {
        const data = await listSources();
        if (!cancelled) {
          setSources(data);
          setLoading(false);
        }
      } catch (err) {
        if (!cancelled) {
          console.error('Failed to load data sources:', err);
          setError('Failed to load data sources. Please try again.');
          setLoading(false);
        }
      }
    }

    load();

    return () => {
      cancelled = true;
    };
  }, []);

  const handleRefresh = () => {
    loadSources(true);
  };

  if (loading) {
    return (
      <SkeletonPage primaryAction>
        <Layout>
          <Layout.Section>
            <Card>
              <SkeletonBodyText lines={4} />
            </Card>
          </Layout.Section>
          <Layout.Section>
            <Card>
              <SkeletonBodyText lines={8} />
            </Card>
          </Layout.Section>
        </Layout>
      </SkeletonPage>
    );
  }

  if (error) {
    return (
      <Page title="Data Sources">
        <Layout>
          <Layout.Section>
            <Banner
              title="Failed to Load Data Sources"
              tone="critical"
              action={{ content: 'Retry', onAction: handleRefresh }}
            >
              <p>{error}</p>
            </Banner>
          </Layout.Section>
        </Layout>
      </Page>
    );
  }

  if (sources.length === 0) {
    return (
      <Page title="Data Sources">
        <Layout>
          <Layout.Section>
            <Card>
              <EmptyState
                heading="No data sources connected"
                image="https://cdn.shopify.com/s/files/1/0262/4071/2726/files/emptystate-files.png"
              >
                <p>Connect your Shopify store or ad platforms to start syncing data.</p>
              </EmptyState>
            </Card>
          </Layout.Section>
        </Layout>
      </Page>
    );
  }

  return (
    <Page
      title="Data Sources"
      subtitle="Manage your connected data sources"
      primaryAction={{
        content: 'Refresh',
        icon: RefreshIcon,
        loading: refreshing,
        onAction: handleRefresh,
      }}
    >
      <Layout>
        <Layout.Section>
          <Card>
            <BlockStack gap="400">
              <Text as="h2" variant="headingMd">
                Connected Sources ({sources.length})
              </Text>

              <BlockStack gap="300">
                {sources.map((source) => (
                  <Box
                    key={source.id}
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
                        <InlineStack gap="200">
                          <Text as="span" variant="bodySm" tone="subdued">
                            {PLATFORM_DISPLAY_NAMES[source.platform] ?? source.platform}
                          </Text>
                          <Text as="span" variant="bodySm" tone="subdued">
                            {formatAuthType(source.authType)}
                          </Text>
                        </InlineStack>
                      </BlockStack>

                      <InlineStack gap="300" blockAlign="center">
                        <BlockStack gap="100" inlineAlign="end">
                          <Text as="span" variant="bodySm" tone="subdued">
                            Last synced
                          </Text>
                          <Text as="span" variant="bodySm">
                            {formatLastSync(source.lastSyncAt)}
                          </Text>
                        </BlockStack>
                        {getStatusBadge(source.status)}
                      </InlineStack>
                    </InlineStack>
                  </Box>
                ))}
              </BlockStack>
            </BlockStack>
          </Card>
        </Layout.Section>
      </Layout>
    </Page>
  );
}
