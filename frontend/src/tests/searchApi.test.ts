/**
 * Contract tests for searchApi.
 *
 * Layer 4 — Verifies frontend calls correct URL and uses createHeadersAsync.
 * If these fail, the frontend-backend contract is broken.
 */

import { beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('../services/apiUtils', () => ({
  API_BASE_URL: '',
  createHeadersAsync: vi.fn().mockResolvedValue({ Authorization: 'Bearer token' }),
  handleResponse: vi.fn(async (res: Response) => res.json()),
}));

import { globalSearch } from '../services/searchApi';

beforeEach(() => {
  vi.clearAllMocks();
  global.fetch = vi.fn().mockResolvedValue({
    ok: true,
    json: vi.fn().mockResolvedValue({ results: [] }),
  });
});

describe('searchApi', () => {
  it('globalSearch calls GET /api/search?q=<query>', async () => {
    await globalSearch('dashboard');
    expect(global.fetch).toHaveBeenCalledWith(
      expect.stringContaining('/api/search?q=dashboard'),
      expect.objectContaining({ headers: expect.any(Object) }),
    );
  });

  it('uses createHeadersAsync for auth', async () => {
    const { createHeadersAsync } = await import('../services/apiUtils');
    await globalSearch('test');
    expect(createHeadersAsync).toHaveBeenCalled();
  });
});
