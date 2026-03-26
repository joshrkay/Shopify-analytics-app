/**
 * Phase 1.7 End-to-End Smoke Tests — layout shell is `Root`.
 */

import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { AppProvider } from '@shopify/polaris';
import { MemoryRouter, Routes, Route } from 'react-router-dom';

import { Root } from '../components/layout/Root';
import { DashboardHome } from '../pages/DashboardHome';

const mockUseUser = vi.fn();
const mockUseOrganization = vi.fn();
const mockSignOut = vi.fn();

vi.mock('@clerk/clerk-react', () => ({
  useUser: () => mockUseUser(),
  useOrganization: () => mockUseOrganization(),
  useClerk: () => ({ signOut: mockSignOut }),
}));

const mockUseEntitlements = vi.fn();
vi.mock('../hooks/useEntitlements', () => ({
  useEntitlements: () => mockUseEntitlements(),
}));

vi.mock('../services/entitlementsApi', async () => ({
  isFeatureEntitled: (entitlements: unknown, feature: string) => {
    const e = entitlements as { features?: Record<string, { is_entitled?: boolean }> };
    if (!e?.features) return false;
    return e.features[feature]?.is_entitled ?? false;
  },
}));

vi.mock('../services/changelogApi', () => ({
  getUnreadCountNumber: vi.fn().mockResolvedValue(0),
  getEntriesForFeature: vi.fn().mockResolvedValue([]),
  markAsRead: vi.fn(),
}));

vi.mock('../services/whatChangedApi', () => ({
  hasCriticalIssues: vi.fn().mockResolvedValue(false),
  getWhatChangedSummary: vi.fn().mockResolvedValue(null),
}));

const mockGetUnreadInsightsCount = vi.fn();
const mockListInsights = vi.fn();
vi.mock('../services/insightsApi', () => ({
  getUnreadInsightsCount: (...args: unknown[]) => mockGetUnreadInsightsCount(...args),
  listInsights: (...args: unknown[]) => mockListInsights(...args),
}));

const mockGetActiveRecommendationsCount = vi.fn();
const mockListRecommendations = vi.fn();
vi.mock('../services/recommendationsApi', () => ({
  getActiveRecommendationsCount: (...args: unknown[]) => mockGetActiveRecommendationsCount(...args),
  listRecommendations: (...args: unknown[]) => mockListRecommendations(...args),
}));

const mockGetCompactHealth = vi.fn();
vi.mock('../services/syncHealthApi', () => ({
  getCompactHealth: (...args: unknown[]) => mockGetCompactHealth(...args),
}));

const mockUseAgency = vi.fn();
vi.mock('../contexts/AgencyContext', () => ({
  useAgency: () => mockUseAgency(),
}));

vi.mock('../services/apiUtils', () => ({
  isApiError: vi.fn().mockReturnValue(false),
  API_BASE_URL: 'http://localhost:8000',
  createHeadersAsync: vi.fn().mockResolvedValue({}),
  handleResponse: vi.fn(),
}));

const mockTranslations = {
  Polaris: {
    Common: { ok: 'OK', cancel: 'Cancel' },
  },
};

function makeEntitlements(featureFlags: Record<string, boolean>) {
  const features: Record<string, Record<string, unknown>> = {};
  for (const [key, entitled] of Object.entries(featureFlags)) {
    features[key] = {
      feature: key,
      is_entitled: entitled,
      billing_state: 'active',
      plan_id: 'plan_1',
      plan_name: 'Pro',
      reason: null,
      required_plan: null,
      grace_period_ends_on: null,
    };
  }
  return {
    billing_state: 'active',
    plan_id: 'plan_1',
    plan_name: 'Pro',
    features,
    grace_period_days_remaining: null,
  };
}

const allEntitled = makeEntitlements({ custom_reports: true, ai_insights: true });

function setupDefaultMocks() {
  mockUseUser.mockReturnValue({
    user: {
      fullName: 'Jane Doe',
      firstName: 'Jane',
      primaryEmailAddress: { emailAddress: 'jane@example.com' },
      imageUrl: null,
    },
  });
  mockUseOrganization.mockReturnValue({ membership: { role: 'org:member' } });
  mockUseEntitlements.mockReturnValue({ entitlements: allEntitled, loading: false, error: null });
  mockUseAgency.mockReturnValue({
    getActiveStore: () => ({ store_name: 'Test Store' }),
    isAgencyUser: false,
    activeTenantId: 'tenant-1',
    loading: false,
    error: null,
    assignedStores: [],
    allowedTenants: [],
    userRoles: [],
    billingTier: 'pro',
    userId: 'user-1',
    accessExpiringAt: null,
    switchStore: vi.fn(),
    refreshStores: vi.fn(),
    canAccessStore: vi.fn().mockReturnValue(true),
  });
}

function setupDataMocks() {
  mockGetUnreadInsightsCount.mockResolvedValue(5);
  mockGetActiveRecommendationsCount.mockResolvedValue(3);
  mockGetCompactHealth.mockResolvedValue({
    overall_status: 'healthy',
    health_score: 92,
    stale_count: 0,
    critical_count: 0,
    has_blocking_issues: false,
    oldest_sync_minutes: null,
    last_checked_at: '2025-01-15T00:00:00Z',
  });
  mockListInsights.mockResolvedValue({
    insights: [{
      insight_id: 'ins-1',
      insight_type: 'spend_anomaly',
      severity: 'warning',
      summary: 'Spend increased 40%',
      why_it_matters: null,
      supporting_metrics: [],
      timeframe: 'last_7d',
      confidence_score: 0.85,
      platform: 'meta',
      campaign_id: null,
      currency: 'USD',
      generated_at: '2025-01-15T00:00:00Z',
      is_read: false,
      is_dismissed: false,
    }],
    total: 1,
    has_more: false,
  });
  mockListRecommendations.mockResolvedValue({
    recommendations: [{
      recommendation_id: 'rec-1',
      related_insight_id: 'ins-1',
      recommendation_type: 'decrease_budget',
      priority: 'high',
      recommendation_text: 'Consider reducing spend',
      rationale: null,
      estimated_impact: 'significant',
      risk_level: 'low',
      confidence_score: 0.8,
      affected_entity: null,
      affected_entity_type: null,
      currency: null,
      generated_at: '2025-01-15T00:00:00Z',
      is_accepted: false,
      is_dismissed: false,
    }],
    total: 1,
    has_more: false,
  });
}

function setupEmptyMocks() {
  mockGetUnreadInsightsCount.mockResolvedValue(0);
  mockGetActiveRecommendationsCount.mockResolvedValue(0);
  mockGetCompactHealth.mockResolvedValue({
    overall_status: 'healthy',
    health_score: 100,
    stale_count: 0,
    critical_count: 0,
    has_blocking_issues: false,
    oldest_sync_minutes: null,
    last_checked_at: '2025-01-15T00:00:00Z',
  });
  mockListInsights.mockResolvedValue({ insights: [], total: 0, has_more: false });
  mockListRecommendations.mockResolvedValue({ recommendations: [], total: 0, has_more: false });
}

function renderApp(
  ui: React.ReactElement,
  { initialEntries = ['/home'] }: { initialEntries?: string[] } = {},
) {
  return render(
    <AppProvider i18n={mockTranslations as Record<string, unknown>}>
      <MemoryRouter initialEntries={initialEntries}>
        {ui}
      </MemoryRouter>
    </AppProvider>,
  );
}

describe('Phase 1.7 — E2E Smoke Tests', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    setupDefaultMocks();
  });

  it('authenticated user with data sees full dashboard in Root shell', async () => {
    setupDataMocks();

    renderApp(
      <Routes>
        <Route element={<Root />}>
          <Route path="/home" element={<DashboardHome />} />
        </Route>
      </Routes>,
    );

    expect(screen.getAllByText('Markinsight').length).toBeGreaterThan(0);

    await waitFor(() => {
      expect(screen.getByText('Unread Insights')).toBeInTheDocument();
    });

    expect(screen.getByText('Active Recommendations')).toBeInTheDocument();
    expect(screen.getByText('Data Health')).toBeInTheDocument();
    expect(screen.getByText('92%')).toBeInTheDocument();
    expect(screen.getByText('Healthy')).toBeInTheDocument();
    expect(screen.getByText('Recent Insights')).toBeInTheDocument();
    expect(screen.getByText('Recommendations')).toBeInTheDocument();
  });

  it('authenticated user without data sees empty state', async () => {
    setupEmptyMocks();

    renderApp(
      <Routes>
        <Route path="/home" element={<DashboardHome />} />
      </Routes>,
    );

    await waitFor(() => {
      expect(screen.getByText('Welcome to your analytics dashboard')).toBeInTheDocument();
    });

    expect(screen.getByText('Connect data sources')).toBeInTheDocument();
  });

  it('sidebar navigation moves between stub routes', async () => {
    setupDataMocks();
    const user = userEvent.setup();

    renderApp(
      <Routes>
        <Route element={<Root />}>
          <Route path="/home" element={<div>Home Page</div>} />
          <Route path="/settings" element={<div>Settings Page</div>} />
        </Route>
      </Routes>,
      { initialEntries: ['/home'] },
    );

    expect(screen.getByText('Home Page')).toBeInTheDocument();

    await user.click(screen.getByRole('link', { name: /settings/i }));
    expect(screen.getByText('Settings Page')).toBeInTheDocument();
  });
});
