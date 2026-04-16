/**
 * Database seed and teardown fixture for E2E tests.
 *
 * Seeds test data via the backend's /api/test/seed endpoint
 * and cleans up via /api/test/teardown after each test.
 *
 * The backend test_seed route is only available when ENV=test.
 */
import { test as base, APIRequestContext } from '@playwright/test';

const API_BASE = process.env.E2E_API_URL || 'http://localhost:8000';

export interface SeedData {
  tenants?: TenantSeed[];
  plans?: PlanSeed[];
  subscriptions?: SubscriptionSeed[];
  stores?: StoreSeed[];
  dashboards?: DashboardSeed[];
  connections?: ConnectionSeed[];
  insights?: InsightSeed[];
  orders?: OrderSeed[];
}

export interface TenantSeed {
  id: string;
  name: string;
  clerk_org_id?: string;
  status?: string;
}

export interface PlanSeed {
  id: string;
  name: string;
  display_name: string;
  price_monthly_cents: number;
  features: string[];
}

export interface SubscriptionSeed {
  tenant_id: string;
  plan_id: string;
  status?: string;
}

export interface StoreSeed {
  tenant_id: string;
  shop_domain: string;
  access_token?: string;
  status?: string;
}

export interface DashboardSeed {
  tenant_id: string;
  name: string;
  status?: string;
  reports?: Array<{ chart_type: string; name: string }>;
}

export interface ConnectionSeed {
  tenant_id: string;
  platform: string;
  status?: string;
  last_synced_at?: string;
}

export interface InsightSeed {
  tenant_id: string;
  title: string;
  severity?: string;
  status?: string;
}

export interface OrderSeed {
  tenant_id: string;
  order_name: string;
  financial_status?: string;
  revenue_gross?: number;
}

export interface DbFixtures {
  /** Seed data into the test database. Returns created entity IDs. */
  seedDatabase: (data: SeedData) => Promise<Record<string, string[]>>;
  /** Teardown all data for a specific tenant. */
  teardownTenant: (tenantId: string) => Promise<void>;
  /** Teardown multiple tenants. */
  teardownTenants: (tenantIds: string[]) => Promise<void>;
  /** Query data from the test database (for assertions). */
  queryDatabase: (query: { table: string; tenant_id: string; filters?: Record<string, string> }) => Promise<Record<string, unknown>[]>;
}

export const test = base.extend<DbFixtures>({
  seedDatabase: async ({ request }, use) => {
    const seededTenants: string[] = [];

    const seed = async (data: SeedData): Promise<Record<string, string[]>> => {
      const response = await request.post(`${API_BASE}/api/test/seed`, {
        data,
        headers: { 'Content-Type': 'application/json' },
      });

      if (!response.ok()) {
        const body = await response.text();
        throw new Error(`Failed to seed database: ${response.status()} - ${body}`);
      }

      const result = await response.json();

      // Track tenant IDs for auto-cleanup
      if (data.tenants) {
        seededTenants.push(...data.tenants.map(t => t.id));
      }

      return result.created_ids || {};
    };

    await use(seed);

    // Auto-cleanup seeded tenants
    for (const tenantId of seededTenants) {
      try {
        await request.post(`${API_BASE}/api/test/teardown`, {
          data: { tenant_id: tenantId },
          headers: { 'Content-Type': 'application/json' },
        });
      } catch {
        // Best-effort cleanup
      }
    }
  },

  teardownTenant: async ({ request }, use) => {
    const teardown = async (tenantId: string): Promise<void> => {
      const response = await request.post(`${API_BASE}/api/test/teardown`, {
        data: { tenant_id: tenantId },
        headers: { 'Content-Type': 'application/json' },
      });
      if (!response.ok()) {
        console.warn(`Teardown warning for tenant ${tenantId}: ${response.status()}`);
      }
    };
    await use(teardown);
  },

  teardownTenants: async ({ request }, use) => {
    const teardown = async (tenantIds: string[]): Promise<void> => {
      for (const tenantId of tenantIds) {
        try {
          await request.post(`${API_BASE}/api/test/teardown`, {
            data: { tenant_id: tenantId },
            headers: { 'Content-Type': 'application/json' },
          });
        } catch {
          // Best-effort
        }
      }
    };
    await use(teardown);
  },

  queryDatabase: async ({ request }, use) => {
    const query = async (params: {
      table: string;
      tenant_id: string;
      filters?: Record<string, string>;
    }): Promise<Record<string, unknown>[]> => {
      const response = await request.post(`${API_BASE}/api/test/query`, {
        data: params,
        headers: { 'Content-Type': 'application/json' },
      });

      if (!response.ok()) {
        const body = await response.text();
        throw new Error(`Failed to query database: ${response.status()} - ${body}`);
      }

      const result = await response.json();
      return result.rows || [];
    };
    await use(query);
  },
});

export { expect } from '@playwright/test';
