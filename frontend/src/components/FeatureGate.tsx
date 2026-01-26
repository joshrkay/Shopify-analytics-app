/**
 * FeatureGate Component
 *
 * Wraps content that requires a specific feature or category entitlement.
 * Shows locked state with tooltip when feature/category is not entitled.
 * Supports premium categories: exports, ai, heavy_recompute
 */

import React, { ReactNode } from 'react';
import {
  Card,
  BlockStack,
  Text,
  Button,
  Tooltip,
  InlineStack,
  Icon,
} from '@shopify/polaris';
import { LockIcon } from '@shopify/polaris-icons';
import type { EntitlementsResponse, PremiumCategory } from '../services/entitlementsApi';
import {
  isFeatureEntitled,
  isCategoryEntitled,
  getCategoryEntitlement,
  getBillingState,
} from '../services/entitlementsApi';

interface FeatureGateProps {
  /**
   * Feature key to check entitlement for (legacy support).
   */
  feature?: string;
  /**
   * Premium category to check entitlement for.
   */
  category?: PremiumCategory;
  /**
   * Current entitlements from server.
   */
  entitlements: EntitlementsResponse | null;
  /**
   * Children to render when feature/category is entitled.
   */
  children: ReactNode;
  /**
   * Custom message to show when locked.
   */
  lockedMessage?: string;
  /**
   * Callback when upgrade button is clicked.
   */
  onUpgrade?: () => void;
  /**
   * Callback when "Fix billing" button is clicked.
   */
  onFixBilling?: () => void;
  /**
   * Whether to show as disabled card or inline.
   */
  variant?: 'card' | 'inline';
  /**
   * Whether to disable children instead of hiding them (for buttons).
   */
  disableInsteadOfHide?: boolean;
}

/**
 * FeatureGate component that locks content based on entitlements.
 */
export function FeatureGate({
  feature,
  category,
  entitlements,
  children,
  lockedMessage,
  onUpgrade,
  onFixBilling,
  variant = 'card',
  disableInsteadOfHide = false,
}: FeatureGateProps) {
  // Determine entitlement
  let isEntitled = false;
  let reason: string | null = null;
  let actionRequired: string | null = null;
  let isDegradedAccess = false;

  if (category) {
    const categoryEntitlement = getCategoryEntitlement(entitlements, category);
    isEntitled = categoryEntitlement?.is_entitled ?? false;
    reason = categoryEntitlement?.reason || null;
    actionRequired = categoryEntitlement?.action_required || null;
    isDegradedAccess = categoryEntitlement?.is_degraded_access ?? false;
  } else if (feature) {
    isEntitled = isFeatureEntitled(entitlements, feature);
    const featureEntitlement = entitlements?.features[feature];
    reason = featureEntitlement?.reason || null;
  } else {
    // No feature or category specified - always allow
    return <>{children}</>;
  }

  const billingState = getBillingState(entitlements);
  const defaultReason = lockedMessage || reason || 'Upgrade required';

  // If entitled, render children normally
  if (isEntitled && !isDegradedAccess) {
    return <>{children}</>;
  }

  // Degraded access: show disabled state with tooltip
  if (isEntitled && isDegradedAccess && disableInsteadOfHide) {
    const tooltipMessage = reason || 
      (billingState === 'grace_period' ? 'Premium features disabled during grace period' :
       billingState === 'canceled' ? 'Premium features disabled for canceled subscription' :
       billingState === 'expired' ? 'Premium features require active subscription' :
       'Feature temporarily unavailable');

    return (
      <Tooltip content={tooltipMessage}>
        <div style={{ opacity: 0.6, pointerEvents: 'none', cursor: 'not-allowed' }}>
          {children}
        </div>
      </Tooltip>
    );
  }

  // Locked state
  if (variant === 'inline') {
    return (
      <Tooltip content={defaultReason}>
        <div>
          <InlineStack gap="200" align="start">
            <Icon source={LockIcon} tone="subdued" />
            <div style={{ opacity: 0.5, pointerEvents: 'none' }}>
              {children}
            </div>
          </InlineStack>
        </div>
      </Tooltip>
    );
  }

  // Card variant (default)
  const actionButton = actionRequired === 'update_payment' && onFixBilling
    ? (
        <Button
          variant="primary"
          onClick={onFixBilling}
        >
          Fix Billing
        </Button>
      )
    : onUpgrade
    ? (
        <Button
          variant="primary"
          onClick={onUpgrade}
        >
          Upgrade Plan
        </Button>
      )
    : null;

  return (
    <Card>
      <BlockStack gap="400">
        <InlineStack gap="200" align="start">
          <Icon source={LockIcon} tone="subdued" />
          <BlockStack gap="200">
            <Text as="h3" variant="headingMd">
              Feature Locked
            </Text>
            <Text as="p" tone="subdued">
              {defaultReason}
            </Text>
          </BlockStack>
        </InlineStack>
        {actionButton}
        {/* Show locked content with reduced opacity */}
        <div style={{ opacity: 0.3, pointerEvents: 'none' }}>
          {children}
        </div>
      </BlockStack>
    </Card>
  );
}

/**
 * Hook to check if a feature is entitled.
 */
export function useFeatureEntitlement(
  feature: string,
  entitlements: EntitlementsResponse | null
): { isEntitled: boolean; reason: string | null } {
  const isEntitled = isFeatureEntitled(entitlements, feature);
  const featureEntitlement = entitlements?.features[feature];
  const reason = featureEntitlement?.reason || null;

  return { isEntitled, reason };
}

/**
 * Hook to check if a category is entitled.
 */
export function useCategoryEntitlement(
  category: PremiumCategory,
  entitlements: EntitlementsResponse | null
): {
  isEntitled: boolean;
  reason: string | null;
  actionRequired: string | null;
  isDegradedAccess: boolean;
} {
  const categoryEntitlement = getCategoryEntitlement(entitlements, category);
  return {
    isEntitled: categoryEntitlement?.is_entitled ?? false,
    reason: categoryEntitlement?.reason || null,
    actionRequired: categoryEntitlement?.action_required || null,
    isDegradedAccess: categoryEntitlement?.is_degraded_access ?? false,
  };
}
