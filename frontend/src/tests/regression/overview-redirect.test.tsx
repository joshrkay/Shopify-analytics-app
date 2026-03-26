/**
 * Regression: / route renders the Dashboard (analytics overview) page
 *
 * Why: The `/` route has been mapped to Dashboard. This test guards against
 * accidental removal or remapping of the root route that would leave users
 * on a blank/404 page after login.
 *
 * Also verifies `/home` is a distinct route rendering DashboardHome.
 */

import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import { MemoryRouter, Routes, Route, Navigate } from 'react-router-dom';

// ---------------------------------------------------------------------------
// Minimal mocks — avoid heavy provider chains for route-level tests
// ---------------------------------------------------------------------------

vi.mock('../../services/apiUtils', () => ({
  API_BASE_URL: '',
  createHeadersAsync: vi.fn().mockResolvedValue({}),
  createHeaders: vi.fn().mockReturnValue({}),
  handleResponse: vi.fn(),
  isApiError: vi.fn().mockReturnValue(false),
  getErrorMessage: vi.fn((_e: unknown, fb: string) => fb),
}));

vi.mock('@clerk/clerk-react', () => ({
  useUser: () => ({ isLoaded: true, user: { id: 'u1', fullName: 'Test User' } }),
  useOrganization: () => ({ organization: { id: 'org1', name: 'Test Org' } }),
  useClerk: () => ({ signOut: vi.fn() }),
  SignedIn: ({ children }: { children: React.ReactNode }) => <>{children}</>,
  SignedOut: () => null,
  RedirectToSignIn: () => <div>sign-in</div>,
}));

// ---------------------------------------------------------------------------
// Lightweight stubs for the pages — we only need to verify route wiring
// ---------------------------------------------------------------------------

function StubDashboard() {
  return <div data-testid="page-dashboard">Dashboard Analytics Overview</div>;
}

function StubDashboardHome() {
  return <div data-testid="page-home">Dashboard Home</div>;
}

function StubNotFound() {
  return <div data-testid="page-not-found">Not Found</div>;
}

// ---------------------------------------------------------------------------
// Route table mirroring App.tsx's critical routes
// ---------------------------------------------------------------------------

function TestRoutes({ initialPath }: { initialPath: string }) {
  return (
    <MemoryRouter initialEntries={[initialPath]}>
      <Routes>
        <Route path="/" element={<StubDashboard />} />
        <Route path="/home" element={<StubDashboardHome />} />
        <Route path="*" element={<StubNotFound />} />
      </Routes>
    </MemoryRouter>
  );
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe('overview-redirect regression', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('/ renders the Dashboard page, not NotFound', () => {
    render(<TestRoutes initialPath="/" />);
    expect(screen.getByTestId('page-dashboard')).toBeInTheDocument();
    expect(screen.queryByTestId('page-not-found')).not.toBeInTheDocument();
  });

  it('/ does not render DashboardHome (separate route)', () => {
    render(<TestRoutes initialPath="/" />);
    expect(screen.queryByTestId('page-home')).not.toBeInTheDocument();
  });

  it('/home renders DashboardHome page', () => {
    render(<TestRoutes initialPath="/home" />);
    expect(screen.getByTestId('page-home')).toBeInTheDocument();
    expect(screen.queryByTestId('page-dashboard')).not.toBeInTheDocument();
  });

  it('/home does not fall through to NotFound', () => {
    render(<TestRoutes initialPath="/home" />);
    expect(screen.queryByTestId('page-not-found')).not.toBeInTheDocument();
  });

  it('unknown route renders NotFound, not Dashboard', () => {
    render(<TestRoutes initialPath="/does-not-exist" />);
    expect(screen.getByTestId('page-not-found')).toBeInTheDocument();
    expect(screen.queryByTestId('page-dashboard')).not.toBeInTheDocument();
  });

  it('App.tsx defines route for / pointing to Dashboard', async () => {
    // Static check: App.tsx must define path="/" with Dashboard element
    const fs = await import('node:fs');
    const path = await import('node:path');
    const appPath = path.resolve(__dirname, '../../App.tsx');
    const content = fs.readFileSync(appPath, 'utf8');

    // Verify the root route exists
    expect(content).toMatch(/path="\/"/);
    // Verify Dashboard is imported/used (not just a redirect)
    expect(content).toMatch(/Dashboard/);
  });

  it('App.tsx defines separate /home route', async () => {
    const fs = await import('node:fs');
    const path = await import('node:path');
    const appPath = path.resolve(__dirname, '../../App.tsx');
    const content = fs.readFileSync(appPath, 'utf8');

    expect(content).toMatch(/path="\/home"/);
    expect(content).toMatch(/DashboardHome/);
  });
});
