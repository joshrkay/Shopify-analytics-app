/**
 * Feature gate / entitlement fixtures for E2E tests.
 *
 * Seeds the database with the correct plan and subscription
 * for a given tenant, ensuring that feature-gated routes
 * work correctly based on the billing tier.
 */
import { test as base } from '@playwright/test';

const API_BASE = process.env.E2E_API_URL || 'http://localhost:8000';

/** Known plan IDs matching seed.sql */
export const PLAN_IDS = {
  free: 'plan-free-001',
  growth: 'plan-growth-001',
  pro: 'plan-pro-001',
  enterprise: 'plan-enterprise-001',
};

/** Feature entitlements per tier */
export const TIER_FEATURES: Record<string, string[]> = {
  free: [],
  growth: ['CUSTOM_REPORTS'],
  pro: ['AI_INSIGHTS', 'AI_RECOMMENDATIONS', 'AI_ACTIONS', 'CUSTOM_REPORTS', 'COHORT_ANALYSIS'],
  enterprise: [
    'AI_INSIGHTS', 'AI_RECOMMENDATIONS', 'AI_ACTIONS',
    'CUSTOM_REPORTS', 'COHORT_ANALYSIS',
    'BUDGET_PACING', 'ALERTS', 'ADVANCED_ANALYTICS',
  ],
};

export type BillingTier = 'free' | 'growth' | 'pro' | 'enterprise';

export interface FeatureGateFixtures {
  /** Set up a tenant with a specific billing tier. Creates plan + subscription in DB. */
  setupTierForTenant: (tenantId: string, tier: BillingTier) => Promise<void>;
  /** Check if a feature is entitled for a given tier. */
  isFeatureEntitled: (feature: string, tier: BillingTier) => boolean;
}

export const test = base.extend<FeatureGateFixtures>({
  setupTierForTenant: async ({ request }, use) => {
    const setup = async (tenantId: string, tier: BillingTier): Promise<void> => {
      if (tier === 'free') {
        // Free tier has no subscription — just ensure the tenant exists
        return;
      }

      const response = await request.post(`${API_BASE}/api/test/seed`, {
        data: {
          subscriptions: [
            {
              tenant_id: tenantId,
              plan_id: PLAN_IDS[tier],
              status: 'active',
            },
          ],
        },
        headers: { 'Content-Type': 'application/json' },
      });

      if (!response.ok()) {
        const body = await response.text();
        throw new Error(`Failed to setup ${tier} tier for tenant ${tenantId}: ${response.status()} - ${body}`);
      }
    };

    await use(setup);
  },

  isFeatureEntitled: async ({}, use) => {
    const check = (feature: string, tier: BillingTier): boolean => {
      return TIER_FEATURES[tier]?.includes(feature) ?? false;
    };
    await use(check);
  },
});

export { expect } from '@playwright/test';
