/**
 * Mock replacements for AgencyContext and DataHealthContext.
 * These provide the same Provider + hook API but with static mock data,
 * avoiding the need for live API calls or auth tokens.
 */
import React, { createContext, useContext, type ReactNode } from 'react';

// =============================================================================
// Agency Context Mock
// =============================================================================

const mockAgencyValue = {
  userId: 'user_mock',
  userRoles: [{ role: 'admin', category: 'merchant' }],
  billingTier: 'growth' as const,
  isAgencyUser: false,
  activeTenantId: 'tenant_mock',
  allowedTenants: ['tenant_mock'],
  assignedStores: [],
  accessExpiringAt: null,
  loading: false,
  error: null,
  switchStore: async () => {},
  refreshStores: async () => {},
  getActiveStore: () => ({
    tenant_id: 'tenant_mock',
    store_name: 'Demo Store',
    shop_domain: 'demo-store.myshopify.com',
    status: 'active' as const,
    role: 'admin',
    assigned_at: '2026-01-01T00:00:00Z',
  }),
  canAccessStore: () => true,
};

const AgencyContext = createContext(mockAgencyValue);

export function AgencyProvider({ children }: { children: ReactNode }) {
  return React.createElement(AgencyContext.Provider, { value: mockAgencyValue }, children);
}

export function useAgency() {
  return useContext(AgencyContext);
}

export function useActiveStore() {
  const { getActiveStore, activeTenantId, loading } = useAgency();
  return { store: getActiveStore(), tenantId: activeTenantId, loading };
}

// =============================================================================
// Data Health Context Mock
// =============================================================================

const mockDataHealthValue = {
  health: {
    overall_status: 'healthy' as const,
    source_count: 2,
    healthy_count: 2,
    degraded_count: 0,
    critical_count: 0,
    last_updated: '2026-03-01T12:00:00Z',
  },
  activeIncidents: [],
  hasCritical: false,
  hasBlocking: false,
  loading: false,
  error: null,
  lastUpdated: new Date('2026-03-01T12:00:00Z'),
  merchantHealth: null,
  refresh: async () => {},
  acknowledgeIncident: async () => {},
  hasStaleData: false,
  hasCriticalIssues: false,
  hasBlockingIssues: false,
  shouldShowBanner: false,
  mostSevereIncident: null,
  freshnessLabel: 'All data fresh',
  merchantHealthState: null,
  merchantHealthMessage: null,
};

const DataHealthContext = createContext(mockDataHealthValue);

export function DataHealthProvider({ children }: { children: ReactNode }) {
  return React.createElement(DataHealthContext.Provider, { value: mockDataHealthValue }, children);
}

export function useDataHealth() {
  return useContext(DataHealthContext);
}

export function useFreshnessStatus() {
  const { health, hasStaleData, hasCriticalIssues, freshnessLabel, loading } = useDataHealth();
  return {
    status: health?.overall_status ?? null,
    hasStaleData,
    hasCriticalIssues,
    freshnessLabel,
    loading,
  };
}

export function useActiveIncidents() {
  const { activeIncidents, shouldShowBanner, mostSevereIncident, acknowledgeIncident } = useDataHealth();
  return { incidents: activeIncidents, shouldShowBanner, mostSevereIncident, acknowledgeIncident };
}

export function useMerchantHealth() {
  const { merchantHealth, merchantHealthState, merchantHealthMessage, loading } = useDataHealth();
  return { merchantHealth, merchantHealthState, merchantHealthMessage, loading };
}

// =============================================================================
// Agency Context — additional hooks
// =============================================================================

export function useIsAgencyUser(): boolean {
  return false;
}
