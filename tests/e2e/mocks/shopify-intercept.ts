/**
 * Playwright route interceptor for Shopify API calls.
 *
 * Intercepts frontend requests that reach Shopify domains.
 * Most Shopify API calls go through the backend, but the
 * embedded app bridge and pixel tracking hit Shopify directly.
 */
import { Page, Route } from '@playwright/test';

const SHOPIFY_PATTERNS = [
  '**/myshopify.com/**',
  '**/shopify.com/admin/api/**',
  '**/cdn.shopify.com/**',
];

export async function interceptShopify(page: Page): Promise<void> {
  for (const pattern of SHOPIFY_PATTERNS) {
    await page.route(pattern, async (route: Route) => {
      const url = route.request().url();

      // Shopify App Bridge script
      if (url.includes('cdn.shopify.com') && url.includes('app-bridge')) {
        return route.fulfill({
          status: 200,
          contentType: 'application/javascript',
          body: '/* mock app bridge */',
        });
      }

      // Shopify Admin API (billing, etc.)
      if (url.includes('/admin/api/')) {
        return route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify({ data: {} }),
        });
      }

      // Default: block with empty response
      return route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({}),
      });
    });
  }
}
