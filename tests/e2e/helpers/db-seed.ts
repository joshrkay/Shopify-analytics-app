/**
 * Database seeding helpers for E2E tests.
 *
 * Provides convenience functions for seeding common test data
 * via the backend's /api/test/seed endpoint.
 */

const API_BASE = process.env.E2E_API_URL || 'http://localhost:8000';

async function postSeed(data: Record<string, unknown>): Promise<Record<string, unknown>> {
  const response = await fetch(`${API_BASE}/api/test/seed`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  });

  if (!response.ok) {
    const body = await response.text();
    throw new Error(`Seed failed: ${response.status} - ${body}`);
  }

  return response.json();
}

/**
 * Seed baseline data required by most E2E tests.
 * Creates plans, test tenants, and basic configuration.
 */
export async function seedBaseline(): Promise<void> {
  await postSeed({
    plans: [
      { id: 'plan-free-001', name: 'free', display_name: 'Free', price_monthly_cents: 0, features: [] },
      { id: 'plan-growth-001', name: 'growth', display_name: 'Growth', price_monthly_cents: 4900, features: ['CUSTOM_REPORTS'] },
      { id: 'plan-pro-001', name: 'pro', display_name: 'Pro', price_monthly_cents: 14900, features: ['AI_INSIGHTS', 'AI_RECOMMENDATIONS', 'AI_ACTIONS', 'CUSTOM_REPORTS', 'COHORT_ANALYSIS'] },
      { id: 'plan-enterprise-001', name: 'enterprise', display_name: 'Enterprise', price_monthly_cents: 49900, features: ['AI_INSIGHTS', 'AI_RECOMMENDATIONS', 'AI_ACTIONS', 'CUSTOM_REPORTS', 'COHORT_ANALYSIS', 'BUDGET_PACING', 'ALERTS', 'ADVANCED_ANALYTICS'] },
    ],
    tenants: [
      { id: 'e2e-tenant-free-001', name: 'E2E Free Store', clerk_org_id: 'e2e-tenant-free-001' },
      { id: 'e2e-tenant-growth-001', name: 'E2E Growth Store', clerk_org_id: 'e2e-tenant-growth-001' },
      { id: 'e2e-tenant-pro-001', name: 'E2E Pro Store', clerk_org_id: 'e2e-tenant-pro-001' },
      { id: 'e2e-tenant-enterprise-001', name: 'E2E Enterprise Store', clerk_org_id: 'e2e-tenant-enterprise-001' },
      { id: 'e2e-tenant-admin-001', name: 'E2E Admin Store', clerk_org_id: 'e2e-tenant-admin-001' },
    ],
    subscriptions: [
      { tenant_id: 'e2e-tenant-growth-001', plan_id: 'plan-growth-001', status: 'active' },
      { tenant_id: 'e2e-tenant-pro-001', plan_id: 'plan-pro-001', status: 'active' },
      { tenant_id: 'e2e-tenant-enterprise-001', plan_id: 'plan-enterprise-001', status: 'active' },
      { tenant_id: 'e2e-tenant-admin-001', plan_id: 'plan-pro-001', status: 'active' },
    ],
  });
}

/**
 * Seed sample dashboard data for a tenant.
 */
export async function seedDashboardData(tenantId: string): Promise<void> {
  await postSeed({
    dashboards: [
      { tenant_id: tenantId, name: 'Overview Dashboard', status: 'published' },
      { tenant_id: tenantId, name: 'Draft Dashboard', status: 'draft' },
    ],
  });
}

/**
 * Seed sample order data for a tenant.
 */
export async function seedOrderData(tenantId: string): Promise<void> {
  await postSeed({
    orders: [
      { tenant_id: tenantId, order_name: '#1001', financial_status: 'paid', revenue_gross: 9999 },
      { tenant_id: tenantId, order_name: '#1002', financial_status: 'paid', revenue_gross: 4500 },
      { tenant_id: tenantId, order_name: '#1003', financial_status: 'pending', revenue_gross: 7800 },
      { tenant_id: tenantId, order_name: '#1004', financial_status: 'refunded', revenue_gross: 3200 },
      { tenant_id: tenantId, order_name: '#1005', financial_status: 'paid', revenue_gross: 15000 },
    ],
  });
}

/**
 * Seed sample insight data for a tenant.
 */
export async function seedInsightData(tenantId: string): Promise<void> {
  await postSeed({
    insights: [
      { tenant_id: tenantId, title: 'Revenue spike detected', severity: 'high', status: 'active' },
      { tenant_id: tenantId, title: 'ROAS declining on Meta Ads', severity: 'medium', status: 'active' },
      { tenant_id: tenantId, title: 'New customer segment growing', severity: 'low', status: 'active' },
    ],
  });
}

/**
 * Seed sample connection data for a tenant.
 */
export async function seedConnectionData(tenantId: string): Promise<void> {
  await postSeed({
    connections: [
      { tenant_id: tenantId, platform: 'shopify', status: 'active', last_synced_at: new Date().toISOString() },
      { tenant_id: tenantId, platform: 'meta_ads', status: 'active', last_synced_at: new Date().toISOString() },
      { tenant_id: tenantId, platform: 'google_ads', status: 'error' },
    ],
  });
}

/**
 * Clean up all E2E test data.
 */
export async function teardownAll(): Promise<void> {
  const tenantIds = [
    'e2e-tenant-free-001',
    'e2e-tenant-growth-001',
    'e2e-tenant-pro-001',
    'e2e-tenant-enterprise-001',
    'e2e-tenant-admin-001',
  ];

  for (const tenantId of tenantIds) {
    try {
      await fetch(`${API_BASE}/api/test/teardown`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ tenant_id: tenantId }),
      });
    } catch {
      // Best-effort cleanup
    }
  }
}
