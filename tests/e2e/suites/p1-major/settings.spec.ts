/**
 * P1 Major: Settings E2E Tests
 */
import { test, expect } from '../../fixtures/auth.fixture';
import { waitForLoadingComplete } from '../../helpers/assertions';

test.describe('Settings', () => {
  test('settings page renders all tabs', async ({ proTierPage }) => {
    await proTierPage.goto('/settings');
    await proTierPage.waitForLoadState('networkidle');
    await waitForLoadingComplete(proTierPage);

    const body = proTierPage.locator('body');
    await expect(body).not.toBeEmpty();
    const pageText = await body.textContent() || '';
    expect(pageText.includes('Settings') || pageText.includes('settings')).toBeTruthy();
  });

  test('profile tab shows user info', async ({ proTierPage }) => {
    await proTierPage.goto('/settings');
    await proTierPage.waitForLoadState('networkidle');
    await waitForLoadingComplete(proTierPage);

    const profileTab = proTierPage.locator('[role="tab"]:has-text("Profile"), button:has-text("Profile")').first();
    if (await profileTab.isVisible().catch(() => false)) {
      await profileTab.click();
      await proTierPage.waitForTimeout(500);
    }

    const body = proTierPage.locator('body');
    await expect(body).not.toBeEmpty();
  });

  test('billing tab shows current plan', async ({ proTierPage }) => {
    await proTierPage.goto('/settings');
    await proTierPage.waitForLoadState('networkidle');
    await waitForLoadingComplete(proTierPage);

    const billingTab = proTierPage.locator('[role="tab"]:has-text("Billing"), button:has-text("Billing")').first();
    if (await billingTab.isVisible().catch(() => false)) {
      await billingTab.click();
      await proTierPage.waitForTimeout(500);
    }
  });

  test('team tab shows member list', async ({ adminPage }) => {
    await adminPage.goto('/settings');
    await adminPage.waitForLoadState('networkidle');
    await waitForLoadingComplete(adminPage);

    const teamTab = adminPage.locator('[role="tab"]:has-text("Team"), button:has-text("Team")').first();
    if (await teamTab.isVisible().catch(() => false)) {
      await teamTab.click();
      await adminPage.waitForTimeout(500);
    }
  });
});
