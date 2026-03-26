/**
 * Phase 1.7 Integration Tests — layout shell is `Root` (sidebar + outlet).
 */

import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { AppProvider } from '@shopify/polaris';
import { MemoryRouter, Routes, Route } from 'react-router-dom';

import { Root } from '../components/layout/Root';
import { DashboardHome } from '../pages/DashboardHome';
import { ProfileMenu } from '../components/layout/ProfileMenu';

const mockNavigate = vi.fn();

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

vi.mock('../services/insightsApi', () => ({
  getUnreadInsightsCount: vi.fn().mockResolvedValue(3),
  listInsights: vi.fn().mockResolvedValue({
    insights: [{
      insight_id: 'ins-1',
      insight_type: 'spend_anomaly',
      severity: 'warning',
      summary: 'Spend increased 40% on Campaign Alpha',
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
  }),
}));

vi.mock('../services/recommendationsApi', () => ({
  getActiveRecommendationsCount: vi.fn().mockResolvedValue(2),
  listRecommendations: vi.fn().mockResolvedValue({
    recommendations: [{
      recommendation_id: 'rec-1',
      related_insight_id: 'ins-1',
      recommendation_type: 'decrease_budget',
      priority: 'high',
      recommendation_text: 'Consider reducing spend on Campaign Alpha',
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
  }),
}));

vi.mock('../services/syncHealthApi', () => ({
  getCompactHealth: vi.fn().mockResolvedValue({
    overall_status: 'healthy',
    health_score: 95,
    stale_count: 0,
    critical_count: 0,
    has_blocking_issues: false,
    oldest_sync_minutes: null,
    last_checked_at: '2025-01-15T00:00:00Z',
  }),
}));

vi.mock('../contexts/AgencyContext', () => ({
  useAgency: () => ({
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
  }),
}));

vi.mock('../services/sourcesApi', () => ({
  listSources: vi.fn().mockResolvedValue([]),
}));

vi.mock('../services/apiUtils', () => ({
  isApiError: vi.fn().mockReturnValue(false),
  API_BASE_URL: 'http://localhost:8000',
  createHeadersAsync: vi.fn().mockResolvedValue({}),
  handleResponse: vi.fn(),
}));

vi.mock('react-router-dom', async () => {
  const actual = await vi.importActual<typeof import('react-router-dom')>('react-router-dom');
  return {
    ...actual,
    useNavigate: () => mockNavigate,
  };
});

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

function renderWithProviders(
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

describe('Phase 1.7 — Integration Tests', () => {
  beforeEach(() => {
    vi.clearAllMocks();
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
  });

  it('/home renders dashboard home inside Root shell', async () => {
    renderWithProviders(
      <Routes>
        <Route element={<Root />}>
          <Route path="/home" element={<DashboardHome />} />
        </Route>
      </Routes>,
      { initialEntries: ['/home'] },
    );

    expect(screen.getAllByText('Markinsight').length).toBeGreaterThan(0);
    await waitFor(() => {
      expect(screen.getByText('Unread Insights')).toBeInTheDocument();
    });
  });

  it('Root sidebar Overview link points to /', () => {
    renderWithProviders(
      <Routes>
        <Route element={<Root />}>
          <Route path="/" element={<div>Overview Page</div>} />
        </Route>
      </Routes>,
      { initialEntries: ['/'] },
    );

    const overview = screen.getByRole('link', { name: /overview/i });
    expect(overview.getAttribute('href')).toBe('/');
  });

  it('ProfileMenu displays user info and workspace name', async () => {
    const user = userEvent.setup();

    renderWithProviders(<ProfileMenu />);

    expect(screen.getByText('Jane Doe')).toBeInTheDocument();

    const activator = screen.getByLabelText('Profile menu for Jane Doe');
    await user.click(activator);

    await waitFor(() => {
      expect(screen.getByText('jane@example.com')).toBeInTheDocument();
    });
    expect(screen.getByText('Test Store')).toBeInTheDocument();
    expect(screen.getByText('Settings')).toBeInTheDocument();
    expect(screen.getByText('Sign out')).toBeInTheDocument();
  });

  it('renders core dashboard home sections', async () => {
    renderWithProviders(
      <Routes>
        <Route path="/home" element={<DashboardHome />} />
      </Routes>,
      { initialEntries: ['/home'] },
    );

    await waitFor(() => {
      expect(screen.getByText('Unread Insights')).toBeInTheDocument();
    });

    expect(screen.getByText('Data Health')).toBeInTheDocument();
  });

  it('Analytics page module remains importable', async () => {
    const mod = await import('../pages/Analytics');
    expect(mod.default).toBeTypeOf('function');
  });
});

