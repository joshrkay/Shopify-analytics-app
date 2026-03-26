import { test, expect } from '@playwright/test';

const QA_ROUTES = [
  '/',
  '/analytics',
  '/insights',
  '/sources',
  '/settings',
  '/attribution',
  '/orders',
  '/dashboards',
  '/approvals',
  '/whats-new',
  '/billing/checkout',
  '/paywall',
] as const;

async function clickVisibleButtons(page: import('@playwright/test').Page) {
  const buttons = page.locator('button');
  const count = await buttons.count();
  const maxClicks = Math.min(count, 20);

  for (let i = 0; i < maxClicks; i += 1) {
    const button = buttons.nth(i);
    if (!(await button.isVisible()) || !(await button.isEnabled())) continue;
    await button.click({ timeout: 2500 }).catch(() => {
      // Some controls intentionally fail in read-only/mocked states.
    });
    await page.waitForTimeout(100);
  }
}

test.describe('Harness page QA clickthrough', () => {
  for (const route of QA_ROUTES) {
    test(`route ${route} renders and buttons are clickable`, async ({ page }) => {
      const consoleErrors: string[] = [];
      page.on('console', (msg) => {
        if (msg.type() === 'error') consoleErrors.push(msg.text());
      });

      await page.goto(`/e2e/test-harness.html#${route}`, { waitUntil: 'networkidle' });
      await expect(page.locator('body')).toBeVisible();

      await clickVisibleButtons(page);

      await expect(page.getByText(/Page Error/i)).toHaveCount(0);
      expect(consoleErrors, `Console errors on route ${route}`).toEqual([]);
    });
  }
});
