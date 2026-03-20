import { beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('../services/apiUtils', () => ({
  API_BASE_URL: '',
  createHeadersAsync: vi.fn().mockResolvedValue({ Authorization: 'Bearer token' }),
  handleResponse: vi.fn(async (res: Response) => {
    if (!res.ok) {
      const err = new Error('request failed') as Error & { status: number };
      err.status = res.status;
      throw err;
    }
    return res.json();
  }),
}));

import {
  getAvailableDatasets,
  exportData,
  exportToSheets,
} from '../services/dataExportApi';

beforeEach(() => {
  vi.clearAllMocks();
  global.fetch = vi.fn().mockResolvedValue({ ok: true, json: vi.fn().mockResolvedValue({}) });
});

describe('dataExportApi', () => {
  describe('getAvailableDatasets', () => {
    it('calls correct URL with /api prefix', async () => {
      const payload = { datasets: [{ id: 'orders', name: 'Orders', description: 'desc', columns: ['id'] }] };
      global.fetch = vi.fn().mockResolvedValue({ ok: true, json: vi.fn().mockResolvedValue(payload) });

      await getAvailableDatasets();

      expect(global.fetch).toHaveBeenCalledWith(
        '/api/exports/datasets',
        expect.objectContaining({ headers: expect.objectContaining({ Authorization: 'Bearer token' }) }),
      );
    });

    it('returns datasets from response', async () => {
      const payload = { datasets: [{ id: 'orders', name: 'Orders', description: 'desc', columns: ['id'] }] };
      global.fetch = vi.fn().mockResolvedValue({ ok: true, json: vi.fn().mockResolvedValue(payload) });

      const result = await getAvailableDatasets();
      expect(result.datasets).toHaveLength(1);
      expect(result.datasets[0].id).toBe('orders');
    });
  });

  describe('exportData', () => {
    it('sends POST to correct URL with payload', async () => {
      const mockResponse = { ok: true, json: vi.fn().mockResolvedValue({}) };
      global.fetch = vi.fn().mockResolvedValue(mockResponse);

      await exportData({ dataset: 'orders', format: 'csv' });

      expect(global.fetch).toHaveBeenCalledWith(
        '/api/exports/data',
        expect.objectContaining({
          method: 'POST',
          body: JSON.stringify({ dataset: 'orders', format: 'csv' }),
        }),
      );
    });

    it('includes Content-Type header', async () => {
      global.fetch = vi.fn().mockResolvedValue({ ok: true, json: vi.fn().mockResolvedValue({}) });

      await exportData({ dataset: 'orders', format: 'json' });

      const callArgs = (global.fetch as ReturnType<typeof vi.fn>).mock.calls[0];
      expect(callArgs[1].headers['Content-Type']).toBe('application/json');
    });

    it('sends date range and limit when provided', async () => {
      global.fetch = vi.fn().mockResolvedValue({ ok: true, json: vi.fn().mockResolvedValue({}) });

      await exportData({
        dataset: 'marketing_metrics',
        format: 'csv',
        date_from: '2025-01-01',
        date_to: '2025-12-31',
        limit: 500,
      });

      const callArgs = (global.fetch as ReturnType<typeof vi.fn>).mock.calls[0];
      const body = JSON.parse(callArgs[1].body);
      expect(body.dataset).toBe('marketing_metrics');
      expect(body.date_from).toBe('2025-01-01');
      expect(body.date_to).toBe('2025-12-31');
      expect(body.limit).toBe(500);
    });
  });

  describe('exportToSheets', () => {
    it('sends POST to correct URL', async () => {
      global.fetch = vi.fn().mockResolvedValue({ ok: true, json: vi.fn().mockResolvedValue({ success: false, error: 'coming soon' }) });

      await exportToSheets({ dataset: 'orders' });

      expect(global.fetch).toHaveBeenCalledWith(
        '/api/exports/sheets',
        expect.objectContaining({
          method: 'POST',
          body: JSON.stringify({ dataset: 'orders' }),
        }),
      );
    });

    it('sends spreadsheet_name when provided', async () => {
      global.fetch = vi.fn().mockResolvedValue({ ok: true, json: vi.fn().mockResolvedValue({ success: false, error: 'coming soon' }) });

      await exportToSheets({ dataset: 'orders', spreadsheet_name: 'My Export' });

      const callArgs = (global.fetch as ReturnType<typeof vi.fn>).mock.calls[0];
      const body = JSON.parse(callArgs[1].body);
      expect(body.spreadsheet_name).toBe('My Export');
    });
  });
});
