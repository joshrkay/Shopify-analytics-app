/**
 * Tests for DataHealthContext
 *
 * Covers:
 * - useDataHealth throws outside provider
 * - DataHealthProvider with disablePolling=true does NOT set up polling
 * - Initial state has loading=true
 * - After fetch, state updates with health data
 * - Computed values: hasStaleData, hasCriticalIssues, shouldShowBanner
 * - mostSevereIncident picks highest severity
 * - freshnessLabel formats correctly
 * - acknowledgeIncident removes incident from state
 * - Error state on fetch failure
 */

import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook, act, waitFor } from '@testing-library/react';
import { render, screen } from '@testing-library/react';

import {
  DataHealthProvider,
  useDataHealth,
  useFreshnessStatus,
  useActiveIncidents,
} from '../contexts/DataHealthContext';

// Mock dependencies
vi.mock('../services/syncHealthApi', () => ({
  getCompactHealth: vi.fn(),
  getActiveIncidents: vi.fn(),
  getMerchantDataHealth: vi.fn(),
  acknowledgeIncident: vi.fn(),
  formatTimeSinceSync: vi.fn(),
}));

vi.mock('../services/apiUtils', () => ({
  isBackendDown: vi.fn().mockReturnValue(false),
  isProvisioningError: vi.fn().mockReturnValue(false),
}));

vi.mock('../hooks/useProvisioningRetry', () => ({
  useProvisioningRetry: vi.fn().mockReturnValue({
    execute: vi.fn((fn: () => Promise<unknown>) => fn()),
    isProvisioning: false,
  }),
}));

import {
  getCompactHealth,
  getActiveIncidents as getActiveIncidentsApi,
  getMerchantDataHealth,
  acknowledgeIncident as acknowledgeIncidentApi,
  formatTimeSinceSync,
} from '../services/syncHealthApi';
import type {
  CompactHealth,
  ActiveIncidentBanner,
  MerchantDataHealthResponse,
} from '../services/syncHealthApi';
import { isBackendDown } from '../services/apiUtils';

const mockGetCompactHealth = getCompactHealth as ReturnType<typeof vi.fn>;
const mockGetActiveIncidents = getActiveIncidentsApi as ReturnType<typeof vi.fn>;
const mockGetMerchantDataHealth = getMerchantDataHealth as ReturnType<typeof vi.fn>;
const mockAcknowledgeIncident = acknowledgeIncidentApi as ReturnType<typeof vi.fn>;
const mockFormatTimeSinceSync = formatTimeSinceSync as ReturnType<typeof vi.fn>;
const mockIsBackendDown = isBackendDown as ReturnType<typeof vi.fn>;

// --- Helpers ---

const createMockHealth = (overrides?: Partial<CompactHealth>): CompactHealth => ({
  overall_status: 'healthy',
  health_score: 100,
  stale_count: 0,
  critical_count: 0,
  has_blocking_issues: false,
  oldest_sync_minutes: 5,
  last_checked_at: '2025-06-01T00:00:00Z',
  ...overrides,
});

const createMockIncident = (overrides?: Partial<ActiveIncidentBanner>): ActiveIncidentBanner => ({
  id: 'incident-1',
  severity: 'warning',
  title: 'Test Incident',
  message: 'Something happened',
  scope: 'connector',
  eta: null,
  status_page_url: null,
  started_at: '2025-06-01T00:00:00Z',
  ...overrides,
});

const createMockMerchantHealth = (
  overrides?: Partial<MerchantDataHealthResponse>,
): MerchantDataHealthResponse => ({
  health_state: 'healthy',
  last_updated: '2025-06-01T00:00:00Z',
  user_safe_message: 'All systems operational',
  ai_insights_enabled: true,
  dashboards_enabled: true,
  exports_enabled: true,
  ...overrides,
});

function wrapper({ children }: { children: React.ReactNode }) {
  return <DataHealthProvider disablePolling>{children}</DataHealthProvider>;
}

function setupDefaultMocks() {
  mockIsBackendDown.mockReturnValue(false);
  mockGetCompactHealth.mockResolvedValue(createMockHealth());
  mockGetActiveIncidents.mockResolvedValue({
    incidents: [],
    has_critical: false,
    has_blocking: false,
  });
  mockGetMerchantDataHealth.mockResolvedValue(createMockMerchantHealth());
  mockFormatTimeSinceSync.mockImplementation((minutes: number | null) => {
    if (minutes === null) return 'Never synced';
    if (minutes < 60) return `${minutes} minutes ago`;
    const hours = Math.floor(minutes / 60);
    if (hours < 24) return `${hours} hours ago`;
    return `${Math.floor(hours / 24)} days ago`;
  });
}

// --- Tests ---

describe('DataHealthContext', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    setupDefaultMocks();
  });

  // ---- useDataHealth outside provider ----
  describe('useDataHealth', () => {
    it('throws if used outside DataHealthProvider', () => {
      const spy = vi.spyOn(console, 'error').mockImplementation(() => {});
      expect(() => {
        renderHook(() => useDataHealth());
      }).toThrow('useDataHealth must be used within a DataHealthProvider');
      spy.mockRestore();
    });
  });

  // ---- DataHealthProvider renders children ----
  describe('DataHealthProvider', () => {
    it('renders children', async () => {
      render(
        <DataHealthProvider disablePolling>
          <div data-testid="child">Hello</div>
        </DataHealthProvider>,
      );
      expect(screen.getByTestId('child')).toHaveTextContent('Hello');
    });
  });

  // ---- disablePolling ----
  describe('disablePolling', () => {
    it('does NOT set up polling when disablePolling=true', async () => {
      const { result } = renderHook(() => useDataHealth(), { wrapper });

      await waitFor(() => {
        expect(result.current.loading).toBe(false);
      });

      // After the initial fetch completes, clear call counts
      const initialCallCount = mockGetCompactHealth.mock.calls.length;

      // Wait a bit to confirm no additional fetches happen
      await new Promise((r) => setTimeout(r, 100));

      // No additional calls should have been made beyond initial fetch
      expect(mockGetCompactHealth.mock.calls.length).toBe(initialCallCount);
    });
  });

  // ---- Initial state ----
  describe('initial state', () => {
    it('has loading=true before fetch completes', () => {
      // Never resolve to keep in loading state
      mockGetCompactHealth.mockReturnValue(new Promise(() => {}));

      const { result } = renderHook(() => useDataHealth(), { wrapper });

      expect(result.current.loading).toBe(true);
      expect(result.current.error).toBeNull();
      expect(result.current.health).toBeNull();
      expect(result.current.activeIncidents).toEqual([]);
    });
  });

  // ---- State updates after fetch ----
  describe('after fetch', () => {
    it('updates state with health data', async () => {
      const health = createMockHealth({ health_score: 95, oldest_sync_minutes: 10 });
      const incidents = [createMockIncident()];
      const merchantHealth = createMockMerchantHealth();

      mockGetCompactHealth.mockResolvedValue(health);
      mockGetActiveIncidents.mockResolvedValue({
        incidents,
        has_critical: false,
        has_blocking: false,
      });
      mockGetMerchantDataHealth.mockResolvedValue(merchantHealth);

      const { result } = renderHook(() => useDataHealth(), { wrapper });

      await waitFor(() => {
        expect(result.current.loading).toBe(false);
      });

      expect(result.current.health).toEqual(health);
      expect(result.current.activeIncidents).toHaveLength(1);
      expect(result.current.activeIncidents[0].id).toBe('incident-1');
      expect(result.current.error).toBeNull();
      expect(result.current.lastUpdated).not.toBeNull();
      expect(result.current.merchantHealth).toEqual(merchantHealth);
    });

    it('sets hasCritical and hasBlocking from incidents response', async () => {
      mockGetActiveIncidents.mockResolvedValue({
        incidents: [createMockIncident({ severity: 'critical' })],
        has_critical: true,
        has_blocking: true,
      });

      const { result } = renderHook(() => useDataHealth(), { wrapper });

      await waitFor(() => {
        expect(result.current.loading).toBe(false);
      });

      expect(result.current.hasCritical).toBe(true);
      expect(result.current.hasBlocking).toBe(true);
    });
  });

  // ---- Computed values ----
  describe('computed values', () => {
    it('hasStaleData is true when stale_count > 0', async () => {
      mockGetCompactHealth.mockResolvedValue(createMockHealth({ stale_count: 2 }));

      const { result } = renderHook(() => useDataHealth(), { wrapper });

      await waitFor(() => {
        expect(result.current.loading).toBe(false);
      });

      expect(result.current.hasStaleData).toBe(true);
    });

    it('hasStaleData is false when stale_count is 0', async () => {
      mockGetCompactHealth.mockResolvedValue(createMockHealth({ stale_count: 0 }));

      const { result } = renderHook(() => useDataHealth(), { wrapper });

      await waitFor(() => {
        expect(result.current.loading).toBe(false);
      });

      expect(result.current.hasStaleData).toBe(false);
    });

    it('hasCriticalIssues is true when critical_count > 0', async () => {
      mockGetCompactHealth.mockResolvedValue(createMockHealth({ critical_count: 1 }));
      mockGetActiveIncidents.mockResolvedValue({
        incidents: [],
        has_critical: false,
        has_blocking: false,
      });

      const { result } = renderHook(() => useDataHealth(), { wrapper });

      await waitFor(() => {
        expect(result.current.loading).toBe(false);
      });

      expect(result.current.hasCriticalIssues).toBe(true);
    });

    it('hasCriticalIssues is true when incidents has_critical is true', async () => {
      mockGetCompactHealth.mockResolvedValue(createMockHealth({ critical_count: 0 }));
      mockGetActiveIncidents.mockResolvedValue({
        incidents: [],
        has_critical: true,
        has_blocking: false,
      });

      const { result } = renderHook(() => useDataHealth(), { wrapper });

      await waitFor(() => {
        expect(result.current.loading).toBe(false);
      });

      expect(result.current.hasCriticalIssues).toBe(true);
    });

    it('hasCriticalIssues is false when both counts are 0', async () => {
      mockGetCompactHealth.mockResolvedValue(createMockHealth({ critical_count: 0 }));
      mockGetActiveIncidents.mockResolvedValue({
        incidents: [],
        has_critical: false,
        has_blocking: false,
      });

      const { result } = renderHook(() => useDataHealth(), { wrapper });

      await waitFor(() => {
        expect(result.current.loading).toBe(false);
      });

      expect(result.current.hasCriticalIssues).toBe(false);
    });

    it('shouldShowBanner is true when there are active incidents', async () => {
      mockGetActiveIncidents.mockResolvedValue({
        incidents: [createMockIncident()],
        has_critical: false,
        has_blocking: false,
      });

      const { result } = renderHook(() => useDataHealth(), { wrapper });

      await waitFor(() => {
        expect(result.current.loading).toBe(false);
      });

      expect(result.current.shouldShowBanner).toBe(true);
    });

    it('shouldShowBanner is false when there are no active incidents', async () => {
      mockGetActiveIncidents.mockResolvedValue({
        incidents: [],
        has_critical: false,
        has_blocking: false,
      });

      const { result } = renderHook(() => useDataHealth(), { wrapper });

      await waitFor(() => {
        expect(result.current.loading).toBe(false);
      });

      expect(result.current.shouldShowBanner).toBe(false);
    });

    it('hasBlockingIssues reflects health has_blocking_issues', async () => {
      mockGetCompactHealth.mockResolvedValue(createMockHealth({ has_blocking_issues: true }));

      const { result } = renderHook(() => useDataHealth(), { wrapper });

      await waitFor(() => {
        expect(result.current.loading).toBe(false);
      });

      expect(result.current.hasBlockingIssues).toBe(true);
    });
  });

  // ---- mostSevereIncident ----
  describe('mostSevereIncident', () => {
    it('picks highest severity incident (critical > high > warning)', async () => {
      const incidents = [
        createMockIncident({ id: 'inc-1', severity: 'warning', title: 'Warning' }),
        createMockIncident({ id: 'inc-2', severity: 'critical', title: 'Critical' }),
        createMockIncident({ id: 'inc-3', severity: 'high', title: 'High' }),
      ];
      mockGetActiveIncidents.mockResolvedValue({
        incidents,
        has_critical: true,
        has_blocking: false,
      });

      const { result } = renderHook(() => useDataHealth(), { wrapper });

      await waitFor(() => {
        expect(result.current.loading).toBe(false);
      });

      expect(result.current.mostSevereIncident).not.toBeNull();
      expect(result.current.mostSevereIncident!.id).toBe('inc-2');
      expect(result.current.mostSevereIncident!.severity).toBe('critical');
    });

    it('returns null when there are no incidents', async () => {
      mockGetActiveIncidents.mockResolvedValue({
        incidents: [],
        has_critical: false,
        has_blocking: false,
      });

      const { result } = renderHook(() => useDataHealth(), { wrapper });

      await waitFor(() => {
        expect(result.current.loading).toBe(false);
      });

      expect(result.current.mostSevereIncident).toBeNull();
    });

    it('returns the only incident when there is just one', async () => {
      const incident = createMockIncident({ id: 'inc-solo', severity: 'high' });
      mockGetActiveIncidents.mockResolvedValue({
        incidents: [incident],
        has_critical: false,
        has_blocking: false,
      });

      const { result } = renderHook(() => useDataHealth(), { wrapper });

      await waitFor(() => {
        expect(result.current.loading).toBe(false);
      });

      expect(result.current.mostSevereIncident!.id).toBe('inc-solo');
    });
  });

  // ---- freshnessLabel ----
  describe('freshnessLabel', () => {
    it('formats using formatTimeSinceSync for non-null oldest_sync_minutes', async () => {
      mockGetCompactHealth.mockResolvedValue(createMockHealth({ oldest_sync_minutes: 45 }));
      mockFormatTimeSinceSync.mockReturnValue('45 minutes ago');

      const { result } = renderHook(() => useDataHealth(), { wrapper });

      await waitFor(() => {
        expect(result.current.loading).toBe(false);
      });

      expect(result.current.freshnessLabel).toBe('45 minutes ago');
      expect(mockFormatTimeSinceSync).toHaveBeenCalledWith(45);
    });

    it('calls formatTimeSinceSync with null when oldest_sync_minutes is null', async () => {
      mockGetCompactHealth.mockResolvedValue(createMockHealth({ oldest_sync_minutes: null }));
      mockFormatTimeSinceSync.mockReturnValue('Never synced');

      const { result } = renderHook(() => useDataHealth(), { wrapper });

      await waitFor(() => {
        expect(result.current.loading).toBe(false);
      });

      expect(mockFormatTimeSinceSync).toHaveBeenCalledWith(null);
    });
  });

  // ---- acknowledgeIncident ----
  describe('acknowledgeIncident', () => {
    it('removes incident from state after acknowledging', async () => {
      const incidents = [
        createMockIncident({ id: 'inc-1', title: 'First' }),
        createMockIncident({ id: 'inc-2', title: 'Second' }),
      ];
      mockGetActiveIncidents.mockResolvedValue({
        incidents,
        has_critical: false,
        has_blocking: false,
      });
      mockAcknowledgeIncident.mockResolvedValue(undefined);

      const { result } = renderHook(() => useDataHealth(), { wrapper });

      await waitFor(() => {
        expect(result.current.loading).toBe(false);
      });

      expect(result.current.activeIncidents).toHaveLength(2);

      await act(async () => {
        await result.current.acknowledgeIncident('inc-1');
      });

      expect(result.current.activeIncidents).toHaveLength(1);
      expect(result.current.activeIncidents[0].id).toBe('inc-2');
      expect(mockAcknowledgeIncident).toHaveBeenCalledWith('inc-1');
    });

    it('throws and keeps incident if API call fails', async () => {
      const incidents = [createMockIncident({ id: 'inc-1' })];
      mockGetActiveIncidents.mockResolvedValue({
        incidents,
        has_critical: false,
        has_blocking: false,
      });
      mockAcknowledgeIncident.mockRejectedValue(new Error('API error'));

      const { result } = renderHook(() => useDataHealth(), { wrapper });

      await waitFor(() => {
        expect(result.current.loading).toBe(false);
      });

      const spy = vi.spyOn(console, 'error').mockImplementation(() => {});

      await expect(
        act(async () => {
          await result.current.acknowledgeIncident('inc-1');
        }),
      ).rejects.toThrow('API error');

      // Incident should still be in the list
      expect(result.current.activeIncidents).toHaveLength(1);

      spy.mockRestore();
    });
  });

  // ---- Error state ----
  describe('error state', () => {
    it('sets error when fetch fails', async () => {
      mockGetCompactHealth.mockRejectedValue(new Error('Network error'));

      const spy = vi.spyOn(console, 'error').mockImplementation(() => {});

      const { result } = renderHook(() => useDataHealth(), { wrapper });

      await waitFor(() => {
        expect(result.current.loading).toBe(false);
      });

      expect(result.current.error).toBe('Network error');
      expect(result.current.health).toBeNull();

      spy.mockRestore();
    });

    it('sets generic error for non-Error exceptions', async () => {
      mockGetCompactHealth.mockRejectedValue('string error');

      const spy = vi.spyOn(console, 'error').mockImplementation(() => {});

      const { result } = renderHook(() => useDataHealth(), { wrapper });

      await waitFor(() => {
        expect(result.current.loading).toBe(false);
      });

      expect(result.current.error).toBe('Failed to fetch health data');

      spy.mockRestore();
    });
  });

  // ---- Merchant health state ----
  describe('merchant health', () => {
    it('exposes merchantHealthState and merchantHealthMessage', async () => {
      mockGetMerchantDataHealth.mockResolvedValue(
        createMockMerchantHealth({
          health_state: 'delayed',
          user_safe_message: 'Some data is delayed',
        }),
      );

      const { result } = renderHook(() => useDataHealth(), { wrapper });

      await waitFor(() => {
        expect(result.current.loading).toBe(false);
      });

      expect(result.current.merchantHealthState).toBe('delayed');
      expect(result.current.merchantHealthMessage).toBe('Some data is delayed');
    });

    it('handles null merchantHealth gracefully', async () => {
      mockGetMerchantDataHealth.mockResolvedValue(null);

      const { result } = renderHook(() => useDataHealth(), { wrapper });

      await waitFor(() => {
        expect(result.current.loading).toBe(false);
      });

      expect(result.current.merchantHealthState).toBeNull();
      expect(result.current.merchantHealthMessage).toBeNull();
    });
  });

  // ---- useFreshnessStatus hook ----
  describe('useFreshnessStatus', () => {
    it('returns freshness status from context', async () => {
      mockGetCompactHealth.mockResolvedValue(
        createMockHealth({ overall_status: 'degraded', stale_count: 1, critical_count: 0 }),
      );
      mockFormatTimeSinceSync.mockReturnValue('2 hours ago');

      const { result } = renderHook(() => useFreshnessStatus(), { wrapper });

      await waitFor(() => {
        expect(result.current.loading).toBe(false);
      });

      expect(result.current.status).toBe('degraded');
      expect(result.current.hasStaleData).toBe(true);
      expect(result.current.hasCriticalIssues).toBe(false);
    });
  });

  // ---- useActiveIncidents hook ----
  describe('useActiveIncidents', () => {
    it('returns incidents and banner state from context', async () => {
      const incidents = [
        createMockIncident({ id: 'inc-1', severity: 'high' }),
      ];
      mockGetActiveIncidents.mockResolvedValue({
        incidents,
        has_critical: false,
        has_blocking: false,
      });

      const { result } = renderHook(() => useActiveIncidents(), { wrapper });

      await waitFor(() => {
        expect(result.current.incidents).toHaveLength(1);
      });

      expect(result.current.shouldShowBanner).toBe(true);
      expect(result.current.mostSevereIncident!.id).toBe('inc-1');
      expect(typeof result.current.acknowledgeIncident).toBe('function');
    });
  });

  // ---- isProvisioning exposed ----
  describe('isProvisioning', () => {
    it('exposes isProvisioning from useProvisioningRetry', async () => {
      const { result } = renderHook(() => useDataHealth(), { wrapper });

      await waitFor(() => {
        expect(result.current.loading).toBe(false);
      });

      expect(result.current.isProvisioning).toBe(false);
    });
  });
});
