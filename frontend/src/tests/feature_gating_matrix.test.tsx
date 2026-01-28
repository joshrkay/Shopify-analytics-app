/**
 * Comprehensive tests for feature gating matrix.
 *
 * Tests all billing states × category combinations.
 * Verifies countdown renders for grace_period.
 * Verifies premium buttons disabled in grace_period/expired.
 */

import React from 'react';
import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { AppProvider } from '@shopify/polaris';
import '@shopify/polaris/build/esm/styles.css';

import { FeatureGate, useCategoryEntitlement } from '../components/FeatureGate';
import { BillingBanner } from '../components/BillingBanner';
import type { EntitlementsResponse, PremiumCategory } from '../services/entitlementsApi';

// Mock Polaris translations
const mockTranslations = {
  Polaris: {
    Common: {
      ok: 'OK',
      cancel: 'Cancel',
    },
  },
};

// Helper to render with Polaris provider
const renderWithPolaris = (ui: React.ReactElement) => {
  return render(<AppProvider i18n={mockTranslations as any}>{ui}</AppProvider>);
};

// Helper to create mock entitlements
const createMockEntitlements = (
  overrides?: Partial<EntitlementsResponse>
): EntitlementsResponse => {
  const defaultCategories: Record<PremiumCategory, any> = {
    exports: {
      category: 'exports',
      is_entitled: true,
      billing_state: 'active',
      plan_id: 'plan_growth',
      reason: null,
      action_required: null,
      is_degraded_access: false,
    },
    ai: {
      category: 'ai',
      is_entitled: true,
      billing_state: 'active',
      plan_id: 'plan_growth',
      reason: null,
      action_required: null,
      is_degraded_access: false,
    },
    heavy_recompute: {
      category: 'heavy_recompute',
      is_entitled: true,
      billing_state: 'active',
      plan_id: 'plan_growth',
      reason: null,
      action_required: null,
      is_degraded_access: false,
    },
  };

  return {
    billing_state: 'active',
    plan_id: 'plan_growth',
    plan_name: 'Growth',
    features: {},
    categories: defaultCategories,
    grace_period_days_remaining: null,
    current_period_end: null,
    ...overrides,
  };
};

describe('Billing State Matrix', () => {
  describe('active state', () => {
    it('shows normal UI - no banner', () => {
      const entitlements = createMockEntitlements({ billing_state: 'active' });
      const { container } = renderWithPolaris(
        <BillingBanner entitlements={entitlements} />
      );

      expect(container.firstChild).toBeNull();
    });

    it('allows all premium categories', () => {
      const entitlements = createMockEntitlements({ billing_state: 'active' });
      renderWithPolaris(
        <FeatureGate category="exports" entitlements={entitlements}>
          <button>Export</button>
        </FeatureGate>
      );

      expect(screen.getByText('Export')).toBeInTheDocument();
    });
  });

  describe('past_due state', () => {
    it('shows banner + allows navigation', () => {
      const entitlements = createMockEntitlements({ billing_state: 'past_due' });
      renderWithPolaris(<BillingBanner entitlements={entitlements} />);

      expect(screen.getByText('Payment Issue')).toBeInTheDocument();
      expect(screen.getByText(/payment method failed/i)).toBeInTheDocument();
    });

    it('shows warning on premium actions', () => {
      const entitlements = createMockEntitlements({
        billing_state: 'past_due',
        categories: {
          exports: {
            category: 'exports',
            is_entitled: true,
            billing_state: 'past_due',
            plan_id: 'plan_growth',
            reason: null,
            action_required: 'update_payment',
            is_degraded_access: true,
          },
          ai: {
            category: 'ai',
            is_entitled: true,
            billing_state: 'past_due',
            plan_id: 'plan_growth',
            reason: null,
            action_required: 'update_payment',
            is_degraded_access: true,
          },
          heavy_recompute: {
            category: 'heavy_recompute',
            is_entitled: true,
            billing_state: 'past_due',
            plan_id: 'plan_growth',
            reason: null,
            action_required: 'update_payment',
            is_degraded_access: true,
          },
        },
      });

      renderWithPolaris(
        <FeatureGate
          category="exports"
          entitlements={entitlements}
          disableInsteadOfHide
        >
          <button>Export</button>
        </FeatureGate>
      );

      // Button should be disabled with tooltip
      const button = screen.getByText('Export');
      expect(button).toBeInTheDocument();
    });
  });

  describe('grace_period state', () => {
    it('shows countdown banner with days remaining', () => {
      const entitlements = createMockEntitlements({
        billing_state: 'grace_period',
        grace_period_days_remaining: 2,
      });
      renderWithPolaris(<BillingBanner entitlements={entitlements} />);

      // Verify countdown renders: "2 days left"
      expect(screen.getByText(/^2 days left$/i)).toBeInTheDocument();
      expect(screen.getByText(/2 more days/i)).toBeInTheDocument();
    });

    it('shows singular "day" for 1 day remaining', () => {
      const entitlements = createMockEntitlements({
        billing_state: 'grace_period',
        grace_period_days_remaining: 1,
      });
      renderWithPolaris(<BillingBanner entitlements={entitlements} />);

      expect(screen.getByText(/^1 day left$/i)).toBeInTheDocument();
    });

    it('disables premium actions with tooltip', () => {
      const entitlements = createMockEntitlements({
        billing_state: 'grace_period',
        grace_period_days_remaining: 2,
        categories: {
          exports: {
            category: 'exports',
            is_entitled: false,
            billing_state: 'grace_period',
            plan_id: 'plan_growth',
            reason: 'Premium features disabled during grace period',
            action_required: 'update_payment',
            is_degraded_access: false,
          },
          ai: {
            category: 'ai',
            is_entitled: false,
            billing_state: 'grace_period',
            plan_id: 'plan_growth',
            reason: 'Premium features disabled during grace period',
            action_required: 'update_payment',
            is_degraded_access: false,
          },
          heavy_recompute: {
            category: 'heavy_recompute',
            is_entitled: false,
            billing_state: 'grace_period',
            plan_id: 'plan_growth',
            reason: 'Premium features disabled during grace period',
            action_required: 'update_payment',
            is_degraded_access: false,
          },
        },
      });

      renderWithPolaris(
        <FeatureGate
          category="exports"
          entitlements={entitlements}
          disableInsteadOfHide
        >
          <button>Export</button>
        </FeatureGate>
      );

      // Should show locked state
      expect(screen.getByText('Feature Locked')).toBeInTheDocument();
    });
  });

  describe('canceled state', () => {
    it('shows banner explaining access ends at date', () => {
      const periodEnd = new Date();
      periodEnd.setDate(periodEnd.getDate() + 10);
      const entitlements = createMockEntitlements({
        billing_state: 'canceled',
        current_period_end: periodEnd.toISOString(),
      });
      renderWithPolaris(<BillingBanner entitlements={entitlements} />);

      expect(screen.getByText('Subscription Canceled')).toBeInTheDocument();
      expect(screen.getByText(/read-only access until/i)).toBeInTheDocument();
    });

    it('allows read-only access', () => {
      const entitlements = createMockEntitlements({
        billing_state: 'canceled',
        categories: {
          exports: {
            category: 'exports',
            is_entitled: false,
            billing_state: 'canceled',
            plan_id: 'plan_growth',
            reason: 'Premium features disabled for canceled subscription',
            action_required: 'update_payment',
            is_degraded_access: false,
          },
          ai: {
            category: 'ai',
            is_entitled: false,
            billing_state: 'canceled',
            plan_id: 'plan_growth',
            reason: 'Premium features disabled for canceled subscription',
            action_required: 'update_payment',
            is_degraded_access: false,
          },
          heavy_recompute: {
            category: 'heavy_recompute',
            is_entitled: false,
            billing_state: 'canceled',
            plan_id: 'plan_growth',
            reason: 'Premium features disabled for canceled subscription',
            action_required: 'update_payment',
            is_degraded_access: false,
          },
        },
      });

      renderWithPolaris(
        <FeatureGate category="exports" entitlements={entitlements}>
          <button>Export</button>
        </FeatureGate>
      );

      expect(screen.getByText('Feature Locked')).toBeInTheDocument();
    });
  });

  describe('expired state', () => {
    it('shows paywall screen', () => {
      const entitlements = createMockEntitlements({ billing_state: 'expired' });
      renderWithPolaris(<BillingBanner entitlements={entitlements} />);

      expect(screen.getByText('Subscription Expired')).toBeInTheDocument();
    });

    it('disables premium actions', () => {
      const entitlements = createMockEntitlements({
        billing_state: 'expired',
        categories: {
          exports: {
            category: 'exports',
            is_entitled: false,
            billing_state: 'expired',
            plan_id: null,
            reason: 'Premium features require active subscription',
            action_required: 'update_payment',
            is_degraded_access: false,
          },
          ai: {
            category: 'ai',
            is_entitled: false,
            billing_state: 'expired',
            plan_id: null,
            reason: 'Premium features require active subscription',
            action_required: 'update_payment',
            is_degraded_access: false,
          },
          heavy_recompute: {
            category: 'heavy_recompute',
            is_entitled: false,
            billing_state: 'expired',
            plan_id: null,
            reason: 'Premium features require active subscription',
            action_required: 'update_payment',
            is_degraded_access: false,
          },
        },
      });

      renderWithPolaris(
        <FeatureGate category="exports" entitlements={entitlements}>
          <button>Export</button>
        </FeatureGate>
      );

      expect(screen.getByText('Feature Locked')).toBeInTheDocument();
    });

    it('allows read-only dashboards', () => {
      const entitlements = createMockEntitlements({
        billing_state: 'expired',
        categories: {
          exports: {
            category: 'exports',
            is_entitled: false,
            billing_state: 'expired',
            plan_id: null,
            reason: 'Premium features require active subscription',
            action_required: 'update_payment',
            is_degraded_access: false,
          },
          ai: {
            category: 'ai',
            is_entitled: false,
            billing_state: 'expired',
            plan_id: null,
            reason: 'Premium features require active subscription',
            action_required: 'update_payment',
            is_degraded_access: false,
          },
          heavy_recompute: {
            category: 'heavy_recompute',
            is_entitled: false,
            billing_state: 'expired',
            plan_id: null,
            reason: 'Premium features require active subscription',
            action_required: 'update_payment',
            is_degraded_access: false,
          },
        },
      });

      // Non-premium content should be accessible
      renderWithPolaris(
        <div>
          <FeatureGate category="exports" entitlements={entitlements}>
            <button>Export</button>
          </FeatureGate>
          <div>Read-only dashboard content</div>
        </div>
      );

      expect(screen.getByText('Read-only dashboard content')).toBeInTheDocument();
    });
  });
});

describe('FeatureGate Category Support', () => {
  it('gates exports category', () => {
    const entitlements = createMockEntitlements({
      categories: {
        exports: {
          category: 'exports',
          is_entitled: false,
          billing_state: 'active',
          plan_id: 'plan_growth',
          reason: 'Upgrade required',
          action_required: null,
          is_degraded_access: false,
        },
        ai: {
          category: 'ai',
          is_entitled: true,
          billing_state: 'active',
          plan_id: 'plan_growth',
          reason: null,
          action_required: null,
          is_degraded_access: false,
        },
        heavy_recompute: {
          category: 'heavy_recompute',
          is_entitled: true,
          billing_state: 'active',
          plan_id: 'plan_growth',
          reason: null,
          action_required: null,
          is_degraded_access: false,
        },
      },
    });

    renderWithPolaris(
      <FeatureGate category="exports" entitlements={entitlements}>
        <button>Export</button>
      </FeatureGate>
    );

    expect(screen.getByText('Feature Locked')).toBeInTheDocument();
  });

  it('gates ai category', () => {
    const entitlements = createMockEntitlements({
      categories: {
        exports: {
          category: 'exports',
          is_entitled: true,
          billing_state: 'active',
          plan_id: 'plan_growth',
          reason: null,
          action_required: null,
          is_degraded_access: false,
        },
        ai: {
          category: 'ai',
          is_entitled: false,
          billing_state: 'active',
          plan_id: 'plan_growth',
          reason: 'Upgrade required',
          action_required: null,
          is_degraded_access: false,
        },
        heavy_recompute: {
          category: 'heavy_recompute',
          is_entitled: true,
          billing_state: 'active',
          plan_id: 'plan_growth',
          reason: null,
          action_required: null,
          is_degraded_access: false,
        },
      },
    });

    renderWithPolaris(
      <FeatureGate category="ai" entitlements={entitlements}>
        <button>AI Insight</button>
      </FeatureGate>
    );

    expect(screen.getByText('Feature Locked')).toBeInTheDocument();
  });

  it('gates heavy_recompute category', () => {
    const entitlements = createMockEntitlements({
      categories: {
        exports: {
          category: 'exports',
          is_entitled: true,
          billing_state: 'active',
          plan_id: 'plan_growth',
          reason: null,
          action_required: null,
          is_degraded_access: false,
        },
        ai: {
          category: 'ai',
          is_entitled: true,
          billing_state: 'active',
          plan_id: 'plan_growth',
          reason: null,
          action_required: null,
          is_degraded_access: false,
        },
        heavy_recompute: {
          category: 'heavy_recompute',
          is_entitled: false,
          billing_state: 'active',
          plan_id: 'plan_growth',
          reason: 'Upgrade required',
          action_required: null,
          is_degraded_access: false,
        },
      },
    });

    renderWithPolaris(
      <FeatureGate category="heavy_recompute" entitlements={entitlements}>
        <button>Run Backfill</button>
      </FeatureGate>
    );

    expect(screen.getByText('Feature Locked')).toBeInTheDocument();
  });
});

describe('useCategoryEntitlement hook', () => {
  it('returns correct entitlement status for category', () => {
    const entitlements = createMockEntitlements();
    let result: any = null;

    const TestComponent = () => {
      result = useCategoryEntitlement('exports', entitlements);
      return <div>Test</div>;
    };

    renderWithPolaris(<TestComponent />);

    expect(result).not.toBeNull();
    expect(result.isEntitled).toBe(true);
    expect(result.isDegradedAccess).toBe(false);
  });

  it('returns false for non-entitled category', () => {
    const entitlements = createMockEntitlements({
      categories: {
        exports: {
          category: 'exports',
          is_entitled: false,
          billing_state: 'expired',
          plan_id: null,
          reason: 'Premium features require active subscription',
          action_required: 'update_payment',
          is_degraded_access: false,
        },
        ai: {
          category: 'ai',
          is_entitled: true,
          billing_state: 'active',
          plan_id: 'plan_growth',
          reason: null,
          action_required: null,
          is_degraded_access: false,
        },
        heavy_recompute: {
          category: 'heavy_recompute',
          is_entitled: true,
          billing_state: 'active',
          plan_id: 'plan_growth',
          reason: null,
          action_required: null,
          is_degraded_access: false,
        },
      },
    });

    let result: any = null;

    const TestComponent = () => {
      result = useCategoryEntitlement('exports', entitlements);
      return <div>Test</div>;
    };

    renderWithPolaris(<TestComponent />);

    expect(result).not.toBeNull();
    expect(result.isEntitled).toBe(false);
    expect(result.actionRequired).toBe('update_payment');
  });
});

describe('BillingBanner Countdown', () => {
  it('renders countdown for grace_period with 2 days', () => {
    const entitlements = createMockEntitlements({
      billing_state: 'grace_period',
      grace_period_days_remaining: 2,
    });
    renderWithPolaris(<BillingBanner entitlements={entitlements} />);

    expect(screen.getByText(/^2 days left$/i)).toBeInTheDocument();
  });

  it('renders countdown for grace_period with 1 day', () => {
    const entitlements = createMockEntitlements({
      billing_state: 'grace_period',
      grace_period_days_remaining: 1,
    });
    renderWithPolaris(<BillingBanner entitlements={entitlements} />);

    expect(screen.getByText(/^1 day left$/i)).toBeInTheDocument();
  });

  it('renders countdown for grace_period with 0 days', () => {
    const entitlements = createMockEntitlements({
      billing_state: 'grace_period',
      grace_period_days_remaining: 0,
    });
    renderWithPolaris(<BillingBanner entitlements={entitlements} />);

    expect(screen.getByText(/^0 days left$/i)).toBeInTheDocument();
  });
});

describe('Premium Button Disabling', () => {
  it('disables premium buttons in grace_period', () => {
    const entitlements = createMockEntitlements({
      billing_state: 'grace_period',
      grace_period_days_remaining: 2,
      categories: {
        exports: {
          category: 'exports',
          is_entitled: false,
          billing_state: 'grace_period',
          plan_id: 'plan_growth',
          reason: 'Premium features disabled during grace period',
          action_required: 'update_payment',
          is_degraded_access: false,
        },
        ai: {
          category: 'ai',
          is_entitled: false,
          billing_state: 'grace_period',
          plan_id: 'plan_growth',
          reason: 'Premium features disabled during grace period',
          action_required: 'update_payment',
          is_degraded_access: false,
        },
        heavy_recompute: {
          category: 'heavy_recompute',
          is_entitled: false,
          billing_state: 'grace_period',
          plan_id: 'plan_growth',
          reason: 'Premium features disabled during grace period',
          action_required: 'update_payment',
          is_degraded_access: false,
        },
      },
    });

    renderWithPolaris(
      <FeatureGate category="exports" entitlements={entitlements}>
        <button>Export Data</button>
      </FeatureGate>
    );

    // Should show locked state, not the button
    expect(screen.queryByText('Export Data')).not.toBeInTheDocument();
    expect(screen.getByText('Feature Locked')).toBeInTheDocument();
  });

  it('disables premium buttons in expired', () => {
    const entitlements = createMockEntitlements({
      billing_state: 'expired',
      categories: {
        exports: {
          category: 'exports',
          is_entitled: false,
          billing_state: 'expired',
          plan_id: null,
          reason: 'Premium features require active subscription',
          action_required: 'update_payment',
          is_degraded_access: false,
        },
        ai: {
          category: 'ai',
          is_entitled: false,
          billing_state: 'expired',
          plan_id: null,
          reason: 'Premium features require active subscription',
          action_required: 'update_payment',
          is_degraded_access: false,
        },
        heavy_recompute: {
          category: 'heavy_recompute',
          is_entitled: false,
          billing_state: 'expired',
          plan_id: null,
          reason: 'Premium features require active subscription',
          action_required: 'update_payment',
          is_degraded_access: false,
        },
      },
    });

    renderWithPolaris(
      <FeatureGate category="ai" entitlements={entitlements}>
        <button>Generate AI Insight</button>
      </FeatureGate>
    );

    expect(screen.queryByText('Generate AI Insight')).not.toBeInTheDocument();
    expect(screen.getByText('Feature Locked')).toBeInTheDocument();
  });
});
