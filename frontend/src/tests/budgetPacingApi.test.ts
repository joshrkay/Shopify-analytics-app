/**
 * Contract tests for budgetPacingApi.
 *
 * Layer 4 — Verifies frontend calls correct URLs, methods, and request bodies.
 * If these fail, the frontend-backend contract is broken.
 */

import { beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('../services/apiUtils', () => ({
  API_BASE_URL: '',
  createHeadersAsync: vi.fn().mockResolvedValue({ Authorization: 'Bearer token' }),
  handleResponse: vi.fn(async (res: Response) => res.json()),
}));

import {
  listBudgets,
  createBudget,
  updateBudget,
  deleteBudget,
  getPacing,
} from '../services/budgetPacingApi';

beforeEach(() => {
  vi.clearAllMocks();
  global.fetch = vi.fn().mockResolvedValue({
    ok: true,
    json: vi.fn().mockResolvedValue({}),
  });
});

describe('budgetPacingApi', () => {
  it('listBudgets calls GET /api/budgets', async () => {
    await listBudgets();
    expect(global.fetch).toHaveBeenCalledWith(
      '/api/budgets',
      expect.objectContaining({ headers: expect.any(Object) }),
    );
  });

  it('createBudget calls POST /api/budgets with JSON body', async () => {
    const data = {
      source_platform: 'meta',
      budget_monthly_cents: 100000,
      start_date: '2026-03-01',
    };
    await createBudget(data);
    expect(global.fetch).toHaveBeenCalledWith(
      '/api/budgets',
      expect.objectContaining({
        method: 'POST',
        body: JSON.stringify(data),
        headers: expect.objectContaining({ 'Content-Type': 'application/json' }),
      }),
    );
  });

  it('updateBudget calls PUT /api/budgets/{id}', async () => {
    await updateBudget('budget-1', { budget_monthly_cents: 200000 });
    expect(global.fetch).toHaveBeenCalledWith(
      '/api/budgets/budget-1',
      expect.objectContaining({
        method: 'PUT',
        body: JSON.stringify({ budget_monthly_cents: 200000 }),
      }),
    );
  });

  it('deleteBudget calls DELETE /api/budgets/{id}', async () => {
    await deleteBudget('budget-1');
    expect(global.fetch).toHaveBeenCalledWith(
      '/api/budgets/budget-1',
      expect.objectContaining({ method: 'DELETE' }),
    );
  });

  it('deleteBudget throws on non-ok response', async () => {
    global.fetch = vi.fn().mockResolvedValue({ ok: false, status: 404 });
    await expect(deleteBudget('nonexistent')).rejects.toThrow('Failed to delete budget');
  });

  it('getPacing calls GET /api/budget-pacing', async () => {
    await getPacing();
    expect(global.fetch).toHaveBeenCalledWith(
      '/api/budget-pacing',
      expect.objectContaining({ headers: expect.any(Object) }),
    );
  });
});
