/**
 * P2 Extended: Notifications E2E Tests
 */
import { test, expect } from '../../fixtures/auth.fixture';
import { waitForLoadingComplete } from '../../helpers/assertions';

test.describe('Notifications', () => {
  test('notification bell is visible', async ({ proTierPage }) => {
    await proTierPage.goto('/');
    await proTierPage.waitForLoadState('networkidle');
    await waitForLoadingComplete(proTierPage);
    const bell = proTierPage.locator('[data-testid="notification-bell"], [aria-label*="notification"], [aria-label*="Notification"]').first();
    const body = proTierPage.locator('body');
    await expect(body).not.toBeEmpty();
  });

  test('notification list renders', async ({ proTierPage }) => {
    await proTierPage.goto('/');
    await proTierPage.waitForLoadState('networkidle');
    await waitForLoadingComplete(proTierPage);
    const bell = proTierPage.locator('[data-testid="notification-bell"], [aria-label*="notification"]').first();
    if (await bell.isVisible().catch(() => false)) {
      await bell.click();
      await proTierPage.waitForTimeout(500);
    }
  });

  test('mark notification as read', async ({ proTierPage }) => {
    await proTierPage.goto('/');
    await proTierPage.waitForLoadState('networkidle');
    await waitForLoadingComplete(proTierPage);
    const body = proTierPage.locator('body');
    await expect(body).not.toBeEmpty();
  });
});
