/**
 * Contract tests for cohortAnalysisApi.
 *
 * Layer 4 — Verifies frontend calls correct URLs, methods, and uses createHeadersAsync.
 * If these fail, the frontend-backend contract is broken.
 */

import { beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('../services/apiUtils', () => ({
  API_BASE_URL: '',
  createHeadersAsync: vi.fn().mockResolvedValue({ Authorization: 'Bearer token' }),
  handleResponse: vi.fn(async (res: Response) => res.json()),
}));

import { getCohortRetention } from '../services/cohortAnalysisApi';

beforeEach(() => {
  vi.clearAllMocks();
  global.fetch = vi.fn().mockResolvedValue({
    ok: true,
    json: vi.fn().mockResolvedValue({
      cohorts: [],
      summary: { avg_retention_month_1: 0, best_cohort: '', worst_cohort: '', total_cohorts: 0 },
    }),
  });
});

describe('cohortAnalysisApi', () => {
  it('getCohortRetention defaults to 12m timeframe', async () => {
    await getCohortRetention();
    expect(global.fetch).toHaveBeenCalledWith(
      expect.stringContaining('/api/analytics/cohort-analysis?timeframe=12m'),
      expect.objectContaining({ method: 'GET' }),
    );
  });

  it('getCohortRetention passes custom timeframe', async () => {
    await getCohortRetention('3m');
    expect(global.fetch).toHaveBeenCalledWith(
      expect.stringContaining('/api/analytics/cohort-analysis?timeframe=3m'),
      expect.any(Object),
    );
  });

  it('uses createHeadersAsync for auth', async () => {
    const { createHeadersAsync } = await import('../services/apiUtils');
    await getCohortRetention();
    expect(createHeadersAsync).toHaveBeenCalled();
  });
});
