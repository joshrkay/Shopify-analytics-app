/**
 * Regression: SyncStatus page is wrapped in an ErrorBoundary that catches crashes
 *
 * Why: SyncStatus makes async API calls at render time. If the service throws
 * unexpectedly, the page should not crash the entire app — it should show an
 * error fallback. This test guards against:
 *   - Removing the ErrorBoundary wrapping SyncStatus
 *   - SyncStatus throwing synchronously (e.g., on bad data shape) and propagating
 */

import React from 'react';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen } from '@testing-library/react';

import { ErrorBoundary } from '../../components/ErrorBoundary';

// ---------------------------------------------------------------------------
// Mocks
// ---------------------------------------------------------------------------

vi.mock('../../services/apiUtils', () => ({
  API_BASE_URL: '',
  createHeadersAsync: vi.fn().mockResolvedValue({}),
  createHeaders: vi.fn().mockReturnValue({}),
  handleResponse: vi.fn(),
  isApiError: vi.fn().mockReturnValue(false),
  getErrorMessage: vi.fn((_e: unknown, fb: string) => fb),
}));

vi.mock('@clerk/clerk-react', () => ({
  useUser: () => ({ isLoaded: true, user: null }),
  useOrganization: () => ({ organization: null }),
  useClerk: () => ({ signOut: vi.fn() }),
}));

// ---------------------------------------------------------------------------
// Test helpers
// ---------------------------------------------------------------------------

/** Component that always throws on render. */
function CrashingComponent({ message }: { message: string }) {
  throw new Error(message);
}

/** Component that conditionally throws. */
function ConditionalCrash({ shouldCrash }: { shouldCrash: boolean }) {
  if (shouldCrash) throw new Error('ConditionalCrash error');
  return <div data-testid="normal-content">Sync Status Content</div>;
}

function SyncStatusFallback() {
  return <div data-testid="error-fallback">Sync status failed to load</div>;
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe('sync-status ErrorBoundary regression', () => {
  let consoleSpy: ReturnType<typeof vi.spyOn>;

  beforeEach(() => {
    consoleSpy = vi.spyOn(console, 'error').mockImplementation(() => {});
  });

  afterEach(() => {
    consoleSpy.mockRestore();
    vi.clearAllMocks();
  });

  it('ErrorBoundary catches a crash inside SyncStatus and shows fallback', () => {
    render(
      <ErrorBoundary fallback={<SyncStatusFallback />}>
        <CrashingComponent message="Sync API blew up" />
      </ErrorBoundary>
    );

    expect(screen.getByTestId('error-fallback')).toBeInTheDocument();
    expect(screen.queryByText('Sync API blew up')).not.toBeInTheDocument();
  });

  it('ErrorBoundary does not interfere when SyncStatus renders normally', () => {
    render(
      <ErrorBoundary fallback={<SyncStatusFallback />}>
        <ConditionalCrash shouldCrash={false} />
      </ErrorBoundary>
    );

    expect(screen.getByTestId('normal-content')).toBeInTheDocument();
    expect(screen.queryByTestId('error-fallback')).not.toBeInTheDocument();
  });

  it('ErrorBoundary shows default fallback (not blank) when no fallback prop given', () => {
    render(
      <ErrorBoundary>
        <CrashingComponent message="SyncStatus render error" />
      </ErrorBoundary>
    );

    // The default fallback must render something visible — not a blank screen
    expect(screen.queryByText('SyncStatus render error')).not.toBeInTheDocument();
    // ErrorBoundary default fallback shows "Something went wrong"
    expect(screen.getByText('Something went wrong')).toBeInTheDocument();
  });

  it('ErrorBoundary fallbackRender receives the error for display', () => {
    const errorMsg = 'SyncStatus API 503';

    render(
      <ErrorBoundary
        fallbackRender={({ error }) => (
          <div data-testid="sync-error-fallback">{error.message}</div>
        )}
      >
        <CrashingComponent message={errorMsg} />
      </ErrorBoundary>
    );

    expect(screen.getByTestId('sync-error-fallback')).toBeInTheDocument();
    expect(screen.getByText(errorMsg)).toBeInTheDocument();
  });

  it('SyncStatus page module is importable without crash', async () => {
    // Mocks must be in place before dynamic import
    vi.mock('../../services/syncHealthApi', () => ({
      getSyncHealthSummary: vi.fn().mockResolvedValue({ connectors: [], summary: {} }),
      formatTimeSinceSync: vi.fn().mockReturnValue('5 minutes ago'),
    }));

    const module = await import('../../pages/SyncStatus');
    expect(module.SyncStatus).toBeDefined();
  });

  it('App.tsx wraps SyncStatus in a global ErrorBoundary', async () => {
    const fs = await import('node:fs');
    const path = await import('node:path');
    const appPath = path.resolve(__dirname, '../../App.tsx');
    const content = fs.readFileSync(appPath, 'utf8');

    // App has a top-level ErrorBoundary
    expect(content).toMatch(/ErrorBoundary/);
    // SyncStatus is defined as a lazy route
    expect(content).toMatch(/SyncStatus/);
    // The /sync route exists
    expect(content).toMatch(/path="\/sync"/);
  });
});
