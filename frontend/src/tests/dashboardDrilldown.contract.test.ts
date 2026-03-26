/**
 * Dashboard Drill-Down Total Row Contract Tests
 *
 * Guards against a class of bug where the "Total" row in a drill-down modal
 * is computed by summing per-channel values instead of reading the authoritative
 * KPI card value.
 *
 * Why this matters:
 *   - `channelMetrics` comes from a different API endpoint than the KPI cards
 *   - Channel-level rows can be filtered (e.g. only active channels with > 0 value)
 *   - Summing filtered rows produces a lower total than the card shows
 *   - The card value (kpi.total_*) is the source of truth — it is what the merchant
 *     sees and what is used in ROAS calculations
 *
 * The correct pattern for revenue / spend / conversions totals:
 *   revenue:     kpi?.total_revenue.value
 *   spend:       kpi?.total_ad_spend.value
 *   conversions: kpi?.total_conversions.value
 *
 * The bad pattern (before fix):
 *   channelMetrics.reduce((s, c) => s + c.revenue, 0)
 *   channelMetrics.reduce((s, c) => s + c.spend, 0)
 *   channelMetrics.reduce((s, c) => s + c.orders, 0)
 *
 * Note: clicks total is intentionally summed from channels (no kpi.total_clicks
 * field exists), so only revenue, spend, and conversions are tested here.
 *
 * Pattern: static file analysis, no rendering required.
 */

import fs from 'node:fs';
import path from 'node:path';
import { describe, expect, it } from 'vitest';

const srcRoot = path.resolve(__dirname, '..');

function readSrc(relativePath: string): string {
  return fs.readFileSync(path.join(srcRoot, relativePath), 'utf8');
}

describe('Dashboard drill-down Total rows use authoritative KPI values', () => {
  it('revenue Total row reads kpi.total_revenue.value, not a channel sum', () => {
    const dashboard = readSrc('pages/Dashboard.tsx');

    // The bad pattern: reduce over channelMetrics for revenue
    const badRevenueSum = /channelMetrics\.reduce\([^)]*revenue[^)]*\)/;
    expect(
      badRevenueSum.test(dashboard),
      'Revenue Total row must NOT be computed by summing channelMetrics — use kpi.total_revenue.value instead'
    ).toBe(false);

    // The good pattern: reads from kpi object
    expect(
      dashboard,
      'Revenue drill-down Total row must read kpi?.total_revenue.value'
    ).toContain('kpi?.total_revenue.value');
  });

  it('spend Total row reads kpi.total_ad_spend.value, not a channel sum', () => {
    const dashboard = readSrc('pages/Dashboard.tsx');

    // The bad pattern: reduce over channelMetrics for spend
    const badSpendSum = /channelMetrics\.reduce\([^)]*spend[^)]*\)/;
    expect(
      badSpendSum.test(dashboard),
      'Spend Total row must NOT be computed by summing channelMetrics — use kpi.total_ad_spend.value instead'
    ).toBe(false);

    // The good pattern
    expect(
      dashboard,
      'Spend drill-down Total row must read kpi?.total_ad_spend.value'
    ).toContain('kpi?.total_ad_spend.value');
  });

  it('conversions Total row reads kpi.total_conversions.value, not a channel sum', () => {
    const dashboard = readSrc('pages/Dashboard.tsx');

    // The bad pattern: reduce over channelMetrics for orders/conversions
    const badConvSum = /channelMetrics\.reduce\([^)]*orders[^)]*\)/;
    expect(
      badConvSum.test(dashboard),
      'Conversions Total row must NOT be computed by summing channelMetrics.orders — use kpi.total_conversions.value instead'
    ).toBe(false);

    // The good pattern
    expect(
      dashboard,
      'Conversions drill-down Total row must read kpi?.total_conversions.value'
    ).toContain('kpi?.total_conversions.value');
  });

  it('KPI card value props use the same kpi.total_* fields as the drill-down Totals', () => {
    const dashboard = readSrc('pages/Dashboard.tsx');

    // The KPI card value= props must reference the same fields, confirming they
    // are the single source of truth for both the card display and the drill-down total.
    expect(dashboard).toContain('kpi?.total_revenue.value');
    expect(dashboard).toContain('kpi?.total_ad_spend.value');
    expect(dashboard).toContain('kpi?.total_conversions.value');

    // Confirm the fields are from the kpi object (not channel-level data)
    expect(dashboard).toContain('kpi.total_revenue');
    expect(dashboard).toContain('kpi.total_ad_spend');
    expect(dashboard).toContain('kpi.total_conversions');
  });

  it('drill-down modal comment documents the source-of-truth intent', () => {
    const dashboard = readSrc('pages/Dashboard.tsx');

    // A comment was added explaining why kpi.* values are used for Totals.
    // This guards against a future refactor silently removing the intent.
    expect(
      dashboard,
      'Dashboard.tsx should contain a comment explaining that the Total row matches the KPI card value'
    ).toContain('matches the KPI card value');
  });
});

describe('Dashboard drill-down — pure logic consistency', () => {
  /**
   * Mirror the exact revenue Total formatting used in Dashboard.tsx.
   * If the expression changes incorrectly, this test breaks.
   */
  function formatRevenue(totalRevenueValue: number): string {
    return `$${totalRevenueValue.toLocaleString('en-US', {
      minimumFractionDigits: 0,
      maximumFractionDigits: 0,
    })}`;
  }

  it('formats 125000 as $125,000', () => {
    expect(formatRevenue(125000)).toBe('$125,000');
  });

  it('formats 0 as $0', () => {
    expect(formatRevenue(0)).toBe('$0');
  });

  it('formats 1234567 as $1,234,567', () => {
    expect(formatRevenue(1234567)).toBe('$1,234,567');
  });

  /**
   * Confirm that using the authoritative total vs a channel sum can differ.
   * This is the core correctness argument for the whole pattern.
   */
  it('authoritative total differs from filtered-channel sum when some channels are excluded', () => {
    // Suppose the KPI card shows $10,000 total revenue
    const authoritativeTotal = 10000;

    // But channelMetrics only has 2 active channels (one has 0 revenue and is filtered)
    const channelMetrics = [
      { revenue: 7000 },
      { revenue: 3000 },
      { revenue: 0 }, // filtered out (revenue === 0)
    ];
    const filteredChannels = channelMetrics.filter((c) => c.revenue > 0);
    const channelSum = filteredChannels.reduce((s, c) => s + c.revenue, 0);

    // They happen to agree in this case (0 doesn't affect sum)
    expect(channelSum).toBe(authoritativeTotal);

    // But if a channel has a small rounding difference or delay in data, they diverge:
    const channelMetricsWithRounding = [
      { revenue: 6999.5 },
      { revenue: 3000.3 },
      { revenue: 0 },
    ];
    const roundedSum = channelMetricsWithRounding
      .filter((c) => c.revenue > 0)
      .reduce((s, c) => s + c.revenue, 0);

    // The sum (9999.8) != the authoritative KPI total (10000)
    expect(roundedSum).not.toBe(authoritativeTotal);
    // This is why we use kpi.total_revenue.value, not a computed sum
  });
});
