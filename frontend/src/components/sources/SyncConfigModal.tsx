/**
 * Sync Configuration Modal
 *
 * Modal for configuring data source sync settings.
 * Allows updating sync frequency and optionally enabled data streams.
 *
 * Reuses patterns from BackfillModal for consistent UX.
 *
 * Phase 3 — Subphase 3.6: Source Management Actions
 */

import { useState, useCallback, useEffect } from 'react';
import { X, Loader2 } from 'lucide-react';

import type { Source } from '../../types/sources';
import type { SyncFrequency, UpdateSyncConfigRequest } from '../../types/sourceConnection';

interface SyncConfigModalProps {
  open: boolean;
  source: Source | null;
  configuring: boolean;
  onSave: (sourceId: string, config: UpdateSyncConfigRequest) => Promise<void>;
  onCancel: () => void;
}

const FREQUENCY_OPTIONS = [
  { label: 'Hourly', value: 'hourly' },
  { label: 'Daily', value: 'daily' },
  { label: 'Weekly', value: 'weekly' },
];

/**
 * Modal for configuring sync frequency.
 */
export function SyncConfigModal({
  open,
  source,
  configuring,
  onSave,
  onCancel,
}: SyncConfigModalProps) {
  const [frequency, setFrequency] = useState<SyncFrequency>('daily');
  const [success, setSuccess] = useState(false);

  useEffect(() => {
    if (open) {
      setFrequency('daily');
      setSuccess(false);
    }
  }, [open]);

  const handleClose = useCallback(() => {
    setFrequency('daily');
    setSuccess(false);
    onCancel();
  }, [onCancel]);

  const handleSave = useCallback(async () => {
    if (!source) return;

    try {
      await onSave(source.id, { sync_frequency: frequency });
      setSuccess(true);
      setTimeout(() => {
        handleClose();
      }, 1500);
    } catch (err) {
      console.error('Failed to update sync config:', err);
    }
  }, [source, frequency, onSave, handleClose]);

  if (!source) return null;

  if (!open) return null;

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/50"
      role="dialog"
      aria-modal="true"
      aria-labelledby="sync-config-modal-title"
      onClick={handleClose}
    >
      <div
        className="bg-white rounded-xl shadow-xl max-w-md w-full max-h-[90vh] overflow-y-auto"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between border-b border-gray-200 px-6 py-4">
          <h2 id="sync-config-modal-title" className="text-lg font-semibold text-gray-900">
            Configure Sync Settings
          </h2>
          <button
            type="button"
            onClick={handleClose}
            className="p-2 hover:bg-gray-100 rounded-lg"
            aria-label="Close"
          >
            <X className="w-5 h-5 text-gray-600" />
          </button>
        </div>

        <div className="p-6 flex flex-col gap-4">
          {success && (
            <div className="rounded-lg border border-green-200 bg-green-50 p-4 text-sm text-green-800">
              Sync configuration updated successfully!
            </div>
          )}

          <p className="text-sm text-gray-600">
            Configure how often data should sync from {source.displayName}.
          </p>

          <div>
            <label htmlFor="sync-frequency-select" className="block text-sm font-medium text-gray-900 mb-2">
              Sync Frequency
            </label>
            <select
              id="sync-frequency-select"
              value={frequency}
              onChange={(e) => setFrequency(e.target.value as SyncFrequency)}
              disabled={configuring || success}
              className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm text-gray-900 focus:ring-2 focus:ring-blue-500 focus:border-transparent disabled:opacity-50"
            >
              {FREQUENCY_OPTIONS.map((opt) => (
                <option key={opt.value} value={opt.value}>
                  {opt.label}
                </option>
              ))}
            </select>
            <p className="mt-1 text-xs text-gray-500">How frequently should we sync data from this source?</p>
          </div>

          <div className="rounded-lg border border-gray-200 bg-gray-50 p-4 text-sm text-gray-700">
            <strong>Note:</strong> More frequent syncs may impact API rate limits and costs. Daily syncs are
            recommended for most use cases.
          </div>

          <div className="flex flex-wrap justify-end gap-2 pt-2 border-t border-gray-200">
            <button
              type="button"
              onClick={handleClose}
              className="rounded-lg border border-gray-300 bg-white px-4 py-2 text-sm font-medium text-gray-700 hover:bg-gray-50"
            >
              Cancel
            </button>
            <button
              type="button"
              onClick={handleSave}
              disabled={configuring || success}
              className="inline-flex items-center justify-center gap-2 rounded-lg bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed"
            >
              {configuring && <Loader2 className="h-4 w-4 animate-spin" />}
              Save
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
