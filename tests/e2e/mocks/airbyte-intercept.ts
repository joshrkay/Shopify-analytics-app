/**
 * Playwright route interceptor for Airbyte API calls.
 *
 * Airbyte is only called server-side (backend → Airbyte API),
 * so this interceptor is primarily for frontend requests that
 * might reference Airbyte status endpoints.
 */
import { Page, Route } from '@playwright/test';

const AIRBYTE_PATTERNS = [
  '**/airbyte.com/**',
  '**/localhost:9002/**',
];

export async function interceptAirbyte(page: Page): Promise<void> {
  for (const pattern of AIRBYTE_PATTERNS) {
    await page.route(pattern, async (route: Route) => {
      return route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          status: 'active',
          connection_id: 'mock-connection-id',
        }),
      });
    });
  }
}
