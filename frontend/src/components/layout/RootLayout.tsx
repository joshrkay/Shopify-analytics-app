/**
 * RootLayout Component
 *
 * Two-column layout wrapper: Sidebar + main content area.
 * Wraps all authenticated routes.
 * Exports SidebarProvider/useSidebar for mobile hamburger toggle.
 *
 * Epic 0.1 — App-wide layout shell
 * Story 0.1.1 — RootLayout wraps authenticated experience
 * Story 0.3.1 — Mobile hamburger toggles sidebar
 */

import React, { useState, useCallback, useContext } from 'react';
import { Sidebar } from './Sidebar';
import './RootLayout.css';

// =============================================================================
// SidebarContext — shared state for mobile sidebar toggle
// =============================================================================

interface SidebarContextValue {
  isOpen: boolean;
  toggle: () => void;
  close: () => void;
}

const SidebarContext = React.createContext<SidebarContextValue>({
  isOpen: false,
  toggle: () => {},
  close: () => {},
});

export const useSidebar = () => useContext(SidebarContext);

export function SidebarProvider({ children }: { children: React.ReactNode }) {
  const [isOpen, setIsOpen] = useState(false);
  const toggle = useCallback(() => setIsOpen((prev) => !prev), []);
  const close = useCallback(() => setIsOpen(false), []);

  return (
    <SidebarContext.Provider value={{ isOpen, toggle, close }}>
      {children}
    </SidebarContext.Provider>
  );
}

// =============================================================================
// RootLayout
// =============================================================================

interface RootLayoutProps {
  children: React.ReactNode;
}

export function RootLayout({ children }: RootLayoutProps) {
  const { isOpen, close } = useSidebar();

  return (
    <div className="root-layout">
      <Sidebar />
      {/* Overlay for mobile — closes sidebar when tapped */}
      <div
        className={`root-layout__overlay${isOpen ? ' root-layout__overlay--visible' : ''}`}
        onClick={close}
        aria-hidden="true"
      />
      <main className="root-layout__content">
        {children}
      </main>
    </div>
  );
}
