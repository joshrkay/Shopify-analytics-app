/**
 * Mock replacement for @clerk/clerk-react
 *
 * Provides stub implementations of all Clerk hooks and components
 * used throughout the app, returning mock user/org data.
 */
import React from 'react';

const mockUser = {
  id: 'user_mock',
  fullName: 'Demo User',
  firstName: 'Demo',
  lastName: 'User',
  primaryEmailAddress: { emailAddress: 'demo@markinsight.net' },
  imageUrl: '',
  organizationMemberships: [{
    id: 'orgmem_mock',
    organization: { id: 'org_demo', name: 'Demo Store', slug: 'demo-store' },
    role: 'admin',
  }],
};

const mockOrganization = {
  id: 'org_demo',
  name: 'Demo Store',
  slug: 'demo-store',
};

export function useUser() {
  return { user: mockUser, isLoaded: true, isSignedIn: true };
}

export function useClerk() {
  return {
    signOut: async () => {},
    openUserProfile: () => {},
    openOrganizationProfile: () => {},
    session: { id: 'sess_mock', getToken: async () => 'mock-token' },
  };
}

export function useAuth() {
  return {
    isLoaded: true,
    isSignedIn: true,
    userId: 'user_mock',
    orgId: 'org_demo',
    orgRole: 'admin',
    getToken: async () => 'mock-jwt-token',
  };
}

export function useOrganization() {
  return {
    organization: mockOrganization,
    membership: { role: 'org:admin' },
    isLoaded: true,
  };
}

export function useOrganizationList() {
  return {
    organizationList: [{ organization: mockOrganization, membership: { role: 'org:admin' } }],
    isLoaded: true,
    setActive: async () => {},
    userMemberships: { data: [{ organization: mockOrganization }] },
  };
}

export function useSession() {
  return {
    session: { id: 'sess_mock', getToken: async () => 'mock-token' },
    isLoaded: true,
    isSignedIn: true,
  };
}

// Components that render children directly
export function SignedIn({ children }: { children: React.ReactNode }) {
  return React.createElement(React.Fragment, null, children);
}

export function SignedOut({ children }: { children: React.ReactNode }) {
  return null;
}

export function ClerkProvider({ children }: { children: React.ReactNode }) {
  return React.createElement(React.Fragment, null, children);
}

export function ClerkLoaded({ children }: { children: React.ReactNode }) {
  return React.createElement(React.Fragment, null, children);
}

export function ClerkLoading({ children }: { children: React.ReactNode }) {
  return null;
}

export function RedirectToSignIn() {
  return null;
}

export function OrganizationSwitcher() {
  return React.createElement('div', { className: 'clerk-mock-org-switcher' }, 'Demo Store');
}

export function UserButton() {
  return React.createElement('div', { className: 'clerk-mock-user-btn' }, 'DU');
}
