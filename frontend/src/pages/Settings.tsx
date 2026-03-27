import { useEffect, useMemo, useState } from 'react';
import {
  Bell,
  CreditCard,
  Database,
  Key,
  Palette,
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
import { BrandingSettingsTab } from '../components/settings/BrandingSettingsTab';
import {
  createApiKey,
  fetchAiInsightsSettings,
  fetchApiKeys,
  revokeApiKey,
  updateAiInsightsSettings,
  type AiInsightsSettings,
  type ApiKeySummary,
} from '../services/settingsApi';
import { getErrorMessage } from '../services/apiUtils';

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
  { id: 'branding', label: 'Branding', icon: Palette, requiredRole: 'admin' },
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
  const [keys, setKeys] = useState<ApiKeySummary[]>([]);
  const [name, setName] = useState('');
  const [expiresInDays, setExpiresInDays] = useState('90');
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [newlyCreatedKey, setNewlyCreatedKey] = useState<string | null>(null);
  const [revokingId, setRevokingId] = useState<string | null>(null);

  useEffect(() => {
    let mounted = true;
    (async () => {
      try {
        setLoading(true);
        setError(null);
        const response = await fetchApiKeys();
        if (!mounted) return;
        setKeys(response.keys);
      } catch (err) {
        if (!mounted) return;
        setError(getErrorMessage(err, 'Failed to load API keys'));
      } finally {
        if (mounted) setLoading(false);
      }
    })();
    return () => {
      mounted = false;
    };
  }, []);

  const submitCreateKey = async () => {
    const trimmedName = name.trim();
    if (trimmedName.length < 3) {
      setError('Key name must be at least 3 characters.');
      return;
    }

    const parsedExpires = Number.parseInt(expiresInDays, 10);
    if (Number.isNaN(parsedExpires) || parsedExpires < 1 || parsedExpires > 365) {
      setError('Expiration must be between 1 and 365 days.');
      return;
    }

    const optimisticKey: ApiKeySummary = {
      id: `optimistic-${Date.now()}`,
      name: trimmedName,
      key_prefix: 'creating...',
      created_at: new Date().toISOString(),
      last_used_at: null,
      expires_at: null,
      revoked_at: null,
      is_active: true,
    };

    const previousKeys = keys;
    setSaving(true);
    setError(null);
    setNewlyCreatedKey(null);
    setKeys([optimisticKey, ...keys]);

    try {
      const response = await createApiKey({
        name: trimmedName,
        expires_in_days: parsedExpires,
      });
      setKeys((current) => [response.key, ...current.filter((key) => key.id !== optimisticKey.id)]);
      setNewlyCreatedKey(response.plaintext_key);
      setName('');
    } catch (err) {
      setKeys(previousKeys);
      setError(getErrorMessage(err, 'Failed to create API key'));
    } finally {
      setSaving(false);
    }
  };

  const onRevoke = async (keyId: string) => {
    const previousKeys = keys;
    setRevokingId(keyId);
    setKeys((current) => current.map((key) => (key.id === keyId ? { ...key, is_active: false } : key)));
    try {
      await revokeApiKey(keyId);
    } catch (err) {
      setKeys(previousKeys);
      setError(getErrorMessage(err, 'Failed to revoke API key'));
    } finally {
      setRevokingId(null);
    }
  };

  return (
    <section data-testid="settings-panel-api">
      <h2 className="text-xl font-semibold mb-1">API Keys</h2>
      <p className="text-gray-500 text-sm mb-6">Programmatic access to your analytics data.</p>

      <div className="bg-white rounded-xl border border-gray-200 p-6">
        {error && (
          <div className="mb-4 rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
            {error}
          </div>
        )}
        {newlyCreatedKey && (
          <div className="mb-4 rounded-lg border border-emerald-200 bg-emerald-50 px-4 py-3 text-sm text-emerald-800">
            Save this key now (it will only be shown once): <span className="font-mono">{newlyCreatedKey}</span>
          </div>
        )}

        <div className="grid gap-3 md:grid-cols-[1fr_150px_auto] mb-5">
          <input
            value={name}
            onChange={(event) => setName(event.target.value)}
            placeholder="Key name (e.g. CI pipeline)"
            className="rounded-lg border border-gray-300 px-3 py-2 text-sm"
          />
          <input
            type="number"
            min={1}
            max={365}
            value={expiresInDays}
            onChange={(event) => setExpiresInDays(event.target.value)}
            className="rounded-lg border border-gray-300 px-3 py-2 text-sm"
            aria-label="Expires in days"
          />
          <button
            onClick={submitCreateKey}
            disabled={saving}
            className="rounded-lg bg-blue-600 px-4 py-2 text-sm font-medium text-white disabled:opacity-50"
          >
            {saving ? 'Creating...' : 'Create key'}
          </button>
        </div>

        <div className="space-y-3">
          {loading && <p className="text-sm text-gray-500">Loading keys...</p>}
          {!loading && keys.length === 0 && (
            <p className="text-sm text-gray-500">No API keys yet. Create one to get started.</p>
          )}
          {keys.map((key) => (
            <div key={key.id} className="rounded-lg border border-gray-200 px-4 py-3">
              <div className="flex items-center justify-between gap-3">
                <div>
                  <p className="font-medium text-gray-900">{key.name}</p>
                  <p className="text-xs text-gray-500">
                    Prefix: <span className="font-mono">{key.key_prefix}</span>
                  </p>
                </div>
                <button
                  onClick={() => onRevoke(key.id)}
                  disabled={!key.is_active || revokingId === key.id}
                  className="rounded border border-gray-300 px-3 py-1.5 text-xs text-gray-700 disabled:opacity-50"
                >
                  {!key.is_active ? 'Revoked' : revokingId === key.id ? 'Revoking...' : 'Revoke'}
                </button>
              </div>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}

function AiInsightsSettingsTab() {
  const [form, setForm] = useState<AiInsightsSettings>({
    enabled: true,
    model: 'gpt-4.1-mini',
    cadence: 'weekly',
    include_recommendations: true,
    max_insights_per_run: 5,
  });
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);
  const [entitled, setEntitled] = useState(true);
  const [entitlementReason, setEntitlementReason] = useState<string | null>(null);

  useEffect(() => {
    let mounted = true;
    (async () => {
      try {
        setLoading(true);
        setError(null);
        const response = await fetchAiInsightsSettings();
        if (!mounted) return;
        setForm(response.settings);
        setEntitled(response.entitled);
        setEntitlementReason(response.entitlement_reason);
      } catch (err) {
        if (!mounted) return;
        setError(getErrorMessage(err, 'Failed to load AI settings'));
      } finally {
        if (mounted) setLoading(false);
      }
    })();
    return () => {
      mounted = false;
    };
  }, []);

  const save = async () => {
    if (form.max_insights_per_run < 1 || form.max_insights_per_run > 20) {
      setError('Max insights per run must be between 1 and 20.');
      return;
    }

    const previousState = form;
    setSaving(true);
    setError(null);
    setSuccess(null);

    try {
      const response = await updateAiInsightsSettings(form);
      setForm(response.settings);
      setEntitled(response.entitled);
      setEntitlementReason(response.entitlement_reason);
      setSuccess('Saved AI insights settings.');
    } catch (err) {
      setForm(previousState);
      setError(getErrorMessage(err, 'Failed to save AI settings'));
    } finally {
      setSaving(false);
    }
  };

  return (
    <section data-testid="settings-panel-ai">
      <h2 className="text-xl font-semibold mb-1">AI Insights</h2>
      <p className="text-gray-500 text-sm mb-6">
        Configure AI-powered analysis and recommendations.
      </p>

      <div className="bg-white rounded-xl border border-gray-200 p-6">
        {error && (
          <div className="mb-4 rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
            {error}
          </div>
        )}
        {success && (
          <div className="mb-4 rounded-lg border border-emerald-200 bg-emerald-50 px-4 py-3 text-sm text-emerald-700">
            {success}
          </div>
        )}
        {!entitled && (
          <div className="mb-4 rounded-lg border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-700">
            AI Insights is not available on your current plan. {entitlementReason ?? ''}
          </div>
        )}
        {loading ? (
          <p className="text-sm text-gray-500">Loading AI settings...</p>
        ) : (
          <div className="space-y-4">
            <label className="flex items-center justify-between rounded-lg border border-gray-200 px-3 py-2">
              <span className="text-sm text-gray-700">Enable AI insights</span>
              <input
                type="checkbox"
                checked={form.enabled}
                onChange={(event) => setForm((current) => ({ ...current, enabled: event.target.checked }))}
                disabled={!entitled}
              />
            </label>
            <label className="block">
              <span className="mb-1 block text-sm text-gray-700">Model</span>
              <select
                value={form.model}
                onChange={(event) => setForm((current) => ({ ...current, model: event.target.value as AiInsightsSettings['model'] }))}
                className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm"
                disabled={!entitled}
              >
                <option value="gpt-4.1-mini">GPT-4.1 Mini</option>
                <option value="gpt-4.1">GPT-4.1</option>
                <option value="gpt-5-mini">GPT-5 Mini</option>
              </select>
            </label>
            <label className="block">
              <span className="mb-1 block text-sm text-gray-700">Insight cadence</span>
              <select
                value={form.cadence}
                onChange={(event) => setForm((current) => ({ ...current, cadence: event.target.value as AiInsightsSettings['cadence'] }))}
                className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm"
                disabled={!entitled}
              >
                <option value="daily">Daily</option>
                <option value="weekly">Weekly</option>
              </select>
            </label>
            <label className="block">
              <span className="mb-1 block text-sm text-gray-700">Max insights per run</span>
              <input
                type="number"
                min={1}
                max={20}
                value={form.max_insights_per_run}
                onChange={(event) => setForm((current) => ({ ...current, max_insights_per_run: Number.parseInt(event.target.value, 10) || 0 }))}
                className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm"
                disabled={!entitled}
              />
            </label>
            <label className="flex items-center justify-between rounded-lg border border-gray-200 px-3 py-2">
              <span className="text-sm text-gray-700">Include recommendations</span>
              <input
                type="checkbox"
                checked={form.include_recommendations}
                onChange={(event) => setForm((current) => ({ ...current, include_recommendations: event.target.checked }))}
                disabled={!entitled}
              />
            </label>
            <button
              onClick={save}
              disabled={saving || !entitled}
              className="rounded-lg bg-purple-600 px-4 py-2 text-sm font-medium text-white disabled:opacity-50"
            >
              {saving ? 'Saving...' : 'Save AI settings'}
            </button>
          </div>
        )}
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

  if (tab === 'branding') {
    return (
      <section data-testid="settings-panel-branding">
        <BrandingSettingsTab />
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
