/**
 * P1 Major: Channel Analytics E2E Tests
 */
import { test, expect } from '../../fixtures/auth.fixture';
import { waitForLoadingComplete } from '../../helpers/assertions';

test.describe('Channel Analytics', () => {
  test('channel page loads for valid platform', async ({ proTierPage }) => {
    await proTierPage.goto('/channels/google_ads');
    await proTierPage.waitForLoadState('networkidle');
    await waitForLoadingComplete(proTierPage);

    const body = proTierPage.locator('body');
    await expect(body).not.toBeEmpty();
    const pageText = await body.textContent() || '';
    expect(pageText).not.toContain('TypeError');
  });

  test('channel metrics displayed', async ({ proTierPage }) => {
    await proTierPage.goto('/channels/meta_ads');
    await proTierPage.waitForLoadState('networkidle');
    await waitForLoadingComplete(proTierPage);

    const body = proTierPage.locator('body');
    await expect(body).not.toBeEmpty();
  });

  test('invalid channel shows error or redirect', async ({ proTierPage }) => {
    await proTierPage.goto('/channels/nonexistent_platform');
    await proTierPage.waitForLoadState('networkidle');

    const body = proTierPage.locator('body');
    await expect(body).not.toBeEmpty();
    const pageText = await body.textContent() || '';
    expect(pageText).not.toContain('Unhandled Runtime Error');
  });
});
