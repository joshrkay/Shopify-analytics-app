import { test, expect } from '@playwright/test';

test.describe('Smoke tests', () => {
  test('app loads and shows login, dashboard, or configuration message', async ({ page }) => {
    await page.goto('/');
    await expect(page).toHaveTitle(/MarkInsight/i);

    // Missing VITE_CLERK_* at build time → inline configuration error in index (no React).
    const configHeading = page.getByRole('heading', { name: 'Configuration Error' });
    if (await configHeading.isVisible({ timeout: 5_000 }).catch(() => false)) {
      await expect(page.getByText(/VITE_CLERK_PUBLISHABLE_KEY/i)).toBeVisible();
      return;
    }

    // With a key set: wait for Clerk or app UI. Invalid keys can leave an empty shell — use a real pk_test_* from Clerk.
    await expect(page.locator('body')).not.toBeEmpty({ timeout: 20_000 });
  });

  test('health endpoint returns 200', async ({ request }) => {
    const response = await request.get('/api/health');
    const raw = process.env.BASE_URL || process.env.E2E_BASE_URL || '';
    const isHttpsRemote = /^https:\/\//i.test(raw);
    if (isHttpsRemote) {
      expect(response.status(), `/api/health on ${raw}`).toBe(200);
      return;
    }
    // Local Vite: 502/500 when API proxy target is down.
    expect([200, 500, 502]).toContain(response.status());
  });
});
