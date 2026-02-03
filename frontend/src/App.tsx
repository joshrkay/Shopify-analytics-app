/**
 * Main App Component
 *
 * Sets up Shopify Polaris provider, data health context, and routing.
 * Requires Frontegg authentication before rendering application content.
 */

import { useEffect } from 'react';
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import { AppProvider } from '@shopify/polaris';
import { useAuth, useLoginWithRedirect } from '@frontegg/react';
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
  const { isAuthenticated, isLoading, user } = useAuth();
  const loginWithRedirect = useLoginWithRedirect();

  // Ensure JWT token is synced to localStorage
  useTokenSync();

  // TEMPORARY DEBUG: Collect auth state info
  const debugInfo = {
    isAuthenticated: isAuthenticated ? 'YES ✅' : 'NO ❌',
    isLoading: isLoading ? 'YES' : 'NO',
    userEmail: user?.email || 'NONE',
    userName: user?.name || 'NONE',
    localStorage_jwt: typeof window !== 'undefined' ? (localStorage.getItem('jwt_token') ? 'EXISTS ✅' : 'MISSING ❌') : 'N/A',
    localStorage_frontegg_keys: typeof window !== 'undefined' ? Object.keys(localStorage).filter(k => k.toLowerCase().includes('frontegg')).join(', ') || 'NONE' : 'N/A',
    currentUrl: typeof window !== 'undefined' ? window.location.href : 'N/A',
  };

  // TEMPORARY: Show debug screen to diagnose auth issue
  return (
    <AppProvider i18n={enTranslations}>
      <div style={{
        padding: '40px',
        fontFamily: 'monospace',
        maxWidth: '800px',
        margin: '0 auto'
      }}>
        <h1 style={{ fontSize: '24px', marginBottom: '20px' }}>🔍 Frontegg Authentication Debug</h1>

        <div style={{
          background: '#f0f0f0',
          padding: '20px',
          borderRadius: '8px',
          marginBottom: '20px'
        }}>
          <h2 style={{ fontSize: '18px', marginBottom: '10px' }}>Authentication State:</h2>
          <pre style={{ fontSize: '14px', lineHeight: '1.6' }}>
            {JSON.stringify(debugInfo, null, 2)}
          </pre>
        </div>

        <div style={{
          background: '#fffbe6',
          padding: '20px',
          borderRadius: '8px',
          border: '1px solid #ffd700',
          marginBottom: '20px'
        }}>
          <h3 style={{ fontSize: '16px', marginBottom: '10px' }}>🔎 What This Means:</h3>
          <ul style={{ lineHeight: '1.8', paddingLeft: '20px' }}>
            <li>If <strong>isAuthenticated = NO ❌</strong> after login → Frontegg session not being created</li>
            <li>If <strong>localStorage_jwt = MISSING ❌</strong> → Tokens aren't being stored</li>
            <li>If <strong>localStorage_frontegg_keys = NONE</strong> → Frontegg not storing any data</li>
            <li>If <strong>isAuthenticated = YES ✅</strong> → Authentication working! Will load app below</li>
          </ul>
        </div>

        <div style={{ display: 'flex', gap: '10px', marginBottom: '20px' }}>
          <button
            onClick={() => window.location.reload()}
            style={{
              padding: '10px 20px',
              fontSize: '14px',
              cursor: 'pointer',
              background: '#4CAF50',
              color: 'white',
              border: 'none',
              borderRadius: '4px'
            }}
          >
            🔄 Reload Page
          </button>
          <button
            onClick={() => loginWithRedirect()}
            style={{
              padding: '10px 20px',
              fontSize: '14px',
              cursor: 'pointer',
              background: '#2196F3',
              color: 'white',
              border: 'none',
              borderRadius: '4px'
            }}
          >
            🔐 Try Login Again
          </button>
        </div>

        <hr style={{ margin: '30px 0', border: '1px solid #ccc' }} />

        {/* Show the actual app if authenticated */}
        {isAuthenticated && (
          <div style={{
            background: '#e8f5e9',
            padding: '20px',
            borderRadius: '8px',
            marginBottom: '20px'
          }}>
            <h2 style={{ fontSize: '18px', color: '#2e7d32' }}>✅ Authentication Successful!</h2>
            <p>Loading the application below...</p>
          </div>
        )}

        {isLoading && (
          <div style={{
            background: '#fff3e0',
            padding: '20px',
            borderRadius: '8px',
            textAlign: 'center'
          }}>
            <p>⏳ Checking authentication...</p>
          </div>
        )}

        {!isAuthenticated && !isLoading && (
          <div style={{
            background: '#ffebee',
            padding: '20px',
            borderRadius: '8px'
          }}>
            <h3 style={{ color: '#c62828' }}>❌ Not Authenticated</h3>
            <p>You should be redirected to Frontegg login. If not, click "Try Login Again" above.</p>
          </div>
        )}
      </div>

      {/* Render actual app if authenticated */}
      {isAuthenticated && (
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
      )}
    </AppProvider>
  );
}

export default App;
