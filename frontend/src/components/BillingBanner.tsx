/**
 * BillingBanner Component
 *
 * Displays banners for different billing states:
 * - past_due: Payment issue warning
 * - grace_period: Countdown banner with days remaining
 * - canceled: Shows access ends at date
 * - expired: Paywall redirect
 */

import React from 'react';
import {
  Banner,
  InlineStack,
  Text,
  Button,
  BlockStack,
} from '@shopify/polaris';
import type { EntitlementsResponse } from '../services/entitlementsApi';
import { getBillingState } from '../services/entitlementsApi';

interface BillingBannerProps {
  /**
   * Current entitlements from server.
   */
  entitlements: EntitlementsResponse | null;
  /**
   * Callback when upgrade button is clicked.
   */
  onUpgrade?: () => void;
  /**
   * Callback when payment update button is clicked.
   */
  onUpdatePayment?: () => void;
}

/**
 * Format date for display.
 */
function formatDate(dateString: string | null): string {
  if (!dateString) return '';
  
  try {
    const date = new Date(dateString);
    return date.toLocaleDateString('en-US', {
      year: 'numeric',
      month: 'long',
      day: 'numeric',
    });
  } catch {
    return dateString;
  }
}

/**
 * BillingBanner component that shows appropriate banner based on billing state.
 */
export function BillingBanner({
  entitlements,
  onUpgrade,
  onUpdatePayment,
}: BillingBannerProps) {
  const billingState = getBillingState(entitlements);

  // No banner for active or none states
  if (billingState === 'active' || billingState === 'none') {
    return null;
  }

  // Past due - payment issue
  if (billingState === 'past_due') {
    return (
      <Banner
        title="Payment Issue"
        tone="critical"
        action={
          onUpdatePayment
            ? {
                content: 'Update Payment Method',
                onAction: onUpdatePayment,
              }
            : undefined
        }
      >
        <BlockStack gap="200">
          <Text as="p">
            Your payment method failed. Please update your payment information to continue using premium features.
          </Text>
        </BlockStack>
      </Banner>
    );
  }

  // Grace period - countdown (format: "2 days left" per acceptance criteria)
  if (billingState === 'grace_period') {
    const daysRemaining = entitlements?.grace_period_days_remaining ?? 0;
    const daysText = daysRemaining === 1 ? 'day' : 'days';

    return (
      <Banner
        title={`${daysRemaining} ${daysText} left`}
        tone="warning"
        action={
          onUpdatePayment
            ? {
                content: 'Update Payment',
                onAction: onUpdatePayment,
              }
            : undefined
        }
      >
        <BlockStack gap="200">
          <Text as="p">
            Your payment method failed, but you still have access for {daysRemaining} more {daysText}.
            Please update your payment information to avoid service interruption.
          </Text>
        </BlockStack>
      </Banner>
    );
  }

  // Canceled - show banner explaining access ends at date
  if (billingState === 'canceled') {
    const periodEnd = entitlements?.current_period_end;
    const periodEndFormatted = periodEnd ? formatDate(periodEnd) : null;

    return (
      <Banner
        title="Subscription Canceled"
        tone="warning"
        action={
          onUpdatePayment
            ? {
                content: 'Fix Billing',
                onAction: onUpdatePayment,
              }
            : undefined
        }
      >
        <BlockStack gap="200">
          <Text as="p">
            Your subscription has been canceled.
            {periodEndFormatted
              ? ` You have read-only access until ${periodEndFormatted}.`
              : ' You have read-only access until your billing period ends.'}
          </Text>
        </BlockStack>
      </Banner>
    );
  }

  // Expired - redirect to paywall handled by parent
  if (billingState === 'expired') {
    return (
      <Banner
        title="Subscription Expired"
        tone="critical"
        action={
          onUpgrade
            ? {
                content: 'Upgrade Now',
                onAction: onUpgrade,
              }
            : undefined
        }
      >
        <BlockStack gap="200">
          <Text as="p">
            Your subscription has expired. Please upgrade to continue using premium features.
          </Text>
        </BlockStack>
      </Banner>
    );
  }

  return null;
}
