import { expect, test } from '@playwright/test';

const criticalPaths = ['/', '/home', '/sources', '/settings'];

for (const path of criticalPaths) {
  test(`loads ${path} without server errors`, async ({ page }) => {
    const response = await page.goto(path, { waitUntil: 'domcontentloaded' });

    expect(response, `no response for ${path}`).not.toBeNull();
    expect(response!.status(), `unexpected status for ${path}`).toBeLessThan(500);

    await expect(page.locator('body')).toBeVisible();
    await page.waitForLoadState('networkidle').catch(() => {});

    const html = (await page.content()).toLowerCase();
    expect(html.length).toBeGreaterThan(200);
    expect(html).not.toContain('internal server error');
  });
}
