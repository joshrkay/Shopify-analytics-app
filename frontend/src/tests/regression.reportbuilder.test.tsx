/**
 * Report Builder paywall regression tests
 *
 * Regression: /builder previously showed "Page not found" when the user was
 * not entitled to the custom_reports feature, because the FeatureGateRoute
 * wrapper was missing. After the fix it redirects to /paywall instead.
 *
 * Tests:
 * 1. FeatureGateRoute redirects to /paywall when custom_reports not entitled
 * 2. FeatureGateRoute renders children when custom_reports IS entitled
 * 3. FeatureGateRoute renders children (fail-open) when entitlements fail to load
 * 4. isFeatureEntitled helper returns false for custom_reports when not present
 */

import React from 'react';
import { describe, it, expect, vi } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter, Routes, Route, Navigate, useLocation } from 'react-router-dom';

import { isFeatureEntitled } from '../services/entitlementsApi';
import type { EntitlementsResponse } from '../services/entitlementsApi';

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function makeEntitlements(customReportsEntitled: boolean): EntitlementsResponse {
  return {
    billing_state: 'active',
    plan_id: customReportsEntitled ? 'plan_pro' : 'plan_growth',
    plan_name: customReportsEntitled ? 'Pro' : 'Growth',
    features: {
      custom_reports: {
        feature: 'custom_reports',
        is_entitled: customReportsEntitled,
        billing_state: 'active',
        plan_id: customReportsEntitled ? 'plan_pro' : 'plan_growth',
        plan_name: customReportsEntitled ? 'Pro' : 'Growth',
        reason: customReportsEntitled ? null : 'Requires Pro plan',
        required_plan: customReportsEntitled ? null : 'plan_pro',
        grace_period_ends_on: null,
      },
    },
    grace_period_days_remaining: null,
  };
}

/**
 * Minimal FeatureGateRoute that mirrors the production behaviour in App.tsx.
 * We re-implement it here so we can test it in isolation without the full
 * App (Clerk, middleware, etc).
 */
function FeatureGateRoute({
  feature,
  entitlements,
  entitlementsLoading,
  entitlementsError,
  children,
}: {
  feature: string;
  entitlements: EntitlementsResponse | null;
  entitlementsLoading: boolean;
  entitlementsError: string | null;
  children: React.ReactNode;
}) {
  const location = useLocation();

  if (entitlementsLoading && entitlements === null) {
    return <div data-testid="loading-spinner">Loading…</div>;
  }

  if (entitlementsError && entitlements === null) {
    // Fail-open: show children with a warning banner
    return (
      <>
        <div data-testid="entitlements-error-banner">Could not verify feature access</div>
        {children}
      </>
    );
  }

  if (!isFeatureEntitled(entitlements, feature)) {
    if (location.pathname === '/paywall') return <div data-testid="paywall-page">Paywall</div>;
    return <Navigate to={`/paywall?feature=${feature}`} replace />;
  }

  return <>{children}</>;
}

// ---------------------------------------------------------------------------
// Test component helpers
// ---------------------------------------------------------------------------

const BuilderPage = () => <div data-testid="builder-page">Dashboard Builder</div>;
const PaywallPage = () => <div data-testid="paywall-page">Upgrade Required</div>;
const NotFoundPage = () => <div data-testid="not-found-page">Page not found</div>;

function TestApp({
  entitlements,
  entitlementsLoading = false,
  entitlementsError = null,
  initialPath = '/builder',
}: {
  entitlements: EntitlementsResponse | null;
  entitlementsLoading?: boolean;
  entitlementsError?: string | null;
  initialPath?: string;
}) {
  return (
    <MemoryRouter initialEntries={[initialPath]}>
      <Routes>
        <Route
          path="/builder"
          element={
            <FeatureGateRoute
              feature="custom_reports"
              entitlements={entitlements}
              entitlementsLoading={entitlementsLoading}
              entitlementsError={entitlementsError}
            >
              <BuilderPage />
            </FeatureGateRoute>
          }
        />
        <Route path="/paywall" element={<PaywallPage />} />
        {/* Catch-all — must NOT match for entitled users */}
        <Route path="*" element={<NotFoundPage />} />
      </Routes>
    </MemoryRouter>
  );
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe('Report Builder — paywall gating regression', () => {
  describe('when custom_reports is NOT entitled', () => {
    it('redirects to /paywall instead of showing "Page not found"', () => {
      const entitlements = makeEntitlements(false);
      render(<TestApp entitlements={entitlements} />);

      // Must show paywall — not the builder, not "not found"
      expect(screen.getByTestId('paywall-page')).toBeInTheDocument();
      expect(screen.queryByTestId('builder-page')).not.toBeInTheDocument();
      expect(screen.queryByTestId('not-found-page')).not.toBeInTheDocument();
    });

    it('does not render the builder content', () => {
      const entitlements = makeEntitlements(false);
      render(<TestApp entitlements={entitlements} />);

      expect(screen.queryByTestId('builder-page')).not.toBeInTheDocument();
    });

    it('redirects when entitlements is null (not yet loaded → locked by default)', () => {
      render(<TestApp entitlements={null} entitlementsLoading={false} />);

      expect(screen.getByTestId('paywall-page')).toBeInTheDocument();
      expect(screen.queryByTestId('builder-page')).not.toBeInTheDocument();
    });
  });

  describe('when custom_reports IS entitled', () => {
    it('renders the builder, not the paywall', () => {
      const entitlements = makeEntitlements(true);
      render(<TestApp entitlements={entitlements} />);

      expect(screen.getByTestId('builder-page')).toBeInTheDocument();
      expect(screen.queryByTestId('paywall-page')).not.toBeInTheDocument();
      expect(screen.queryByTestId('not-found-page')).not.toBeInTheDocument();
    });
  });

  describe('when entitlements are still loading', () => {
    it('shows a loading spinner, not NotFound', () => {
      render(
        <TestApp
          entitlements={null}
          entitlementsLoading={true}
          entitlementsError={null}
        />
      );

      expect(screen.getByTestId('loading-spinner')).toBeInTheDocument();
      expect(screen.queryByTestId('not-found-page')).not.toBeInTheDocument();
      expect(screen.queryByTestId('builder-page')).not.toBeInTheDocument();
    });
  });

  describe('when entitlements fail to load (network error)', () => {
    it('fails open — shows the builder with an error banner, not paywall or NotFound', () => {
      render(
        <TestApp
          entitlements={null}
          entitlementsLoading={false}
          entitlementsError="Network error"
        />
      );

      // Fail-open: builder is accessible but banner is shown
      expect(screen.getByTestId('entitlements-error-banner')).toBeInTheDocument();
      expect(screen.getByTestId('builder-page')).toBeInTheDocument();
      expect(screen.queryByTestId('not-found-page')).not.toBeInTheDocument();
    });
  });
});

// ---------------------------------------------------------------------------
// isFeatureEntitled unit tests for custom_reports specifically
// ---------------------------------------------------------------------------

describe('isFeatureEntitled — custom_reports', () => {
  it('returns false when custom_reports is not in features map', () => {
    const entitlements: EntitlementsResponse = {
      billing_state: 'active',
      plan_id: 'plan_growth',
      plan_name: 'Growth',
      features: {},
      grace_period_days_remaining: null,
    };
    expect(isFeatureEntitled(entitlements, 'custom_reports')).toBe(false);
  });

  it('returns false when custom_reports.is_entitled is false', () => {
    const entitlements = makeEntitlements(false);
    expect(isFeatureEntitled(entitlements, 'custom_reports')).toBe(false);
  });

  it('returns true when custom_reports.is_entitled is true', () => {
    const entitlements = makeEntitlements(true);
    expect(isFeatureEntitled(entitlements, 'custom_reports')).toBe(true);
  });

  it('returns false when entitlements is null', () => {
    expect(isFeatureEntitled(null, 'custom_reports')).toBe(false);
  });
});
