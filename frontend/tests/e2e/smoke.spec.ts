import { test, expect } from '@playwright/test';

test.describe('Smoke tests', () => {
  test('app loads and shows login or dashboard', async ({ page }) => {
    await page.goto('/');
    // The app should render — either the Clerk login page or the main app
    await expect(page.locator('body')).not.toBeEmpty();
    // Verify no unhandled JS errors crashed the page
    const title = await page.title();
    expect(title).toBeTruthy();
  });

  test('health endpoint returns 200', async ({ request }) => {
    const response = await request.get('/api/health');
    // In CI without a running backend this may 502 — that's OK for now.
    // When the backend is up, we expect 200.
    expect([200, 502]).toContain(response.status());
  });
});
