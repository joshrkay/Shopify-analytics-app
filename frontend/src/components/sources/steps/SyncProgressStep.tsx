/**
 * Sync Progress Step Component
 *
 * Step 5 of the connection wizard.
 * Shows real-time sync progress with a progress bar and stage indicators.
 * Uses DetailedSyncProgress from the wizard hook for accurate percentages.
 *
 * Phase 3 — Subphase 3.5: Connection Wizard Steps 4-6
 */

import { useState } from 'react';
import { Loader2 } from 'lucide-react';
import { cn } from '../../ui/utils';
import type { DataSourceDefinition, DetailedSyncProgress } from '../../../types/sourceConnection';

interface SyncProgressStepProps {
  platform: DataSourceDefinition;
  progress: DetailedSyncProgress | null;
  error: string | null;
  onNavigateDashboard?: () => void;
}

function getSyncStages(progress: DetailedSyncProgress | null) {
  if (!progress) {
    return [
      { label: 'Connecting to source', status: 'pending' as const },
      { label: 'Retrieving account information', status: 'pending' as const },
      { label: 'Fetching data', status: 'pending' as const },
      { label: 'Processing metrics', status: 'pending' as const },
    ];
  }

  const isRunning = progress.status === 'running';
  const isComplete = progress.status === 'completed' || progress.lastSyncStatus === 'succeeded';
  const isFailed = progress.status === 'failed' || progress.lastSyncStatus === 'failed';

  if (isComplete) {
    return [
      { label: 'Connected to source', status: 'completed' as const },
      { label: 'Retrieved account information', status: 'completed' as const },
      { label: 'Fetched data', status: 'completed' as const },
      { label: 'Processed metrics', status: 'completed' as const },
    ];
  }

  if (isFailed) {
    return [
      { label: 'Connected to source', status: 'completed' as const },
      { label: 'Retrieved account information', status: 'completed' as const },
      { label: 'Fetching data', status: 'failed' as const },
      { label: 'Processing metrics', status: 'pending' as const },
    ];
  }

  if (isRunning) {
    return [
      { label: 'Connected to source', status: 'completed' as const },
      { label: 'Retrieved account information', status: 'completed' as const },
      { label: 'Fetching data', status: 'in_progress' as const },
      { label: 'Processing metrics', status: 'pending' as const },
    ];
  }

  return [
    { label: 'Connecting to source', status: 'in_progress' as const },
    { label: 'Retrieving account information', status: 'pending' as const },
    { label: 'Fetching data', status: 'pending' as const },
    { label: 'Processing metrics', status: 'pending' as const },
  ];
}

function getStageIcon(status: 'completed' | 'in_progress' | 'pending' | 'failed') {
  switch (status) {
    case 'completed':
      return '✓';
    case 'in_progress':
      return '◎';
    case 'failed':
      return '✗';
    default:
      return '○';
  }
}

export function SyncProgressStep({ platform, progress, error, onNavigateDashboard }: SyncProgressStepProps) {
  const [ctaDismissed, setCtaDismissed] = useState(false);
  const stages = getSyncStages(progress);
  const percent = progress?.percentComplete ?? 0;

  return (
    <div className="flex flex-col gap-8">
      <div className="flex flex-col gap-2 items-center text-center">
        <div className="flex items-center justify-center gap-2">
          <Loader2 className="h-5 w-5 animate-spin text-blue-600 shrink-0" aria-label="Loading" />
          <h2 className="text-xl font-semibold text-gray-900">Syncing your {platform.displayName} data</h2>
        </div>
      </div>

      <div className="w-full">
        <div className="h-2 w-full overflow-hidden rounded-full bg-gray-200">
          <div
            className="h-full rounded-full bg-blue-600 transition-[width] duration-300"
            style={{ width: `${Math.min(100, Math.max(0, percent))}%` }}
            role="progressbar"
            aria-valuenow={percent}
            aria-valuemin={0}
            aria-valuemax={100}
          />
        </div>
      </div>

      <div className="flex flex-col gap-2">
        {stages.map((stage) => (
          <div key={stage.label} className="flex items-center gap-2">
            <span
              className={cn(
                'text-sm w-4 text-center',
                stage.status === 'failed'
                  ? 'text-red-600'
                  : stage.status === 'completed'
                    ? 'text-green-600'
                    : 'text-gray-500'
              )}
            >
              {getStageIcon(stage.status)}
            </span>
            <span
              className={cn(
                'text-sm',
                stage.status === 'in_progress' ? 'font-semibold text-gray-900' : '',
                stage.status === 'pending' ? 'text-gray-500' : 'text-gray-800'
              )}
            >
              {stage.label}
            </span>
          </div>
        ))}
      </div>

      {error && (
        <div className="rounded-lg border border-red-200 bg-red-50 p-4">
          <h3 className="text-sm font-semibold text-red-900 mb-1">Sync Error</h3>
          <p className="text-sm text-red-800">{error}</p>
        </div>
      )}

      <div className="rounded-lg border border-blue-200 bg-blue-50 p-4 text-sm text-blue-900">
        Feel free to explore the app while your data syncs. We&apos;ll notify you when it&apos;s complete.
      </div>

      {!error && !ctaDismissed && onNavigateDashboard && (
        <div className="flex flex-wrap justify-end gap-2">
          <button
            type="button"
            onClick={() => setCtaDismissed(true)}
            className="rounded-lg border border-gray-300 bg-white px-4 py-2 text-sm font-medium text-gray-700 hover:bg-gray-50"
          >
            Stay here
          </button>
          <button
            type="button"
            onClick={onNavigateDashboard}
            className="rounded-lg bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700"
          >
            Continue to Dashboard
          </button>
        </div>
      )}
    </div>
  );
}
