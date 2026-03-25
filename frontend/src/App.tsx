/** Main App Component
 *
 * Sets up Shopify Polaris provider, data health context, and routing.
 * Includes root-level error boundary for graceful error handling.
 *
 * Authentication: Clerk (https://clerk.com)
 * - ClerkProvider is set up in main.tsx
 * - SignedIn/SignedOut components control access
 * - useClerkToken hook syncs tokens for API calls
 *
 * Feature gating:
 * - FeatureGateRoute wraps routes that require entitlements
 * - Redirect loop prevention: checks pathname !== '/paywall'
 * - Shared dashboard view (/dashboards/:id) is NOT gated — viewable on any plan
 */

import { lazy, Suspense } from 'react';
import { BrowserRouter, Routes, Route, Navigate, useLocation, useParams } from 'react-router-dom';
import { SignedIn, SignedOut, RedirectToSignIn } from '@clerk/clerk-react';
import { AppProvider } from '@shopify/polaris';
import enTranslations from '@shopify/polaris/locales/en.json';
import '@shopify/polaris/build/esm/styles.css';

import { ErrorBoundary } from './components/ErrorBoundary';
import { RootErrorFallback } from './components/ErrorFallback';
import { DataHealthProvider } from './contexts/DataHealthContext';
import { AgencyProvider } from './contexts/AgencyContext';
import { Root } from './components/layout/Root';
import { useAutoOrganization } from './hooks/useAutoOrganization';
import { useClerkToken } from './hooks/useClerkToken';
import { useEntitlements } from './hooks/useEntitlements';
import { isFeatureEntitled } from './services/entitlementsApi';
import type { EntitlementsResponse } from './services/entitlementsApi';
import { DashboardBuilderProvider } from './contexts/DashboardBuilderContext';
import { DateRangeProvider } from './contexts/DateRangeContext';

// Default route — loaded eagerly (users always land here)
import { Dashboard } from './pages/Dashboard';

// Lazy-loaded pages — split into separate chunks
const AdminPlans = lazy(() => import('./pages/AdminPlans'));
const RootCausePanel = lazy(() => import('./pages/admin/RootCausePanel'));
const Analytics = lazy(() => import('./pages/Analytics'));
const Paywall = lazy(() => import('./pages/Paywall'));
const InsightsFeed = lazy(() => import('./pages/InsightsFeed'));
const ApprovalsInbox = lazy(() => import('./pages/ApprovalsInbox'));
const WhatsNew = lazy(() => import('./pages/WhatsNew'));
const DashboardList = lazy(() => import('./pages/DashboardList').then(m => ({ default: m.DashboardList })));
const DashboardView = lazy(() => import('./pages/DashboardView').then(m => ({ default: m.DashboardView })));
const DashboardBuilder = lazy(() => import('./pages/DashboardBuilder').then(m => ({ default: m.DashboardBuilder })));
const WizardFlow = lazy(() => import('./components/dashboards/wizard/WizardFlow').then(m => ({ default: m.WizardFlow })));
const DataSources = lazy(() => import('./pages/DataSources'));
const OAuthCallback = lazy(() => import('./pages/OAuthCallback'));
const Settings = lazy(() => import('./pages/Settings'));
const DashboardHome = lazy(() => import('./pages/DashboardHome').then(m => ({ default: m.DashboardHome })));
const BillingCheckout = lazy(() => import('./pages/BillingCheckout'));
const Attribution = lazy(() => import('./pages/Attribution').then(m => ({ default: m.Attribution })));
const Orders = lazy(() => import('./pages/Orders').then(m => ({ default: m.Orders })));
const Onboarding = lazy(() => import('./pages/Onboarding').then(m => ({ default: m.Onboarding })));
const ChannelAnalytics = lazy(() => import('./pages/ChannelAnalytics').then(m => ({ default: m.ChannelAnalytics })));
const NotFound = lazy(() => import('./pages/NotFound').then(m => ({ default: m.NotFound })));
const CohortAnalysis = lazy(() => import('./pages/CohortAnalysis').then(m => ({ default: m.CohortAnalysis })));
const BudgetPacing = lazy(() => import('./pages/BudgetPacing').then(m => ({ default: m.BudgetPacing })));
const Alerts = lazy(() => import('./pages/Alerts').then(m => ({ default: m.Alerts })));
const AIConsultant = lazy(() => import('./pages/AIConsultant').then(m => ({ default: m.AIConsultant })));
const SyncStatus = lazy(() => import('./pages/SyncStatus').then(m => ({ default: m.SyncStatus })));

const PageLoader = () => (
  <div className="flex items-center justify-center h-64">
    <div className="w-8 h-8 border-4 border-blue-600 border-t-transparent rounded-full animate-spin" />
  </div>
);

// =============================================================================
// FeatureGateRoute — redirects to paywall if feature not entitled
// =============================================================================

interface FeatureGateRouteProps {
  feature: string;
  entitlements: EntitlementsResponse | null;
  entitlementsLoading: boolean;
  entitlementsError: string | null;
  onRetry: () => Promise<void>;
  children: React.ReactNode;
}

function FeatureGateRoute({
  feature,
  entitlements,
  entitlementsLoading,
  entitlementsError,
  onRetry,
  children,
}: FeatureGateRouteProps) {
  const location = useLocation();

  // Still loading entitlements — show spinner
  if (entitlementsLoading && entitlements === null) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="w-8 h-8 border-4 border-blue-600 border-t-transparent rounded-full animate-spin" />
      </div>
    );
  }

  // Failed to load entitlements — fail open so the page is still accessible.
  // A banner is shown at the top but the user can still use the feature.
  if (entitlementsError && entitlements === null) {
    return (
      <>
        <div className="mx-8 mt-6 flex items-start gap-3 bg-yellow-50 border border-yellow-200 rounded-lg px-4 py-3 text-sm text-yellow-800">
          <svg className="w-4 h-4 mt-0.5 flex-shrink-0" fill="currentColor" viewBox="0 0 20 20">
            <path fillRule="evenodd" d="M8.485 2.495c.673-1.167 2.357-1.167 3.03 0l6.28 10.875c.673 1.167-.17 2.625-1.516 2.625H3.72c-1.347 0-2.189-1.458-1.515-2.625L8.485 2.495zM10 5a.75.75 0 01.75.75v3.5a.75.75 0 01-1.5 0v-3.5A.75.75 0 0110 5zm0 9a1 1 0 100-2 1 1 0 000 2z" clipRule="evenodd" />
          </svg>
          <span>
            Could not verify feature access — the server may be unavailable.{' '}
            <button onClick={onRetry} className="underline font-medium hover:text-yellow-900">
              Retry
            </button>
          </span>
        </div>
        {children}
      </>
    );
  }

  if (!isFeatureEntitled(entitlements, feature)) {
    // Edge case: prevent redirect loop if already on /paywall
    if (location.pathname === '/paywall') return <Paywall />;
    return <Navigate to={`/paywall?feature=${feature}`} replace />;
  }

  return <>{children}</>;
}

// =============================================================================
// OnboardingGate — redirects new users to /onboarding on first visit
// =============================================================================

function OnboardingGate({ children }: { children: React.ReactNode }) {
  const location = useLocation();
  const onboardingComplete = localStorage.getItem('onboardingComplete') === 'true';

  // Only redirect from root path — don't interrupt deep links
  if (!onboardingComplete && location.pathname === '/') {
    return <Navigate to="/onboarding" replace />;
  }

  return <>{children}</>;
}

// =============================================================================
// Authenticated app content
// =============================================================================

/**
 * AuthenticatedApp — waits for Clerk organization to be active before
 * mounting the token provider and routes.  This guarantees that
 * getToken() returns a JWT that contains org_id, which the backend
 * tenant_context middleware requires.
 */
function AuthenticatedApp() {
  const { isLoading: isOrgLoading, hasOrg } = useAutoOrganization();

  if (isOrgLoading) {
    return (
      <div className="flex items-center justify-center h-screen bg-gray-50">
        <div className="w-8 h-8 border-4 border-blue-600 border-t-transparent rounded-full animate-spin" />
      </div>
    );
  }

  if (!hasOrg) {
    return (
      <div style={{ padding: '2rem', textAlign: 'center' }}>
        <h2>Organization Required</h2>
        <p>
          Your account is not part of an organization yet.
          Please contact your administrator or create an organization
          in the Clerk dashboard.
        </p>
      </div>
    );
  }

  // Org is active — safe to mount the token provider
  return <AppWithOrg />;
}

/** Inner shell: only mounts once the Clerk org is active so the token has org_id. */
function AppWithOrg() {
  const { isTokenReady } = useClerkToken();
  const { entitlements, loading: entitlementsLoading, error: entitlementsError, refetch: refetchEntitlements } = useEntitlements(isTokenReady);

  if (!isTokenReady) {
    return (
      <div className="flex items-center justify-center h-screen bg-gray-50">
        <div className="w-8 h-8 border-4 border-blue-600 border-t-transparent rounded-full animate-spin" />
      </div>
    );
  }

  return (
    <AgencyProvider>
      <DataHealthProvider>
        <DateRangeProvider>
        <Suspense fallback={<PageLoader />}>
        <Routes>
          {/* Onboarding wizard — full-screen, no sidebar */}
          <Route path="/onboarding" element={<Onboarding />} />

          {/* New Tailwind-based layout with sidebar + header */}
          <Route element={<OnboardingGate><Root /></OnboardingGate>}>
            <Route path="/" element={<Dashboard />} />
            <Route path="/builder" element={
              <FeatureGateRoute feature="custom_reports" entitlements={entitlements} entitlementsLoading={entitlementsLoading} entitlementsError={entitlementsError} onRetry={refetchEntitlements}>
                <DashboardBuilderProvider>
                  <WizardFlow />
                </DashboardBuilderProvider>
              </FeatureGateRoute>
            } />
            <Route path="/sources" element={<DataSources />} />
            <Route path="/oauth/callback" element={<OAuthCallback />} />
            <Route path="/settings" element={<Settings />} />
            <Route path="/home" element={<DashboardHome />} />
            <Route path="/analytics" element={<Analytics />} />
            <Route path="/paywall" element={<Paywall />} />
            <Route path="/billing/checkout" element={<BillingCheckout />} />
            <Route path="/billing/callback" element={<BillingCheckout />} />
            <Route path="/insights" element={<InsightsFeed />} />
            <Route path="/approvals" element={<ApprovalsInbox />} />
            <Route path="/attribution" element={<Attribution />} />
            <Route path="/orders" element={<Orders />} />
            <Route path="/channels/:platform" element={<ChannelAnalytics />} />
            {/* Figma-matched routes */}
            <Route path="/channel/:channelKey" element={<ChannelByKey />} />
            <Route path="/ai-consultant" element={<AIConsultant />} />
            <Route path="/sync" element={<SyncStatus />} />
            <Route path="/cohorts" element={
              <FeatureGateRoute feature="cohort_analysis" entitlements={entitlements} entitlementsLoading={entitlementsLoading} entitlementsError={entitlementsError} onRetry={refetchEntitlements}>
                <CohortAnalysis />
              </FeatureGateRoute>
            } />
            <Route path="/reports" element={
              <FeatureGateRoute feature="custom_reports" entitlements={entitlements} entitlementsLoading={entitlementsLoading} entitlementsError={entitlementsError} onRetry={refetchEntitlements}>
                <DashboardBuilderProvider>
                  <WizardFlow />
                </DashboardBuilderProvider>
              </FeatureGateRoute>
            } />
            <Route path="/cohort-analysis" element={
              <FeatureGateRoute feature="cohort_analysis" entitlements={entitlements} entitlementsLoading={entitlementsLoading} entitlementsError={entitlementsError} onRetry={refetchEntitlements}>
                <CohortAnalysis />
              </FeatureGateRoute>
            } />
            <Route path="/budget-pacing" element={
              <FeatureGateRoute feature="budget_pacing" entitlements={entitlements} entitlementsLoading={entitlementsLoading} entitlementsError={entitlementsError} onRetry={refetchEntitlements}>
                <BudgetPacing />
              </FeatureGateRoute>
            } />
            <Route path="/alerts" element={
              <FeatureGateRoute feature="alerts" entitlements={entitlements} entitlementsLoading={entitlementsLoading} entitlementsError={entitlementsError} onRetry={refetchEntitlements}>
                <Alerts />
              </FeatureGateRoute>
            } />
            <Route path="/whats-new" element={<WhatsNew />} />
            <Route path="/data-sources" element={<DataSources />} />
            <Route path="/admin/plans" element={<AdminPlans />} />
            <Route path="/admin/diagnostics" element={<RootCausePanel />} />

            {/* Custom Dashboards — gated routes */}
            <Route
              path="/dashboards"
              element={
                <FeatureGateRoute feature="custom_reports" entitlements={entitlements} entitlementsLoading={entitlementsLoading} entitlementsError={entitlementsError} onRetry={refetchEntitlements}>
                  <DashboardList />
                </FeatureGateRoute>
              }
            />
            <Route
              path="/dashboards/wizard"
              element={
                <FeatureGateRoute feature="custom_reports" entitlements={entitlements} entitlementsLoading={entitlementsLoading} entitlementsError={entitlementsError} onRetry={refetchEntitlements}>
                  <DashboardBuilderProvider>
                    <WizardFlow />
                  </DashboardBuilderProvider>
                </FeatureGateRoute>
              }
            />
            <Route
              path="/dashboards/:dashboardId/edit"
              element={
                <FeatureGateRoute feature="custom_reports" entitlements={entitlements} entitlementsLoading={entitlementsLoading} entitlementsError={entitlementsError} onRetry={refetchEntitlements}>
                  <DashboardBuilder />
                </FeatureGateRoute>
              }
            />
            {/* View route is NOT gated — shared dashboards viewable on any plan */}
            <Route path="/dashboards/:dashboardId" element={<DashboardView />} />
            <Route path="*" element={<NotFound />} />
          </Route>
        </Routes>
        </Suspense>
        </DateRangeProvider>
      </DataHealthProvider>
    </AgencyProvider>
  );
}

// Maps Figma channel keys (e.g. "google") to platform API names (e.g. "google_ads")
const CHANNEL_KEY_TO_PLATFORM: Record<string, string> = {
  google: 'google_ads',
  facebook: 'facebook_ads',
  instagram: 'instagram_ads',
  tiktok: 'tiktok_ads',
  pinterest: 'pinterest_ads',
  twitter: 'twitter_ads',
  organic: 'organic',
};

// Resolves /channel/:channelKey → redirects to /channels/:platform
function ChannelByKey() {
  const { channelKey } = useParams<{ channelKey: string }>();
  const platform = channelKey ? CHANNEL_KEY_TO_PLATFORM[channelKey] : undefined;
  if (!platform) return <Navigate to="/" replace />;
  return <Navigate to={`/channels/${platform}`} replace />;
}

function App() {
  return (
    <ErrorBoundary
      fallbackRender={({ error, errorInfo, resetErrorBoundary }) => (
        <AppProvider i18n={enTranslations}>
          <RootErrorFallback
            error={error}
            errorInfo={errorInfo}
            resetErrorBoundary={resetErrorBoundary}
          />
        </AppProvider>
      )}
      onError={(error, errorInfo) => {
        console.error('Root error boundary caught error:', error);
        console.error('Component stack:', errorInfo.componentStack);
      }}
    >
      <AppProvider i18n={enTranslations}>
        <BrowserRouter>
          <SignedIn>
            <AuthenticatedApp />
          </SignedIn>
          <SignedOut>
            <RedirectToSignIn />
          </SignedOut>
        </BrowserRouter>
      </AppProvider>
    </ErrorBoundary>
  );
}

export default App;
