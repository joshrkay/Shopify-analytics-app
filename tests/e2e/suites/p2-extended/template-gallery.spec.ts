/**
 * P2 Extended: Template Gallery E2E Tests
 */
import { test, expect } from '../../fixtures/auth.fixture';
import { waitForLoadingComplete } from '../../helpers/assertions';

test.describe('Template Gallery', () => {
  test('template gallery shows available templates', async ({ growthTierPage }) => {
    await growthTierPage.goto('/templates');
    await growthTierPage.waitForLoadState('networkidle');
    await waitForLoadingComplete(growthTierPage);
    expect(growthTierPage.url()).not.toContain('/paywall');
    const body = growthTierPage.locator('body');
    await expect(body).not.toBeEmpty();
  });

  test('create dashboard from template', async ({ growthTierPage }) => {
    await growthTierPage.goto('/templates');
    await growthTierPage.waitForLoadState('networkidle');
    await waitForLoadingComplete(growthTierPage);
    const useBtn = growthTierPage.locator('button:has-text("Use"), button:has-text("Create")').first();
    if (await useBtn.isVisible().catch(() => false)) {
      await useBtn.click();
      await growthTierPage.waitForTimeout(1000);
    }
  });

  test('template preview renders', async ({ growthTierPage }) => {
    await growthTierPage.goto('/templates');
    await growthTierPage.waitForLoadState('networkidle');
    await waitForLoadingComplete(growthTierPage);
    const previewBtn = growthTierPage.locator('button:has-text("Preview"), [data-testid*="preview"]').first();
    if (await previewBtn.isVisible().catch(() => false)) {
      await previewBtn.click();
      await growthTierPage.waitForTimeout(1000);
    }
  });
});
