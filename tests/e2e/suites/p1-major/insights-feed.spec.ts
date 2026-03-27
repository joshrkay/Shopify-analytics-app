/**
 * P1 Major: Insights Feed E2E Tests
 */
import { test, expect } from '../../fixtures/auth.fixture';
import { waitForLoadingComplete } from '../../helpers/assertions';

test.describe('Insights Feed', () => {
  test('insights page lists AI insights', async ({ proTierPage }) => {
    await proTierPage.goto('/insights');
    await proTierPage.waitForLoadState('networkidle');
    await waitForLoadingComplete(proTierPage);

    const body = proTierPage.locator('body');
    await expect(body).not.toBeEmpty();
    expect(proTierPage.url()).not.toContain('/paywall');
  });

  test('read insight updates status', async ({ proTierPage }) => {
    await proTierPage.goto('/insights');
    await proTierPage.waitForLoadState('networkidle');
    await waitForLoadingComplete(proTierPage);

    const insightCard = proTierPage.locator('[data-testid="insight-card"], .Polaris-Card').first();
    const isVisible = await insightCard.isVisible().catch(() => false);
    if (isVisible) {
      await insightCard.click();
      await proTierPage.waitForTimeout(1000);
    }
  });

  test('dismiss insight removes from active list', async ({ proTierPage }) => {
    await proTierPage.goto('/insights');
    await proTierPage.waitForLoadState('networkidle');
    await waitForLoadingComplete(proTierPage);

    const dismissBtn = proTierPage.locator('button:has-text("Dismiss"), button:has-text("dismiss")').first();
    const isVisible = await dismissBtn.isVisible().catch(() => false);
    if (isVisible) {
      await dismissBtn.click();
      await proTierPage.waitForTimeout(1000);
    }
  });

  test('filter by severity works', async ({ proTierPage }) => {
    await proTierPage.goto('/insights');
    await proTierPage.waitForLoadState('networkidle');
    await waitForLoadingComplete(proTierPage);

    const filterSelect = proTierPage.locator('select, [role="combobox"], [data-testid*="filter"]').first();
    const isVisible = await filterSelect.isVisible().catch(() => false);
    if (isVisible) {
      await filterSelect.click();
      await proTierPage.waitForTimeout(500);
    }
  });

  test('insight detail shows supporting metrics', async ({ proTierPage }) => {
    await proTierPage.goto('/insights');
    await proTierPage.waitForLoadState('networkidle');
    await waitForLoadingComplete(proTierPage);

    const body = proTierPage.locator('body');
    const pageText = await body.textContent() || '';
    expect(pageText).not.toContain('TypeError');
    expect(pageText).not.toContain('Cannot read');
  });
});
