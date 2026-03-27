/**
 * P2 Extended: Admin Features E2E Tests
 */
import { test, expect } from '../../fixtures/auth.fixture';
import { waitForLoadingComplete } from '../../helpers/assertions';

test.describe('Admin Features', () => {
  test('admin plans page renders', async ({ adminPage }) => {
    await adminPage.goto('/admin/plans');
    await adminPage.waitForLoadState('networkidle');
    await waitForLoadingComplete(adminPage);

    const body = adminPage.locator('body');
    await expect(body).not.toBeEmpty();
  });

  test('admin diagnostics page renders', async ({ adminPage }) => {
    await adminPage.goto('/admin/diagnostics');
    await adminPage.waitForLoadState('networkidle');
    await waitForLoadingComplete(adminPage);

    const body = adminPage.locator('body');
    await expect(body).not.toBeEmpty();
  });

  test('non-admin cannot access admin routes', async ({ freeTierPage }) => {
    await freeTierPage.goto('/admin/plans');
    await freeTierPage.waitForLoadState('networkidle');

    // Should be blocked or show access denied
    const body = freeTierPage.locator('body');
    await expect(body).not.toBeEmpty();
    const pageText = await body.textContent() || '';
    // Should not show admin content to non-admin users
    const url = freeTierPage.url();
    // Either redirected away or shows error/empty
    expect(url.includes('/admin/plans') && pageText.includes('Plan Management')).toBeFalsy();
  });
});
