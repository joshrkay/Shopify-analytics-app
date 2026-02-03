/**
 * Multi-Tenant Error Boundary Integration Tests
 *
 * Tests that error boundaries work correctly in multi-tenant scenarios:
 * - Errors are isolated to the tenant session that triggered them
 * - Tenant context is preserved after error recovery
 * - Different tenant configurations don't interfere with each other
 * - Store switching works correctly after error recovery
 */

import React, { useState } from 'react';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { AppProvider } from '@shopify/polaris';
import { BrowserRouter } from 'react-router-dom';

import { ErrorBoundary } from '../components/ErrorBoundary';
import {
  PageErrorFallback,
  ComponentErrorFallback,
} from '../components/ErrorFallback';

// Mock translations
const mockTranslations = {
  Polaris: {
    Common: { ok: 'OK', cancel: 'Cancel' },
  },
};

// Simulated tenant context
interface TenantContext {
  tenantId: string;
  storeName: string;
  plan: 'free' | 'growth' | 'enterprise';
}

const TenantContext = React.createContext<TenantContext | null>(null);

function TenantProvider({
  children,
  tenant,
}: {
  children: React.ReactNode;
  tenant: TenantContext;
}) {
  return (
    <TenantContext.Provider value={tenant}>{children}</TenantContext.Provider>
  );
}

function useTenant() {
  const context = React.useContext(TenantContext);
  if (!context) {
    throw new Error('useTenant must be used within TenantProvider');
  }
  return context;
}

// Component that displays tenant info
function TenantInfo() {
  const tenant = useTenant();
  return (
    <div data-testid="tenant-info">
      <span data-testid="tenant-id">{tenant.tenantId}</span>
      <span data-testid="store-name">{tenant.storeName}</span>
      <span data-testid="plan">{tenant.plan}</span>
    </div>
  );
}

// Component that throws based on tenant
function TenantAwareComponent({
  shouldThrowForTenant,
}: {
  shouldThrowForTenant?: string;
}) {
  const tenant = useTenant();

  if (shouldThrowForTenant && tenant.tenantId === shouldThrowForTenant) {
    throw new Error(`Error for tenant: ${tenant.tenantId}`);
  }

  return (
    <div data-testid="tenant-content">
      <TenantInfo />
      <span data-testid="content-status">Content loaded successfully</span>
    </div>
  );
}

// Component that can trigger errors on demand
function InteractiveTenantComponent() {
  const tenant = useTenant();
  const [shouldThrow, setShouldThrow] = useState(false);

  if (shouldThrow) {
    throw new Error(`User-triggered error for tenant: ${tenant.tenantId}`);
  }

  return (
    <div data-testid="interactive-tenant-content">
      <TenantInfo />
      <button
        data-testid="trigger-error-btn"
        onClick={() => setShouldThrow(true)}
      >
        Trigger Error
      </button>
    </div>
  );
}

// Full app simulation with error boundary
function TenantApp({
  tenant,
  shouldThrowForTenant,
  children,
}: {
  tenant: TenantContext;
  shouldThrowForTenant?: string;
  children?: React.ReactNode;
}) {
  return (
    <AppProvider i18n={mockTranslations as any}>
      <BrowserRouter>
        <TenantProvider tenant={tenant}>
          <ErrorBoundary
            fallbackRender={({ error, errorInfo, resetErrorBoundary }) => (
              <PageErrorFallback
                error={error}
                errorInfo={errorInfo}
                resetErrorBoundary={resetErrorBoundary}
                pageName={`${tenant.storeName} Dashboard`}
              />
            )}
          >
            {children || (
              <TenantAwareComponent
                shouldThrowForTenant={shouldThrowForTenant}
              />
            )}
          </ErrorBoundary>
        </TenantProvider>
      </BrowserRouter>
    </AppProvider>
  );
}

// Helper to render with tenant
const renderWithTenant = (
  ui: React.ReactElement,
  tenant: TenantContext = { tenantId: 'tenant-1', storeName: 'Test Store', plan: 'growth' }
) => {
  return render(
    <AppProvider i18n={mockTranslations as any}>
      <BrowserRouter>
        <TenantProvider tenant={tenant}>{ui}</TenantProvider>
      </BrowserRouter>
    </AppProvider>
  );
};

describe('Multi-Tenant Error Boundary Tests', () => {
  let consoleSpy: ReturnType<typeof vi.spyOn>;

  beforeEach(() => {
    consoleSpy = vi.spyOn(console, 'error').mockImplementation(() => {});
  });

  afterEach(() => {
    consoleSpy.mockRestore();
  });

  describe('error isolation between tenants', () => {
    it('error in tenant A does not affect tenant B rendered separately', () => {
      const tenantA: TenantContext = {
        tenantId: 'tenant-a',
        storeName: 'Store A',
        plan: 'growth',
      };
      const tenantB: TenantContext = {
        tenantId: 'tenant-b',
        storeName: 'Store B',
        plan: 'enterprise',
      };

      // Render both tenants - A will error, B should work
      const { container: containerA } = render(
        <TenantApp tenant={tenantA} shouldThrowForTenant="tenant-a" />
      );

      const { container: containerB } = render(
        <TenantApp tenant={tenantB} shouldThrowForTenant="tenant-a" />
      );

      // Tenant A should show error fallback
      expect(
        within(containerA).getByText('Store A Dashboard encountered an error')
      ).toBeInTheDocument();

      // Tenant B should show content normally
      expect(
        within(containerB).getByTestId('tenant-content')
      ).toBeInTheDocument();
      expect(within(containerB).getByTestId('tenant-id').textContent).toBe(
        'tenant-b'
      );
      expect(
        within(containerB).getByText('Content loaded successfully')
      ).toBeInTheDocument();
    });

    it('each tenant maintains its own error state', async () => {
      const user = userEvent.setup();

      const tenantA: TenantContext = {
        tenantId: 'tenant-a',
        storeName: 'Store A',
        plan: 'growth',
      };
      const tenantB: TenantContext = {
        tenantId: 'tenant-b',
        storeName: 'Store B',
        plan: 'enterprise',
      };

      // Render both with interactive components
      const { container: containerA } = render(
        <TenantApp tenant={tenantA}>
          <InteractiveTenantComponent />
        </TenantApp>
      );

      const { container: containerB } = render(
        <TenantApp tenant={tenantB}>
          <InteractiveTenantComponent />
        </TenantApp>
      );

      // Both should start with content
      expect(
        within(containerA).getByTestId('interactive-tenant-content')
      ).toBeInTheDocument();
      expect(
        within(containerB).getByTestId('interactive-tenant-content')
      ).toBeInTheDocument();

      // Trigger error only in tenant A
      await user.click(within(containerA).getByTestId('trigger-error-btn'));

      // Tenant A should show error
      expect(
        within(containerA).getByText('Store A Dashboard encountered an error')
      ).toBeInTheDocument();

      // Tenant B should still show content
      expect(
        within(containerB).getByTestId('interactive-tenant-content')
      ).toBeInTheDocument();
      expect(within(containerB).getByTestId('tenant-id').textContent).toBe(
        'tenant-b'
      );
    });
  });

  describe('tenant context preservation', () => {
    it('preserves tenant context after error recovery', async () => {
      const user = userEvent.setup();

      const tenant: TenantContext = {
        tenantId: 'tenant-xyz',
        storeName: 'XYZ Store',
        plan: 'enterprise',
      };

      // Start with an error, then recover using interactive component
      render(
        <TenantApp tenant={tenant}>
          <InteractiveTenantComponent />
        </TenantApp>
      );

      // Should show content initially with tenant info
      expect(screen.getByTestId('interactive-tenant-content')).toBeInTheDocument();
      expect(screen.getByTestId('tenant-id').textContent).toBe('tenant-xyz');
      expect(screen.getByTestId('store-name').textContent).toBe('XYZ Store');

      // Trigger error
      await user.click(screen.getByTestId('trigger-error-btn'));

      // Should show error
      await waitFor(() => {
        expect(
          screen.getByText('XYZ Store Dashboard encountered an error')
        ).toBeInTheDocument();
      });

      // Click retry
      await user.click(screen.getByText('Try again'));

      // After recovery, tenant context should be preserved
      await waitFor(() => {
        expect(screen.getByTestId('interactive-tenant-content')).toBeInTheDocument();
      });

      expect(screen.getByTestId('tenant-id').textContent).toBe('tenant-xyz');
      expect(screen.getByTestId('store-name').textContent).toBe('XYZ Store');
      expect(screen.getByTestId('plan').textContent).toBe('enterprise');
    });

    it('error fallback displays correct tenant information', () => {
      const tenant: TenantContext = {
        tenantId: 'tenant-123',
        storeName: 'My Awesome Store',
        plan: 'growth',
      };

      render(<TenantApp tenant={tenant} shouldThrowForTenant="tenant-123" />);

      // Fallback should show tenant-specific message
      expect(
        screen.getByText('My Awesome Store Dashboard encountered an error')
      ).toBeInTheDocument();
    });
  });

  describe('different tenant configurations', () => {
    it('handles errors correctly for different plan tiers', () => {
      const freeTenant: TenantContext = {
        tenantId: 'free-tenant',
        storeName: 'Free Store',
        plan: 'free',
      };
      const enterpriseTenant: TenantContext = {
        tenantId: 'enterprise-tenant',
        storeName: 'Enterprise Store',
        plan: 'enterprise',
      };

      // Both error, both should show fallback with their store name
      const { container: freeContainer } = render(
        <TenantApp tenant={freeTenant} shouldThrowForTenant="free-tenant" />
      );

      const { container: enterpriseContainer } = render(
        <TenantApp
          tenant={enterpriseTenant}
          shouldThrowForTenant="enterprise-tenant"
        />
      );

      expect(
        within(freeContainer).getByText(
          'Free Store Dashboard encountered an error'
        )
      ).toBeInTheDocument();

      expect(
        within(enterpriseContainer).getByText(
          'Enterprise Store Dashboard encountered an error'
        )
      ).toBeInTheDocument();
    });

    it('error in one plan tier does not affect other tiers', () => {
      const freeTenant: TenantContext = {
        tenantId: 'free-tenant',
        storeName: 'Free Store',
        plan: 'free',
      };
      const enterpriseTenant: TenantContext = {
        tenantId: 'enterprise-tenant',
        storeName: 'Enterprise Store',
        plan: 'enterprise',
      };

      // Only free tenant errors
      const { container: freeContainer } = render(
        <TenantApp tenant={freeTenant} shouldThrowForTenant="free-tenant" />
      );

      const { container: enterpriseContainer } = render(
        <TenantApp tenant={enterpriseTenant} />
      );

      // Free shows error
      expect(
        within(freeContainer).getByText(
          'Free Store Dashboard encountered an error'
        )
      ).toBeInTheDocument();

      // Enterprise works fine
      expect(
        within(enterpriseContainer).getByTestId('tenant-content')
      ).toBeInTheDocument();
      expect(
        within(enterpriseContainer).getByTestId('plan').textContent
      ).toBe('enterprise');
    });
  });

  describe('component-level error boundaries with tenant context', () => {
    it('component error does not crash entire tenant page', async () => {
      const user = userEvent.setup();
      const tenant: TenantContext = {
        tenantId: 'tenant-comp',
        storeName: 'Component Test Store',
        plan: 'growth',
      };

      function PageWithWidgets() {
        const tenantCtx = useTenant();
        const [widgetError, setWidgetError] = useState(false);

        return (
          <div>
            <h1 data-testid="page-header">{tenantCtx.storeName} Dashboard</h1>

            {/* Widget 1 - will error */}
            <ErrorBoundary
              fallbackRender={({ error, resetErrorBoundary }) => (
                <ComponentErrorFallback
                  error={error}
                  resetErrorBoundary={resetErrorBoundary}
                  componentName="Sales Widget"
                />
              )}
            >
              {widgetError ? (
                <WidgetThatThrows />
              ) : (
                <div data-testid="widget-1">
                  <span>Sales Widget</span>
                  <button
                    data-testid="break-widget"
                    onClick={() => setWidgetError(true)}
                  >
                    Break Widget
                  </button>
                </div>
              )}
            </ErrorBoundary>

            {/* Widget 2 - should keep working */}
            <div data-testid="widget-2">
              <span>Orders Widget - Tenant: {tenantCtx.tenantId}</span>
            </div>
          </div>
        );
      }

      function WidgetThatThrows() {
        throw new Error('Widget crashed');
      }

      render(
        <AppProvider i18n={mockTranslations as any}>
          <BrowserRouter>
            <TenantProvider tenant={tenant}>
              <PageWithWidgets />
            </TenantProvider>
          </BrowserRouter>
        </AppProvider>
      );

      // Initially both widgets work
      expect(screen.getByTestId('page-header').textContent).toBe(
        'Component Test Store Dashboard'
      );
      expect(screen.getByTestId('widget-1')).toBeInTheDocument();
      expect(screen.getByTestId('widget-2')).toBeInTheDocument();

      // Break widget 1
      await user.click(screen.getByTestId('break-widget'));

      // Page header still visible
      expect(screen.getByTestId('page-header')).toBeInTheDocument();

      // Widget 1 shows error fallback
      expect(screen.getByText('Sales Widget failed to load')).toBeInTheDocument();

      // Widget 2 still works with tenant context
      expect(screen.getByTestId('widget-2')).toBeInTheDocument();
      expect(screen.getByTestId('widget-2').textContent).toContain('tenant-comp');
    });
  });

  describe('error callbacks with tenant information', () => {
    it('onError callback receives error with tenant context available', () => {
      const onError = vi.fn();
      const tenant: TenantContext = {
        tenantId: 'callback-tenant',
        storeName: 'Callback Store',
        plan: 'growth',
      };

      function ComponentWithCallback() {
        return (
          <AppProvider i18n={mockTranslations as any}>
            <BrowserRouter>
              <TenantProvider tenant={tenant}>
                <ErrorBoundary
                  onError={onError}
                  fallbackRender={({ error, resetErrorBoundary }) => (
                    <PageErrorFallback
                      error={error}
                      resetErrorBoundary={resetErrorBoundary}
                    />
                  )}
                >
                  <TenantAwareComponent shouldThrowForTenant="callback-tenant" />
                </ErrorBoundary>
              </TenantProvider>
            </BrowserRouter>
          </AppProvider>
        );
      }

      render(<ComponentWithCallback />);

      expect(onError).toHaveBeenCalledTimes(1);
      expect(onError).toHaveBeenCalledWith(
        expect.objectContaining({
          message: 'Error for tenant: callback-tenant',
        }),
        expect.objectContaining({
          componentStack: expect.any(String),
        })
      );
    });
  });

  describe('concurrent tenant sessions', () => {
    it('simulates multiple tenant sessions with independent error states', async () => {
      const user = userEvent.setup();

      // Create 3 tenants
      const tenants: TenantContext[] = [
        { tenantId: 'shop-1', storeName: 'Shop One', plan: 'free' },
        { tenantId: 'shop-2', storeName: 'Shop Two', plan: 'growth' },
        { tenantId: 'shop-3', storeName: 'Shop Three', plan: 'enterprise' },
      ];

      // Render all three
      const containers = tenants.map((tenant) =>
        render(
          <TenantApp key={tenant.tenantId} tenant={tenant}>
            <InteractiveTenantComponent />
          </TenantApp>
        )
      );

      // All should be working
      containers.forEach((result, idx) => {
        expect(
          within(result.container).getByTestId('interactive-tenant-content')
        ).toBeInTheDocument();
        expect(
          within(result.container).getByTestId('tenant-id').textContent
        ).toBe(tenants[idx].tenantId);
      });

      // Trigger error only in shop-2 (middle one)
      await user.click(
        within(containers[1].container).getByTestId('trigger-error-btn')
      );

      // Shop 1 still works
      expect(
        within(containers[0].container).getByTestId('interactive-tenant-content')
      ).toBeInTheDocument();

      // Shop 2 shows error
      expect(
        within(containers[1].container).getByText(
          'Shop Two Dashboard encountered an error'
        )
      ).toBeInTheDocument();

      // Shop 3 still works
      expect(
        within(containers[2].container).getByTestId('interactive-tenant-content')
      ).toBeInTheDocument();
    });
  });
});

describe('Error Recovery with Tenant State', () => {
  let consoleSpy: ReturnType<typeof vi.spyOn>;

  beforeEach(() => {
    consoleSpy = vi.spyOn(console, 'error').mockImplementation(() => {});
  });

  afterEach(() => {
    consoleSpy.mockRestore();
  });

  it('tenant can recover after error and retry multiple times', async () => {
    const user = userEvent.setup();
    const tenant: TenantContext = {
      tenantId: 'resilient-tenant',
      storeName: 'Resilient Store',
      plan: 'enterprise',
    };

    // Use InteractiveTenantComponent which already handles error/recovery
    render(
      <TenantApp tenant={tenant}>
        <InteractiveTenantComponent />
      </TenantApp>
    );

    // Initial state - should show content
    expect(screen.getByTestId('interactive-tenant-content')).toBeInTheDocument();
    expect(screen.getByTestId('tenant-id').textContent).toBe('resilient-tenant');

    // First error cycle
    await user.click(screen.getByTestId('trigger-error-btn'));

    await waitFor(() => {
      expect(
        screen.getByText('Resilient Store Dashboard encountered an error')
      ).toBeInTheDocument();
    });

    // Recover
    await user.click(screen.getByText('Try again'));

    await waitFor(() => {
      expect(screen.getByTestId('interactive-tenant-content')).toBeInTheDocument();
    });

    // Tenant context should be preserved
    expect(screen.getByTestId('tenant-id').textContent).toBe('resilient-tenant');

    // Second error cycle
    await user.click(screen.getByTestId('trigger-error-btn'));

    await waitFor(() => {
      expect(
        screen.getByText('Resilient Store Dashboard encountered an error')
      ).toBeInTheDocument();
    });

    await user.click(screen.getByText('Try again'));

    await waitFor(() => {
      expect(screen.getByTestId('interactive-tenant-content')).toBeInTheDocument();
    });

    // Still have tenant context after multiple recoveries
    expect(screen.getByTestId('tenant-id').textContent).toBe('resilient-tenant');
  });
});
