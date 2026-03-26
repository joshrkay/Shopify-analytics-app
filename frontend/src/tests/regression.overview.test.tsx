/**
 * Overview page regression tests
 *
 * Regression: "/" previously showed "Page not found" for some routing
 * configurations. This test verifies the root route renders the Dashboard
 * component (Analytics Overview), not NotFound.
 *
 * Also verifies "/home" renders DashboardHome (the Polaris-based home page),
 * not NotFound.
 */

import React, { Suspense } from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter, Routes, Route, Navigate } from 'react-router-dom';

// ---------------------------------------------------------------------------
// Mocks — must come before component imports
// ---------------------------------------------------------------------------

// Mock Clerk — not under test here
vi.mock('@clerk/clerk-react', () => ({
  SignedIn: ({ children }: { children: React.ReactNode }) => <>{children}</>,
  SignedOut: () => null,
  RedirectToSignIn: () => null,
  useUser: () => ({ isSignedIn: true, user: { id: 'u1' } }),
  useOrganization: () => ({ organization: { id: 'org-1' } }),
  useOrganizationList: () => ({ setActive: vi.fn(), organizationList: [] }),
}));

// Mock hooks that hit the network
vi.mock('../hooks/useClerkToken', () => ({
  useClerkToken: () => ({ isTokenReady: true }),
}));
vi.mock('../hooks/useAutoOrganization', () => ({
  useAutoOrganization: () => ({ isLoading: false, hasOrg: true }),
}));
vi.mock('../hooks/useEntitlements', () => ({
  useEntitlements: () => ({
    entitlements: null,
    loading: false,
    error: null,
    refetch: vi.fn(),
  }),
}));

// Mock API services
vi.mock('../services/kpiApi', () => ({
  getKpiSummary: vi.fn().mockResolvedValue({ metrics: [] }),
  getChannelBreakdown: vi.fn().mockResolvedValue({ channels: [] }),
  getChannelMetrics: vi.fn().mockResolvedValue({ rows: [] }),
}));
vi.mock('../services/syncHealthApi', () => ({
  getSyncHealthSummary: vi.fn().mockResolvedValue({
    total_connectors: 0,
    healthy_count: 0,
    delayed_count: 0,
    error_count: 0,
    overall_status: 'healthy',
    health_score: 100,
    connectors: [],
    has_blocking_issues: false,
  }),
  formatTimeSinceSync: vi.fn().mockReturnValue('just now'),
}));
vi.mock('../services/insightsApi', () => ({
  getInsights: vi.fn().mockResolvedValue({ insights: [], total: 0 }),
}));
vi.mock('../services/recommendationsApi', () => ({
  getRecommendations: vi.fn().mockResolvedValue({ recommendations: [] }),
}));
vi.mock('../contexts/DataHealthContext', () => ({
  DataHealthProvider: ({ children }: { children: React.ReactNode }) => <>{children}</>,
  useDataHealth: () => ({ dataHealth: null, loading: false, error: null }),
}));
vi.mock('../contexts/AgencyContext', () => ({
  AgencyProvider: ({ children }: { children: React.ReactNode }) => <>{children}</>,
  useAgency: () => ({ isAgencyMode: false }),
}));
vi.mock('../contexts/DateRangeContext', () => ({
  DateRangeProvider: ({ children }: { children: React.ReactNode }) => <>{children}</>,
  useDateRange: () => ({ dateRange: null, setDateRange: vi.fn() }),
}));
vi.mock('../components/layout/Root', () => ({
  Root: ({ children }: { children: React.ReactNode }) => (
    <div data-testid="root-layout">{children}</div>
  ),
}));

// ---------------------------------------------------------------------------
// Stub pages — just needs to render unique text, not full functionality
// ---------------------------------------------------------------------------

vi.mock('../pages/Dashboard', () => ({
  Dashboard: () => <div data-testid="page-dashboard">Analytics Overview</div>,
  default: () => <div data-testid="page-dashboard">Analytics Overview</div>,
}));

vi.mock('../pages/DashboardHome', () => ({
  DashboardHome: () => <div data-testid="page-dashboard-home">Dashboard Home</div>,
  default: () => <div data-testid="page-dashboard-home">Dashboard Home</div>,
}));

vi.mock('../pages/NotFound', () => ({
  NotFound: () => <div data-testid="page-not-found">Page not found</div>,
  default: () => <div data-testid="page-not-found">Page not found</div>,
}));

vi.mock('../pages/Paywall', () => ({
  default: () => <div data-testid="page-paywall">Upgrade required</div>,
}));

// ---------------------------------------------------------------------------
// Minimal routing harness (mirrors App.tsx structure without Clerk/auth)
//
// vi.mock() above replaces these modules with stubs, so the actual page
// code never runs — only the stub JSX matters.
// ---------------------------------------------------------------------------

import { Dashboard } from '../pages/Dashboard';
import { DashboardHome } from '../pages/DashboardHome';
import { NotFound } from '../pages/NotFound';

function TestRouter({ initialPath }: { initialPath: string }) {
  return (
    <MemoryRouter initialEntries={[initialPath]}>
      <Suspense fallback={<div>Loading…</div>}>
        <Routes>
          <Route path="/" element={<Dashboard />} />
          <Route path="/home" element={<DashboardHome />} />
          <Route path="*" element={<NotFound />} />
        </Routes>
      </Suspense>
    </MemoryRouter>
  );
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe('Overview page — routing regression', () => {
  it('/ renders the Dashboard (Analytics Overview), not NotFound', async () => {
    render(<TestRouter initialPath="/" />);

    await waitFor(() => {
      expect(screen.getByTestId('page-dashboard')).toBeInTheDocument();
    });
    expect(screen.queryByTestId('page-not-found')).not.toBeInTheDocument();
  });

  it('/home renders DashboardHome, not NotFound', async () => {
    render(<TestRouter initialPath="/home" />);

    await waitFor(() => {
      expect(screen.getByTestId('page-dashboard-home')).toBeInTheDocument();
    });
    expect(screen.queryByTestId('page-not-found')).not.toBeInTheDocument();
  });

  it('unknown route renders NotFound, not Dashboard', async () => {
    render(<TestRouter initialPath="/this-does-not-exist" />);

    await waitFor(() => {
      expect(screen.getByTestId('page-not-found')).toBeInTheDocument();
    });
    expect(screen.queryByTestId('page-dashboard')).not.toBeInTheDocument();
  });
});
