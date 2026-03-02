/**
 * Visual Test Harness
 *
 * Renders each page component with mock providers, bypassing Clerk entirely.
 * Uses URL hash to determine which page to render: e.g., #/sources
 *
 * Renders pages with the Root layout (sidebar + header) but without
 * AgencyProvider/DataHealthProvider (which need live API tokens).
 * Instead, mocks the context hooks at the module level.
 */
import React from 'react';
import { createRoot } from 'react-dom/client';
import { MemoryRouter, Routes, Route } from 'react-router-dom';
import { AppProvider } from '@shopify/polaris';
import enTranslations from '@shopify/polaris/locales/en.json';
import '@shopify/polaris/build/esm/styles.css';
import '../src/index.css';

// Import page components
import { Dashboard } from '../src/pages/Dashboard';
import Analytics from '../src/pages/Analytics';
import InsightsFeed from '../src/pages/InsightsFeed';
import DataSources from '../src/pages/DataSources';
import { Attribution } from '../src/pages/Attribution';
import { Orders } from '../src/pages/Orders';
import { DashboardList } from '../src/pages/DashboardList';
import Settings from '../src/pages/Settings';
import ApprovalsInbox from '../src/pages/ApprovalsInbox';
import WhatsNew from '../src/pages/WhatsNew';
import BillingCheckout from '../src/pages/BillingCheckout';
import Paywall from '../src/pages/Paywall';
import { DashboardHome } from '../src/pages/DashboardHome';
import { Root } from '../src/components/layout/Root';

// Get target page from URL hash
const targetPath = window.location.hash.replace('#', '') || '/';

// Mock fetch globally for all API calls
const originalFetch = window.fetch;
window.fetch = async (input: RequestInfo | URL, init?: RequestInit) => {
  const url = typeof input === 'string' ? input : input.toString();

  if (url.includes('/api/')) {
    const mockResponses: Record<string, unknown> = {
      '/api/billing/entitlements': {
        billing_state: 'active', plan_id: 'plan_growth', plan_name: 'Growth',
        features: {
          custom_reports: { feature: 'custom_reports', is_entitled: true, billing_state: 'active' },
          ai_insights: { feature: 'ai_insights', is_entitled: true, billing_state: 'active' },
        },
      },
      '/api/sources/catalog': [
        { platform: 'shopify', name: 'Shopify', category: 'ecommerce', auth_type: 'oauth' },
        { platform: 'meta', name: 'Meta Ads', category: 'advertising', auth_type: 'oauth' },
        { platform: 'google', name: 'Google Ads', category: 'advertising', auth_type: 'oauth' },
        { platform: 'tiktok', name: 'TikTok Ads', category: 'advertising', auth_type: 'oauth' },
      ],
      '/api/sources': [
        { id: 'src-1', platform: 'shopify', name: 'My Shopify Store', status: 'active', last_sync_at: '2026-03-01T12:00:00Z', created_at: '2026-01-15T00:00:00Z' },
        { id: 'src-2', platform: 'meta', name: 'Meta Ads', status: 'active', last_sync_at: '2026-03-01T10:00:00Z', created_at: '2026-02-01T00:00:00Z' },
      ],
      '/api/dashboards': [
        { id: 'dash-1', name: 'Sales Overview', description: 'Key sales metrics', widget_count: 4, created_at: '2026-02-15T00:00:00Z', updated_at: '2026-03-01T12:00:00Z' },
      ],
      '/api/insights': {
        insights: [
          { id: 'ins-1', title: 'Revenue trending up 15%', description: 'Revenue increased 15% vs last week', category: 'revenue', severity: 'positive', estimated_dollar_impact: 2500, created_at: '2026-03-01T08:00:00Z', is_read: false },
          { id: 'ins-2', title: 'Cart abandonment spike', description: 'Cart abandonment rate increased by 8%', category: 'conversion', severity: 'warning', estimated_dollar_impact: -1200, created_at: '2026-03-01T06:00:00Z', is_read: false },
        ],
        total: 2,
      },
      '/api/data-health': { overall_status: 'healthy', sources: [], active_incidents: [] },
      '/api/health': { overall_status: 'healthy', sources: [], active_incidents: [] },
      '/api/notifications': [],
      '/api/agency': { agencies: [], current_agency: null, user_roles: [] },
      '/api/team': { members: [] },
      '/api/attribution': { data: [], summary: {} },
      '/api/orders': { orders: [], total: 0 },
      '/api/analytics': { metrics: {}, charts: {} },
      '/api/whats-new': { entries: [] },
      '/api/changelog': { entries: [] },
      '/api/approvals': { approvals: [], total: 0 },
      '/api/billing': { plan: 'growth', status: 'active' },
    };

    const matchKey = Object.keys(mockResponses)
      .sort((a, b) => b.length - a.length) // Match longer paths first
      .find(key => url.includes(key));
    const data = matchKey ? mockResponses[matchKey] : {};

    return new Response(JSON.stringify(data), {
      status: 200,
      headers: { 'Content-Type': 'application/json' },
    });
  }

  return originalFetch(input, init);
};

// Error boundary to catch render errors gracefully
class ErrorBoundary extends React.Component<
  { children: React.ReactNode; fallback?: string },
  { error: Error | null }
> {
  state = { error: null as Error | null };
  static getDerivedStateFromError(error: Error) {
    return { error };
  }
  render() {
    if (this.state.error) {
      return (
        <div style={{ padding: 40, fontFamily: 'system-ui, sans-serif' }}>
          <h2 style={{ color: '#d32f2f' }}>Page Error</h2>
          <p>{this.state.error.message}</p>
          <pre style={{ fontSize: 12, color: '#666', whiteSpace: 'pre-wrap' }}>
            {this.state.error.stack}
          </pre>
        </div>
      );
    }
    return this.props.children;
  }
}

function TestApp() {
  return (
    <AppProvider i18n={enTranslations}>
      <ErrorBoundary>
        <MemoryRouter initialEntries={[targetPath]}>
          <Routes>
            <Route element={<Root />}>
              <Route path="/" element={
                <ErrorBoundary fallback="Dashboard"><Dashboard /></ErrorBoundary>
              } />
              <Route path="/home" element={
                <ErrorBoundary fallback="DashboardHome"><DashboardHome /></ErrorBoundary>
              } />
              <Route path="/analytics" element={
                <ErrorBoundary fallback="Analytics"><Analytics /></ErrorBoundary>
              } />
              <Route path="/insights" element={
                <ErrorBoundary fallback="InsightsFeed"><InsightsFeed /></ErrorBoundary>
              } />
              <Route path="/sources" element={
                <ErrorBoundary fallback="DataSources"><DataSources /></ErrorBoundary>
              } />
              <Route path="/data-sources" element={
                <ErrorBoundary fallback="DataSources"><DataSources /></ErrorBoundary>
              } />
              <Route path="/attribution" element={
                <ErrorBoundary fallback="Attribution"><Attribution /></ErrorBoundary>
              } />
              <Route path="/orders" element={
                <ErrorBoundary fallback="Orders"><Orders /></ErrorBoundary>
              } />
              <Route path="/dashboards" element={
                <ErrorBoundary fallback="DashboardList"><DashboardList /></ErrorBoundary>
              } />
              <Route path="/settings" element={
                <ErrorBoundary fallback="Settings"><Settings /></ErrorBoundary>
              } />
              <Route path="/approvals" element={
                <ErrorBoundary fallback="ApprovalsInbox"><ApprovalsInbox /></ErrorBoundary>
              } />
              <Route path="/whats-new" element={
                <ErrorBoundary fallback="WhatsNew"><WhatsNew /></ErrorBoundary>
              } />
              <Route path="/billing/checkout" element={
                <ErrorBoundary fallback="BillingCheckout"><BillingCheckout /></ErrorBoundary>
              } />
              <Route path="/paywall" element={
                <ErrorBoundary fallback="Paywall"><Paywall /></ErrorBoundary>
              } />
            </Route>
          </Routes>
        </MemoryRouter>
      </ErrorBoundary>
    </AppProvider>
  );
}

createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <TestApp />
  </React.StrictMode>
);
