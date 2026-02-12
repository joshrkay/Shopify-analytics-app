/**
 * Tests for useDataSources hooks
 *
 * Tests the QueryClientLite-based hooks for data source management:
 * mount fetching, derived state, polling, mutations, and cache invalidation.
 *
 * Phase 3 — Subphase 3.2: Data Sources Hooks
 */

import { renderHook, waitFor, act } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('../services/dataSourcesApi', () => ({
  getConnections: vi.fn(),
  getAvailableSources: vi.fn(),
  getConnection: vi.fn(),
  getSyncProgress: vi.fn(),
  initiateOAuth: vi.fn(),
  disconnectSource: vi.fn(),
  updateSyncConfig: vi.fn(),
  getGlobalSyncSettings: vi.fn(),
  updateGlobalSyncSettings: vi.fn(),
}));

import {
  useDataSources,
  useDataSourceCatalog,
  useConnection,
  useDisconnectSource,
  useSyncConfigMutation,
  useGlobalSyncSettings,
} from '../hooks/useDataSources';
import * as api from '../services/dataSourcesApi';

const mocked = vi.mocked(api);

const mockSource = {
  id: 'src-1',
  platform: 'shopify' as const,
  displayName: 'My Store',
  authType: 'oauth' as const,
  status: 'active' as const,
  isEnabled: true,
  lastSyncAt: '2025-06-15T10:30:00Z',
  lastSyncStatus: 'succeeded',
};

const mockCatalogItem = {
  id: 'shopify',
  platform: 'shopify' as const,
  displayName: 'Shopify',
  description: 'Connect your Shopify store',
  authType: 'oauth' as const,
  category: 'ecommerce' as const,
  isEnabled: true,
};

const mockConnection = {
  id: 'conn-1',
  platform: 'shopify' as const,
  displayName: 'My Store',
  authType: 'oauth' as const,
  status: 'active' as const,
  isEnabled: true,
  lastSyncAt: '2025-06-15T10:30:00Z',
  lastSyncStatus: 'succeeded',
  freshnessStatus: 'fresh',
  minutesSinceSync: 15,
  isStale: false,
  isHealthy: true,
  warningMessage: null,
  syncFrequencyMinutes: 60,
  expectedNextSyncAt: '2025-06-15T11:30:00Z',
};

const mockGlobalSettings = {
  defaultFrequency: 'daily' as const,
  pauseAllSyncs: false,
  maxConcurrentSyncs: 3,
};

beforeEach(() => {
  vi.clearAllMocks();
  mocked.getConnections.mockResolvedValue([mockSource]);
  mocked.getAvailableSources.mockResolvedValue([mockCatalogItem]);
  mocked.getConnection.mockResolvedValue(mockConnection);
  mocked.disconnectSource.mockResolvedValue(undefined);
  mocked.updateSyncConfig.mockResolvedValue(undefined);
  mocked.getGlobalSyncSettings.mockResolvedValue(mockGlobalSettings);
  mocked.updateGlobalSyncSettings.mockResolvedValue(mockGlobalSettings);
});

describe('useDataSources', () => {
  it('fetches connections on mount', async () => {
    const { result } = renderHook(() => useDataSources());
    await waitFor(() => expect(result.current.isLoading).toBe(false));
    expect(mocked.getConnections).toHaveBeenCalled();
    expect(result.current.connections).toEqual([mockSource]);
  });

  it('returns hasConnectedSources: true when connections exist', async () => {
    const { result } = renderHook(() => useDataSources());
    await waitFor(() => expect(result.current.isLoading).toBe(false));
    expect(result.current.hasConnectedSources).toBe(true);
  });

  it('returns hasConnectedSources: false when no connections', async () => {
    mocked.getConnections.mockResolvedValue([]);
    const { result } = renderHook(() => useDataSources());
    await waitFor(() => expect(result.current.isLoading).toBe(false));
    expect(result.current.hasConnectedSources).toBe(false);
  });
});

describe('useDataSourceCatalog', () => {
  it('fetches catalog on mount', async () => {
    const { result } = renderHook(() => useDataSourceCatalog());
    await waitFor(() => expect(result.current.isLoading).toBe(false));
    expect(mocked.getAvailableSources).toHaveBeenCalled();
    expect(result.current.catalog).toEqual([mockCatalogItem]);
  });
});

describe('useConnection', () => {
  it('fetches single connection by ID', async () => {
    const { result } = renderHook(() => useConnection('conn-1'));
    await waitFor(() => expect(result.current.isLoading).toBe(false));
    expect(mocked.getConnection).toHaveBeenCalledWith('conn-1');
    expect(result.current.connection).toEqual(mockConnection);
  });
});

describe('useDisconnectSource', () => {
  it('calls disconnect and mutation resolves', async () => {
    const { result } = renderHook(() => useDisconnectSource());
    await act(async () => {
      await result.current.mutateAsync('src-1');
    });
    expect(mocked.disconnectSource).toHaveBeenCalledWith('src-1');
  });
});

describe('useSyncConfigMutation', () => {
  it('calls updateSyncConfig with sourceId and config', async () => {
    const { result } = renderHook(() => useSyncConfigMutation());
    await act(async () => {
      await result.current.mutateAsync({ sourceId: 'src-1', config: { sync_frequency: 'daily' } });
    });
    expect(mocked.updateSyncConfig).toHaveBeenCalledWith('src-1', { sync_frequency: 'daily' });
  });
});

describe('useGlobalSyncSettings', () => {
  it('fetches settings and provides update mutation', async () => {
    const { result } = renderHook(() => useGlobalSyncSettings());
    await waitFor(() => expect(result.current.isLoading).toBe(false));
    expect(result.current.settings).toEqual(mockGlobalSettings);

    await act(async () => {
      await result.current.updateSettings({ pauseAllSyncs: true });
    });
    expect(mocked.updateGlobalSyncSettings).toHaveBeenCalledWith({ pauseAllSyncs: true });
  });
});
