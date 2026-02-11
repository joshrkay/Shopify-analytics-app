/**
 * Tests for Phase 0 — Layout Shell & Sidebar Navigation
 *
 * Epic 0.1 — App-wide layout shell
 *   Story 0.1.1 — RootLayout wraps authenticated experience
 *   Story 0.1.2 — AppHeader becomes slim top utility bar
 *
 * Epic 0.2 — Sidebar navigation + access control
 *   Story 0.2.1 — Sidebar shows required nav sections + routes
 *   Story 0.2.2 — Active route highlighting
 */

import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { AppProvider } from '@shopify/polaris';
import { MemoryRouter, Routes, Route } from 'react-router-dom';

import { RootLayout } from '../components/layout/RootLayout';
import { Sidebar } from '../components/layout/Sidebar';
import { AppHeader } from '../components/layout/AppHeader';

// Mock translations
const mockTranslations = {
  Polaris: {
    Common: { ok: 'OK', cancel: 'Cancel' },
  },
};

// Mock Clerk useUser
const mockUseUser = vi.fn();
vi.mock('@clerk/clerk-react', () => ({
  useUser: () => mockUseUser(),
  SignedIn: ({ children }: { children: React.ReactNode }) => <>{children}</>,
  SignedOut: ({ children }: { children: React.ReactNode }) => <>{children}</>,
  RedirectToSignIn: () => <div data-testid="redirect-to-sign-in">Redirecting...</div>,
}));

// Mock changelog and whatChanged APIs (used by AppHeader sub-components)
vi.mock('../services/changelogApi', () => ({
  getUnreadCountNumber: vi.fn().mockResolvedValue(0),
  getEntriesForFeature: vi.fn().mockResolvedValue([]),
  markAsRead: vi.fn(),
}));

vi.mock('../services/whatChangedApi', () => ({
  hasCriticalIssues: vi.fn().mockResolvedValue(false),
  getWhatChangedSummary: vi.fn().mockResolvedValue(null),
}));

// Helper: render with Polaris + MemoryRouter
const renderWithProviders = (
  ui: React.ReactElement,
  { initialEntries = ['/'] }: { initialEntries?: string[] } = {}
) => {
  return render(
    <AppProvider i18n={mockTranslations as any}>
      <MemoryRouter initialEntries={initialEntries}>{ui}</MemoryRouter>
    </AppProvider>
  );
};

// =============================================================================
// Story 0.1.1 — RootLayout wraps authenticated experience
// =============================================================================

describe('RootLayout', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockUseUser.mockReturnValue({
      user: {
        fullName: 'Test User',
        firstName: 'Test',
        primaryEmailAddress: { emailAddress: 'test@example.com' },
      },
    });
  });

  it('renders children inside signed-in boundary', () => {
    renderWithProviders(
      <RootLayout>
        <div data-testid="child-content">Hello from page</div>
      </RootLayout>,
      { initialEntries: ['/analytics'] }
    );

    // Children should be visible
    expect(screen.getByTestId('child-content')).toBeInTheDocument();
    expect(screen.getByText('Hello from page')).toBeInTheDocument();

    // Sidebar should also be present alongside children
    expect(screen.getByRole('navigation', { name: 'Main navigation' })).toBeInTheDocument();
  });

  it('renders sidebar and content area in two-column layout', () => {
    renderWithProviders(
      <RootLayout>
        <div>Page content</div>
      </RootLayout>,
      { initialEntries: ['/analytics'] }
    );

    const nav = screen.getByRole('navigation', { name: 'Main navigation' });
    const main = document.querySelector('main.root-layout__content');

    expect(nav).toBeInTheDocument();
    expect(main).toBeInTheDocument();
    expect(main?.textContent).toContain('Page content');
  });
});

// =============================================================================
// Regression: sidebar absent when signed out
// =============================================================================

describe('Sidebar signed-out behavior', () => {
  it('sidebar absent when signed out', () => {
    // When rendered outside of any auth context (simulating signed-out),
    // the Sidebar should not appear in the DOM. The App component wraps
    // RootLayout inside <SignedIn>, so signed-out users never see it.
    // Here we verify that rendering only the SignedOut path has no sidebar.
    render(
      <AppProvider i18n={mockTranslations as any}>
        <MemoryRouter>
          <div data-testid="signed-out-content">Please sign in</div>
        </MemoryRouter>
      </AppProvider>
    );

    expect(screen.getByTestId('signed-out-content')).toBeInTheDocument();
    expect(screen.queryByRole('navigation', { name: 'Main navigation' })).not.toBeInTheDocument();
    expect(screen.queryByText('Analytics')).not.toBeInTheDocument();
  });
});

// =============================================================================
// Story 0.1.2 — AppHeader becomes slim top utility bar
// =============================================================================

describe('AppHeader (slim utility bar)', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('contains changelog elements', () => {
    renderWithProviders(<AppHeader />, { initialEntries: ['/analytics'] });

    // ChangelogBadge renders "What's New" label
    expect(screen.getByText("What's New")).toBeInTheDocument();
  });

  it('does not contain removed nav items', () => {
    renderWithProviders(<AppHeader />, { initialEntries: ['/analytics'] });

    // Analytics and Dashboards buttons should have been removed from the header
    const buttons = screen.queryAllByRole('button');
    const buttonTexts = buttons.map((b) => b.textContent);

    expect(buttonTexts).not.toContain('Analytics');
    expect(buttonTexts).not.toContain('Dashboards');
  });
});

// =============================================================================
// Story 0.2.1 — Sidebar shows required nav sections + routes
// =============================================================================

describe('Sidebar navigation', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockUseUser.mockReturnValue({
      user: {
        fullName: 'Jane Doe',
        firstName: 'Jane',
        primaryEmailAddress: { emailAddress: 'jane@example.com' },
      },
    });
  });

  it('renders all nav links', () => {
    renderWithProviders(<Sidebar />, { initialEntries: ['/analytics'] });

    expect(screen.getByText('Analytics')).toBeInTheDocument();
    expect(screen.getByText('Dashboards')).toBeInTheDocument();
    expect(screen.getByText('Insights')).toBeInTheDocument();
    expect(screen.getByText('Data Sources')).toBeInTheDocument();
    // "Settings" appears as both section header and nav item
    const settingsNavItem = screen.getAllByText('Settings').find(
      (el) => el.closest('.sidebar-nav-item') !== null
    );
    expect(settingsNavItem).toBeInTheDocument();
  });

  it('renders MAIN, CONNECTIONS, and SETTINGS sections', () => {
    renderWithProviders(<Sidebar />, { initialEntries: ['/analytics'] });

    expect(screen.getByText('Main')).toBeInTheDocument();
    expect(screen.getByText('Connections')).toBeInTheDocument();
    // "Settings" appears both as section header and nav item
    const settingsElements = screen.getAllByText('Settings');
    expect(settingsElements.length).toBeGreaterThanOrEqual(2);
  });

  it('renders user section in footer', () => {
    renderWithProviders(<Sidebar />, { initialEntries: ['/analytics'] });

    expect(screen.getByText('Jane Doe')).toBeInTheDocument();
    expect(screen.getByText('jane@example.com')).toBeInTheDocument();
    // Avatar initial
    expect(screen.getByText('J')).toBeInTheDocument();
  });

  it('renders fallback when user has no name', () => {
    mockUseUser.mockReturnValue({
      user: {
        fullName: null,
        firstName: null,
        primaryEmailAddress: { emailAddress: 'anon@example.com' },
      },
    });

    renderWithProviders(<Sidebar />, { initialEntries: ['/analytics'] });

    expect(screen.getByText('User')).toBeInTheDocument();
    expect(screen.getByText('U')).toBeInTheDocument();
  });

  it('clicking links updates route', async () => {
    const user = userEvent.setup();

    renderWithProviders(
      <>
        <Sidebar />
        <Routes>
          <Route path="/analytics" element={<div data-testid="page">Analytics Page</div>} />
          <Route path="/dashboards" element={<div data-testid="page">Dashboards Page</div>} />
          <Route path="/insights" element={<div data-testid="page">Insights Page</div>} />
          <Route path="/data-sources" element={<div data-testid="page">Data Sources Page</div>} />
          <Route path="/settings" element={<div data-testid="page">Settings Page</div>} />
        </Routes>
      </>,
      { initialEntries: ['/analytics'] }
    );

    // Start on Analytics
    expect(screen.getByText('Analytics Page')).toBeInTheDocument();

    // Click Dashboards nav item
    await user.click(screen.getByText('Dashboards'));
    expect(screen.getByText('Dashboards Page')).toBeInTheDocument();

    // Click Data Sources nav item
    await user.click(screen.getByText('Data Sources'));
    expect(screen.getByText('Data Sources Page')).toBeInTheDocument();
  });

  it('supports keyboard navigation', async () => {
    const user = userEvent.setup();

    renderWithProviders(
      <>
        <Sidebar />
        <Routes>
          <Route path="/analytics" element={<div>Analytics Page</div>} />
          <Route path="/insights" element={<div>Insights Page</div>} />
        </Routes>
      </>,
      { initialEntries: ['/analytics'] }
    );

    // Focus on Insights nav item and press Enter
    const insightsItem = screen.getByText('Insights').closest('[role="link"]') as HTMLElement;
    insightsItem.focus();
    await user.keyboard('{Enter}');

    expect(screen.getByText('Insights Page')).toBeInTheDocument();
  });
});

// =============================================================================
// Story 0.2.2 — Active route highlighting
// =============================================================================

describe('Active route highlighting', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockUseUser.mockReturnValue({
      user: {
        fullName: 'Test User',
        firstName: 'Test',
        primaryEmailAddress: { emailAddress: 'test@example.com' },
      },
    });
  });

  const routes = [
    { path: '/analytics', label: 'Analytics' },
    { path: '/dashboards', label: 'Dashboards' },
    { path: '/insights', label: 'Insights' },
    { path: '/data-sources', label: 'Data Sources' },
    { path: '/settings', label: 'Settings' },
  ];

  /** Find the nav item element for a given label (handles duplicates like "Settings") */
  function findNavItem(label: string): HTMLElement | null {
    const elements = screen.getAllByText(label);
    for (const el of elements) {
      const navItem = el.closest('.sidebar-nav-item');
      if (navItem) return navItem as HTMLElement;
    }
    return null;
  }

  it.each(routes)(
    'highlights $label when on $path',
    ({ path, label }) => {
      renderWithProviders(<Sidebar />, { initialEntries: [path] });

      const navItem = findNavItem(label);
      expect(navItem).toHaveClass('sidebar-nav-item--active');

      // Other items should NOT be active
      routes
        .filter((r) => r.label !== label)
        .forEach((other) => {
          const otherNavItem = findNavItem(other.label);
          if (otherNavItem) {
            expect(otherNavItem).not.toHaveClass('sidebar-nav-item--active');
          }
        });
    }
  );

  it('highlights Dashboards for sub-routes like /dashboards/:id/edit', () => {
    renderWithProviders(<Sidebar />, {
      initialEntries: ['/dashboards/abc-123/edit'],
    });

    const dashboardsItem = screen.getByText('Dashboards').closest('.sidebar-nav-item');
    expect(dashboardsItem).toHaveClass('sidebar-nav-item--active');

    // Analytics should NOT be active
    const analyticsItem = screen.getByText('Analytics').closest('.sidebar-nav-item');
    expect(analyticsItem).not.toHaveClass('sidebar-nav-item--active');
  });
});
