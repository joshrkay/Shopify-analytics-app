import { describe, it, expect, vi, beforeEach } from 'vitest';

// Mock apiUtils before importing API modules
vi.mock('../services/apiUtils', () => ({
  API_BASE_URL: '',
  createHeadersAsync: vi.fn().mockResolvedValue({ 'Content-Type': 'application/json' }),
  handleResponse: vi.fn(async (res: Response) => res.json()),
  buildQueryString: vi.fn((filters: Record<string, unknown>) => {
    const params = new URLSearchParams();
    for (const [key, value] of Object.entries(filters)) {
      if (value !== undefined && value !== null) params.append(key, String(value));
    }
    const qs = params.toString();
    return qs ? `?${qs}` : '';
  }),
}));

import {
  listDashboards,
  getDashboard,
  createDashboard,
  updateDashboard,
  deleteDashboard,
  publishDashboard,
  duplicateDashboard,
} from '../services/customDashboardsApi';
import {
  createReport,
  updateReport,
  deleteReport,
  reorderReports,
} from '../services/customReportsApi';
import {
  createHeadersAsync,
  handleResponse,
  buildQueryString,
} from '../services/apiUtils';

beforeEach(() => {
  vi.resetAllMocks();

  // Re-mock apiUtils functions after reset
  (createHeadersAsync as ReturnType<typeof vi.fn>).mockResolvedValue({
    'Content-Type': 'application/json',
  });

  (handleResponse as ReturnType<typeof vi.fn>).mockImplementation(
    async (res: Response) => res.json(),
  );

  (buildQueryString as ReturnType<typeof vi.fn>).mockImplementation(
    (filters: Record<string, unknown>) => {
      const params = new URLSearchParams();
      for (const [key, value] of Object.entries(filters)) {
        if (value !== undefined && value !== null) params.append(key, String(value));
      }
      const qs = params.toString();
      return qs ? `?${qs}` : '';
    },
  );

  global.fetch = vi.fn().mockResolvedValue({
    ok: true,
    json: vi.fn().mockResolvedValue({}),
  });
});

// ---------------------------------------------------------------------------
// Dashboard API tests
// ---------------------------------------------------------------------------
describe('customDashboardsApi', () => {
  describe('listDashboards', () => {
    it('calls GET /api/v1/dashboards with no query params when filters are empty', async () => {
      await listDashboards({});

      expect(global.fetch).toHaveBeenCalledWith(
        '/api/v1/dashboards',
        expect.objectContaining({ method: 'GET' }),
      );
    });

    it('includes query params for status and limit', async () => {
      await listDashboards({ status: 'draft', limit: 10 });

      const fetchCall = (global.fetch as ReturnType<typeof vi.fn>).mock.calls[0];
      const url: string = fetchCall[0];
      expect(url).toContain('status=draft');
      expect(url).toContain('limit=10');
    });
  });

  describe('getDashboard', () => {
    it('calls GET /api/v1/dashboards/db-1', async () => {
      await getDashboard('db-1');

      expect(global.fetch).toHaveBeenCalledWith(
        '/api/v1/dashboards/db-1',
        expect.objectContaining({ method: 'GET' }),
      );
    });
  });

  describe('createDashboard', () => {
    it('calls POST /api/v1/dashboards with correct body', async () => {
      await createDashboard({ name: 'Test' });

      expect(global.fetch).toHaveBeenCalledWith(
        '/api/v1/dashboards',
        expect.objectContaining({
          method: 'POST',
          body: JSON.stringify({ name: 'Test' }),
        }),
      );
    });
  });

  describe('updateDashboard', () => {
    it('calls PUT /api/v1/dashboards/db-1 with correct body', async () => {
      await updateDashboard('db-1', { name: 'Updated' });

      expect(global.fetch).toHaveBeenCalledWith(
        '/api/v1/dashboards/db-1',
        expect.objectContaining({
          method: 'PUT',
          body: JSON.stringify({ name: 'Updated' }),
        }),
      );
    });
  });

  describe('deleteDashboard', () => {
    it('calls DELETE /api/v1/dashboards/db-1', async () => {
      await deleteDashboard('db-1');

      expect(global.fetch).toHaveBeenCalledWith(
        '/api/v1/dashboards/db-1',
        expect.objectContaining({ method: 'DELETE' }),
      );
    });
  });

  describe('publishDashboard', () => {
    it('calls POST /api/v1/dashboards/db-1/publish', async () => {
      await publishDashboard('db-1');

      expect(global.fetch).toHaveBeenCalledWith(
        '/api/v1/dashboards/db-1/publish',
        expect.objectContaining({ method: 'POST' }),
      );
    });
  });

  describe('duplicateDashboard', () => {
    it('calls POST /api/v1/dashboards/db-1/duplicate with new_name in body', async () => {
      await duplicateDashboard('db-1', 'Copy');

      expect(global.fetch).toHaveBeenCalledWith(
        '/api/v1/dashboards/db-1/duplicate',
        expect.objectContaining({
          method: 'POST',
          body: JSON.stringify({ new_name: 'Copy' }),
        }),
      );
    });
  });
});

// ---------------------------------------------------------------------------
// Report API tests
// ---------------------------------------------------------------------------
describe('customReportsApi', () => {
  describe('createReport', () => {
    it('calls POST /api/v1/dashboards/db-1/reports with body', async () => {
      const body = {
        name: 'Revenue over time',
        chart_type: 'line' as const,
        dataset_name: 'orders',
        config_json: {
          metrics: [{ column: 'total', aggregation: 'SUM' as const }],
          dimensions: ['order_date'],
          time_range: 'P30D',
          time_grain: 'P1D' as const,
          filters: [],
          display: { show_legend: true },
        },
        position_json: { x: 0, y: 0, w: 6, h: 4 },
      };

      await createReport('db-1', body);

      expect(global.fetch).toHaveBeenCalledWith(
        '/api/v1/dashboards/db-1/reports',
        expect.objectContaining({
          method: 'POST',
          body: JSON.stringify(body),
        }),
      );
    });
  });

  describe('updateReport', () => {
    it('calls PUT /api/v1/dashboards/db-1/reports/rpt-1 with updates', async () => {
      const updates = { name: 'Updated Report' };

      await updateReport('db-1', 'rpt-1', updates);

      expect(global.fetch).toHaveBeenCalledWith(
        '/api/v1/dashboards/db-1/reports/rpt-1',
        expect.objectContaining({
          method: 'PUT',
          body: JSON.stringify(updates),
        }),
      );
    });
  });

  describe('deleteReport', () => {
    it('calls DELETE /api/v1/dashboards/db-1/reports/rpt-1', async () => {
      await deleteReport('db-1', 'rpt-1');

      expect(global.fetch).toHaveBeenCalledWith(
        '/api/v1/dashboards/db-1/reports/rpt-1',
        expect.objectContaining({ method: 'DELETE' }),
      );
    });
  });

  describe('reorderReports', () => {
    it('calls PUT /api/v1/dashboards/db-1/reports/reorder with report_ids', async () => {
      await reorderReports('db-1', { report_ids: ['a', 'b'] });

      expect(global.fetch).toHaveBeenCalledWith(
        '/api/v1/dashboards/db-1/reports/reorder',
        expect.objectContaining({
          method: 'PUT',
          body: JSON.stringify({ report_ids: ['a', 'b'] }),
        }),
      );
    });
  });
});
