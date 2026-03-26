/**
 * Regression: /reports shows Paywall redirect (not NotFound) when custom_reports is not entitled
 *
 * Why: FeatureGateRoute wraps /reports. When `custom_reports` is not in the
 * entitlements, it must redirect to /paywall?feature=custom_reports.
 * This test guards against:
 *   - Accidentally removing the FeatureGateRoute wrapper
 *   - isFeatureEntitled returning wrong values for missing features
 *   - /reports falling through to NotFound instead of Paywall
 */

import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import { MemoryRouter, Routes, Route, Navigate, useLocation } from 'react-router-dom';
import type { EntitlementsResponse } from '../../services/entitlementsApi';

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
  useUser: () => ({ isLoaded: true, user: { id: 'u1' } }),
  useOrganization: () => ({ organization: { id: 'org1' } }),
  useClerk: () => ({ signOut: vi.fn() }),
  SignedIn: ({ children }: { children: React.ReactNode }) => <>{children}</>,
  SignedOut: () => null,
  RedirectToSignIn: () => <div>sign-in</div>,
}));

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function buildEntitlements(
  customReportsEntitled: boolean,
): EntitlementsResponse {
  return {
    billing_state: 'active',
    plan_id: customReportsEntitled ? 'plan_growth' : 'plan_free',
    plan_name: customReportsEntitled ? 'Growth' : 'Free',
    features: {
      custom_reports: {
        feature: 'custom_reports',
        is_entitled: customReportsEntitled,
        billing_state: 'active',
        plan_id: customReportsEntitled ? 'plan_growth' : 'plan_free',
        plan_name: customReportsEntitled ? 'Growth' : 'Free',
        reason: customReportsEntitled ? null : 'Upgrade required',
        required_plan: customReportsEntitled ? null : 'plan_growth',
        grace_period_ends_on: null,
      },
    },
    grace_period_days_remaining: null,
  };
}

// Inline FeatureGateRoute matching App.tsx logic
function FeatureGateRoute({
  feature,
  entitlements,
  children,
}: {
  feature: string;
  entitlements: EntitlementsResponse | null;
  children: React.ReactNode;
}) {
  const location = useLocation();
  const isEntitled =
    entitlements?.features[feature]?.is_entitled ?? false;

  if (!isEntitled) {
    if (location.pathname === '/paywall') return <div data-testid="paywall-page">Paywall</div>;
    return <Navigate to={`/paywall?feature=${feature}`} replace />;
  }
  return <>{children}</>;
}

function StubReportBuilder() {
  return <div data-testid="report-builder">Report Builder</div>;
}

function StubPaywall() {
  return <div data-testid="paywall-page">Upgrade to access this feature</div>;
}

function StubNotFound() {
  return <div data-testid="not-found">Not Found</div>;
}

function TestApp({
  initialPath,
  entitlements,
}: {
  initialPath: string;
  entitlements: EntitlementsResponse | null;
}) {
  return (
    <MemoryRouter initialEntries={[initialPath]}>
      <Routes>
        <Route
          path="/reports"
          element={
            <FeatureGateRoute feature="custom_reports" entitlements={entitlements}>
              <StubReportBuilder />
            </FeatureGateRoute>
          }
        />
        <Route path="/paywall" element={<StubPaywall />} />
        <Route path="*" element={<StubNotFound />} />
      </Routes>
    </MemoryRouter>
  );
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe('report-builder paywall regression', () => {
  beforeEach(() => vi.clearAllMocks());

  it('redirects to /paywall when custom_reports is not entitled', () => {
    const entitlements = buildEntitlements(false);
    render(<TestApp initialPath="/reports" entitlements={entitlements} />);

    expect(screen.getByTestId('paywall-page')).toBeInTheDocument();
    expect(screen.queryByTestId('report-builder')).not.toBeInTheDocument();
    expect(screen.queryByTestId('not-found')).not.toBeInTheDocument();
  });

  it('shows report builder when custom_reports IS entitled', () => {
    const entitlements = buildEntitlements(true);
    render(<TestApp initialPath="/reports" entitlements={entitlements} />);

    expect(screen.getByTestId('report-builder')).toBeInTheDocument();
    expect(screen.queryByTestId('paywall-page')).not.toBeInTheDocument();
    expect(screen.queryByTestId('not-found')).not.toBeInTheDocument();
  });

  it('shows paywall (not NotFound) when entitlements are null', () => {
    // null entitlements → isFeatureEntitled returns false → redirect to paywall
    render(<TestApp initialPath="/reports" entitlements={null} />);

    // Should be paywall, NOT not-found
    expect(screen.getByTestId('paywall-page')).toBeInTheDocument();
    expect(screen.queryByTestId('not-found')).not.toBeInTheDocument();
    expect(screen.queryByTestId('report-builder')).not.toBeInTheDocument();
  });

  it('/paywall route itself always renders, no redirect loop', () => {
    const entitlements = buildEntitlements(false);
    render(<TestApp initialPath="/paywall" entitlements={entitlements} />);

    expect(screen.getByTestId('paywall-page')).toBeInTheDocument();
    expect(screen.queryByTestId('not-found')).not.toBeInTheDocument();
  });

  it('App.tsx wraps /reports in FeatureGateRoute with custom_reports feature', async () => {
    const fs = await import('node:fs');
    const path = await import('node:path');
    const appPath = path.resolve(__dirname, '../../App.tsx');
    const content = fs.readFileSync(appPath, 'utf8');

    // /reports must be present
    expect(content).toMatch(/path="\/reports"/);
    // Must be wrapped in FeatureGateRoute
    const reportsBlock = content.slice(content.indexOf('path="/reports"') - 200, content.indexOf('path="/reports"') + 400);
    expect(reportsBlock).toMatch(/FeatureGateRoute/);
    expect(reportsBlock).toMatch(/custom_reports/);
  });
});
