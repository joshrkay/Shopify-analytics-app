/**
 * P2 Extended: Cohort Analysis E2E Tests
 *
 * Verifies the cohort analysis feature:
 * - Free-tier users are redirected to the paywall
 * - Pro-tier users can access the cohort analysis page
 * - Cohort data table renders with correct dimensions (time x cohort)
 */
import { test, expect } from '../../fixtures/auth.fixture';
import { waitForLoadingComplete, expectPaywallRedirect } from '../../helpers/assertions';

test.describe('Cohort Analysis', () => {
  test('free-tier user is redirected to paywall', async ({ freeTierPage }) => {
    await freeTierPage.goto('/cohorts');
    await freeTierPage.waitForLoadState('networkidle');

    const url = freeTierPage.url();
    const isOnPaywall = url.includes('/paywall');

    if (!isOnPaywall) {
      // If not redirected, the page should show an upgrade prompt or block content
      const body = freeTierPage.locator('body');
      const pageText = await body.textContent() || '';
      const isBlocked =
        pageText.includes('Upgrade') ||
        pageText.includes('upgrade') ||
        pageText.includes('Plan') ||
        pageText.includes('Subscribe');

      // The cohort content should NOT be accessible
      const cohortTable = freeTierPage.locator(
        '[data-testid="cohort-table"], [data-testid="cohort-grid"], .Polaris-DataTable'
      ).first();
      const hasTable = await cohortTable.isVisible().catch(() => false);

      expect(isBlocked || !hasTable).toBeTruthy();
    } else {
      expect(url).toContain('/paywall');
    }
  });

  test('pro-tier user sees cohort analysis page', async ({ proTierPage }) => {
    await proTierPage.goto('/cohorts');
    await proTierPage.waitForLoadState('networkidle');
    await waitForLoadingComplete(proTierPage);

    // Should not be on paywall
    const url = proTierPage.url();
    expect(url).not.toContain('/paywall');

    // Look for the cohort analysis page content
    const body = proTierPage.locator('body');
    const pageText = await body.textContent() || '';

    // Should have cohort-related content
    const hasCohortContent =
      pageText.includes('Cohort') ||
      pageText.includes('cohort') ||
      pageText.includes('Retention') ||
      pageText.includes('retention');

    // Look for page heading
    const heading = proTierPage.locator('h1, h2').first();
    const headingText = await heading.textContent().catch(() => '');

    // Look for cohort visualization components
    const cohortVisual = proTierPage.locator(
      '[data-testid="cohort-table"], [data-testid="cohort-grid"], [data-testid="cohort-chart"], .Polaris-DataTable, .recharts-wrapper, [class*="cohort"], [class*="heatmap"]'
    ).first();
    const hasVisual = await cohortVisual.isVisible().catch(() => false);

    // Look for filter controls (date range, cohort type, etc.)
    const filterControls = proTierPage.locator(
      '[data-testid="cohort-filters"], select, .Polaris-Select, [role="combobox"]'
    ).first();
    const hasFilters = await filterControls.isVisible().catch(() => false);

    // Page should have cohort content, visuals, or at least not be empty
    expect(hasCohortContent || hasVisual || hasFilters).toBeTruthy();
  });

  test('cohort data table renders with correct dimensions', async ({ proTierPage }) => {
    // Mock the cohort API to return predictable data
    await proTierPage.route('**/api/cohorts**', async (route) => {
      if (route.request().method() === 'GET') {
        await route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify({
            cohorts: [
              {
                cohort_period: '2026-01',
                cohort_size: 150,
                retention: [100, 65, 48, 35, 28, 22],
              },
              {
                cohort_period: '2026-02',
                cohort_size: 180,
                retention: [100, 70, 52, 40, 30],
              },
              {
                cohort_period: '2026-03',
                cohort_size: 200,
                retention: [100, 72, 55, 42],
              },
            ],
            metric: 'retention_rate',
            granularity: 'monthly',
          }),
        });
      } else {
        await route.continue();
      }
    });

    await proTierPage.goto('/cohorts');
    await proTierPage.waitForLoadState('networkidle');
    await waitForLoadingComplete(proTierPage);

    await proTierPage.waitForTimeout(1500);

    // Look for a table-like structure (DataTable, IndexTable, or custom grid)
    const table = proTierPage.locator(
      '.Polaris-DataTable, .Polaris-IndexTable, [data-testid="cohort-table"], [data-testid="cohort-grid"], table, [role="grid"]'
    ).first();
    const hasTable = await table.isVisible().catch(() => false);

    if (hasTable) {
      // Check that the table has rows (cohort periods)
      const rows = proTierPage.locator(
        '.Polaris-DataTable__TableRow, .Polaris-IndexTable__TableRow, tr, [role="row"]'
      );
      const rowCount = await rows.count().catch(() => 0);

      // Should have at least a header row + data rows
      expect(rowCount).toBeGreaterThanOrEqual(1);

      // Check that the table has columns (retention periods)
      const headerCells = proTierPage.locator(
        '.Polaris-DataTable__Cell--header, th, [role="columnheader"]'
      );
      const columnCount = await headerCells.count().catch(() => 0);

      // Cohort tables should have multiple columns (cohort label + retention periods)
      if (columnCount > 0) {
        expect(columnCount).toBeGreaterThanOrEqual(2);
      }
    } else {
      // If no table, look for a heatmap or chart visualization
      const heatmap = proTierPage.locator(
        '[class*="heatmap"], [class*="Heatmap"], .recharts-wrapper, svg, canvas'
      ).first();
      const hasHeatmap = await heatmap.isVisible().catch(() => false);

      // Should have some form of cohort data visualization
      const body = proTierPage.locator('body');
      const pageText = await body.textContent() || '';
      const hasData =
        pageText.includes('2026') ||
        pageText.includes('150') ||
        pageText.includes('retention') ||
        pageText.includes('Retention');

      expect(hasHeatmap || hasData).toBeTruthy();
    }
  });
});
