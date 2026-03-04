import { useState, useEffect, useCallback } from 'react';
import {
  Page, Card, Tabs, SkeletonPage, SkeletonBodyText, EmptyState,
  Banner, Modal, FormLayout, TextField, Select, Badge, Button,
  InlineStack, BlockStack, Text, Box,
} from '@shopify/polaris';
import {
  listAlertRules, createAlertRule, deleteAlertRule, toggleAlertRule, getAlertHistory,
} from '../services/alertsApi';
import type { AlertRule, AlertExecution, RulesListResponse } from '../services/alertsApi';

const SEVERITY_TONES: Record<string, 'info' | 'warning' | 'critical'> = {
  info: 'info',
  warning: 'warning',
  critical: 'critical',
};

const OPERATOR_LABELS: Record<string, string> = {
  gt: '>',
  lt: '<',
  eq: '=',
  gte: '>=',
  lte: '<=',
};

export function Alerts() {
  const [selectedTab, setSelectedTab] = useState(0);
  const [rulesData, setRulesData] = useState<RulesListResponse | null>(null);
  const [history, setHistory] = useState<AlertExecution[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [modalOpen, setModalOpen] = useState(false);

  // Create form state
  const [formName, setFormName] = useState('');
  const [formMetric, setFormMetric] = useState('roas');
  const [formOperator, setFormOperator] = useState('lt');
  const [formThreshold, setFormThreshold] = useState('');
  const [formPeriod, setFormPeriod] = useState('daily');
  const [formSeverity, setFormSeverity] = useState('warning');

  const fetchRules = useCallback(async () => {
    try {
      const result = await listAlertRules();
      setRulesData(result);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load rules');
    }
  }, []);

  const fetchHistory = useCallback(async () => {
    try {
      const result = await getAlertHistory();
      setHistory(result);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load history');
    }
  }, []);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    Promise.all([fetchRules(), fetchHistory()]).then(() => {
      if (!cancelled) setLoading(false);
    });
    return () => { cancelled = true; };
  }, [fetchRules, fetchHistory]);

  const handleCreate = async () => {
    const threshold = parseFloat(formThreshold);
    if (!formName || isNaN(threshold)) return;
    try {
      await createAlertRule({
        name: formName,
        metric_name: formMetric,
        comparison_operator: formOperator,
        threshold_value: threshold,
        evaluation_period: formPeriod,
        severity: formSeverity,
      });
      setModalOpen(false);
      setFormName('');
      setFormThreshold('');
      await fetchRules();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to create rule');
    }
  };

  const handleToggle = async (rule: AlertRule) => {
    await toggleAlertRule(rule.id, !rule.enabled);
    await fetchRules();
  };

  const handleDelete = async (ruleId: string) => {
    await deleteAlertRule(ruleId);
    await fetchRules();
  };

  if (loading && !rulesData) {
    return (
      <SkeletonPage title="Alerts">
        <Card><SkeletonBodyText lines={6} /></Card>
      </SkeletonPage>
    );
  }

  const tabs = [
    { id: 'rules', content: `Rules (${rulesData?.count ?? 0})`, accessibilityLabel: 'Alert Rules' },
    { id: 'history', content: 'History', accessibilityLabel: 'Alert History' },
  ];

  const metricOptions = [
    { label: 'ROAS', value: 'roas' },
    { label: 'Ad Spend', value: 'spend' },
    { label: 'Revenue', value: 'revenue' },
  ];

  const operatorOptions = [
    { label: 'Greater than (>)', value: 'gt' },
    { label: 'Less than (<)', value: 'lt' },
    { label: 'Equal to (=)', value: 'eq' },
    { label: 'Greater or equal (>=)', value: 'gte' },
    { label: 'Less or equal (<=)', value: 'lte' },
  ];

  const periodOptions = [
    { label: 'Daily', value: 'daily' },
    { label: 'Weekly', value: 'weekly' },
    { label: 'Monthly', value: 'monthly' },
  ];

  const severityOptions = [
    { label: 'Info', value: 'info' },
    { label: 'Warning', value: 'warning' },
    { label: 'Critical', value: 'critical' },
  ];

  return (
    <Page
      title="Alerts"
      primaryAction={{ content: 'Create Alert', onAction: () => setModalOpen(true) }}
    >
      {error && (
        <Box paddingBlockEnd="400">
          <Banner tone="critical" title="Error">{error}</Banner>
        </Box>
      )}

      <Tabs tabs={tabs} selected={selectedTab} onSelect={setSelectedTab}>
        {selectedTab === 0 && (
          <Box paddingBlockStart="400">
            {rulesData && rulesData.rules.length > 0 ? (
              <BlockStack gap="300">
                {rulesData.rules.map(rule => (
                  <Card key={rule.id}>
                    <InlineStack align="space-between" blockAlign="center">
                      <BlockStack gap="100">
                        <InlineStack gap="200" blockAlign="center">
                          <Text as="span" variant="headingSm">{rule.name}</Text>
                          <Badge tone={SEVERITY_TONES[rule.severity]}>{rule.severity}</Badge>
                          {!rule.enabled && <Badge>Disabled</Badge>}
                        </InlineStack>
                        <Text as="p" variant="bodySm" tone="subdued">
                          {rule.metric_name} {OPERATOR_LABELS[rule.comparison_operator] || rule.comparison_operator} {rule.threshold_value} ({rule.evaluation_period})
                        </Text>
                      </BlockStack>
                      <InlineStack gap="200">
                        <Button size="slim" onClick={() => handleToggle(rule)}>
                          {rule.enabled ? 'Disable' : 'Enable'}
                        </Button>
                        <Button size="slim" tone="critical" onClick={() => handleDelete(rule.id)}>
                          Delete
                        </Button>
                      </InlineStack>
                    </InlineStack>
                  </Card>
                ))}
              </BlockStack>
            ) : (
              <Card>
                <EmptyState
                  heading="No alert rules yet"
                  action={{ content: 'Create Alert', onAction: () => setModalOpen(true) }}
                  image=""
                >
                  <p>Set up threshold alerts for ROAS, spend, and revenue.</p>
                </EmptyState>
              </Card>
            )}
          </Box>
        )}

        {selectedTab === 1 && (
          <Box paddingBlockStart="400">
            {history.length > 0 ? (
              <Card>
                <BlockStack gap="300">
                  {history.map(exec => (
                    <Box key={exec.id} paddingBlockEnd="200" borderBlockEndWidth="025" borderColor="border">
                      <InlineStack align="space-between">
                        <BlockStack gap="050">
                          <Text as="p" variant="bodySm">
                            Metric value: {exec.metric_value.toFixed(2)} (threshold: {exec.threshold_value.toFixed(2)})
                          </Text>
                          <Text as="p" variant="bodySm" tone="subdued">
                            {new Date(exec.fired_at).toLocaleString()}
                          </Text>
                        </BlockStack>
                        {exec.resolved_at && <Badge tone="success">Resolved</Badge>}
                      </InlineStack>
                    </Box>
                  ))}
                </BlockStack>
              </Card>
            ) : (
              <Card>
                <EmptyState heading="No alert history" image="">
                  <p>Alert executions will appear here when rules are triggered.</p>
                </EmptyState>
              </Card>
            )}
          </Box>
        )}
      </Tabs>

      <Modal
        open={modalOpen}
        onClose={() => setModalOpen(false)}
        title="Create Alert Rule"
        primaryAction={{ content: 'Create', onAction: handleCreate }}
        secondaryActions={[{ content: 'Cancel', onAction: () => setModalOpen(false) }]}
      >
        <Modal.Section>
          <FormLayout>
            <TextField label="Rule Name" value={formName} onChange={setFormName} autoComplete="off" />
            <Select label="Metric" options={metricOptions} value={formMetric} onChange={setFormMetric} />
            <Select label="Condition" options={operatorOptions} value={formOperator} onChange={setFormOperator} />
            <TextField label="Threshold" type="number" value={formThreshold} onChange={setFormThreshold} autoComplete="off" />
            <Select label="Evaluation Period" options={periodOptions} value={formPeriod} onChange={setFormPeriod} />
            <Select label="Severity" options={severityOptions} value={formSeverity} onChange={setFormSeverity} />
          </FormLayout>
        </Modal.Section>
      </Modal>
    </Page>
  );
}
