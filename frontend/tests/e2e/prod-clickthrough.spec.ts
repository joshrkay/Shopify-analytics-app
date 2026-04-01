import { test, expect } from '@playwright/test';

/**
 * Real-app click-through against whatever `baseURL` is (local Vite or production).
 * Run with a visible browser + slow motion so you can watch navigation:
 *
 *   npm run test:e2e:visual
 *   BASE_URL=https://your.app npm run test:e2e:visual
 */
const pause = (ms: number) => new Promise<void>((resolve) => setTimeout(resolve, ms));

const PUBLIC_ROUTES = [
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

test.describe('Live app click-through', { tag: '@visual-tour' }, () => {
  test.describe.configure({ mode: 'serial' });

  test('walk key routes in the real app (watch the Chromium window)', async ({ page }) => {
    for (const route of PUBLIC_ROUTES) {
      await test.step(`Open ${route}`, async () => {
        const response = await page.goto(route, {
          waitUntil: 'domcontentloaded',
          timeout: 60_000,
        });
        expect(response?.status(), `${route} should respond`).toBeLessThan(500);
        await expect(page.locator('body')).toBeVisible();

        // Let you see the page (headed + --slow-mo amplifies this).
        await page.evaluate(() => window.scrollBy({ top: 320, behavior: 'smooth' }));
        await pause(1200);
        await page.evaluate(() => window.scrollTo({ top: 0, behavior: 'smooth' }));
        await pause(600);
      });
    }
  });

  test('tap a few safe in-app controls (non-destructive)', async ({ page }) => {
    await page.goto('/', { waitUntil: 'domcontentloaded', timeout: 60_000 });
    await expect(page.locator('body')).toBeVisible();
    await pause(800);

    const links = page.locator('a[href^="/"]:visible');
    const n = await links.count();
    const max = Math.min(n, 5);
    for (let i = 0; i < max; i += 1) {
      const href = await links.nth(i).getAttribute('href');
      if (!href || href.startsWith('//') || href.includes('logout')) continue;
      await links.nth(i).click({ timeout: 5000 }).catch(() => undefined);
      await pause(1500);
      await page.goBack({ waitUntil: 'domcontentloaded' }).catch(() => undefined);
      await pause(600);
    }
  });
});
