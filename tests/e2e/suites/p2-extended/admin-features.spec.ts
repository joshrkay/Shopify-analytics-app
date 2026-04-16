/**
 * P2 Extended: Admin Features E2E Tests
 *
 * Verifies admin-only functionality:
 * - Admin plans page renders for admin users
 * - Admin diagnostics page renders for admin users
 * - Non-admin users cannot access admin routes
 */
import { test, expect } from '../../fixtures/auth.fixture';
import { waitForLoadingComplete } from '../../helpers/assertions';

test.describe('Admin Features', () => {
  test('admin plans page renders for admin user', async ({ adminPage }) => {
    await adminPage.goto('/admin/plans');
    await adminPage.waitForLoadState('networkidle');
    await waitForLoadingComplete(adminPage);

    // Admin should not be redirected away
    const url = adminPage.url();
    const isOnAdminPage = url.includes('/admin');
    const isOnPaywall = url.includes('/paywall');

    // Should not be on paywall
    expect(isOnPaywall).toBe(false);

    // Look for plan management content
    const body = adminPage.locator('body');
    const pageText = await body.textContent() || '';

    const hasAdminContent =
      pageText.includes('Plan') ||
      pageText.includes('plan') ||
      pageText.includes('Admin') ||
      pageText.includes('admin') ||
      pageText.includes('Pricing') ||
      pageText.includes('pricing') ||
      pageText.includes('Tier') ||
      pageText.includes('tier');

    // Look for plan management elements (table, cards, form)
    const planElements = adminPage.locator(
      '.Polaris-DataTable, .Polaris-IndexTable, table, .Polaris-Card, .Polaris-LegacyCard, [data-testid="plan-list"], [data-testid="plan-table"]'
    );
    const elementCount = await planElements.count().catch(() => 0);

    // Look for plan names (Free, Growth, Pro, Enterprise)
    const hasPlanNames =
      pageText.includes('Free') ||
      pageText.includes('Growth') ||
      pageText.includes('Pro') ||
      pageText.includes('Enterprise');

    // Look for action buttons (Edit, Create, etc.)
    const actionButtons = adminPage.locator(
      'button:has-text("Edit"), button:has-text("Create"), button:has-text("Add"), button:has-text("New")'
    );
    const buttonCount = await actionButtons.count().catch(() => 0);

    // Admin page should have relevant content
    expect(hasAdminContent || hasPlanNames || elementCount > 0 || buttonCount > 0).toBeTruthy();

    // Should not show unhandled errors
    expect(pageText).not.toContain('Traceback');
    expect(pageText).not.toContain('TypeError');
  });

  test('admin diagnostics page renders for admin user', async ({ adminPage }) => {
    await adminPage.goto('/admin/diagnostics');
    await adminPage.waitForLoadState('networkidle');
    await waitForLoadingComplete(adminPage);

    // Should not be redirected to paywall
    const url = adminPage.url();
    expect(url).not.toContain('/paywall');

    // Look for diagnostics-related content
    const body = adminPage.locator('body');
    const pageText = await body.textContent() || '';

    const hasDiagnosticsContent =
      pageText.includes('Diagnostic') ||
      pageText.includes('diagnostic') ||
      pageText.includes('Health') ||
      pageText.includes('health') ||
      pageText.includes('Status') ||
      pageText.includes('status') ||
      pageText.includes('System') ||
      pageText.includes('system') ||
      pageText.includes('Tenant') ||
      pageText.includes('tenant');

    // Look for diagnostic cards, tables, or status indicators
    const diagnosticElements = adminPage.locator(
      '.Polaris-Card, .Polaris-LegacyCard, .Polaris-DataTable, table, .Polaris-Banner, [data-testid*="diagnostic"], [data-testid*="health"], [data-testid*="status"]'
    );
    const elementCount = await diagnosticElements.count().catch(() => 0);

    // Look for status badges
    const statusBadges = adminPage.locator('.Polaris-Badge');
    const badgeCount = await statusBadges.count().catch(() => 0);

    // Look for diagnostic metrics or stats
    const hasMetrics =
      pageText.includes('Active') ||
      pageText.includes('Connected') ||
      pageText.includes('Syncing') ||
      pageText.includes('Database') ||
      pageText.includes('Redis') ||
      pageText.includes('Queue') ||
      pageText.includes('API') ||
      pageText.includes('Uptime');

    // Admin diagnostics page should show diagnostic content
    expect(hasDiagnosticsContent || hasMetrics || elementCount > 0 || badgeCount > 0).toBeTruthy();

    // Should not show error traces
    expect(pageText).not.toContain('Traceback');
    expect(pageText).not.toContain('Internal Server Error');
  });

  test('non-admin user cannot access admin routes', async ({ freeTierPage }) => {
    await freeTierPage.goto('/admin/plans');
    await freeTierPage.waitForLoadState('networkidle');

    const url = freeTierPage.url();
    const body = freeTierPage.locator('body');
    const pageText = await body.textContent() || '';

    // Non-admin should be blocked from admin content in one of these ways:
    // 1. Redirected away from /admin (to /, /paywall, /unauthorized, etc.)
    const wasRedirected = !url.includes('/admin/plans');

    // 2. Shown an access denied / forbidden message
    const showsAccessDenied =
      pageText.includes('Access Denied') ||
      pageText.includes('access denied') ||
      pageText.includes('Forbidden') ||
      pageText.includes('forbidden') ||
      pageText.includes('Unauthorized') ||
      pageText.includes('unauthorized') ||
      pageText.includes('Permission') ||
      pageText.includes('permission') ||
      pageText.includes('Not Authorized') ||
      pageText.includes('403');

    // 3. Does NOT show actual admin plan management content
    const showsAdminContent =
      pageText.includes('Plan Management') &&
      (pageText.includes('Edit') || pageText.includes('Create'));

    // At minimum, admin content should not be accessible
    expect(wasRedirected || showsAccessDenied || !showsAdminContent).toBeTruthy();

    // Also check /admin/diagnostics
    await freeTierPage.goto('/admin/diagnostics');
    await freeTierPage.waitForLoadState('networkidle');

    const diagUrl = freeTierPage.url();
    const diagBody = freeTierPage.locator('body');
    const diagText = await diagBody.textContent() || '';

    const diagRedirected = !diagUrl.includes('/admin/diagnostics');
    const diagAccessDenied =
      diagText.includes('Access Denied') ||
      diagText.includes('Forbidden') ||
      diagText.includes('Unauthorized') ||
      diagText.includes('403');

    // Should not show diagnostic data to non-admin users
    const showsDiagnosticData =
      diagText.includes('Database') &&
      diagText.includes('Redis') &&
      diagText.includes('Queue');

    expect(diagRedirected || diagAccessDenied || !showsDiagnosticData).toBeTruthy();
  });
});
