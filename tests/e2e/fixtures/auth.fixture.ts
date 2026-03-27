/**
 * Authentication fixtures for E2E tests.
 *
 * Provides pre-authenticated browser contexts by injecting JWTs
 * into localStorage, bypassing the Clerk sign-in flow entirely.
 *
 * The frontend's clerk-mock.ts (loaded via Vite alias in E2E mode)
 * reads the token from localStorage. The backend verifies it using
 * the shared RSA key pair (E2E_AUTH_MODE=mock).
 */
import { test as base, Page, BrowserContext } from '@playwright/test';
import {
  createTestToken,
  createFreeTierToken,
  createProTierToken,
  createEnterpriseTierToken,
  createAdminToken,
  createAgencyToken,
  createGrowthTierToken,
  createExpiredToken,
  TokenOptions,
} from '../helpers/jwt-generator';

/** Storage keys matching the frontend's apiUtils.ts and App.tsx */
const JWT_STORAGE_KEY = 'jwt_token';
const ONBOARDING_COMPLETE_KEY = 'onboardingComplete';

export interface AuthFixtures {
  /** Page authenticated as a free-tier user. */
  freeTierPage: Page;
  /** Page authenticated as a Growth-tier user. */
  growthTierPage: Page;
  /** Page authenticated as a Pro-tier user (AI features enabled). */
  proTierPage: Page;
  /** Page authenticated as an Enterprise-tier user (all features). */
  enterpriseTierPage: Page;
  /** Page authenticated as an admin user. */
  adminPage: Page;
  /** Create a page with custom auth options. */
  createAuthenticatedPage: (options: TokenOptions) => Promise<Page>;
  /** Create a page for a specific tenant (for isolation tests). */
  createTenantPage: (tenantId: string, tier?: 'free' | 'growth' | 'pro' | 'enterprise') => Promise<Page>;
}

/**
 * Inject a JWT into the browser's localStorage before navigating.
 * This bypasses the Clerk auth flow entirely.
 */
async function injectAuth(context: BrowserContext, token: string): Promise<Page> {
  const page = await context.newPage();

  // Navigate to a blank page first to set localStorage on the correct origin
  await page.goto('about:blank');

  // Set the origin to match the app's URL so localStorage is on the right domain
  const baseURL = page.context().browser()?.contexts()[0]?.pages()[0]?.url() || 'http://localhost:3000';
  await page.goto(`${process.env.E2E_BASE_URL || 'http://localhost:3000'}/`);
  await page.waitForLoadState('domcontentloaded');

  // Inject auth token and onboarding flag
  await page.evaluate(
    ({ token, jwtKey, onboardingKey }) => {
      localStorage.setItem(jwtKey, token);
      localStorage.setItem(onboardingKey, 'true');
    },
    { token, jwtKey: JWT_STORAGE_KEY, onboardingKey: ONBOARDING_COMPLETE_KEY },
  );

  // Reload to pick up the injected auth state
  await page.reload({ waitUntil: 'networkidle' });

  return page;
}

/** Default tenant IDs for test tiers */
const DEFAULT_TENANT_IDS = {
  free: 'e2e-tenant-free-001',
  growth: 'e2e-tenant-growth-001',
  pro: 'e2e-tenant-pro-001',
  enterprise: 'e2e-tenant-enterprise-001',
  admin: 'e2e-tenant-admin-001',
};

/**
 * Extended Playwright test with pre-authenticated page fixtures.
 *
 * Usage:
 *   import { test } from '../fixtures/auth.fixture';
 *
 *   test('dashboard loads for pro user', async ({ proTierPage }) => {
 *     await proTierPage.goto('/');
 *     await expect(proTierPage.locator('[data-testid="kpi-card"]')).toBeVisible();
 *   });
 */
export const test = base.extend<AuthFixtures>({
  freeTierPage: async ({ browser }, use) => {
    const context = await browser.newContext();
    const token = createFreeTierToken(DEFAULT_TENANT_IDS.free, 'user_e2e_free');
    const page = await injectAuth(context, token);
    await use(page);
    await context.close();
  },

  growthTierPage: async ({ browser }, use) => {
    const context = await browser.newContext();
    const token = createGrowthTierToken(DEFAULT_TENANT_IDS.growth, 'user_e2e_growth');
    const page = await injectAuth(context, token);
    await use(page);
    await context.close();
  },

  proTierPage: async ({ browser }, use) => {
    const context = await browser.newContext();
    const token = createProTierToken(DEFAULT_TENANT_IDS.pro, 'user_e2e_pro');
    const page = await injectAuth(context, token);
    await use(page);
    await context.close();
  },

  enterpriseTierPage: async ({ browser }, use) => {
    const context = await browser.newContext();
    const token = createEnterpriseTierToken(DEFAULT_TENANT_IDS.enterprise, 'user_e2e_enterprise');
    const page = await injectAuth(context, token);
    await use(page);
    await context.close();
  },

  adminPage: async ({ browser }, use) => {
    const context = await browser.newContext();
    const token = createAdminToken(DEFAULT_TENANT_IDS.admin, 'user_e2e_admin');
    const page = await injectAuth(context, token);
    await use(page);
    await context.close();
  },

  createAuthenticatedPage: async ({ browser }, use) => {
    const contexts: BrowserContext[] = [];

    const factory = async (options: TokenOptions): Promise<Page> => {
      const context = await browser.newContext();
      contexts.push(context);
      const token = createTestToken(options);
      return injectAuth(context, token);
    };

    await use(factory);

    for (const ctx of contexts) {
      await ctx.close();
    }
  },

  createTenantPage: async ({ browser }, use) => {
    const contexts: BrowserContext[] = [];

    const factory = async (tenantId: string, tier: 'free' | 'growth' | 'pro' | 'enterprise' = 'free'): Promise<Page> => {
      const context = await browser.newContext();
      contexts.push(context);

      const tokenCreators = {
        free: createFreeTierToken,
        growth: createGrowthTierToken,
        pro: createProTierToken,
        enterprise: createEnterpriseTierToken,
      };

      const token = tokenCreators[tier](tenantId);
      return injectAuth(context, token);
    };

    await use(factory);

    for (const ctx of contexts) {
      await ctx.close();
    }
  },
});

export { expect } from '@playwright/test';
export { DEFAULT_TENANT_IDS };
