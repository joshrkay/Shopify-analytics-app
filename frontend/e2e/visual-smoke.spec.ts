/**
 * Visual Smoke Tests — Playwright
 *
 * Takes screenshots of each major page to prove the UI renders correctly.
 * Mocks Clerk auth and backend API calls so pages can render without
 * a live backend or Clerk account.
 */
import { test, expect } from '@playwright/test';
import type { Page, Route } from '@playwright/test';

const BASE = 'http://localhost:4173';

// Mock data for API responses
const MOCK_ENTITLEMENTS = {
  plan: 'growth',
  features: {
    custom_reports: true,
    ai_insights: true,
    ai_recommendations: true,
    ai_actions: true,
  },
};

const MOCK_SOURCES = [
  {
    id: 'src-1',
    platform: 'shopify',
    name: 'My Shopify Store',
    status: 'active',
    last_sync_at: '2026-03-01T12:00:00Z',
    created_at: '2026-01-15T00:00:00Z',
  },
  {
    id: 'src-2',
    platform: 'meta',
    name: 'Meta Ads',
    status: 'active',
    last_sync_at: '2026-03-01T10:00:00Z',
    created_at: '2026-02-01T00:00:00Z',
  },
];

const MOCK_DASHBOARDS = [
  {
    id: 'dash-1',
    name: 'Sales Overview',
    description: 'Key sales metrics',
    created_at: '2026-02-15T00:00:00Z',
    updated_at: '2026-03-01T12:00:00Z',
    widget_count: 4,
  },
];

const MOCK_INSIGHTS = [
  {
    id: 'ins-1',
    title: 'Revenue trending up 15%',
    description: 'Your revenue has increased 15% compared to last week',
    category: 'revenue',
    severity: 'positive',
    estimated_dollar_impact: 2500,
    created_at: '2026-03-01T08:00:00Z',
    is_read: false,
  },
  {
    id: 'ins-2',
    title: 'Cart abandonment spike detected',
    description: 'Cart abandonment rate increased by 8% in the last 24 hours',
    category: 'conversion',
    severity: 'warning',
    estimated_dollar_impact: -1200,
    created_at: '2026-03-01T06:00:00Z',
    is_read: false,
  },
];

const MOCK_HEALTH = {
  overall_status: 'healthy',
  sources: [
    { platform: 'shopify', status: 'healthy', last_sync: '2026-03-01T12:00:00Z' },
    { platform: 'meta', status: 'healthy', last_sync: '2026-03-01T10:00:00Z' },
  ],
};

const MOCK_CATALOG = [
  { platform: 'shopify', name: 'Shopify', category: 'ecommerce', auth_type: 'oauth', logo_url: '' },
  { platform: 'meta', name: 'Meta Ads', category: 'advertising', auth_type: 'oauth', logo_url: '' },
  { platform: 'google', name: 'Google Ads', category: 'advertising', auth_type: 'oauth', logo_url: '' },
  { platform: 'tiktok', name: 'TikTok Ads', category: 'advertising', auth_type: 'oauth', logo_url: '' },
];

/**
 * Set up route interception to mock all API and Clerk calls
 */
async function mockAllRequests(page: Page) {
  // Mock Clerk API calls — make Clerk think we're signed in
  await page.route('**clerk**', async (route: Route) => {
    const url = route.request().url();

    // Clerk client/environment endpoint
    if (url.includes('/v1/client') || url.includes('/v1/environment')) {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          response: {
            id: 'client_mock',
            sessions: [{
              id: 'sess_mock',
              status: 'active',
              user: {
                id: 'user_mock',
                first_name: 'Demo',
                last_name: 'User',
                email_addresses: [{ email_address: 'demo@markinsight.net' }],
                primary_email_address_id: 'email_mock',
                organization_memberships: [{
                  id: 'orgmem_mock',
                  organization: {
                    id: 'org_demo',
                    name: 'Demo Store',
                    slug: 'demo-store',
                  },
                  role: 'admin',
                }],
              },
              last_active_organization_id: 'org_demo',
            }],
            sign_in: null,
            sign_up: null,
            last_active_session_id: 'sess_mock',
          },
          client: {
            id: 'client_mock',
            sessions: [],
            last_active_session_id: 'sess_mock',
          },
        }),
      });
      return;
    }

    // All other Clerk calls — return empty success
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ response: {} }),
    });
  });

  // Mock backend API calls
  await page.route('**/api/**', async (route: Route) => {
    const url = route.request().url();

    if (url.includes('/api/billing/entitlements')) {
      await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(MOCK_ENTITLEMENTS) });
    } else if (url.includes('/api/sources/catalog')) {
      await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(MOCK_CATALOG) });
    } else if (url.includes('/api/sources')) {
      await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(MOCK_SOURCES) });
    } else if (url.includes('/api/dashboards') && !url.includes('/api/dashboards/')) {
      await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(MOCK_DASHBOARDS) });
    } else if (url.includes('/api/insights')) {
      await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(MOCK_INSIGHTS) });
    } else if (url.includes('/api/health') || url.includes('/api/data-health')) {
      await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(MOCK_HEALTH) });
    } else if (url.includes('/api/notifications')) {
      await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify([]) });
    } else if (url.includes('/api/agency')) {
      await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ agencies: [], current_agency: null }) });
    } else if (url.includes('/api/team')) {
      await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ members: [] }) });
    } else if (url.includes('/api/attribution')) {
      await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ data: [], summary: {} }) });
    } else if (url.includes('/api/orders')) {
      await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ orders: [], total: 0 }) });
    } else if (url.includes('/api/analytics')) {
      await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ metrics: {}, charts: {} }) });
    } else {
      // Default: return empty JSON for any unhandled API call
      await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({}) });
    }
  });
}

// Pages to screenshot
const PAGES = [
  { path: '/', name: '01-dashboard-home', waitFor: 2000 },
  { path: '/analytics', name: '02-analytics', waitFor: 2000 },
  { path: '/insights', name: '03-insights-feed', waitFor: 2000 },
  { path: '/sources', name: '04-data-sources', waitFor: 2000 },
  { path: '/attribution', name: '05-attribution', waitFor: 2000 },
  { path: '/orders', name: '06-orders', waitFor: 2000 },
  { path: '/dashboards', name: '07-dashboard-list', waitFor: 2000 },
  { path: '/settings', name: '08-settings', waitFor: 2000 },
  { path: '/approvals', name: '09-approvals', waitFor: 2000 },
  { path: '/whats-new', name: '10-whats-new', waitFor: 2000 },
  { path: '/billing/checkout', name: '11-billing', waitFor: 2000 },
  { path: '/paywall', name: '12-paywall', waitFor: 2000 },
];

for (const { path, name, waitFor } of PAGES) {
  test(`screenshot: ${name} (${path})`, async ({ page }) => {
    await mockAllRequests(page);
    await page.goto(`${BASE}${path}`, { waitUntil: 'networkidle' });
    await page.waitForTimeout(waitFor);
    await page.screenshot({
      path: `e2e/screenshots/${name}.png`,
      fullPage: true,
    });
    // Basic assertion: page should have rendered something (not blank)
    const bodyText = await page.locator('body').textContent();
    expect(bodyText?.length).toBeGreaterThan(0);
  });
}
