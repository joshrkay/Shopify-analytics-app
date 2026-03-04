import { useState, useEffect } from 'react';
import { Page, Card, Select, SkeletonPage, SkeletonBodyText, EmptyState, Banner, InlineGrid, Text, Box } from '@shopify/polaris';
import { RetentionHeatmap } from '../components/charts/RetentionHeatmap';
import { getCohortRetention } from '../services/cohortAnalysisApi';
import type { CohortAnalysisResponse } from '../services/cohortAnalysisApi';

export function CohortAnalysis() {
  const [timeframe, setTimeframe] = useState('12m');
  const [data, setData] = useState<CohortAnalysisResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);

    getCohortRetention(timeframe)
      .then(result => {
        if (!cancelled) {
          setData(result);
          setLoading(false);
        }
      })
      .catch(err => {
        if (!cancelled) {
          setError(err.message || 'Failed to load cohort data');
          setLoading(false);
        }
      });

    return () => { cancelled = true; };
  }, [timeframe]);

  if (loading && !data) {
    return (
      <SkeletonPage title="Cohort Analysis">
        <Card><SkeletonBodyText lines={8} /></Card>
      </SkeletonPage>
    );
  }

  const timeframeOptions = [
    { label: '3 months', value: '3m' },
    { label: '6 months', value: '6m' },
    { label: '12 months', value: '12m' },
  ];

  return (
    <Page title="Cohort Analysis">
      <Box paddingBlockEnd="400">
        <InlineGrid columns={4} gap="400">
          <Select
            label="Timeframe"
            options={timeframeOptions}
            value={timeframe}
            onChange={setTimeframe}
          />
        </InlineGrid>
      </Box>

      {error && (
        <Box paddingBlockEnd="400">
          <Banner tone="critical" title="Error loading cohort data">
            {error}
          </Banner>
        </Box>
      )}

      {data && data.cohorts.length > 0 && (
        <>
          <Box paddingBlockEnd="400">
            <InlineGrid columns={4} gap="400">
              <Card>
                <Text as="p" variant="bodySm" tone="subdued">Avg Retention (M1)</Text>
                <Text as="p" variant="headingLg">{(data.summary.avg_retention_month_1 * 100).toFixed(1)}%</Text>
              </Card>
              <Card>
                <Text as="p" variant="bodySm" tone="subdued">Best Cohort</Text>
                <Text as="p" variant="headingLg">{data.summary.best_cohort.slice(0, 7) || '-'}</Text>
              </Card>
              <Card>
                <Text as="p" variant="bodySm" tone="subdued">Worst Cohort</Text>
                <Text as="p" variant="headingLg">{data.summary.worst_cohort.slice(0, 7) || '-'}</Text>
              </Card>
              <Card>
                <Text as="p" variant="bodySm" tone="subdued">Total Cohorts</Text>
                <Text as="p" variant="headingLg">{data.summary.total_cohorts}</Text>
              </Card>
            </InlineGrid>
          </Box>

          <Card>
            <RetentionHeatmap cohorts={data.cohorts} />
          </Card>
        </>
      )}

      {data && data.cohorts.length === 0 && (
        <Card>
          <EmptyState
            heading="No cohort data yet"
            image=""
          >
            <p>Connect data sources to see cohort analysis.</p>
          </EmptyState>
        </Card>
      )}
    </Page>
  );
}
