/**
 * Multi-tenant context fixtures for E2E tests.
 *
 * Provides isolated tenant contexts for testing tenant isolation,
 * agency multi-tenant access, and cross-tenant security.
 */
import { test as base, Page, BrowserContext } from '@playwright/test';
import * as crypto from 'crypto';
import {
  createTestToken,
  createAgencyToken,
  createFreeTierToken,
  createProTierToken,
} from '../helpers/jwt-generator';

const JWT_STORAGE_KEY = 'jwt_token';
const ONBOARDING_COMPLETE_KEY = 'onboardingComplete';

export interface TenantFixtures {
  /** Generate a unique tenant ID for test isolation. */
  uniqueTenantId: () => string;
  /** Create two isolated tenant pages (for cross-tenant tests). */
  createIsolatedTenantPair: () => Promise<{ tenantA: TenantContext; tenantB: TenantContext }>;
  /** Create an agency user page with access to multiple tenants. */
  createAgencyPage: (primaryTenantId: string, allowedTenants: string[]) => Promise<Page>;
}

export interface TenantContext {
  tenantId: string;
  userId: string;
  page: Page;
  context: BrowserContext;
}

async function injectAuthAndNavigate(
  context: BrowserContext,
  token: string,
): Promise<Page> {
  const page = await context.newPage();
  await page.goto(process.env.E2E_BASE_URL || 'http://localhost:3000');
  await page.waitForLoadState('domcontentloaded');
  await page.evaluate(
    ({ token, jwtKey, onboardingKey }) => {
      localStorage.setItem(jwtKey, token);
      localStorage.setItem(onboardingKey, 'true');
    },
    { token, jwtKey: JWT_STORAGE_KEY, onboardingKey: ONBOARDING_COMPLETE_KEY },
  );
  await page.reload({ waitUntil: 'networkidle' });
  return page;
}

export const test = base.extend<TenantFixtures>({
  uniqueTenantId: async ({}, use) => {
    const generator = () => `e2e-tenant-${crypto.randomUUID().slice(0, 12)}`;
    await use(generator);
  },

  createIsolatedTenantPair: async ({ browser }, use) => {
    const contexts: BrowserContext[] = [];

    const factory = async () => {
      const tenantAId = `e2e-tenant-a-${crypto.randomUUID().slice(0, 8)}`;
      const tenantBId = `e2e-tenant-b-${crypto.randomUUID().slice(0, 8)}`;
      const userAId = `user_e2e_a_${crypto.randomUUID().slice(0, 8)}`;
      const userBId = `user_e2e_b_${crypto.randomUUID().slice(0, 8)}`;

      const ctxA = await browser.newContext();
      const ctxB = await browser.newContext();
      contexts.push(ctxA, ctxB);

      const tokenA = createProTierToken(tenantAId, userAId);
      const tokenB = createProTierToken(tenantBId, userBId);

      const pageA = await injectAuthAndNavigate(ctxA, tokenA);
      const pageB = await injectAuthAndNavigate(ctxB, tokenB);

      return {
        tenantA: { tenantId: tenantAId, userId: userAId, page: pageA, context: ctxA },
        tenantB: { tenantId: tenantBId, userId: userBId, page: pageB, context: ctxB },
      };
    };

    await use(factory);

    for (const ctx of contexts) {
      await ctx.close();
    }
  },

  createAgencyPage: async ({ browser }, use) => {
    const contexts: BrowserContext[] = [];

    const factory = async (primaryTenantId: string, allowedTenants: string[]) => {
      const ctx = await browser.newContext();
      contexts.push(ctx);
      const token = createAgencyToken(primaryTenantId, allowedTenants);
      return injectAuthAndNavigate(ctx, token);
    };

    await use(factory);

    for (const ctx of contexts) {
      await ctx.close();
    }
  },
});

export { expect } from '@playwright/test';
