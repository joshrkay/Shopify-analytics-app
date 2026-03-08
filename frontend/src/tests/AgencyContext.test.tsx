/**
 * Tests for AgencyContext
 *
 * Covers:
 * - useAgency throws outside provider
 * - AgencyProvider renders children
 * - Initial state (loading=true)
 * - State updates from API after initialization
 * - switchStore throws for non-agency users
 * - switchStore throws for unauthorized tenant
 * - canAccessStore returns true/false
 * - Error state on API failure
 * - useActiveStore returns current store info
 * - useIsAgencyUser returns boolean
 */

import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook, act, waitFor } from '@testing-library/react';
import { render, screen } from '@testing-library/react';

import {
  AgencyProvider,
  useAgency,
  useActiveStore,
  useIsAgencyUser,
} from '../contexts/AgencyContext';
import { UserRole, BillingTier } from '../types/agency';
import type { UserContext, AssignedStore, AssignedStoresResponse } from '../types/agency';

// Mock dependencies
vi.mock('../services/agencyApi', () => ({
  fetchUserContext: vi.fn(),
  fetchAssignedStores: vi.fn(),
}));

vi.mock('../utils/auth', () => ({
  refreshTenantToken: vi.fn(),
}));

vi.mock('../services/apiUtils', () => ({
  isBackendDown: vi.fn().mockReturnValue(false),
  isApiError: vi.fn().mockReturnValue(false),
  isProvisioningError: vi.fn().mockReturnValue(false),
}));

import { fetchUserContext, fetchAssignedStores } from '../services/agencyApi';
import { refreshTenantToken } from '../utils/auth';
import { isBackendDown } from '../services/apiUtils';

const mockFetchUserContext = fetchUserContext as ReturnType<typeof vi.fn>;
const mockFetchAssignedStores = fetchAssignedStores as ReturnType<typeof vi.fn>;
const mockRefreshTenantToken = refreshTenantToken as ReturnType<typeof vi.fn>;
const mockIsBackendDown = isBackendDown as ReturnType<typeof vi.fn>;

// --- Helpers ---

const createMockUserContext = (overrides?: Partial<UserContext>): UserContext => ({
  user_id: 'user-1',
  tenant_id: 'tenant-1',
  org_id: 'org-1',
  roles: [UserRole.MERCHANT_ADMIN],
  allowed_tenants: ['tenant-1'],
  billing_tier: BillingTier.FREE,
  is_agency_user: false,
  ...overrides,
});

const createMockAgencyUserContext = (overrides?: Partial<UserContext>): UserContext =>
  createMockUserContext({
    roles: [UserRole.AGENCY_ADMIN],
    allowed_tenants: ['tenant-1', 'tenant-2', 'tenant-3'],
    is_agency_user: true,
    ...overrides,
  });

const createMockStore = (overrides?: Partial<AssignedStore>): AssignedStore => ({
  tenant_id: 'tenant-1',
  store_name: 'Test Store',
  shop_domain: 'test.myshopify.com',
  status: 'active',
  assigned_at: '2025-01-01T00:00:00Z',
  permissions: ['read', 'write'],
  ...overrides,
});

const createMockStoresResponse = (
  stores: AssignedStore[] = [createMockStore()],
): AssignedStoresResponse => ({
  stores,
  total_count: stores.length,
  active_tenant_id: 'tenant-1',
  max_stores_allowed: 10,
});

function wrapper({ children }: { children: React.ReactNode }) {
  return <AgencyProvider>{children}</AgencyProvider>;
}

// --- Tests ---

describe('AgencyContext', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockIsBackendDown.mockReturnValue(false);
    // Default: merchant user, no stores
    mockFetchUserContext.mockResolvedValue(createMockUserContext());
    mockFetchAssignedStores.mockResolvedValue(createMockStoresResponse());
  });

  // ---- useAgency outside provider ----
  describe('useAgency', () => {
    it('throws if used outside AgencyProvider', () => {
      // Suppress React error boundary console noise
      const spy = vi.spyOn(console, 'error').mockImplementation(() => {});
      expect(() => {
        renderHook(() => useAgency());
      }).toThrow('useAgency must be used within an AgencyProvider');
      spy.mockRestore();
    });
  });

  // ---- AgencyProvider renders children ----
  describe('AgencyProvider', () => {
    it('renders children', () => {
      render(
        <AgencyProvider>
          <div data-testid="child">Hello</div>
        </AgencyProvider>,
      );
      expect(screen.getByTestId('child')).toHaveTextContent('Hello');
    });
  });

  // ---- Initial state ----
  describe('initial state', () => {
    it('has loading=true before initialization completes', () => {
      // Never resolve to keep the provider in loading state
      mockFetchUserContext.mockReturnValue(new Promise(() => {}));

      const { result } = renderHook(() => useAgency(), { wrapper });

      expect(result.current.loading).toBe(true);
      expect(result.current.error).toBeNull();
      expect(result.current.userId).toBeNull();
    });
  });

  // ---- State updates after initialization ----
  describe('after initialization', () => {
    it('updates state from API for a merchant user', async () => {
      const userCtx = createMockUserContext();
      mockFetchUserContext.mockResolvedValue(userCtx);

      const { result } = renderHook(() => useAgency(), { wrapper });

      await waitFor(() => {
        expect(result.current.loading).toBe(false);
      });

      expect(result.current.userId).toBe('user-1');
      expect(result.current.isAgencyUser).toBe(false);
      expect(result.current.activeTenantId).toBe('tenant-1');
      expect(result.current.billingTier).toBe('free');
      expect(result.current.error).toBeNull();
      // Non-agency users should not have stores fetched
      expect(mockFetchAssignedStores).not.toHaveBeenCalled();
    });

    it('fetches assigned stores for agency users', async () => {
      const agencyCtx = createMockAgencyUserContext();
      const stores = [
        createMockStore({ tenant_id: 'tenant-1', store_name: 'Store A' }),
        createMockStore({ tenant_id: 'tenant-2', store_name: 'Store B' }),
      ];
      mockFetchUserContext.mockResolvedValue(agencyCtx);
      mockFetchAssignedStores.mockResolvedValue(createMockStoresResponse(stores));

      const { result } = renderHook(() => useAgency(), { wrapper });

      await waitFor(() => {
        expect(result.current.loading).toBe(false);
      });

      expect(result.current.isAgencyUser).toBe(true);
      expect(result.current.assignedStores).toHaveLength(2);
      expect(result.current.assignedStores[0].store_name).toBe('Store A');
      expect(mockFetchAssignedStores).toHaveBeenCalledOnce();
    });
  });

  // ---- switchStore ----
  describe('switchStore', () => {
    it('throws for non-agency users', async () => {
      mockFetchUserContext.mockResolvedValue(createMockUserContext());

      const { result } = renderHook(() => useAgency(), { wrapper });

      await waitFor(() => {
        expect(result.current.loading).toBe(false);
      });

      await expect(
        act(() => result.current.switchStore('tenant-2')),
      ).rejects.toThrow('Store switching is only available for agency users');
    });

    it('throws for unauthorized tenant', async () => {
      const agencyCtx = createMockAgencyUserContext({
        allowed_tenants: ['tenant-1', 'tenant-2'],
      });
      mockFetchUserContext.mockResolvedValue(agencyCtx);
      mockFetchAssignedStores.mockResolvedValue(createMockStoresResponse());

      const { result } = renderHook(() => useAgency(), { wrapper });

      await waitFor(() => {
        expect(result.current.loading).toBe(false);
      });

      await expect(
        act(() => result.current.switchStore('tenant-999')),
      ).rejects.toThrow('Access to this store is not authorized');
    });

    it('successfully switches store for authorized agency user', async () => {
      const agencyCtx = createMockAgencyUserContext({
        allowed_tenants: ['tenant-1', 'tenant-2'],
      });
      mockFetchUserContext.mockResolvedValue(agencyCtx);
      mockFetchAssignedStores.mockResolvedValue(
        createMockStoresResponse([
          createMockStore({ tenant_id: 'tenant-1' }),
          createMockStore({ tenant_id: 'tenant-2' }),
        ]),
      );
      mockRefreshTenantToken.mockResolvedValue({
        jwt_token: 'new-token',
        active_tenant_id: 'tenant-2',
        access_surface: 'external_app',
        access_expiring_at: null,
      });

      const { result } = renderHook(() => useAgency(), { wrapper });

      await waitFor(() => {
        expect(result.current.loading).toBe(false);
      });

      await act(async () => {
        await result.current.switchStore('tenant-2');
      });

      expect(result.current.activeTenantId).toBe('tenant-2');
      expect(mockRefreshTenantToken).toHaveBeenCalledWith(
        'tenant-2',
        ['tenant-1', 'tenant-2'],
      );
    });
  });

  // ---- canAccessStore ----
  describe('canAccessStore', () => {
    it('returns true for tenants in allowedTenants', async () => {
      mockFetchUserContext.mockResolvedValue(
        createMockAgencyUserContext({
          allowed_tenants: ['tenant-1', 'tenant-2'],
        }),
      );
      mockFetchAssignedStores.mockResolvedValue(createMockStoresResponse());

      const { result } = renderHook(() => useAgency(), { wrapper });

      await waitFor(() => {
        expect(result.current.loading).toBe(false);
      });

      expect(result.current.canAccessStore('tenant-1')).toBe(true);
      expect(result.current.canAccessStore('tenant-2')).toBe(true);
    });

    it('returns false for tenants not in allowedTenants', async () => {
      mockFetchUserContext.mockResolvedValue(
        createMockAgencyUserContext({
          allowed_tenants: ['tenant-1'],
        }),
      );
      mockFetchAssignedStores.mockResolvedValue(createMockStoresResponse());

      const { result } = renderHook(() => useAgency(), { wrapper });

      await waitFor(() => {
        expect(result.current.loading).toBe(false);
      });

      expect(result.current.canAccessStore('tenant-99')).toBe(false);
    });
  });

  // ---- Error state ----
  describe('error state', () => {
    it('sets error when fetchUserContext fails', async () => {
      mockFetchUserContext.mockRejectedValue(new Error('Network error'));

      const { result } = renderHook(() => useAgency(), { wrapper });

      await waitFor(() => {
        expect(result.current.loading).toBe(false);
      });

      expect(result.current.error).toBe('Network error');
    });

    it('sets generic error for non-Error exceptions', async () => {
      mockFetchUserContext.mockRejectedValue('string error');

      const { result } = renderHook(() => useAgency(), { wrapper });

      await waitFor(() => {
        expect(result.current.loading).toBe(false);
      });

      expect(result.current.error).toBe('Failed to initialize user context');
    });
  });

  // ---- useActiveStore ----
  describe('useActiveStore', () => {
    it('returns current store info when active tenant matches an assigned store', async () => {
      const store = createMockStore({ tenant_id: 'tenant-1', store_name: 'My Store' });
      mockFetchUserContext.mockResolvedValue(
        createMockAgencyUserContext({ tenant_id: 'tenant-1' }),
      );
      mockFetchAssignedStores.mockResolvedValue(createMockStoresResponse([store]));

      const { result } = renderHook(() => useActiveStore(), { wrapper });

      await waitFor(() => {
        expect(result.current.loading).toBe(false);
      });

      expect(result.current.store).not.toBeNull();
      expect(result.current.store?.store_name).toBe('My Store');
      expect(result.current.tenantId).toBe('tenant-1');
    });

    it('returns null store when no assigned store matches active tenant', async () => {
      mockFetchUserContext.mockResolvedValue(
        createMockAgencyUserContext({ tenant_id: 'tenant-99' }),
      );
      mockFetchAssignedStores.mockResolvedValue(
        createMockStoresResponse([createMockStore({ tenant_id: 'tenant-1' })]),
      );

      const { result } = renderHook(() => useActiveStore(), { wrapper });

      await waitFor(() => {
        expect(result.current.loading).toBe(false);
      });

      expect(result.current.store).toBeNull();
      expect(result.current.tenantId).toBe('tenant-99');
    });
  });

  // ---- useIsAgencyUser ----
  describe('useIsAgencyUser', () => {
    it('returns true for agency users', async () => {
      mockFetchUserContext.mockResolvedValue(createMockAgencyUserContext());
      mockFetchAssignedStores.mockResolvedValue(createMockStoresResponse());

      const { result } = renderHook(() => useIsAgencyUser(), { wrapper });

      await waitFor(() => {
        expect(result.current).toBe(true);
      });
    });

    it('returns false for merchant users', async () => {
      mockFetchUserContext.mockResolvedValue(createMockUserContext());

      const { result } = renderHook(() => useIsAgencyUser(), { wrapper });

      await waitFor(() => {
        expect(result.current).toBe(false);
      });
    });
  });

  // ---- Backend down ----
  describe('backend down', () => {
    it('sets error and stops loading when backend is down', async () => {
      mockIsBackendDown.mockReturnValue(true);

      const { result } = renderHook(() => useAgency(), { wrapper });

      await waitFor(() => {
        expect(result.current.loading).toBe(false);
      });

      expect(result.current.error).toBe('Backend unavailable — waiting for recovery');
      expect(mockFetchUserContext).not.toHaveBeenCalled();
    });
  });
});
