/**
 * Notifications Settings Tab
 *
 * Lets users control which notification events they receive,
 * and through which channels (in-app vs email).
 *
 * Data:
 *   GET /api/notifications/preferences  → load current preferences
 *   PUT /api/notifications/preferences  → save changes
 *
 * The backend returns one row per event type (10 total). If no DB row
 * exists for a type, the backend defaults both channels to enabled=true.
 */

import { useEffect, useState, useCallback } from 'react';
import { Bell, Mail, Monitor, Save } from 'lucide-react';
import {
  getNotificationPreferences,
  updateNotificationPreferences,
  type NotificationPreferenceItem,
} from '../../services/notificationsPrefsApi';

// ---------------------------------------------------------------------------
// Event type metadata — labels, descriptions, importance badge
// ---------------------------------------------------------------------------

interface EventMeta {
  label: string;
  description: string;
  important: boolean;
}

const EVENT_META: Record<string, EventMeta> = {
  connector_failed: {
    label: 'Connector Failed',
    description: 'A data source connector stops syncing or encounters an error.',
    important: true,
  },
  sync_completed: {
    label: 'Sync Completed',
    description: 'A scheduled data sync finishes successfully.',
    important: false,
  },
  action_requires_approval: {
    label: 'Action Requires Approval',
    description: 'An AI-recommended action is waiting for your review.',
    important: true,
  },
  action_executed: {
    label: 'Action Executed',
    description: 'An approved action has been carried out.',
    important: false,
  },
  action_failed: {
    label: 'Action Failed',
    description: 'An action could not be completed.',
    important: true,
  },
  incident_declared: {
    label: 'Incident Declared',
    description: 'A data health or platform incident has been opened.',
    important: true,
  },
  incident_resolved: {
    label: 'Incident Resolved',
    description: 'An active incident has been closed.',
    important: false,
  },
  alert_triggered: {
    label: 'Alert Triggered',
    description: 'A metric threshold alert rule has fired.',
    important: true,
  },
  insight_generated: {
    label: 'Insight Generated',
    description: 'A new AI insight is available in your feed.',
    important: false,
  },
  recommendation_created: {
    label: 'Recommendation Created',
    description: 'A new AI recommendation is ready for review.',
    important: false,
  },
};

// Ordered groups for display
const GROUPS: { title: string; eventTypes: string[] }[] = [
  {
    title: 'Connectors & Sync',
    eventTypes: ['connector_failed', 'sync_completed'],
  },
  {
    title: 'Actions',
    eventTypes: ['action_requires_approval', 'action_executed', 'action_failed'],
  },
  {
    title: 'Incidents',
    eventTypes: ['incident_declared', 'incident_resolved'],
  },
  {
    title: 'Insights & Alerts',
    eventTypes: ['alert_triggered', 'insight_generated', 'recommendation_created'],
  },
];

// ---------------------------------------------------------------------------
// Toggle component
// ---------------------------------------------------------------------------

interface ToggleProps {
  enabled: boolean;
  onChange: (val: boolean) => void;
  disabled?: boolean;
}

function Toggle({ enabled, onChange, disabled }: ToggleProps) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={enabled}
      disabled={disabled}
      onClick={() => onChange(!enabled)}
      className={`relative inline-flex h-5 w-9 flex-shrink-0 cursor-pointer rounded-full border-2 border-transparent
        transition-colors duration-200 ease-in-out focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-1
        disabled:cursor-not-allowed disabled:opacity-50
        ${enabled ? 'bg-blue-600' : 'bg-gray-200'}`}
    >
      <span
        className={`inline-block h-4 w-4 transform rounded-full bg-white shadow ring-0
          transition duration-200 ease-in-out
          ${enabled ? 'translate-x-4' : 'translate-x-0'}`}
      />
    </button>
  );
}

// ---------------------------------------------------------------------------
// Main component
// ---------------------------------------------------------------------------

export function NotificationsSettingsTab() {
  const [prefs, setPrefs] = useState<NotificationPreferenceItem[]>([]);
  const [original, setOriginal] = useState<NotificationPreferenceItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [savedOk, setSavedOk] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await getNotificationPreferences();
      setPrefs(data.preferences);
      setOriginal(data.preferences);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load notification preferences.');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  const isDirty = JSON.stringify(prefs) !== JSON.stringify(original);

  function setPref(eventType: string, field: 'in_app_enabled' | 'email_enabled', value: boolean) {
    setPrefs((prev) =>
      prev.map((p) =>
        p.event_type === eventType ? { ...p, [field]: value } : p,
      ),
    );
    setSavedOk(false);
  }

  function getPref(eventType: string): NotificationPreferenceItem {
    return (
      prefs.find((p) => p.event_type === eventType) ?? {
        event_type: eventType,
        in_app_enabled: true,
        email_enabled: true,
      }
    );
  }

  async function handleSave() {
    setSaving(true);
    setError(null);
    setSavedOk(false);
    try {
      const updated = await updateNotificationPreferences(prefs);
      setPrefs(updated.preferences);
      setOriginal(updated.preferences);
      setSavedOk(true);
      setTimeout(() => setSavedOk(false), 3000);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to save preferences.');
    } finally {
      setSaving(false);
    }
  }

  // -------------------------------------------------------------------------
  // Render
  // -------------------------------------------------------------------------

  if (loading) {
    return (
      <div className="space-y-4">
        {Array.from({ length: 4 }).map((_, i) => (
          <div key={i} className="border border-gray-200 rounded-lg p-4 animate-pulse">
            <div className="h-4 bg-gray-200 rounded w-32 mb-3" />
            <div className="space-y-3">
              {Array.from({ length: 2 }).map((_, j) => (
                <div key={j} className="h-12 bg-gray-100 rounded" />
              ))}
            </div>
          </div>
        ))}
      </div>
    );
  }

  return (
    <div className="space-y-6" data-testid="notifications-settings-tab">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-xl font-semibold text-gray-900">Notification Preferences</h2>
          <p className="text-sm text-gray-500 mt-0.5">
            Choose which events notify you and through which channels.
          </p>
        </div>
        <button
          onClick={handleSave}
          disabled={!isDirty || saving}
          className="flex items-center gap-2 px-4 py-2 bg-blue-600 text-white text-sm font-medium
            rounded-lg hover:bg-blue-700 transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
        >
          <Save className="w-4 h-4" />
          {saving ? 'Saving…' : 'Save Changes'}
        </button>
      </div>

      {/* Error */}
      {error && (
        <div className="bg-red-50 border border-red-200 rounded-lg px-4 py-3 text-sm text-red-700">
          {error}
        </div>
      )}

      {/* Success */}
      {savedOk && (
        <div className="bg-green-50 border border-green-200 rounded-lg px-4 py-3 text-sm text-green-700">
          Preferences saved.
        </div>
      )}

      {/* Channel legend */}
      <div className="flex items-center gap-6 text-sm text-gray-500 bg-gray-50 rounded-lg px-4 py-3">
        <span className="flex items-center gap-1.5">
          <Monitor className="w-4 h-4" /> In-App — shown in the notification inbox
        </span>
        <span className="flex items-center gap-1.5">
          <Mail className="w-4 h-4" /> Email — sent to your account email
        </span>
      </div>

      {/* Column headers */}
      <div className="grid grid-cols-[1fr_80px_80px] gap-2 px-4 text-xs font-medium text-gray-400 uppercase tracking-wide">
        <span>Event</span>
        <span className="text-center">In-App</span>
        <span className="text-center">Email</span>
      </div>

      {/* Groups */}
      {GROUPS.map((group) => (
        <section key={group.title} className="border border-gray-200 rounded-lg overflow-hidden">
          <div className="bg-gray-50 px-4 py-2 border-b border-gray-200">
            <h3 className="text-xs font-semibold text-gray-500 uppercase tracking-wide">
              {group.title}
            </h3>
          </div>
          <div className="divide-y divide-gray-100">
            {group.eventTypes.map((eventType) => {
              const meta = EVENT_META[eventType];
              const pref = getPref(eventType);
              if (!meta) return null;
              return (
                <div
                  key={eventType}
                  className="grid grid-cols-[1fr_80px_80px] items-center gap-2 px-4 py-3"
                >
                  {/* Label + description */}
                  <div>
                    <div className="flex items-center gap-2">
                      <span className="text-sm font-medium text-gray-900">{meta.label}</span>
                      {meta.important && (
                        <span className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-xs font-medium bg-red-50 text-red-600">
                          <Bell className="w-2.5 h-2.5" />
                          Important
                        </span>
                      )}
                    </div>
                    <p className="text-xs text-gray-400 mt-0.5">{meta.description}</p>
                  </div>

                  {/* In-app toggle */}
                  <div className="flex justify-center">
                    <Toggle
                      enabled={pref.in_app_enabled}
                      onChange={(val) => setPref(eventType, 'in_app_enabled', val)}
                      disabled={saving}
                    />
                  </div>

                  {/* Email toggle */}
                  <div className="flex justify-center">
                    <Toggle
                      enabled={pref.email_enabled}
                      onChange={(val) => setPref(eventType, 'email_enabled', val)}
                      disabled={saving}
                    />
                  </div>
                </div>
              );
            })}
          </div>
        </section>
      ))}
    </div>
  );
}

export default NotificationsSettingsTab;
