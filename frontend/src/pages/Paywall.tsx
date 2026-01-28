/**
 * Paywall Page
 *
 * Full-screen paywall shown when subscription is expired.
 * Displays upgrade options and plan comparison.
 * For expired state: shows paywall screen, premium actions disabled, allows read-only dashboards.
 */

import React, { useEffect, useState } from 'react';
import {
  Page,
  Layout,
  Card,
  BlockStack,
  InlineStack,
  Text,
  Button,
  Banner,
  List,
} from '@shopify/polaris';
import { useNavigate } from 'react-router-dom';
import { fetchEntitlements, type EntitlementsResponse } from '../services/entitlementsApi';
import { plansApi, type Plan } from '../services/plansApi';

const Paywall: React.FC = () => {
  const navigate = useNavigate();
  const [entitlements, setEntitlements] = useState<EntitlementsResponse | null>(null);
  const [plans, setPlans] = useState<Plan[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const loadData = async () => {
      try {
        const [entitlementsData, plansData] = await Promise.all([
          fetchEntitlements(),
          plansApi.listPlans({ include_inactive: false }),
        ]);
        setEntitlements(entitlementsData);
        setPlans(plansData.plans.filter((p) => p.is_active));
      } catch (err) {
        console.error('Failed to load paywall data:', err);
        setError(err instanceof Error ? err.message : 'Failed to load upgrade options');
      } finally {
        setLoading(false);
      }
    };

    loadData();
  }, []);

  const handleUpgrade = async (planId: string) => {
    try {
      // Navigate to billing action endpoint
      // This would typically create a checkout session or redirect to Shopify billing
      navigate(`/billing/checkout?plan_id=${planId}`);
    } catch (err) {
      console.error('Failed to start upgrade:', err);
      setError('Failed to start upgrade process');
    }
  };

  const handleFixBilling = () => {
    // Navigate to billing action endpoint
    navigate('/billing/update-payment');
  };

  const formatPrice = (cents: number | null): string => {
    if (!cents) return 'Free';
    return `$${(cents / 100).toFixed(2)}`;
  };

  if (loading) {
    return (
      <Page title="Upgrade Required">
        <Layout>
          <Layout.Section>
            <Card>
              <BlockStack gap="400">
                <Text as="p">Loading upgrade options...</Text>
              </BlockStack>
            </Card>
          </Layout.Section>
        </Layout>
      </Page>
    );
  }

  if (error) {
    return (
      <Page title="Upgrade Required">
        <Layout>
          <Layout.Section>
            <Banner tone="critical" title="Error">
              <p>{error}</p>
            </Banner>
          </Layout.Section>
        </Layout>
      </Page>
    );
  }

  const billingState = entitlements?.billing_state;
  const isExpired = billingState === 'expired';
  const isCanceled = billingState === 'canceled';

  // For expired state: show paywall screen
  if (isExpired) {
    return (
      <Page
        title="Subscription Expired"
        narrowWidth
      >
        <Layout>
          <Layout.Section>
            <Card>
              <BlockStack gap="500">
                <BlockStack gap="300">
                  <Text as="h1" variant="heading2xl">
                    Your Subscription Has Expired
                  </Text>
                  <Text as="p" tone="subdued">
                    To continue using premium features, please upgrade your plan.
                    You can still access read-only dashboards.
                  </Text>
                </BlockStack>

                {/* Plan comparison */}
                {plans.length > 0 && (
                  <BlockStack gap="400">
                    <Text as="h2" variant="headingMd">
                      Choose a Plan
                    </Text>
                    <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(250px, 1fr))', gap: '1rem' }}>
                      {plans.map((plan) => (
                        <Card key={plan.id}>
                          <BlockStack gap="400">
                            <BlockStack gap="200">
                              <Text as="h3" variant="headingMd">
                                {plan.display_name}
                              </Text>
                              <Text as="p" variant="heading2xl">
                                {plan.price_monthly_cents ? (
                                  <>
                                    {formatPrice(plan.price_monthly_cents)}
                                    <Text as="span" variant="bodyMd" tone="subdued">
                                      {' '}/month
                                    </Text>
                                  </>
                                ) : (
                                  'Free'
                                )}
                              </Text>
                              {plan.description && (
                                <Text as="p" tone="subdued">
                                  {plan.description}
                                </Text>
                              )}
                            </BlockStack>
                            <Button
                              variant="primary"
                              fullWidth
                              onClick={() => handleUpgrade(plan.id)}
                            >
                              {plan.id === entitlements?.plan_id ? 'Current Plan' : 'Upgrade'}
                            </Button>
                          </BlockStack>
                        </Card>
                      ))}
                    </div>
                  </BlockStack>
                )}

                {/* Features list */}
                <BlockStack gap="300">
                  <Text as="h2" variant="headingMd">
                    Premium Features Include:
                  </Text>
                  <List type="bullet">
                    <List.Item>Advanced analytics and reporting</List.Item>
                    <List.Item>Data export capabilities (CSV, Excel)</List.Item>
                    <List.Item>AI-powered insights and recommendations</List.Item>
                    <List.Item>Heavy computation features (attribution, backfills)</List.Item>
                    <List.Item>Custom dashboards</List.Item>
                    <List.Item>Priority support</List.Item>
                  </List>
                </BlockStack>

                {/* Fix billing CTA */}
                <Button
                  variant="primary"
                  onClick={handleFixBilling}
                >
                  Fix Billing
                </Button>
              </BlockStack>
            </Card>
          </Layout.Section>
        </Layout>
      </Page>
    );
  }

  // For canceled state: similar but with different messaging
  if (isCanceled) {
    return (
      <Page
        title="Subscription Canceled"
        narrowWidth
      >
        <Layout>
          <Layout.Section>
            <Card>
              <BlockStack gap="500">
                <BlockStack gap="300">
                  <Text as="h1" variant="heading2xl">
                    Subscription Canceled
                  </Text>
                  <Text as="p" tone="subdued">
                    Your subscription has been canceled. Upgrade to reactivate premium features.
                  </Text>
                </BlockStack>

                {/* Plan comparison */}
                {plans.length > 0 && (
                  <BlockStack gap="400">
                    <Text as="h2" variant="headingMd">
                      Choose a Plan
                    </Text>
                    <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(250px, 1fr))', gap: '1rem' }}>
                      {plans.map((plan) => (
                        <Card key={plan.id}>
                          <BlockStack gap="400">
                            <BlockStack gap="200">
                              <Text as="h3" variant="headingMd">
                                {plan.display_name}
                              </Text>
                              <Text as="p" variant="heading2xl">
                                {plan.price_monthly_cents ? (
                                  <>
                                    {formatPrice(plan.price_monthly_cents)}
                                    <Text as="span" variant="bodyMd" tone="subdued">
                                      {' '}/month
                                    </Text>
                                  </>
                                ) : (
                                  'Free'
                                )}
                              </Text>
                              {plan.description && (
                                <Text as="p" tone="subdued">
                                  {plan.description}
                                </Text>
                              )}
                            </BlockStack>
                            <Button
                              variant="primary"
                              fullWidth
                              onClick={() => handleUpgrade(plan.id)}
                            >
                              {plan.id === entitlements?.plan_id ? 'Current Plan' : 'Upgrade'}
                            </Button>
                          </BlockStack>
                        </Card>
                      ))}
                    </div>
                  </BlockStack>
                )}

                {/* Fix billing CTA */}
                <Button
                  variant="primary"
                  onClick={handleFixBilling}
                >
                  Fix Billing
                </Button>
              </BlockStack>
            </Card>
          </Layout.Section>
        </Layout>
      </Page>
    );
  }

  // Default upgrade required page
  return (
    <Page
      title="Upgrade Required"
      narrowWidth
    >
      <Layout>
        <Layout.Section>
          <Card>
            <BlockStack gap="500">
              <BlockStack gap="300">
                <Text as="h1" variant="heading2xl">
                  Upgrade Required
                </Text>
                <Text as="p" tone="subdued">
                  This feature requires a premium plan. Choose a plan below to get started.
                </Text>
              </BlockStack>

              {/* Plan comparison */}
              {plans.length > 0 && (
                <BlockStack gap="400">
                  <Text as="h2" variant="headingMd">
                    Choose a Plan
                  </Text>
                  <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(250px, 1fr))', gap: '1rem' }}>
                    {plans.map((plan) => (
                      <Card key={plan.id}>
                        <BlockStack gap="400">
                          <BlockStack gap="200">
                            <Text as="h3" variant="headingMd">
                              {plan.display_name}
                            </Text>
                            <Text as="p" variant="heading2xl">
                              {plan.price_monthly_cents ? (
                                <>
                                  {formatPrice(plan.price_monthly_cents)}
                                  <Text as="span" variant="bodyMd" tone="subdued">
                                    {' '}/month
                                  </Text>
                                </>
                              ) : (
                                'Free'
                              )}
                            </Text>
                            {plan.description && (
                              <Text as="p" tone="subdued">
                                {plan.description}
                              </Text>
                            )}
                          </BlockStack>
                          <Button
                            variant="primary"
                            fullWidth
                            onClick={() => handleUpgrade(plan.id)}
                          >
                            {plan.id === entitlements?.plan_id ? 'Current Plan' : 'Upgrade'}
                          </Button>
                        </BlockStack>
                      </Card>
                    ))}
                  </div>
                </BlockStack>
              )}

              {/* Features list */}
              <BlockStack gap="300">
                <Text as="h2" variant="headingMd">
                  Premium Features Include:
                </Text>
                <List type="bullet">
                  <List.Item>Advanced analytics and reporting</List.Item>
                  <List.Item>Custom dashboards</List.Item>
                  <List.Item>Data export capabilities</List.Item>
                  <List.Item>AI-powered insights</List.Item>
                  <List.Item>Priority support</List.Item>
                </List>
              </BlockStack>
            </BlockStack>
          </Card>
        </Layout.Section>
      </Layout>
    </Page>
  );
};

export default Paywall;
