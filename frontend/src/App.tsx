/**
 * Main App Component
 *
 * Sets up Shopify Polaris provider, data health context, and routing.
 * Requires Frontegg authentication before rendering application content.
 */

import { useEffect } from 'react';
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import { AppProvider } from '@shopify/polaris';
import { useAuth } from '@frontegg/react';
import enTranslations from '@shopify/polaris/locales/en.json';
import '@shopify/polaris/build/esm/styles.css';

import { DataHealthProvider } from './contexts/DataHealthContext';
import { AppHeader } from './components/layout/AppHeader';
import { useTokenSync } from './hooks/useTokenSync';
import AdminPlans from './pages/AdminPlans';
import Analytics from './pages/Analytics';
import Paywall from './pages/Paywall';
import InsightsFeed from './pages/InsightsFeed';
import ApprovalsInbox from './pages/ApprovalsInbox';
import WhatsNew from './pages/WhatsNew';

function App() {
  const { isAuthenticated, isLoading } = useAuth();

  // Ensure JWT token is synced to localStorage
  useTokenSync();

  // Show loading state while checking authentication
  if (isLoading) {
    return (
      <AppProvider i18n={enTranslations}>
        <div style={{
          display: 'flex',
          justifyContent: 'center',
          alignItems: 'center',
          height: '100vh'
        }}>
          <p>Loading...</p>
        </div>
      </AppProvider>
    );
  }

  // If not authenticated, Frontegg will automatically render embedded login form
  // We just need to provide a styled container
  if (!isAuthenticated) {
    return (
      <AppProvider i18n={enTranslations}>
        <div style={{
          display: 'flex',
          justifyContent: 'center',
          alignItems: 'center',
          height: '100vh',
          backgroundColor: '#f4f6f8'
        }}>
          {/* Frontegg's embedded login form will render here automatically */}
          <div style={{ width: '100%', maxWidth: '400px', padding: '20px' }}>
            {/* The FronteggProvider handles rendering the login UI */}
          </div>
        </div>
      </AppProvider>
    );
  }

  // User is authenticated - render the app
  return (
    <AppProvider i18n={enTranslations}>
      <DataHealthProvider>
        <BrowserRouter>
          <AppHeader />
          <Routes>
            <Route path="/admin/plans" element={<AdminPlans />} />
            <Route path="/analytics" element={<Analytics />} />
            <Route path="/paywall" element={<Paywall />} />
            <Route path="/insights" element={<InsightsFeed />} />
            <Route path="/approvals" element={<ApprovalsInbox />} />
            <Route path="/whats-new" element={<WhatsNew />} />
            <Route path="/" element={<Navigate to="/analytics" replace />} />
          </Routes>
        </BrowserRouter>
      </DataHealthProvider>
    </AppProvider>
  );
}

export default App;
