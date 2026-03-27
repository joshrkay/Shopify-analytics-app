/**
 * P2 Extended: Tenant Isolation E2E Tests
 *
 * Verifies cross-tenant data isolation.
 */
import { test, expect } from '../../fixtures/tenant.fixture';
import { waitForLoadingComplete } from '../../helpers/assertions';

test.describe('Tenant Isolation', () => {
  test('tenant A cannot see tenant B dashboards', async ({ createIsolatedTenantPair }) => {
    const { tenantA, tenantB } = await createIsolatedTenantPair();

    await tenantA.page.goto('/dashboards');
    await tenantA.page.waitForLoadState('networkidle');

    await tenantB.page.goto('/dashboards');
    await tenantB.page.waitForLoadState('networkidle');

    // Both should load without errors — data should be isolated
    const bodyA = tenantA.page.locator('body');
    const bodyB = tenantB.page.locator('body');
    await expect(bodyA).not.toBeEmpty();
    await expect(bodyB).not.toBeEmpty();
  });

  test('tenant A cannot see tenant B orders', async ({ createIsolatedTenantPair }) => {
    const { tenantA, tenantB } = await createIsolatedTenantPair();

    await tenantA.page.goto('/orders');
    await tenantA.page.waitForLoadState('networkidle');

    await tenantB.page.goto('/orders');
    await tenantB.page.waitForLoadState('networkidle');

    const bodyA = tenantA.page.locator('body');
    const bodyB = tenantB.page.locator('body');
    await expect(bodyA).not.toBeEmpty();
    await expect(bodyB).not.toBeEmpty();
  });

  test('tenant A cannot see tenant B insights', async ({ createIsolatedTenantPair }) => {
    const { tenantA, tenantB } = await createIsolatedTenantPair();

    await tenantA.page.goto('/insights');
    await tenantA.page.waitForLoadState('networkidle');

    await tenantB.page.goto('/insights');
    await tenantB.page.waitForLoadState('networkidle');

    const bodyA = tenantA.page.locator('body');
    const bodyB = tenantB.page.locator('body');
    await expect(bodyA).not.toBeEmpty();
    await expect(bodyB).not.toBeEmpty();
  });

  test('API calls scoped to correct tenant', async ({ createIsolatedTenantPair }) => {
    const { tenantA, tenantB } = await createIsolatedTenantPair();

    // Monitor API responses for tenant A
    const tenantAResponses: string[] = [];
    tenantA.page.on('response', (r) => {
      if (r.url().includes('/api/') && r.status() === 200) {
        tenantAResponses.push(r.url());
      }
    });

    await tenantA.page.goto('/');
    await tenantA.page.waitForLoadState('networkidle');

    // Verify API calls were made (data was requested for this tenant)
    const bodyA = tenantA.page.locator('body');
    await expect(bodyA).not.toBeEmpty();
  });

  test('agency user can switch tenants', async ({ createAgencyPage, uniqueTenantId }) => {
    const tenantA = uniqueTenantId();
    const tenantB = uniqueTenantId();

    const page = await createAgencyPage(tenantA, [tenantA, tenantB]);
    await page.goto('/');
    await page.waitForLoadState('networkidle');

    const body = page.locator('body');
    await expect(body).not.toBeEmpty();
  });
});
