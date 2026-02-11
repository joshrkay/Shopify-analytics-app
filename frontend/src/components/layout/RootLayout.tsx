/**
 * RootLayout Component
 *
 * Two-column layout wrapper: Sidebar + main content area.
 * Wraps all authenticated routes.
 *
 * Epic 0.1 — App-wide layout shell
 * Story 0.1.1 — RootLayout wraps authenticated experience
 */

import { Sidebar } from './Sidebar';
import './RootLayout.css';

interface RootLayoutProps {
  children: React.ReactNode;
}

export function RootLayout({ children }: RootLayoutProps) {
  return (
    <div className="root-layout">
      <Sidebar />
      <main className="root-layout__content">
        {children}
      </main>
    </div>
  );
}
