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
      // Billing entitlements (used by many pages)
      '/api/billing/entitlements': {
        billing_state: 'active', plan_id: 'plan_growth', plan_name: 'Growth',
        features: {
          custom_reports: { feature: 'custom_reports', is_entitled: true, billing_state: 'active', plan_id: 'plan_growth', plan_name: 'Growth', reason: null, required_plan: null, grace_period_ends_on: null },
          ai_insights: { feature: 'ai_insights', is_entitled: true, billing_state: 'active', plan_id: 'plan_growth', plan_name: 'Growth', reason: null, required_plan: null, grace_period_ends_on: null },
          ai_recommendations: { feature: 'ai_recommendations', is_entitled: true, billing_state: 'active', plan_id: 'plan_growth', plan_name: 'Growth', reason: null, required_plan: null, grace_period_ends_on: null },
          ai_actions: { feature: 'ai_actions', is_entitled: true, billing_state: 'active', plan_id: 'plan_growth', plan_name: 'Growth', reason: null, required_plan: null, grace_period_ends_on: null },
        },
        grace_period_days_remaining: null,
      },
      // Source catalog (wrapped in CatalogResponse shape)
      '/api/sources/catalog': {
        sources: [
          { platform: 'shopify', name: 'Shopify', category: 'ecommerce', auth_type: 'oauth', description: 'Shopify store data', is_available: true },
          { platform: 'meta_ads', name: 'Meta Ads', category: 'advertising', auth_type: 'oauth', description: 'Facebook & Instagram Ads', is_available: true },
          { platform: 'google_ads', name: 'Google Ads', category: 'advertising', auth_type: 'oauth', description: 'Google advertising', is_available: true },
          { platform: 'tiktok_ads', name: 'TikTok Ads', category: 'advertising', auth_type: 'oauth', description: 'TikTok advertising', is_available: true },
        ],
        total: 4,
      },
      // Data sources list (snake_case fields for normalizeApiSource)
      '/api/sources': {
        sources: [
          { id: 'src-1', platform: 'shopify', display_name: 'My Shopify Store', auth_type: 'oauth', status: 'active', is_enabled: true, last_sync_at: '2026-03-01T12:00:00Z', last_sync_status: 'success' },
          { id: 'src-2', platform: 'meta_ads', display_name: 'Meta Ads', auth_type: 'oauth', status: 'active', is_enabled: true, last_sync_at: '2026-03-01T10:00:00Z', last_sync_status: 'success' },
        ],
        total: 2,
      },
      // Dashboard list + count
      '/api/v1/dashboards/count': { current_count: 1, max_count: 10, can_create: true },
      '/api/v1/dashboards': {
        dashboards: [
          { id: 'dash-1', name: 'Sales Overview', description: 'Key sales metrics', status: 'published', layout_json: {}, filters_json: null, template_id: null, is_template_derived: false, version_number: 1, reports: [], access_level: 'owner', created_by: 'user_mock', created_at: '2026-02-15T00:00:00Z', updated_at: '2026-03-01T12:00:00Z' },
        ],
        total: 1, offset: 0, limit: 20, has_more: false,
      },
      '/api/dashboards': {
        dashboards: [
          { id: 'dash-1', name: 'Sales Overview', description: 'Key sales metrics', status: 'published', layout_json: {}, reports: [], access_level: 'owner', created_by: 'user_mock', created_at: '2026-02-15T00:00:00Z', updated_at: '2026-03-01T12:00:00Z' },
        ],
        total: 1, offset: 0, limit: 20, has_more: false,
      },
      // Insights
      '/api/insights': {
        insights: [
          { insight_id: 'ins-1', insight_type: 'roas_change', severity: 'info', summary: 'Revenue trending up 15%', why_it_matters: 'Your ROAS improved significantly', supporting_metrics: [{ metric: 'ROAS', previous: 2.8, current: 3.6, change: 0.8, change_pct: 28.6 }], timeframe: '7d', confidence_score: 0.92, platform: 'meta', campaign_id: null, currency: 'USD', generated_at: '2026-03-01T08:00:00Z', is_read: false, is_dismissed: false, estimated_dollar_impact: 2500, dollar_impact_explanation: 'Based on current trends' },
          { insight_id: 'ins-2', insight_type: 'spend_anomaly', severity: 'warning', summary: 'Cart abandonment spike detected', why_it_matters: 'Revenue loss from abandoned carts', supporting_metrics: [{ metric: 'Abandonment Rate', previous: 0.22, current: 0.30, change: 0.08, change_pct: 36.4 }], timeframe: '24h', confidence_score: 0.85, platform: null, campaign_id: null, currency: 'USD', generated_at: '2026-03-01T06:00:00Z', is_read: false, is_dismissed: false, estimated_dollar_impact: -1200, dollar_impact_explanation: 'Estimated lost revenue' },
        ],
        total: 2, has_more: false,
      },
      // Attribution summary + orders
      '/api/attribution/summary': {
        attributed_orders: 156, unattributed_orders: 44, attribution_rate: 78.0, total_attributed_revenue: 34500.00,
        top_campaigns: [
          { campaign_name: 'Summer Sale', platform: 'meta', revenue: 12500, orders: 52, spend: 3200, roas: 3.9 },
          { campaign_name: 'Brand Awareness', platform: 'google', revenue: 8900, orders: 38, spend: 2800, roas: 3.2 },
          { campaign_name: 'Product Launch', platform: 'tiktok', revenue: 6200, orders: 28, spend: 2100, roas: 3.0 },
        ],
        channel_roas: [
          { platform: 'meta', gross_roas: 3.9, revenue: 15200, spend: 3900 },
          { platform: 'google', gross_roas: 3.2, revenue: 11500, spend: 3600 },
          { platform: 'tiktok', gross_roas: 2.8, revenue: 7800, spend: 2800 },
        ],
      },
      '/api/attribution/orders': { orders: [], total: 0, has_more: false },
      '/api/attribution': {
        attributed_orders: 156, unattributed_orders: 44, attribution_rate: 78.0, total_attributed_revenue: 34500.00,
        top_campaigns: [], channel_roas: [],
      },
      // Action proposals (approvals)
      '/api/action-proposals': { proposals: [], total: 0, has_more: false, pending_count: 0 },
      // Plans (for paywall)
      '/api/admin/plans': {
        plans: [
          { id: 'plan_free', name: 'free', display_name: 'Free', description: 'Basic analytics', price_monthly_cents: 0, price_yearly_cents: 0, shopify_plan_id: null, is_active: true, features: [], created_at: '2026-01-01T00:00:00Z', updated_at: '2026-01-01T00:00:00Z' },
          { id: 'plan_growth', name: 'growth', display_name: 'Growth', description: 'Advanced analytics + AI', price_monthly_cents: 2900, price_yearly_cents: 29000, shopify_plan_id: null, is_active: true, features: [], created_at: '2026-01-01T00:00:00Z', updated_at: '2026-01-01T00:00:00Z' },
          { id: 'plan_pro', name: 'pro', display_name: 'Pro', description: 'Everything in Growth + custom reports', price_monthly_cents: 7900, price_yearly_cents: 79000, shopify_plan_id: null, is_active: true, features: [], created_at: '2026-01-01T00:00:00Z', updated_at: '2026-01-01T00:00:00Z' },
        ],
        total: 3, limit: 20, offset: 0,
      },
      // Billing checkout (returns "activated" state for free plan)
      '/api/billing/checkout': { success: true, checkout_url: '', subscription_id: 'sub_mock', shopify_subscription_id: null },
      // Changelog feature entries (FeatureUpdateBanner)
      '/api/changelog/feature': { entries: [], total: 0, has_more: false, unread_count: 0 },
      '/api/changelog/unread/count': { count: 0, by_feature_area: {} },
      // Recommendations (InsightsFeed modal)
      '/api/recommendations': { recommendations: [], total: 0, has_more: false },
      // Other endpoints
      '/api/data-health': { overall_status: 'healthy', sources: [], active_incidents: [] },
      '/api/health': { overall_status: 'healthy', sources: [], active_incidents: [] },
      '/api/notifications': [],
      '/api/agency': { agencies: [], current_agency: null, user_roles: [] },
      '/api/team': { members: [] },
      '/api/orders': { orders: [], total: 0 },
      '/api/analytics': { metrics: {}, charts: {} },
      '/api/whats-new': { entries: [] },
      '/api/changelog': { entries: [], total: 0, has_more: false, unread_count: 0 },
      '/api/approvals': { proposals: [], total: 0, has_more: false, pending_count: 0 },
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
