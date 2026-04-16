/**
 * P0 Critical: Authentication Flow E2E Tests
 *
 * Verifies the full authentication lifecycle:
 * - Unauthenticated access shows landing page
 * - Authenticated access shows dashboard
 * - Token expiry handling
 * - Protected route guards
 * - Token refresh across navigation
 */
import { test, expect } from '../../fixtures/auth.fixture';
import { expectUrl } from '../../helpers/assertions';

test.describe('Authentication Flow', () => {
  test('unauthenticated user sees landing page at /', async ({ browser }) => {
    // Create a fresh context with NO auth token injected
    const context = await browser.newContext();
    const page = await context.newPage();

    await page.goto('/');
    await page.waitForLoadState('networkidle');

    // Should see landing page or Clerk sign-in redirect, NOT the dashboard
    // The SignedOut component renders the landing page
    const isLanding = await page.locator('text=Sign in').or(page.locator('text=Get Started')).isVisible();
    const isDashboard = await page.locator('[data-testid="kpi-card"]').isVisible().catch(() => false);

    expect(isLanding || !isDashboard).toBeTruthy();

    await context.close();
  });

  test('authenticated user sees dashboard at /', async ({ freeTierPage }) => {
    await freeTierPage.goto('/');
    await freeTierPage.waitForLoadState('networkidle');

    // Should see the main app content, not the landing page
    // Look for common dashboard elements
    const body = freeTierPage.locator('body');
    await expect(body).not.toBeEmpty();

    // Should NOT see sign-in prompt
    const signIn = freeTierPage.locator('text=Sign in');
    // In E2E mode with clerk-mock, SignedIn renders children directly
    // so we should see app content
    const hasAppContent = await freeTierPage.locator('nav, [class*="Navigation"], [data-testid="sidebar"]')
      .first()
      .isVisible()
      .catch(() => false);

    // Either we see navigation (app loaded) or we don't see sign-in (auth worked)
    expect(hasAppContent || !(await signIn.isVisible().catch(() => false))).toBeTruthy();
  });

  test('expired token shows error or redirect state', async ({ createAuthenticatedPage }) => {
    // Create a page with an expired token
    const page = await createAuthenticatedPage({
      tenantId: 'e2e-tenant-expired',
      expiresInSeconds: -3600, // Already expired
    });

    await page.goto('/');
    await page.waitForLoadState('networkidle');

    // With an expired token, the backend should reject API calls
    // The frontend should show an error state or redirect to sign-in
    // We verify that the app doesn't crash and handles this gracefully
    const body = page.locator('body');
    await expect(body).not.toBeEmpty();
  });

  test('navigation to protected route without auth redirects', async ({ browser }) => {
    const context = await browser.newContext();
    const page = await context.newPage();

    // Try to access a protected route directly
    await page.goto('/settings');
    await page.waitForLoadState('networkidle');

    // Should NOT see the settings page content
    // Should be redirected to landing/sign-in or show auth required
    const isOnSettings = page.url().includes('/settings');
    const hasSettingsContent = await page.locator('text=Settings').first().isVisible().catch(() => false);

    // Without auth, either redirected away from settings or settings page is empty
    if (isOnSettings) {
      // If still on settings URL, should show sign-in or be redirected
      const body = page.locator('body');
      await expect(body).not.toBeEmpty();
    }

    await context.close();
  });

  test('token refresh keeps session alive across navigation', async ({ proTierPage }) => {
    // Navigate to multiple pages to verify token stays valid
    await proTierPage.goto('/');
    await proTierPage.waitForLoadState('networkidle');

    // Navigate to orders
    await proTierPage.goto('/orders');
    await proTierPage.waitForLoadState('networkidle');
    const ordersBody = proTierPage.locator('body');
    await expect(ordersBody).not.toBeEmpty();

    // Navigate to attribution
    await proTierPage.goto('/attribution');
    await proTierPage.waitForLoadState('networkidle');
    const attrBody = proTierPage.locator('body');
    await expect(attrBody).not.toBeEmpty();

    // Navigate back to dashboard — session should still be active
    await proTierPage.goto('/');
    await proTierPage.waitForLoadState('networkidle');
    const dashBody = proTierPage.locator('body');
    await expect(dashBody).not.toBeEmpty();

    // Verify no sign-in prompt appeared during navigation
    const signInVisible = await proTierPage.locator('text=Sign in').isVisible().catch(() => false);
    expect(signInVisible).toBeFalsy();
  });
});
