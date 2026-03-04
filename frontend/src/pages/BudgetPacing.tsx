import { useState, useEffect, useCallback } from 'react';
import { Page, Card, SkeletonPage, SkeletonBodyText, EmptyState, Banner, Modal, FormLayout, TextField, Select, Box } from '@shopify/polaris';
import { PacingProgressBar } from '../components/budget/PacingProgressBar';
import { getPacing, listBudgets, createBudget } from '../services/budgetPacingApi';
import type { PacingItem, Budget } from '../services/budgetPacingApi';

export function BudgetPacing() {
  const [pacing, setPacing] = useState<PacingItem[]>([]);
  const [, setBudgets] = useState<Budget[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [modalOpen, setModalOpen] = useState(false);

  // New budget form state
  const [newPlatform, setNewPlatform] = useState('meta_ads');
  const [newBudget, setNewBudget] = useState('');

  const fetchData = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [pacingResult, budgetsResult] = await Promise.all([
        getPacing(),
        listBudgets(),
      ]);
      setPacing(pacingResult.pacing);
      setBudgets(budgetsResult);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load budget data');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    let cancelled = false;
    fetchData().then(() => {
      if (cancelled) return;
    });
    return () => { cancelled = true; };
  }, [fetchData]);

  const handleCreateBudget = async () => {
    const cents = Math.round(parseFloat(newBudget) * 100);
    if (isNaN(cents) || cents <= 0) return;

    try {
      await createBudget({
        source_platform: newPlatform,
        budget_monthly_cents: cents,
        start_date: new Date().toISOString().slice(0, 10),
      });
      setModalOpen(false);
      setNewBudget('');
      await fetchData();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to create budget');
    }
  };

  if (loading && pacing.length === 0) {
    return (
      <SkeletonPage title="Budget Pacing">
        <Card><SkeletonBodyText lines={6} /></Card>
      </SkeletonPage>
    );
  }

  const now = new Date();
  const monthLabel = now.toLocaleString('default', { month: 'long', year: 'numeric' });

  const platformOptions = [
    { label: 'Meta Ads', value: 'meta_ads' },
    { label: 'Google Ads', value: 'google_ads' },
    { label: 'TikTok Ads', value: 'tiktok_ads' },
    { label: 'Snapchat Ads', value: 'snapchat_ads' },
    { label: 'Pinterest Ads', value: 'pinterest_ads' },
    { label: 'Twitter Ads', value: 'twitter_ads' },
  ];

  return (
    <Page
      title="Budget Pacing"
      subtitle={monthLabel}
      primaryAction={{ content: 'Set Budget', onAction: () => setModalOpen(true) }}
    >
      {error && (
        <Box paddingBlockEnd="400">
          <Banner tone="critical" title="Error">{error}</Banner>
        </Box>
      )}

      {pacing.length > 0 ? (
        <Card>
          {pacing.map(item => (
            <PacingProgressBar
              key={item.budget_id}
              platform={item.platform}
              pctSpent={item.pct_spent}
              pctTime={item.pct_time}
              budgetCents={item.budget_cents}
              spentCents={item.spent_cents}
              status={item.status}
            />
          ))}
        </Card>
      ) : (
        <Card>
          <EmptyState
            heading="No budgets configured"
            action={{ content: 'Set Budget', onAction: () => setModalOpen(true) }}
            image=""
          >
            <p>Set monthly ad spend budgets to track pacing across platforms.</p>
          </EmptyState>
        </Card>
      )}

      <Modal
        open={modalOpen}
        onClose={() => setModalOpen(false)}
        title="Set Monthly Budget"
        primaryAction={{ content: 'Create', onAction: handleCreateBudget }}
        secondaryActions={[{ content: 'Cancel', onAction: () => setModalOpen(false) }]}
      >
        <Modal.Section>
          <FormLayout>
            <Select
              label="Platform"
              options={platformOptions}
              value={newPlatform}
              onChange={setNewPlatform}
            />
            <TextField
              label="Monthly Budget ($)"
              type="number"
              value={newBudget}
              onChange={setNewBudget}
              autoComplete="off"
            />
          </FormLayout>
        </Modal.Section>
      </Modal>
    </Page>
  );
}
