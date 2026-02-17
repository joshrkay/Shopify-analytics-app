/**
 * BillingCheckout — handles the checkout flow for plan upgrades.
 *
 * Reads plan_id from URL query params, calls POST /api/billing/checkout,
 * and redirects to the Shopify confirmation URL for paid plans,
 * or navigates back to the app for free plan activations.
 */

import { useEffect, useState, useCallback } from 'react';
import { useSearchParams, useNavigate } from 'react-router-dom';
import { Page, Banner, Spinner, BlockStack, Text, Button, Card } from '@shopify/polaris';
import { createCheckout } from '../services/billingApi';

type CheckoutState = 'loading' | 'error' | 'redirecting' | 'activated';

export default function BillingCheckout() {
  const [searchParams] = useSearchParams();
  const navigate = useNavigate();
  const planId = searchParams.get('plan_id');

  const [state, setState] = useState<CheckoutState>('loading');
  const [errorMessage, setErrorMessage] = useState('');

  const initiateCheckout = useCallback(async () => {
    if (!planId) {
      setState('error');
      setErrorMessage('No plan selected. Please go back and choose a plan.');
      return;
    }

    setState('loading');
    setErrorMessage('');

    try {
      const result = await createCheckout({
        plan_id: planId,
        return_url: window.location.origin + '/billing/callback',
      });

      if (!result.success) {
        setState('error');
        setErrorMessage('Checkout creation failed. Please try again.');
        return;
      }

      // If checkout_url is empty or points to our app, it means the plan
      // was activated directly (e.g. free plan — no Shopify redirect needed)
      if (!result.checkout_url || result.checkout_url.startsWith(window.location.origin)) {
        setState('activated');
        return;
      }

      // Redirect to Shopify confirmation page
      setState('redirecting');
      window.location.href = result.checkout_url;
    } catch (err: unknown) {
      setState('error');
      const message = err instanceof Error ? err.message : 'An unexpected error occurred.';
      setErrorMessage(message);
    }
  }, [planId]);

  useEffect(() => {
    initiateCheckout();
  }, [initiateCheckout]);

  if (state === 'loading') {
    return (
      <Page title="Processing Checkout">
        <Card>
          <BlockStack gap="400" inlineAlign="center">
            <Spinner size="large" />
            <Text as="p" variant="bodyMd">
              Setting up your subscription, please wait...
            </Text>
          </BlockStack>
        </Card>
      </Page>
    );
  }

  if (state === 'redirecting') {
    return (
      <Page title="Redirecting to Shopify">
        <Card>
          <BlockStack gap="400" inlineAlign="center">
            <Spinner size="large" />
            <Text as="p" variant="bodyMd">
              Redirecting you to Shopify to confirm your subscription...
            </Text>
          </BlockStack>
        </Card>
      </Page>
    );
  }

  if (state === 'activated') {
    return (
      <Page title="Plan Activated">
        <Card>
          <BlockStack gap="400">
            <Banner tone="success" title="Your plan has been activated!">
              <p>You can now access all features included in your plan.</p>
            </Banner>
            <Button variant="primary" onClick={() => navigate('/')}>
              Go to Dashboard
            </Button>
          </BlockStack>
        </Card>
      </Page>
    );
  }

  // Error state
  return (
    <Page title="Checkout Error">
      <Card>
        <BlockStack gap="400">
          <Banner tone="critical" title="Unable to process checkout">
            <p>{errorMessage}</p>
          </Banner>
          <BlockStack gap="200" inlineAlign="start">
            <Button variant="primary" onClick={initiateCheckout}>
              Try Again
            </Button>
            <Button onClick={() => navigate('/paywall')}>
              Back to Plans
            </Button>
          </BlockStack>
        </BlockStack>
      </Card>
    </Page>
  );
}
