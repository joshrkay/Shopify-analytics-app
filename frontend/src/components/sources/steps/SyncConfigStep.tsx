/**
 * Sync Config Step Component
 *
 * Step 4 of the connection wizard.
 * Configures historical data range, sync frequency, and metrics.
 *
 * Phase 3 — Subphase 3.5: Connection Wizard Steps 4-6
 */

import { Loader2 } from 'lucide-react';
import type { DataSourceDefinition, WizardSyncConfig } from '../../../types/sourceConnection';

interface SyncConfigStepProps {
  platform: DataSourceDefinition;
  syncConfig: WizardSyncConfig;
  onUpdateConfig: (config: Partial<WizardSyncConfig>) => void;
  onConfirm: () => void;
  onBack: () => void;
  loading: boolean;
}

const RANGE_OPTIONS = [
  { label: 'Last 30 days', value: '30d' },
  { label: 'Last 90 days (Recommended)', value: '90d' },
  { label: 'Last 365 days', value: '365d' },
  { label: 'All time', value: 'all' },
];

const FREQUENCY_OPTIONS = [
  { label: 'Every 1 hour (Recommended)', value: 'hourly' },
  { label: 'Every 6 hours', value: 'six_hourly' },
  { label: 'Daily', value: 'daily' },
];

export function SyncConfigStep({
  platform,
  syncConfig,
  onUpdateConfig,
  onConfirm,
  onBack,
  loading,
}: SyncConfigStepProps) {
  return (
    <div className="flex flex-col gap-8">
      <div className="flex flex-col gap-2">
        <h2 className="text-xl font-semibold text-gray-900">Configure Sync</h2>
        <p className="text-sm text-gray-600">
          Choose how much data to import and how often to sync from {platform.displayName}.
        </p>
      </div>

      <div>
        <label htmlFor="sync-historical-range" className="block text-sm font-medium text-gray-900 mb-2">
          Historical Data Range
        </label>
        <select
          id="sync-historical-range"
          value={syncConfig.historicalRange}
          onChange={(e) =>
            onUpdateConfig({ historicalRange: e.target.value as WizardSyncConfig['historicalRange'] })
          }
          className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm text-gray-900 focus:ring-2 focus:ring-blue-500 focus:border-transparent"
        >
          {RANGE_OPTIONS.map((opt) => (
            <option key={opt.value} value={opt.value}>
              {opt.label}
            </option>
          ))}
        </select>
        <p className="mt-1 text-xs text-gray-500">How far back should we import your historical data?</p>
      </div>

      <div>
        <label htmlFor="sync-frequency" className="block text-sm font-medium text-gray-900 mb-2">
          Sync Frequency
        </label>
        <select
          id="sync-frequency"
          value={syncConfig.frequency}
          onChange={(e) =>
            onUpdateConfig({ frequency: e.target.value as WizardSyncConfig['frequency'] })
          }
          className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm text-gray-900 focus:ring-2 focus:ring-blue-500 focus:border-transparent"
        >
          {FREQUENCY_OPTIONS.map((opt) => (
            <option key={opt.value} value={opt.value}>
              {opt.label}
            </option>
          ))}
        </select>
        <p className="mt-1 text-xs text-gray-500">How often should we sync new data?</p>
      </div>

      <div className="rounded-lg border border-gray-200 bg-gray-50 p-4 text-sm text-gray-700">
        <strong>Note:</strong> More frequent syncs may impact API rate limits and costs. Initial sync will
        take approximately 5-10 minutes depending on your data volume.
      </div>

      <div className="flex flex-wrap justify-end gap-2">
        <button
          type="button"
          onClick={onBack}
          className="rounded-lg border border-gray-300 bg-white px-4 py-2 text-sm font-medium text-gray-700 hover:bg-gray-50"
        >
          Back
        </button>
        <button
          type="button"
          onClick={onConfirm}
          disabled={loading}
          className="inline-flex items-center justify-center gap-2 rounded-lg bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed"
        >
          {loading && <Loader2 className="h-4 w-4 animate-spin" />}
          Start Sync →
        </button>
      </div>
    </div>
  );
}
