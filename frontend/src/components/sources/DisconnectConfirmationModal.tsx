/**
 * Disconnect Confirmation Modal
 *
 * Confirmation dialog for disconnecting a data source.
 * Requires typing the source name to confirm the destructive action.
 *
 * Phase 3 — Subphase 3.6: Source Management Actions
 */

import { useState, useCallback, useEffect } from 'react';
import { X } from 'lucide-react';

import type { Source } from '../../types/sources';

interface DisconnectConfirmationModalProps {
  open: boolean;
  source: Source | null;
  disconnecting: boolean;
  onConfirm: (sourceId: string) => Promise<void>;
  onCancel: () => void;
}

/**
 * Modal for confirming source disconnection.
 *
 * Requires user to type the source name to prevent accidental deletion.
 * Warns about data sync stopping and credential removal.
 */
export function DisconnectConfirmationModal({
  open,
  source,
  disconnecting,
  onConfirm,
  onCancel,
}: DisconnectConfirmationModalProps) {
  const [confirmationText, setConfirmationText] = useState('');

  const handleClose = useCallback(() => {
    setConfirmationText('');
    onCancel();
  }, [onCancel]);

  const handleConfirm = useCallback(async () => {
    if (!source) return;
    try {
      await onConfirm(source.id);
      setConfirmationText('');
    } catch (err) {
      console.error('Disconnect failed:', err);
    }
  }, [source, onConfirm]);

  const isConfirmed = source ? confirmationText === source.displayName : false;

  useEffect(() => {
    if (!open) setConfirmationText('');
  }, [open]);

  if (!source) return null;

  if (!open) return null;

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/50"
      role="dialog"
      aria-modal="true"
      aria-labelledby="disconnect-modal-title"
      onClick={handleClose}
    >
      <div
        className="bg-white rounded-xl shadow-xl max-w-lg w-full max-h-[90vh] overflow-y-auto"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between border-b border-gray-200 px-6 py-4">
          <h2 id="disconnect-modal-title" className="text-lg font-semibold text-gray-900">
            Disconnect Data Source
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
          <div className="rounded-lg border border-amber-200 bg-amber-50 p-4 text-sm text-amber-900">
            <strong>Warning:</strong> This action cannot be undone.
          </div>

          <p className="text-sm text-gray-800">
            Disconnecting <strong>{source.displayName}</strong> will:
          </p>

          <ul className="list-disc pl-5 text-sm text-gray-700 space-y-1">
            <li>Stop all data syncing from this source</li>
            <li>Remove stored credentials</li>
            <li>
              Historical data will remain available in dashboards, but no new data will be synced
            </li>
          </ul>

          <p className="text-sm text-gray-800">
            To confirm, type <strong>{source.displayName}</strong> below:
          </p>

          <div>
            <label htmlFor="disconnect-source-name" className="block text-sm font-medium text-gray-900 mb-2">
              Source name
            </label>
            <input
              id="disconnect-source-name"
              type="text"
              value={confirmationText}
              onChange={(e) => setConfirmationText(e.target.value)}
              autoComplete="off"
              placeholder={source.displayName}
              className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm focus:ring-2 focus:ring-blue-500 focus:border-transparent"
            />
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
              onClick={handleConfirm}
              disabled={!isConfirmed || disconnecting}
              className="rounded-lg bg-red-600 px-4 py-2 text-sm font-medium text-white hover:bg-red-700 disabled:opacity-50 disabled:cursor-not-allowed"
            >
              {disconnecting ? 'Disconnecting…' : 'Disconnect'}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
