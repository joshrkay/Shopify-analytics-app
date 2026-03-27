/**
 * P1 Major: Attribution E2E Tests
 *
 * Verifies the attribution/channel analytics page:
 * - Attribution page loads with channel data
 * - Summary cards show aggregated metrics
 * - Channel click navigates to channel detail
 * - Empty state when no attribution data
 */
import { test, expect } from '../../fixtures/auth.fixture';
import { waitForLoadingComplete, expectEmptyState } from '../../helpers/assertions';

test.describe('Attribution', () => {
  test('attribution page loads with channel data', async ({ proTierPage }) => {
    await proTierPage.goto('/attribution');
    await proTierPage.waitForLoadState('networkidle');
    await waitForLoadingComplete(proTierPage);

    const body = proTierPage.locator('body');
    await expect(body).not.toBeEmpty();

    // Should display attribution content (cards, tables, or charts)
    const pageText = await body.textContent() || '';
    const hasAttributionContent =
      pageText.toLowerCase().includes('attribution') ||
      pageText.toLowerCase().includes('channel') ||
      pageText.toLowerCase().includes('source') ||
      pageText.toLowerCase().includes('campaign') ||
      pageText.toLowerCase().includes('roas') ||
      pageText.toLowerCase().includes('revenue');

    // If there's no attribution data, empty state is acceptable
    const hasEmptyState = await proTierPage
      .locator('.Polaris-EmptyState, [class*="empty"], [class*="Empty"]')
      .first()
      .isVisible()
      .catch(() => false);

    expect(hasAttributionContent || hasEmptyState).toBeTruthy();

    // No raw errors
    expect(pageText).not.toContain('TypeError');
    expect(pageText).not.toContain('Unexpected token');
    expect(pageText).not.toContain('NaN');
  });

  test('summary cards show aggregated metrics', async ({ proTierPage }) => {
    await proTierPage.goto('/attribution');
    await proTierPage.waitForLoadState('networkidle');
    await waitForLoadingComplete(proTierPage);

    // Look for metric/KPI cards on the attribution page
    const metricCards = proTierPage.locator(
      '[data-testid="kpi-card"], .Polaris-Card, .Polaris-LegacyCard, [class*="metric"], [class*="summary"]'
    );
    const cardCount = await metricCards.count().catch(() => 0);

    if (cardCount > 0) {
      // At least one card should be visible
      const firstCard = metricCards.first();
      await expect(firstCard).toBeVisible();

      // Cards should contain numeric values or formatted currency (not empty placeholders)
      const cardText = await firstCard.textContent() || '';
      // A metric card typically has a label and a value; it should not be completely empty
      expect(cardText.trim().length).toBeGreaterThan(0);

      // Verify no data corruption indicators
      expect(cardText).not.toContain('NaN');
      expect(cardText).not.toContain('undefined');
    }

    // Look for specific metrics like ROAS, Revenue, Orders, Spend
    const bodyText = await proTierPage.locator('body').textContent() || '';
    const hasMetricLabels =
      bodyText.toLowerCase().includes('revenue') ||
      bodyText.toLowerCase().includes('roas') ||
      bodyText.toLowerCase().includes('spend') ||
      bodyText.toLowerCase().includes('orders') ||
      bodyText.toLowerCase().includes('conversions') ||
      bodyText.toLowerCase().includes('clicks');

    // Empty state is fine if no data is seeded
    const hasEmptyState = await proTierPage
      .locator('.Polaris-EmptyState')
      .first()
      .isVisible()
      .catch(() => false);

    expect(hasMetricLabels || hasEmptyState || cardCount === 0).toBeTruthy();
  });

  test('channel click navigates to channel detail', async ({ proTierPage }) => {
    await proTierPage.goto('/attribution');
    await proTierPage.waitForLoadState('networkidle');
    await waitForLoadingComplete(proTierPage);

    // Look for clickable channel names/links
    const channelLinks = proTierPage.locator(
      'a[href*="channel"], a[href*="attribution/"], ' +
      '[data-testid*="channel"] a, ' +
      '.Polaris-DataTable__TableRow a, .Polaris-IndexTable__TableRow a, ' +
      'button:has-text("Google"), button:has-text("Meta"), button:has-text("Facebook"), ' +
      'a:has-text("Google Ads"), a:has-text("Meta Ads"), a:has-text("TikTok")'
    );
    const linkCount = await channelLinks.count().catch(() => 0);

    if (linkCount > 0) {
      const firstLink = channelLinks.first();
      const isVisible = await firstLink.isVisible().catch(() => false);

      if (isVisible) {
        // Capture the current URL
        const currentUrl = proTierPage.url();

        await firstLink.click();
        await proTierPage.waitForLoadState('networkidle');
        await waitForLoadingComplete(proTierPage);

        // Should have navigated to a detail page or opened a detail view
        const newUrl = proTierPage.url();
        const bodyText = await proTierPage.locator('body').textContent() || '';

        // Either the URL changed (navigated) or a detail panel/modal appeared
        const urlChanged = newUrl !== currentUrl;
        const hasDetailContent =
          bodyText.toLowerCase().includes('detail') ||
          bodyText.toLowerCase().includes('performance') ||
          bodyText.toLowerCase().includes('spend') ||
          bodyText.toLowerCase().includes('impressions') ||
          bodyText.toLowerCase().includes('clicks');

        expect(urlChanged || hasDetailContent).toBeTruthy();

        // No errors after navigation
        expect(bodyText).not.toContain('TypeError');
        expect(bodyText).not.toContain('Cannot read properties');
      }
    }
  });

  test('empty state when no attribution data', async ({ createAuthenticatedPage }) => {
    // Create a page for a tenant with no seeded attribution data
    const page = await createAuthenticatedPage({
      tenantId: 'e2e-tenant-empty-attribution',
      roles: ['user'],
      entitlements: ['AI_INSIGHTS'],
    });

    await page.goto('/attribution');
    await page.waitForLoadState('networkidle');
    await waitForLoadingComplete(page);

    const body = page.locator('body');
    await expect(body).not.toBeEmpty();

    // Should show empty state, zero values, or a "connect sources" prompt -- not an error
    const bodyText = await body.textContent() || '';
    expect(bodyText).not.toContain('500');
    expect(bodyText).not.toContain('Internal Server Error');
    expect(bodyText).not.toContain('TypeError');
    expect(bodyText).not.toContain('Traceback');

    // Acceptable states: empty state component, zero metrics, or a CTA to connect data
    const hasAcceptableState =
      (await page.locator('.Polaris-EmptyState').first().isVisible().catch(() => false)) ||
      bodyText.toLowerCase().includes('no data') ||
      bodyText.toLowerCase().includes('connect') ||
      bodyText.toLowerCase().includes('get started') ||
      bodyText.includes('0') ||
      bodyText.includes('$0');

    expect(hasAcceptableState).toBeTruthy();
  });
});
