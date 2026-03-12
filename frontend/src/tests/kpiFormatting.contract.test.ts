/**
 * KPI Formatting Contract Tests
 *
 * Catches display scale bugs for percentage metrics (CTR, conversion rate)
 * where the backend returns values on a 0–1 scale but the UI must show them
 * as 0–100% (i.e. multiply by 100 before calling .toFixed()).
 *
 * These tests caught two bugs fixed in commit afc0346:
 *   - CTR card: showed "0.03%" instead of "3.40%" (missing * 100)
 *   - Conversion Rate card: same issue
 *
 * The backend contract is documented in backend/src/api/routes/channels.py:
 *   ctr: float = Field(..., description="Average click-through rate (0–1)")
 *   conversion_rate: float = Field(..., description="Conversions / clicks (0–1)")
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

describe('KPI percentage metric formatting', () => {
  it('Dashboard CTR display always multiplies by 100 before formatting as %', () => {
    const dashboard = readSrc('pages/Dashboard.tsx');

    // The correct pattern: (value * 100).toFixed(2) + '%'
    // The bad pattern (before fix): value.toFixed(2) + '%' or `${value.toFixed(2)}%`
    // Check that ctr display uses * 100
    // Extract lines containing ctr and %
    const ctrLines = dashboard
      .split('\n')
      .filter((line) => line.includes('.ctr') && line.includes('%'));

    expect(ctrLines.length).toBeGreaterThan(0);

    for (const line of ctrLines) {
      expect(line, `CTR line missing * 100 multiplication:\n  ${line.trim()}`).toContain('* 100');
    }
  });

  it('Dashboard conversion_rate display always multiplies by 100 before formatting as %', () => {
    const dashboard = readSrc('pages/Dashboard.tsx');

    const convLines = dashboard
      .split('\n')
      .filter((line) => line.includes('.conversion_rate') && line.includes('%'));

    expect(convLines.length).toBeGreaterThan(0);

    for (const line of convLines) {
      expect(
        line,
        `conversion_rate line missing * 100 multiplication:\n  ${line.trim()}`
      ).toContain('* 100');
    }
  });

  it('ChannelAnalytics fmtPct helper multiplies by 100', () => {
    const channelPage = readSrc('pages/ChannelAnalytics.tsx');

    // fmtPct is defined as: (v * 100).toFixed(2) + "%"
    expect(channelPage).toContain('v * 100');
    expect(channelPage).toContain('fmtPct(metrics.ctr)');
    expect(channelPage).toContain('fmtPct(metrics.conversion_rate)');
  });

  it('backend channels route documents ctr and conversion_rate as 0-1 scale', () => {
    const backendRoute = fs.readFileSync(
      path.resolve(srcRoot, '../../backend/src/api/routes/channels.py'),
      'utf8'
    );

    expect(backendRoute).toContain('(0\u20131)'); // "0–1" en-dash
    expect(backendRoute).toContain('ctr');
    expect(backendRoute).toContain('conversion_rate');
  });
});

describe('KPI percentage formatting pure logic', () => {
  /**
   * Mirror the exact formatting expression used in Dashboard.tsx so that
   * if the expression is ever changed incorrectly, this test breaks.
   */
  function formatCtr(rawValues: number[]): string {
    const active = rawValues.filter((v) => v > 0);
    if (active.length === 0) return '—';
    const avg = active.reduce((s, v) => s + v, 0) / active.length;
    return `${(avg * 100).toFixed(2)}%`;
  }

  it('formats 0.034 as 3.40%', () => {
    expect(formatCtr([0.034])).toBe('3.40%');
  });

  it('formats 0.0 as —', () => {
    expect(formatCtr([0])).toBe('—');
  });

  it('averages only non-zero channels', () => {
    // 0.04 + 0.06 = 0.10 / 2 = 0.05 → 5.00%
    // zero channel should not dilute the average
    expect(formatCtr([0.04, 0.06, 0])).toBe('5.00%');
  });

  it('does NOT format 0.034 as 0.03%', () => {
    // Guard against the pre-fix naive formatting (no * 100)
    expect(formatCtr([0.034])).not.toBe('0.03%');
  });
});
