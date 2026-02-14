import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import { ClerkProvider, ClerkLoaded, ClerkLoading } from '@clerk/clerk-react';
import App from './App';
import './index.css';

// Clerk publishable key from environment
const PUBLISHABLE_KEY = import.meta.env.VITE_CLERK_PUBLISHABLE_KEY;

/**
 * Inline loading indicator shown while Clerk SDK initialises.
 * Without this, users see a blank white screen until Clerk connects
 * to its API — which can hang indefinitely if the Clerk domain is
 * unreachable (e.g. DNS misconfiguration).
 */
function ClerkLoadingIndicator() {
  return (
    <div
      style={{
        display: 'flex',
        flexDirection: 'column',
        alignItems: 'center',
        justifyContent: 'center',
        height: '100vh',
        fontFamily: 'system-ui, -apple-system, sans-serif',
        color: '#6b7280',
      }}
    >
      <div
        style={{
          width: 40,
          height: 40,
          border: '3px solid #e5e7eb',
          borderTopColor: '#6366f1',
          borderRadius: '50%',
          animation: 'spin 0.8s linear infinite',
        }}
      />
      <p style={{ marginTop: 16, fontSize: 14 }}>Loading MarkInsight…</p>
      <style>{`@keyframes spin { to { transform: rotate(360deg); } }`}</style>
    </div>
  );
}

const root = document.getElementById('root')!;

// Remove the static HTML loading indicator placed by index.html
// once JS has loaded and React is taking over.
root.innerHTML = '';

if (!PUBLISHABLE_KEY) {
  // Show a visible error instead of a silent white screen.
  // This fires when the env var was missing at Vite build time.
  root.innerHTML =
    '<div style="padding:40px;text-align:center;font-family:system-ui,sans-serif">' +
    '<h1 style="color:#d32f2f">Configuration Error</h1>' +
    '<p>Missing <code>VITE_CLERK_PUBLISHABLE_KEY</code> environment variable.</p>' +
    '<p style="color:#666">This variable must be set at build time. Redeploy after setting it in your hosting dashboard.</p>' +
    '</div>';
} else {
  createRoot(root).render(
    <StrictMode>
      <ClerkProvider publishableKey={PUBLISHABLE_KEY} afterSignOutUrl="/">
        <ClerkLoading>
          <ClerkLoadingIndicator />
        </ClerkLoading>
        <ClerkLoaded>
          <App />
        </ClerkLoaded>
      </ClerkProvider>
    </StrictMode>
  );
}
