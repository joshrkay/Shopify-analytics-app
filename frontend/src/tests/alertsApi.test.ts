/**
 * Contract tests for alertsApi.
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
  listAlertRules,
  createAlertRule,
  updateAlertRule,
  deleteAlertRule,
  toggleAlertRule,
  getAlertHistory,
  getRuleHistory,
} from '../services/alertsApi';

beforeEach(() => {
  vi.clearAllMocks();
  global.fetch = vi.fn().mockResolvedValue({
    ok: true,
    json: vi.fn().mockResolvedValue({}),
  });
});

describe('alertsApi', () => {
  it('listAlertRules calls GET /api/alerts/rules', async () => {
    await listAlertRules();
    expect(global.fetch).toHaveBeenCalledWith(
      '/api/alerts/rules',
      expect.objectContaining({ headers: expect.any(Object) }),
    );
  });

  it('createAlertRule calls POST /api/alerts/rules with JSON body', async () => {
    const data = {
      name: 'ROAS Alert',
      metric_name: 'roas',
      comparison_operator: 'lt',
      threshold_value: 2.0,
      evaluation_period: 'last_7_days',
    };
    await createAlertRule(data);
    expect(global.fetch).toHaveBeenCalledWith(
      '/api/alerts/rules',
      expect.objectContaining({
        method: 'POST',
        body: JSON.stringify(data),
        headers: expect.objectContaining({ 'Content-Type': 'application/json' }),
      }),
    );
  });

  it('updateAlertRule calls PUT /api/alerts/rules/{id}', async () => {
    await updateAlertRule('rule-1', { name: 'Updated' });
    expect(global.fetch).toHaveBeenCalledWith(
      '/api/alerts/rules/rule-1',
      expect.objectContaining({
        method: 'PUT',
        body: JSON.stringify({ name: 'Updated' }),
      }),
    );
  });

  it('deleteAlertRule calls DELETE /api/alerts/rules/{id}', async () => {
    await deleteAlertRule('rule-1');
    expect(global.fetch).toHaveBeenCalledWith(
      '/api/alerts/rules/rule-1',
      expect.objectContaining({ method: 'DELETE' }),
    );
  });

  it('deleteAlertRule throws on non-ok response', async () => {
    global.fetch = vi.fn().mockResolvedValue({ ok: false, status: 404 });
    await expect(deleteAlertRule('nonexistent')).rejects.toThrow('Failed to delete rule');
  });

  it('toggleAlertRule calls PATCH /api/alerts/rules/{id}/toggle', async () => {
    await toggleAlertRule('rule-1', true);
    expect(global.fetch).toHaveBeenCalledWith(
      '/api/alerts/rules/rule-1/toggle',
      expect.objectContaining({
        method: 'PATCH',
        body: JSON.stringify({ enabled: true }),
        headers: expect.objectContaining({ 'Content-Type': 'application/json' }),
      }),
    );
  });

  it('getAlertHistory calls GET /api/alerts/history with pagination', async () => {
    await getAlertHistory(10, 5);
    expect(global.fetch).toHaveBeenCalledWith(
      expect.stringContaining('/api/alerts/history?limit=10&offset=5'),
      expect.any(Object),
    );
  });

  it('getRuleHistory calls GET /api/alerts/rules/{id}/history', async () => {
    await getRuleHistory('rule-1', 20, 0);
    expect(global.fetch).toHaveBeenCalledWith(
      expect.stringContaining('/api/alerts/rules/rule-1/history?limit=20&offset=0'),
      expect.any(Object),
    );
  });
});
