/**
 * Sync Status page regression tests
 *
 * Regression: SyncStatus previously white-screened when getSyncHealthSummary()
 * threw an error because there was no error boundary around the component.
 * After the fix, the page catches errors via its own try/catch in the load()
 * callback and renders a red error card with a Retry button — no white-screen.
 *
 * Tests:
 * 1. Page renders the title heading in the happy path
 * 2. Page shows error card (not white-screen) when the API throws
 * 3. Error card contains a Retry button
 * 4. Loading spinner appears before data arrives
 * 5. Connector list renders when data loads
 * 6. ErrorBoundary wrapping prevents white-screen on unexpected throws
 */

import React from 'react';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

import { ErrorBoundary } from '../components/ErrorBoundary';
import { SyncStatus } from '../pages/SyncStatus';

// ---------------------------------------------------------------------------
// Mock the sync health API
// ---------------------------------------------------------------------------

vi.mock('../services/syncHealthApi', () => ({
  getSyncHealthSummary: vi.fn(),
  formatTimeSinceSync: vi.fn().mockReturnValue('30 minutes ago'),
}));

import { getSyncHealthSummary } from '../services/syncHealthApi';
const mockGetSyncHealth = vi.mocked(getSyncHealthSummary);

// ---------------------------------------------------------------------------
// Fixtures
// ---------------------------------------------------------------------------

const healthySummary = {
  total_connectors: 2,
  healthy_count: 2,
  delayed_count: 0,
  error_count: 0,
  blocking_issues: 0,
  overall_status: 'healthy' as const,
  health_score: 100,
  connectors: [
    {
      connector_id: 'conn-1',
      connector_name: 'Shopify Orders',
      source_type: 'shopify',
      status: 'healthy' as const,
      freshness_status: 'fresh',
      severity: null,
      last_sync_at: new Date().toISOString(),
      last_rows_synced: 1500,
      minutes_since_sync: 30,
      message: 'Data is fresh',
      merchant_message: 'Data is up to date.',
      recommended_actions: [],
      is_blocking: false,
      has_open_incidents: false,
      open_incident_count: 0,
    },
  ],
  has_blocking_issues: false,
};

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe('SyncStatus page — error handling regression', () => {
  let consoleSpy: ReturnType<typeof vi.spyOn>;

  beforeEach(() => {
    // Suppress expected error logs in tests that intentionally trigger errors
    consoleSpy = vi.spyOn(console, 'error').mockImplementation(() => {});
  });

  afterEach(() => {
    consoleSpy.mockRestore();
    vi.clearAllMocks();
  });

  describe('happy path', () => {
    it('renders the Sync Status heading', async () => {
      mockGetSyncHealth.mockResolvedValue(healthySummary);
      render(<SyncStatus />);

      await waitFor(() => {
        expect(screen.getByText('Sync Status')).toBeInTheDocument();
      });
    });

    it('shows the Refresh button', async () => {
      mockGetSyncHealth.mockResolvedValue(healthySummary);
      render(<SyncStatus />);

      await waitFor(() => {
        expect(screen.getByRole('button', { name: /refresh/i })).toBeInTheDocument();
      });
    });

    it('renders connector list when data loads', async () => {
      mockGetSyncHealth.mockResolvedValue(healthySummary);
      render(<SyncStatus />);

      await waitFor(() => {
        expect(screen.getByText('Shopify Orders')).toBeInTheDocument();
      });
    });

    it('shows health score in summary card', async () => {
      mockGetSyncHealth.mockResolvedValue(healthySummary);
      render(<SyncStatus />);

      await waitFor(() => {
        expect(screen.getByText(/100%/)).toBeInTheDocument();
      });
    });
  });

  describe('error state — no white-screen', () => {
    it('shows error card when API throws, not a white-screen', async () => {
      mockGetSyncHealth.mockRejectedValue(new Error('Network error: connection refused'));
      render(<SyncStatus />);

      // Must show an error message, not crash
      await waitFor(() => {
        const errorMessages = screen.getAllByText(/failed to load sync status/i);
        expect(errorMessages.length).toBeGreaterThan(0);
      });
    });

    it('shows the error message text in the error card', async () => {
      mockGetSyncHealth.mockRejectedValue(new Error('API timeout'));
      render(<SyncStatus />);

      await waitFor(() => {
        expect(screen.getByText('API timeout')).toBeInTheDocument();
      });
    });

    it('shows a Retry button in the error card', async () => {
      mockGetSyncHealth.mockRejectedValue(new Error('503 Service Unavailable'));
      render(<SyncStatus />);

      await waitFor(() => {
        expect(screen.getByRole('button', { name: /retry/i })).toBeInTheDocument();
      });
    });

    it('clicking Retry re-fetches the data', async () => {
      const user = userEvent.setup();
      mockGetSyncHealth
        .mockRejectedValueOnce(new Error('First attempt failed'))
        .mockResolvedValueOnce(healthySummary);

      render(<SyncStatus />);

      // Wait for error state
      await waitFor(() => {
        expect(screen.getByRole('button', { name: /retry/i })).toBeInTheDocument();
      });

      await user.click(screen.getByRole('button', { name: /retry/i }));

      // After retry, health data should load
      await waitFor(() => {
        expect(screen.getByText('Shopify Orders')).toBeInTheDocument();
      });
      expect(mockGetSyncHealth).toHaveBeenCalledTimes(2);
    });

    it('does not crash when API returns non-Error rejection', async () => {
      mockGetSyncHealth.mockRejectedValue('string error message');
      render(<SyncStatus />);

      // Should show fallback message, not propagate the non-Error rejection
      await waitFor(() => {
        const errorMessages = screen.getAllByText(/failed to load sync status/i);
        expect(errorMessages.length).toBeGreaterThan(0);
      });
    });
  });

  describe('loading state', () => {
    it('shows loading spinner before data arrives', () => {
      // Never resolves — holds the loading state
      mockGetSyncHealth.mockReturnValue(new Promise(() => {}));
      render(<SyncStatus />);

      expect(screen.getByText(/loading sync status/i)).toBeInTheDocument();
    });
  });

  describe('error boundary — prevents white-screen on unexpected throws', () => {
    it('ErrorBoundary wrapping SyncStatus catches render errors', async () => {
      // Force getSyncHealthSummary to resolve but then have SyncStatus throw
      // during render by making the data have an unexpected shape
      mockGetSyncHealth.mockResolvedValue(null as any);

      render(
        <ErrorBoundary fallback={<div data-testid="boundary-fallback">Something went wrong</div>}>
          <SyncStatus />
        </ErrorBoundary>
      );

      // If SyncStatus throws during render, ErrorBoundary catches it —
      // the test should not throw and the boundary fallback should appear
      // OR if SyncStatus handles null gracefully, neither throws.
      // Either way: no unhandled error, no white-screen.
      await waitFor(() => {
        const fallback = screen.queryByTestId('boundary-fallback');
        const heading = screen.queryByText('Sync Status');
        // At least one of these must be rendered (component handled it gracefully
        // OR boundary caught the error)
        expect(fallback || heading).toBeTruthy();
      });
    });
  });

  describe('empty connectors state', () => {
    it('shows "No connectors configured" when connectors list is empty', async () => {
      mockGetSyncHealth.mockResolvedValue({
        ...healthySummary,
        total_connectors: 0,
        healthy_count: 0,
        connectors: [],
      });
      render(<SyncStatus />);

      await waitFor(() => {
        expect(screen.getByText(/no connectors configured/i)).toBeInTheDocument();
      });
    });
  });
});
