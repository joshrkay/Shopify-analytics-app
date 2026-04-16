/**
 * Playwright route interceptor for Clerk API calls.
 *
 * Intercepts outgoing requests to Clerk's API domains and returns
 * mock responses so tests don't depend on external Clerk services.
 */
import { Page, Route } from '@playwright/test';

const CLERK_DOMAINS = [
  '**/clerk.accounts.dev/**',
  '**/clerk.example.com/**',
  '**/.well-known/jwks.json',
  '**/v1/client/**',
];

interface ClerkInterceptOptions {
  userId?: string;
  orgId?: string;
  orgName?: string;
}

/**
 * Set up Clerk API interception on a page.
 * Call this before navigating to any authenticated route.
 */
export async function interceptClerk(page: Page, options?: ClerkInterceptOptions): Promise<void> {
  const userId = options?.userId || 'user_mock';
  const orgId = options?.orgId || 'org_demo';
  const orgName = options?.orgName || 'Demo Store';

  for (const pattern of CLERK_DOMAINS) {
    await page.route(pattern, async (route: Route) => {
      const url = route.request().url();

      // JWKS endpoint
      if (url.includes('.well-known/jwks.json') || url.includes('/jwks')) {
        return route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify({ keys: [] }),
        });
      }

      // Client session endpoint
      if (url.includes('/v1/client')) {
        return route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify({
            response: {
              sessions: [{
                id: 'sess_mock',
                status: 'active',
                user: { id: userId, first_name: 'E2E', last_name: 'User' },
                last_active_organization_id: orgId,
              }],
            },
          }),
        });
      }

      // Default: return empty success
      return route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({}),
      });
    });
  }
}
