import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor, fireEvent } from '@testing-library/react';
import { AppProvider } from '@shopify/polaris';
import { MemoryRouter } from 'react-router-dom';

import Analytics from '../pages/Analytics';

vi.mock('../services/embedApi', () => ({
  checkEmbedReadiness: vi.fn(),
  getEmbedConfig: vi.fn(),
}));

vi.mock('../services/customDashboardsApi', () => ({
  listDashboards: vi.fn(),
}));

vi.mock('../components/ShopifyEmbeddedSuperset', () => ({
  default: () => <div>Embedded Dashboard</div>,
}));

vi.mock('../components/health/IncidentBanner', () => ({
  IncidentBanner: () => null,
}));

vi.mock('../components/changelog/FeatureUpdateBanner', () => ({
  FeatureUpdateBanner: () => null,
}));

vi.mock('../components/health/DataFreshnessBadge', () => ({
  DataFreshnessBadge: () => <span>Fresh</span>,
}));

vi.mock('../components/health/DashboardFreshnessIndicator', () => ({
  DashboardFreshnessIndicator: () => null,
}));

import { checkEmbedReadiness, getEmbedConfig } from '../services/embedApi';
import { listDashboards } from '../services/customDashboardsApi';

const mockTranslations = {
  Polaris: {
    Common: { ok: 'OK', cancel: 'Cancel' },
  },
};

function renderPage() {
  return render(
    <AppProvider i18n={mockTranslations as any}>
      <MemoryRouter>
        <Analytics />
      </MemoryRouter>
    </AppProvider>
  );
}

describe('Analytics page bootstrap', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    (checkEmbedReadiness as any).mockResolvedValue({
      status: 'ready',
      embed_configured: true,
      superset_url_configured: true,
      allowed_dashboards_configured: true,
    });
    (listDashboards as any).mockResolvedValue({ dashboards: [], has_more: false });
    (getEmbedConfig as any).mockResolvedValue({
      superset_url: 'https://analytics.example.com',
      allowed_dashboards: ['overview'],
      session_refresh_interval_ms: 300000,
      csp_frame_ancestors: ['self'],
    });
  });


  it('renders full analytics layout with system and custom dashboards', async () => {
    (getEmbedConfig as any).mockResolvedValue({
      superset_url: 'https://analytics.example.com',
      allowed_dashboards: ['overview', 'sales'],
      session_refresh_interval_ms: 300000,
      csp_frame_ancestors: ['self'],
    });
    (listDashboards as any).mockResolvedValue({
      dashboards: [{ id: 'db_1', name: 'QBR Report', status: 'published' }],
      has_more: true,
    });

    renderPage();

    await waitFor(() => {
      expect(screen.getByText('Analytics')).toBeInTheDocument();
      expect(screen.getByText('Select Dashboard')).toBeInTheDocument();
      expect(screen.getByText('Embedded Dashboard')).toBeInTheDocument();
      expect(screen.getByText('Create Custom Dashboard')).toBeInTheDocument();
    });

    expect(screen.queryByText('No Dashboards Available')).not.toBeInTheDocument();
  });

  it('shows permission-specific message for 403 config response', async () => {
    const error = new Error('forbidden') as Error & { status: number; detail: string };
    error.status = 403;
    error.detail = 'forbidden';
    (getEmbedConfig as any).mockRejectedValue(error);

    renderPage();

    await waitFor(() => {
      expect(
        screen.getByText('Your account does not have access to Analytics.')
      ).toBeInTheDocument();
    });
  });

  it('shows session-expired message for 401 config response', async () => {
    const error = new Error('unauthorized') as Error & { status: number; detail: string };
    error.status = 401;
    error.detail = 'unauthorized';
    (getEmbedConfig as any).mockRejectedValue(error);

    renderPage();

    await waitFor(() => {
      expect(
        screen.getByText('Your session has expired. Please sign in again.')
      ).toBeInTheDocument();
    });
  });


  it('shows informational banner when no embedded dashboards are available', async () => {
    (listDashboards as any).mockResolvedValue({ dashboards: [], has_more: false });
    (getEmbedConfig as any).mockResolvedValue({
      superset_url: 'https://analytics.example.com',
      allowed_dashboards: [],
      session_refresh_interval_ms: 300000,
      csp_frame_ancestors: ['self'],
    });

    renderPage();

    await waitFor(() => {
      expect(screen.getByText('No Dashboards Available')).toBeInTheDocument();
    });
  });

  it('retries loading after clicking retry', async () => {
    (checkEmbedReadiness as any)
      .mockResolvedValueOnce({
        status: 'not_ready',
        embed_configured: false,
        superset_url_configured: false,
        allowed_dashboards_configured: false,
        message: 'Service warming up',
      })
      .mockResolvedValueOnce({
        status: 'ready',
        embed_configured: true,
        superset_url_configured: true,
        allowed_dashboards_configured: true,
      });

    renderPage();

    await waitFor(() => {
      expect(screen.getByText('Service warming up')).toBeInTheDocument();
    });

    fireEvent.click(screen.getByRole('button', { name: 'Retry' }));

    await waitFor(() => {
      expect(screen.getByText('Embedded Dashboard')).toBeInTheDocument();
    }, { timeout: 4000 });
  });
});
