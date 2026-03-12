import { useEffect, useMemo } from 'react';
import {
  Bell,
  CreditCard,
  Database,
  Key,
  RefreshCw,
  Sparkles,
  User,
  Users,
} from 'lucide-react';
import type { LucideIcon } from 'lucide-react';
import { useSearchParams, useNavigate } from 'react-router-dom';
import { useAgency } from '../contexts/AgencyContext';
import type { SettingsTab } from '../types/settingsTypes';
import { SettingsTabButton } from '../components/settings/SettingsTabButton';
import { DataSourcesSettingsTab } from '../components/settings/DataSourcesSettingsTab';
import { SyncSettingsTab } from '../components/settings/SyncSettingsTab';
import { TeamSettings } from '../components/settings/TeamSettings';
import { NotificationsSettingsTab } from '../components/settings/NotificationsSettingsTab';

const ROLE_RANK = {
  viewer: 0,
  admin: 1,
  owner: 2,
} as const;

type RequiredRole = keyof typeof ROLE_RANK;

interface SettingsTabDefinition {
  id: SettingsTab;
  label: string;
  icon: LucideIcon;
  requiredRole: RequiredRole;
}

const SETTINGS_TABS: SettingsTabDefinition[] = [
  { id: 'sources', label: 'Data Sources', icon: Database, requiredRole: 'viewer' },
  { id: 'sync', label: 'Sync Settings', icon: RefreshCw, requiredRole: 'admin' },
  { id: 'notifications', label: 'Notifications', icon: Bell, requiredRole: 'viewer' },
  { id: 'account', label: 'Account', icon: User, requiredRole: 'viewer' },
  { id: 'team', label: 'Team', icon: Users, requiredRole: 'admin' },
  { id: 'billing', label: 'Billing', icon: CreditCard, requiredRole: 'owner' },
  { id: 'api', label: 'API Keys', icon: Key, requiredRole: 'admin' },
  { id: 'ai', label: 'AI Insights', icon: Sparkles, requiredRole: 'admin' },
];

function deriveUserRole(userRoles: string[] = []): RequiredRole {
  if (userRoles.some((role) => role === 'owner' || role === 'super_admin' || role === 'agency_admin')) {
    return 'owner';
  }

  if (userRoles.some((role) => role === 'admin' || role === 'merchant_admin' || role === 'editor')) {
    return 'admin';
  }

  return 'viewer';
}

function canAccessTab(userRole: RequiredRole, requiredRole: RequiredRole): boolean {
  return ROLE_RANK[userRole] >= ROLE_RANK[requiredRole];
}

// ---------------------------------------------------------------------------
// Stub tab components — Account, Billing, API Keys, AI Insights
// ---------------------------------------------------------------------------

function AccountSettingsTab() {
  return (
    <section data-testid="settings-panel-account">
      <h2 className="text-xl font-semibold mb-1">Account</h2>
      <p className="text-gray-500 text-sm mb-6">Manage your personal account and preferences.</p>

      <div className="bg-white rounded-xl border border-gray-200 p-6 mb-4">
        <div className="flex items-center gap-4 mb-4">
          <div className="w-14 h-14 rounded-full bg-blue-100 flex items-center justify-center">
            <User className="w-7 h-7 text-blue-600" />
          </div>
          <div>
            <p className="font-semibold text-gray-900">Your Account</p>
            <p className="text-sm text-gray-500">
              Account details are managed via your Shopify identity provider.
            </p>
          </div>
        </div>
        <div className="bg-gray-50 rounded-lg p-3 text-sm text-gray-600">
          To update your name, email, or password, visit your Shopify account settings or contact
          your workspace owner.
        </div>
      </div>
    </section>
  );
}

function BillingSettingsTab() {
  const navigate = useNavigate();
  return (
    <section data-testid="settings-panel-billing">
      <h2 className="text-xl font-semibold mb-1">Billing</h2>
      <p className="text-gray-500 text-sm mb-6">Manage your subscription and billing details.</p>

      <div className="bg-white rounded-xl border border-gray-200 p-6">
        <div className="flex items-center justify-between mb-5">
          <div>
            <p className="font-semibold text-gray-900">Subscription</p>
            <p className="text-sm text-gray-500 mt-0.5">
              View your current plan and upgrade options.
            </p>
          </div>
          <CreditCard className="w-8 h-8 text-gray-400" />
        </div>
        <button
          onClick={() => navigate('/billing/checkout')}
          className="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition-colors text-sm font-medium"
        >
          Manage Billing
        </button>
      </div>
    </section>
  );
}

function ApiKeysSettingsTab() {
  return (
    <section data-testid="settings-panel-api">
      <h2 className="text-xl font-semibold mb-1">API Keys</h2>
      <p className="text-gray-500 text-sm mb-6">Programmatic access to your analytics data.</p>

      <div className="bg-white rounded-xl border border-gray-200 p-6">
        <div className="flex items-center gap-3 mb-4">
          <div className="bg-gray-100 p-2 rounded-lg">
            <Key className="w-5 h-5 text-gray-600" />
          </div>
          <div>
            <p className="font-semibold text-gray-900">API Access</p>
            <p className="text-sm text-gray-500">
              Coming soon — API key management is under development.
            </p>
          </div>
        </div>
        <div className="bg-blue-50 border border-blue-100 rounded-lg p-4 text-sm text-blue-700">
          API access will let you pull your analytics data into external tools and workflows.
          This feature is on the roadmap for the next release.
        </div>
      </div>
    </section>
  );
}

function AiInsightsSettingsTab() {
  return (
    <section data-testid="settings-panel-ai">
      <h2 className="text-xl font-semibold mb-1">AI Insights</h2>
      <p className="text-gray-500 text-sm mb-6">
        Configure AI-powered analysis and recommendations.
      </p>

      <div className="bg-white rounded-xl border border-gray-200 p-6">
        <div className="flex items-center gap-3 mb-4">
          <div className="bg-purple-100 p-2 rounded-lg">
            <Sparkles className="w-5 h-5 text-purple-600" />
          </div>
          <div>
            <p className="font-semibold text-gray-900">AI Configuration</p>
            <p className="text-sm text-gray-500">
              Advanced AI settings are coming soon.
            </p>
          </div>
        </div>
        <div className="bg-purple-50 border border-purple-100 rounded-lg p-4 text-sm text-purple-700">
          Upcoming settings will include AI model selection, insight frequency, and custom analysis
          prompts. AI insights are currently enabled and running with default settings.
        </div>
      </div>
    </section>
  );
}

// ---------------------------------------------------------------------------
// Tab content router
// ---------------------------------------------------------------------------

function renderTabContent(tab: SettingsTab) {
  if (tab === 'sources') {
    return (
      <section data-testid="settings-panel-sources">
        <DataSourcesSettingsTab />
      </section>
    );
  }

  if (tab === 'sync') {
    return (
      <section data-testid="settings-panel-sync">
        <SyncSettingsTab />
      </section>
    );
  }

  if (tab === 'team') {
    return (
      <section data-testid="settings-panel-team">
        <TeamSettings />
      </section>
    );
  }

  if (tab === 'notifications') {
    return (
      <section data-testid="settings-panel-notifications">
        <NotificationsSettingsTab />
      </section>
    );
  }

  if (tab === 'account') return <AccountSettingsTab />;
  if (tab === 'billing') return <BillingSettingsTab />;
  if (tab === 'api') return <ApiKeysSettingsTab />;
  if (tab === 'ai') return <AiInsightsSettingsTab />;

  return null;
}

export default function Settings() {
  const { userRoles } = useAgency();
  const userRole = deriveUserRole(userRoles);
  const [searchParams, setSearchParams] = useSearchParams();
  const tabFromUrl = searchParams.get('tab');

  const visibleTabs = useMemo(
    () => SETTINGS_TABS.filter((tab) => canAccessTab(userRole, tab.requiredRole)),
    [userRole],
  );

  const fallbackTab = visibleTabs[0]?.id ?? 'sources';
  const requestedTab = (tabFromUrl ?? fallbackTab) as SettingsTab;
  const activeTab = visibleTabs.some((tab) => tab.id === requestedTab) ? requestedTab : fallbackTab;

  useEffect(() => {
    if (!visibleTabs.some((tab) => tab.id === requestedTab)) {
      const nextParams = new URLSearchParams(searchParams);
      nextParams.set('tab', fallbackTab);
      setSearchParams(nextParams, { replace: true });
    }
  }, [fallbackTab, requestedTab, searchParams, setSearchParams, visibleTabs]);

  return (
    <div className="p-6" data-testid="settings-page">
      <h1 className="text-2xl font-bold mb-6">Settings</h1>
      <div className="flex flex-col md:flex-row gap-6">
        <aside className="md:w-64" data-testid="settings-sidebar">
          <div className="flex md:flex-col gap-2 overflow-x-auto" data-testid="settings-tab-list">
            {visibleTabs.map((tab) => (
              <SettingsTabButton
                key={tab.id}
                icon={tab.icon}
                active={activeTab === tab.id}
                onClick={() => {
                  const nextParams = new URLSearchParams(searchParams);
                  nextParams.set('tab', tab.id);
                  setSearchParams(nextParams);
                }}
              >
                {tab.label}
              </SettingsTabButton>
            ))}
          </div>
        </aside>

        <main className="flex-1" data-testid="settings-content">
          {renderTabContent(activeTab)}
        </main>
      </div>
    </div>
  );
}

export { SETTINGS_TABS, deriveUserRole, canAccessTab };
