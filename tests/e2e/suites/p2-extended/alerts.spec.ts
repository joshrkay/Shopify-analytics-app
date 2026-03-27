/**
 * P2 Extended: Alerts E2E Tests
 */
import { test, expect } from '../../fixtures/auth.fixture';
import { waitForLoadingComplete } from '../../helpers/assertions';

test.describe('Alerts', () => {
  test('alert rules list page loads', async ({ enterpriseTierPage }) => {
    await enterpriseTierPage.goto('/alerts');
    await enterpriseTierPage.waitForLoadState('networkidle');
    await waitForLoadingComplete(enterpriseTierPage);
    expect(enterpriseTierPage.url()).not.toContain('/paywall');
    const body = enterpriseTierPage.locator('body');
    await expect(body).not.toBeEmpty();
  });

  test('create new alert rule', async ({ enterpriseTierPage }) => {
    await enterpriseTierPage.goto('/alerts');
    await enterpriseTierPage.waitForLoadState('networkidle');
    await waitForLoadingComplete(enterpriseTierPage);
    const createBtn = enterpriseTierPage.locator('button:has-text("Create"), button:has-text("New")').first();
    if (await createBtn.isVisible().catch(() => false)) {
      await createBtn.click();
      await enterpriseTierPage.waitForTimeout(1000);
    }
  });

  test('toggle alert rule enabled/disabled', async ({ enterpriseTierPage }) => {
    await enterpriseTierPage.goto('/alerts');
    await enterpriseTierPage.waitForLoadState('networkidle');
    await waitForLoadingComplete(enterpriseTierPage);
    const toggle = enterpriseTierPage.locator('input[type="checkbox"], [role="switch"]').first();
    if (await toggle.isVisible().catch(() => false)) {
      await toggle.click();
      await enterpriseTierPage.waitForTimeout(500);
    }
  });

  test('delete alert rule', async ({ enterpriseTierPage }) => {
    await enterpriseTierPage.goto('/alerts');
    await enterpriseTierPage.waitForLoadState('networkidle');
    await waitForLoadingComplete(enterpriseTierPage);
    const deleteBtn = enterpriseTierPage.locator('button:has-text("Delete"), button[aria-label="Delete"]').first();
    if (await deleteBtn.isVisible().catch(() => false)) {
      await deleteBtn.click();
      await enterpriseTierPage.waitForTimeout(500);
    }
  });
});
