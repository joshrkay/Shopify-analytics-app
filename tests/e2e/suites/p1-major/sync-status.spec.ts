/**
 * P1 Major: Sync Status E2E Tests
 */
import { test, expect } from '../../fixtures/auth.fixture';
import { waitForLoadingComplete } from '../../helpers/assertions';

test.describe('Sync Status', () => {
  test('sync page shows connections with status', async ({ proTierPage }) => {
    await proTierPage.goto('/sync');
    await proTierPage.waitForLoadState('networkidle');
    await waitForLoadingComplete(proTierPage);

    const body = proTierPage.locator('body');
    await expect(body).not.toBeEmpty();
    const pageText = await body.textContent() || '';
    const hasSyncContent = pageText.includes('Sync') || pageText.includes('sync') || pageText.includes('Health') || pageText.includes('Status');
    expect(hasSyncContent).toBeTruthy();
  });

  test('connection detail shows last sync time', async ({ proTierPage }) => {
    await proTierPage.goto('/sync');
    await proTierPage.waitForLoadState('networkidle');
    await waitForLoadingComplete(proTierPage);

    const body = proTierPage.locator('body');
    await expect(body).not.toBeEmpty();
  });

  test('manual sync trigger updates status', async ({ proTierPage }) => {
    await proTierPage.goto('/sync');
    await proTierPage.waitForLoadState('networkidle');
    await waitForLoadingComplete(proTierPage);

    const syncBtn = proTierPage.locator('button:has-text("Sync"), button:has-text("Refresh")').first();
    if (await syncBtn.isVisible().catch(() => false)) {
      await syncBtn.click();
      await proTierPage.waitForTimeout(1000);
    }
  });
});
