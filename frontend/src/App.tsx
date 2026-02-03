/**
 * Main App Component - DIAGNOSTIC VERSION
 *
 * Displays visible debugging information to diagnose authentication issues.
 * This version will help us see exactly what's happening since browser console won't open.
 */

import { useState, useEffect } from 'react';
import { Routes, Route, Navigate } from 'react-router-dom';
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
  const [showDiagnostics, setShowDiagnostics] = useState(true);
  const [hookError, setHookError] = useState<string | null>(null);

  // Get auth data - if this throws, let React error boundary handle it
  const { isAuthenticated, isLoading, user } = useAuth();

  // Ensure JWT token is synced to localStorage
  useTokenSync();

  // Check for initialization errors in useEffect (not during render)
  useEffect(() => {
    // This runs after render, so we can safely detect issues
    if (!isLoading && !isAuthenticated) {
      // Check if Frontegg SDK initialized properly
      const fronteggElements = document.querySelectorAll('[data-frontegg]');
      if (fronteggElements.length === 0) {
        setHookError('Frontegg SDK may not have initialized');
      }
    }
  }, [isLoading, isAuthenticated]);

  // Collect diagnostic information
  const diagnostics = {
    timestamp: new Date().toISOString(),
    isAuthenticated: isAuthenticated ? 'YES ✅' : 'NO ❌',
    isLoading: isLoading ? 'YES' : 'NO',
    userEmail: user?.email || 'NONE',
    userId: user?.id || 'NONE',
    tenantId: user?.tenantId || 'NONE',
    hookError: hookError || 'NONE',
    envVars: {
      VITE_FRONTEGG_BASE_URL: import.meta.env.VITE_FRONTEGG_BASE_URL || 'MISSING ❌',
      VITE_FRONTEGG_CLIENT_ID: import.meta.env.VITE_FRONTEGG_CLIENT_ID || 'MISSING ❌',
      VITE_API_URL: import.meta.env.VITE_API_URL || 'MISSING ❌',
    },
    localStorage: {
      jwt_token: typeof window !== 'undefined' ? (localStorage.getItem('jwt_token') ? 'EXISTS ✅' : 'MISSING ❌') : 'N/A',
      allFronteggKeys: typeof window !== 'undefined' ? Object.keys(localStorage).filter(k => k.toLowerCase().includes('frontegg')).join(', ') || 'NONE' : 'N/A',
    }
  };

  // If diagnostics are visible, show debug screen
  if (showDiagnostics) {
    return (
      <div style={{
        padding: '40px',
        fontFamily: '-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif',
        maxWidth: '1200px',
        margin: '0 auto',
        backgroundColor: '#ffffff'
      }}>
        <div style={{
          backgroundColor: '#1a1a1a',
          color: '#ffffff',
          padding: '20px',
          borderRadius: '8px',
          marginBottom: '20px'
        }}>
          <h1 style={{ margin: '0 0 10px 0', fontSize: '24px' }}>🔍 Frontegg Authentication Diagnostics</h1>
          <p style={{ margin: 0, opacity: 0.8 }}>Embedded Login Mode (hostedLoginBox: false)</p>
        </div>

        <div style={{
          backgroundColor: '#f5f5f5',
          padding: '20px',
          borderRadius: '8px',
          marginBottom: '20px',
          border: '2px solid #e0e0e0'
        }}>
          <h2 style={{ marginTop: 0, fontSize: '18px', color: '#333' }}>Authentication State</h2>
          <pre style={{
            backgroundColor: '#ffffff',
            padding: '15px',
            borderRadius: '4px',
            overflow: 'auto',
            fontSize: '14px',
            lineHeight: '1.6',
            margin: 0,
            border: '1px solid #ddd'
          }}>
{JSON.stringify(diagnostics, null, 2)}
          </pre>
        </div>

        <div style={{
          backgroundColor: isAuthenticated ? '#e8f5e9' : '#fff3e0',
          padding: '20px',
          borderRadius: '8px',
          marginBottom: '20px',
          border: `2px solid ${isAuthenticated ? '#4caf50' : '#ff9800'}`
        }}>
          <h2 style={{ marginTop: 0, fontSize: '18px', color: '#333' }}>Current Status</h2>
          {isLoading && (
            <p style={{ fontSize: '16px', margin: '10px 0' }}>
              ⏳ <strong>Loading authentication state...</strong>
            </p>
          )}
          {!isLoading && !isAuthenticated && (
            <div>
              <p style={{ fontSize: '16px', margin: '10px 0' }}>
                🔐 <strong>Not Authenticated</strong>
              </p>
              <p style={{ fontSize: '14px', margin: '10px 0', color: '#666' }}>
                With embedded login, Frontegg should automatically render a login form below.
                If you don't see a login form, there may be an SDK initialization issue.
              </p>
              {hookError && (
                <div style={{
                  backgroundColor: '#ffebee',
                  padding: '15px',
                  borderRadius: '4px',
                  marginTop: '10px',
                  border: '1px solid #ef5350'
                }}>
                  <strong style={{ color: '#c62828' }}>useAuth Hook Error:</strong>
                  <pre style={{ margin: '10px 0 0 0', fontSize: '13px' }}>{hookError}</pre>
                </div>
              )}
            </div>
          )}
          {!isLoading && isAuthenticated && (
            <p style={{ fontSize: '16px', margin: '10px 0' }}>
              ✅ <strong>Authenticated as {user?.email}</strong>
            </p>
          )}
        </div>

        <div style={{
          backgroundColor: '#e3f2fd',
          padding: '20px',
          borderRadius: '8px',
          marginBottom: '20px',
          border: '2px solid #2196f3'
        }}>
          <h2 style={{ marginTop: 0, fontSize: '18px', color: '#333' }}>Environment Configuration</h2>
          <div style={{ fontSize: '14px', lineHeight: '1.8' }}>
            <p><strong>Base URL:</strong> {diagnostics.envVars.VITE_FRONTEGG_BASE_URL}</p>
            <p><strong>Client ID:</strong> {diagnostics.envVars.VITE_FRONTEGG_CLIENT_ID}</p>
            <p><strong>API URL:</strong> {diagnostics.envVars.VITE_API_URL}</p>
          </div>
          {diagnostics.envVars.VITE_FRONTEGG_BASE_URL === 'MISSING ❌' && (
            <div style={{
              backgroundColor: '#ffebee',
              padding: '10px',
              borderRadius: '4px',
              marginTop: '10px',
              fontSize: '14px',
              color: '#c62828'
            }}>
              ⚠️ Environment variables are not loaded! Check frontend/.env file.
            </div>
          )}
        </div>

        <div style={{ display: 'flex', gap: '10px', marginBottom: '20px' }}>
          <button
            onClick={() => setShowDiagnostics(false)}
            style={{
              backgroundColor: '#4caf50',
              color: 'white',
              padding: '12px 24px',
              border: 'none',
              borderRadius: '4px',
              fontSize: '14px',
              cursor: 'pointer',
              fontWeight: 'bold'
            }}
          >
            {isAuthenticated ? '✅ Continue to App' : '🔄 Try to Show Login Form'}
          </button>
          <button
            onClick={() => window.location.reload()}
            style={{
              backgroundColor: '#2196f3',
              color: 'white',
              padding: '12px 24px',
              border: 'none',
              borderRadius: '4px',
              fontSize: '14px',
              cursor: 'pointer'
            }}
          >
            🔄 Reload Page
          </button>
          <button
            onClick={() => {
              localStorage.clear();
              window.location.reload();
            }}
            style={{
              backgroundColor: '#ff9800',
              color: 'white',
              padding: '12px 24px',
              border: 'none',
              borderRadius: '4px',
              fontSize: '14px',
              cursor: 'pointer'
            }}
          >
            🗑️ Clear Storage & Reload
          </button>
        </div>

        <div style={{
          backgroundColor: '#fff9c4',
          padding: '15px',
          borderRadius: '4px',
          fontSize: '13px',
          color: '#666',
          border: '1px solid #fff59d'
        }}>
          <strong>What to look for:</strong>
          <ul style={{ margin: '10px 0', paddingLeft: '20px' }}>
            <li>If isAuthenticated = NO after clicking "Try to Show Login Form", Frontegg embedded login may not be rendering</li>
            <li>If Environment Variables show MISSING, the .env file is not being loaded by Vite</li>
            <li>If localStorage jwt_token = MISSING, tokens are not being stored after login</li>
            <li>If there's a Hook Error, the Frontegg SDK is failing to initialize</li>
          </ul>
        </div>
      </div>
    );
  }

  // Show loading state while checking authentication
  if (isLoading) {
    return (
      <AppProvider i18n={enTranslations}>
        <div style={{
          display: 'flex',
          justifyContent: 'center',
          alignItems: 'center',
          height: '100vh',
          flexDirection: 'column',
          gap: '20px'
        }}>
          <p style={{ fontSize: '18px' }}>Loading authentication...</p>
          <button
            onClick={() => setShowDiagnostics(true)}
            style={{
              padding: '10px 20px',
              fontSize: '14px',
              cursor: 'pointer'
            }}
          >
            Show Diagnostics
          </button>
        </div>
      </AppProvider>
    );
  }

  // If not authenticated, Frontegg will automatically render embedded login form
  if (!isAuthenticated) {
    return (
      <AppProvider i18n={enTranslations}>
        <div style={{
          display: 'flex',
          justifyContent: 'center',
          alignItems: 'center',
          height: '100vh',
          backgroundColor: '#f4f6f8',
          flexDirection: 'column',
          gap: '20px'
        }}>
          <div style={{
            backgroundColor: '#ffffff',
            padding: '20px',
            borderRadius: '8px',
            boxShadow: '0 2px 8px rgba(0,0,0,0.1)',
            textAlign: 'center',
            marginBottom: '20px'
          }}>
            <h2 style={{ margin: '0 0 10px 0', color: '#333' }}>🔐 Login Required</h2>
            <p style={{ margin: '0', color: '#666', fontSize: '14px' }}>
              Frontegg embedded login form should appear below
            </p>
          </div>

          {/* Frontegg's embedded login form will render here automatically */}
          <div style={{
            width: '100%',
            maxWidth: '400px',
            padding: '20px',
            backgroundColor: '#ffffff',
            borderRadius: '8px',
            boxShadow: '0 2px 8px rgba(0,0,0,0.1)',
            minHeight: '300px'
          }}>
            {/* The FronteggProvider handles rendering the login UI */}
            <p style={{ textAlign: 'center', color: '#999', fontSize: '13px', marginTop: '140px' }}>
              ⏳ Waiting for Frontegg login form to render...
            </p>
          </div>

          <button
            onClick={() => setShowDiagnostics(true)}
            style={{
              padding: '10px 20px',
              fontSize: '14px',
              cursor: 'pointer',
              backgroundColor: '#2196f3',
              color: 'white',
              border: 'none',
              borderRadius: '4px'
            }}
          >
            🔍 Show Diagnostics
          </button>
        </div>
      </AppProvider>
    );
  }

  // User is authenticated - render the app
  return (
    <AppProvider i18n={enTranslations}>
      <DataHealthProvider>
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
      </DataHealthProvider>
    </AppProvider>
  );
}

export default App;
