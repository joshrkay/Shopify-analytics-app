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
  getWarehouseTypes,
  listWarehouseDestinations,
  createWarehouseDestination,
  deleteWarehouseDestination,
  testWarehouseConnection,
  triggerWarehouseSync,
} from '../services/warehouseExportApi';

beforeEach(() => {
  vi.clearAllMocks();
  global.fetch = vi.fn().mockResolvedValue({ ok: true, json: vi.fn().mockResolvedValue({}) });
});

describe('warehouseExportApi', () => {
  describe('getWarehouseTypes', () => {
    it('calls correct URL', async () => {
      await getWarehouseTypes();
      expect(global.fetch).toHaveBeenCalledWith(
        '/api/warehouse/types',
        expect.objectContaining({ headers: expect.objectContaining({ Authorization: 'Bearer token' }) }),
      );
    });
  });

  describe('listWarehouseDestinations', () => {
    it('calls correct URL', async () => {
      await listWarehouseDestinations();
      expect(global.fetch).toHaveBeenCalledWith(
        '/api/warehouse/destinations',
        expect.objectContaining({ headers: expect.objectContaining({ Authorization: 'Bearer token' }) }),
      );
    });
  });

  describe('createWarehouseDestination', () => {
    it('sends POST with correct payload', async () => {
      const request = {
        destination_type: 'bigquery',
        display_name: 'My BQ',
        configuration: { project_id: 'p', dataset_id: 'd', credentials_json: '{}' },
      };

      await createWarehouseDestination(request);

      expect(global.fetch).toHaveBeenCalledWith(
        '/api/warehouse/destinations',
        expect.objectContaining({
          method: 'POST',
          body: JSON.stringify(request),
        }),
      );
    });

    it('includes Content-Type header', async () => {
      await createWarehouseDestination({
        destination_type: 'snowflake',
        display_name: 'My Snowflake',
        configuration: { host: 'h' },
      });

      const callArgs = (global.fetch as ReturnType<typeof vi.fn>).mock.calls[0];
      expect(callArgs[1].headers['Content-Type']).toBe('application/json');
    });
  });

  describe('deleteWarehouseDestination', () => {
    it('sends DELETE to correct URL with ID', async () => {
      global.fetch = vi.fn().mockResolvedValue({ ok: true });

      await deleteWarehouseDestination('dest-123');

      expect(global.fetch).toHaveBeenCalledWith(
        '/api/warehouse/destinations/dest-123',
        expect.objectContaining({ method: 'DELETE' }),
      );
    });

    it('throws on non-ok response', async () => {
      global.fetch = vi.fn().mockResolvedValue({ ok: false, status: 404 });

      await expect(deleteWarehouseDestination('nonexistent')).rejects.toThrow();
    });
  });

  describe('testWarehouseConnection', () => {
    it('sends POST to correct URL', async () => {
      await testWarehouseConnection('dest-456');

      expect(global.fetch).toHaveBeenCalledWith(
        '/api/warehouse/destinations/dest-456/test',
        expect.objectContaining({ method: 'POST' }),
      );
    });
  });

  describe('triggerWarehouseSync', () => {
    it('sends POST to correct URL', async () => {
      await triggerWarehouseSync('dest-789');

      expect(global.fetch).toHaveBeenCalledWith(
        '/api/warehouse/destinations/dest-789/sync',
        expect.objectContaining({ method: 'POST' }),
      );
    });
  });
});
