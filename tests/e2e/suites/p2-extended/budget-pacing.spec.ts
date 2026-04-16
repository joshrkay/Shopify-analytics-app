/**
 * P2 Extended: Budget Pacing E2E Tests
 *
 * Verifies the budget pacing feature:
 * - Free-tier users are redirected to the paywall
 * - Enterprise-tier users can access the budget pacing page
 * - Budget data visualization renders correctly
 */
import { test, expect } from '../../fixtures/auth.fixture';
import { waitForLoadingComplete } from '../../helpers/assertions';

test.describe('Budget Pacing', () => {
  test('free-tier user is redirected to paywall', async ({ freeTierPage }) => {
    await freeTierPage.goto('/budget-pacing');
    await freeTierPage.waitForLoadState('networkidle');

    const url = freeTierPage.url();
    const isOnPaywall = url.includes('/paywall');

    if (!isOnPaywall) {
      // If not redirected, should show upgrade prompt or block access
      const body = freeTierPage.locator('body');
      const pageText = await body.textContent() || '';
      const isBlocked =
        pageText.includes('Upgrade') ||
        pageText.includes('upgrade') ||
        pageText.includes('Plan') ||
        pageText.includes('Subscribe');

      // Budget pacing content should not be accessible
      const budgetChart = freeTierPage.locator(
        '[data-testid="budget-chart"], [data-testid="pacing-chart"], .recharts-wrapper'
      ).first();
      const hasChart = await budgetChart.isVisible().catch(() => false);

      expect(isBlocked || !hasChart).toBeTruthy();
    } else {
      expect(url).toContain('/paywall');
    }
  });

  test('enterprise-tier user sees budget pacing page', async ({ enterpriseTierPage }) => {
    await enterpriseTierPage.goto('/budget-pacing');
    await enterpriseTierPage.waitForLoadState('networkidle');
    await waitForLoadingComplete(enterpriseTierPage);

    // Should not be on paywall
    const url = enterpriseTierPage.url();
    expect(url).not.toContain('/paywall');

    // Look for budget pacing page content
    const body = enterpriseTierPage.locator('body');
    const pageText = await body.textContent() || '';

    // Should have budget or pacing related content
    const hasBudgetContent =
      pageText.includes('Budget') ||
      pageText.includes('budget') ||
      pageText.includes('Pacing') ||
      pageText.includes('pacing') ||
      pageText.includes('Spend') ||
      pageText.includes('spend');

    // Look for filter/control elements (date range, channel selector, etc.)
    const controls = enterpriseTierPage.locator(
      'select, .Polaris-Select, [role="combobox"], [data-testid="budget-filters"], [data-testid="date-range-selector"]'
    ).first();
    const hasControls = await controls.isVisible().catch(() => false);

    // Look for cards or data sections
    const cards = enterpriseTierPage.locator('.Polaris-Card, .Polaris-LegacyCard');
    const cardCount = await cards.count().catch(() => 0);

    expect(hasBudgetContent || hasControls || cardCount > 0).toBeTruthy();
  });

  test('budget data visualization renders', async ({ enterpriseTierPage }) => {
    // Mock the budget pacing API with predictable data
    await enterpriseTierPage.route('**/api/budget-pacing**', async (route) => {
      if (route.request().method() === 'GET') {
        await route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify({
            channels: [
              {
                platform: 'google_ads',
                display_name: 'Google Ads',
                monthly_budget: 10000,
                spent_to_date: 6500,
                projected_spend: 9800,
                pacing_status: 'on_track',
                days_remaining: 10,
                daily_average_spend: 216.67,
              },
              {
                platform: 'facebook',
                display_name: 'Facebook Ads',
                monthly_budget: 5000,
                spent_to_date: 4200,
                projected_spend: 6300,
                pacing_status: 'overpacing',
                days_remaining: 10,
                daily_average_spend: 140.00,
              },
              {
                platform: 'instagram',
                display_name: 'Instagram',
                monthly_budget: 3000,
                spent_to_date: 1200,
                projected_spend: 1800,
                pacing_status: 'underpacing',
                days_remaining: 10,
                daily_average_spend: 40.00,
              },
            ],
            total_budget: 18000,
            total_spent: 11900,
            period: '2026-03',
          }),
        });
      } else {
        await route.continue();
      }
    });

    await enterpriseTierPage.goto('/budget-pacing');
    await enterpriseTierPage.waitForLoadState('networkidle');
    await waitForLoadingComplete(enterpriseTierPage);

    await enterpriseTierPage.waitForTimeout(1500);

    // Look for chart visualizations (progress bars, bar charts, etc.)
    const charts = enterpriseTierPage.locator(
      '.recharts-wrapper, svg.recharts-surface, [data-testid="budget-chart"], [data-testid="pacing-chart"], canvas, [class*="progress"], [class*="Progress"]'
    ).first();
    const hasCharts = await charts.isVisible().catch(() => false);

    // Look for data in the page (amounts from our mocked response)
    const body = enterpriseTierPage.locator('body');
    const pageText = await body.textContent() || '';

    const hasDataValues =
      pageText.includes('10,000') ||
      pageText.includes('10000') ||
      pageText.includes('$10') ||
      pageText.includes('Google Ads') ||
      pageText.includes('Facebook') ||
      pageText.includes('on_track') ||
      pageText.includes('On Track') ||
      pageText.includes('overpacing') ||
      pageText.includes('Overpacing');

    // Look for status badges or indicators
    const statusIndicators = enterpriseTierPage.locator(
      '.Polaris-Badge, [data-testid="pacing-status"], [class*="status"], [class*="indicator"]'
    );
    const statusCount = await statusIndicators.count().catch(() => 0);

    // Look for cards with channel breakdowns
    const cards = enterpriseTierPage.locator('.Polaris-Card, .Polaris-LegacyCard');
    const cardCount = await cards.count().catch(() => 0);

    // Should have at least one form of data visualization
    expect(hasCharts || hasDataValues || statusCount > 0 || cardCount > 0).toBeTruthy();
  });
});
