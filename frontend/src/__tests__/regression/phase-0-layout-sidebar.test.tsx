/**
 * Layout shell regression — production uses `Root` (Tailwind sidebar).
 */

import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import { AppProvider } from '@shopify/polaris';
import { MemoryRouter, Routes, Route } from 'react-router-dom';

import { Root } from '../../components/layout/Root';

const mockTranslations = {
  Polaris: {
    Common: { ok: 'OK', cancel: 'Cancel' },
  },
};

const mockUseUser = vi.fn();
vi.mock('@clerk/clerk-react', () => ({
  useUser: () => mockUseUser(),
  useClerk: () => ({ signOut: vi.fn() }),
  SignedIn: ({ children }: { children: React.ReactNode }) => <>{children}</>,
  SignedOut: ({ children }: { children: React.ReactNode }) => <>{children}</>,
  SignIn: () => <div data-testid="sign-in" />,
  SignUp: () => <div data-testid="sign-up" />,
}));

function renderShell(initialEntries = ['/']) {
  mockUseUser.mockReturnValue({
    user: {
      fullName: 'Test User',
      firstName: 'Test',
      primaryEmailAddress: { emailAddress: 'test@example.com' },
      imageUrl: null,
    },
  });
  return render(
    <AppProvider i18n={mockTranslations as Record<string, unknown>}>
      <MemoryRouter initialEntries={initialEntries}>
        <Routes>
          <Route element={<Root />}>
            <Route path="/" element={<div>Home</div>} />
            <Route path="/attribution" element={<div>Attr</div>} />
          </Route>
        </Routes>
      </MemoryRouter>
    </AppProvider>,
  );
}

describe('Phase 0 — Root layout shell', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders Markinsight branding and primary nav', () => {
    renderShell(['/']);
    expect(screen.getAllByText('Markinsight').length).toBeGreaterThan(0);
    expect(screen.getByText('Overview')).toBeInTheDocument();
    expect(screen.getByText('Attribution')).toBeInTheDocument();
    expect(screen.getByText('Google Ads')).toBeInTheDocument();
  });

});
