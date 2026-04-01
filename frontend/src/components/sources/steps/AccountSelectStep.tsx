/**
 * Account Select Step Component
 *
 * Step 3 of the connection wizard.
 * Shows discoverable ad accounts with checkboxes for selection.
 * Displays account ID, status badge, and last 30-day spend.
 *
 * Phase 3 — Subphase 3.4: Connection Wizard Steps 1-3
 */

import { Loader2 } from 'lucide-react';
import { cn } from '../../ui/utils';
import type { AccountOption } from '../../../types/sourceConnection';

interface AccountSelectStepProps {
  accounts: AccountOption[];
  selectedAccountIds: string[];
  loading: boolean;
  error: string | null;
  onToggleAccount: (accountId: string) => void;
  onSelectAll: () => void;
  onDeselectAll: () => void;
  onConfirm: () => void;
  onBack: () => void;
}

function formatSpend(spend: number | null): string {
  if (spend === null) return 'No spend data';
  return `$${spend.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
}

export function AccountSelectStep({
  accounts,
  selectedAccountIds,
  loading,
  error,
  onToggleAccount,
  onSelectAll,
  onDeselectAll,
  onConfirm,
  onBack,
}: AccountSelectStepProps) {
  const selectedCount = selectedAccountIds.length;

  if (loading) {
    return (
      <div className="flex flex-col items-center gap-4 py-8">
        <Loader2 className="h-10 w-10 animate-spin text-blue-600" aria-label="Loading" />
        <p className="text-sm text-gray-600">Loading accounts...</p>
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-8">
      <div className="flex flex-col gap-2">
        <h2 className="text-xl font-semibold text-gray-900">Select Accounts</h2>
        <p className="text-sm text-gray-600">Choose which accounts to sync data from.</p>
      </div>

      {error && (
        <div className="rounded-lg border border-red-200 bg-red-50 p-4 text-sm text-red-800">{error}</div>
      )}

      {accounts.length === 0 && !error ? (
        <div className="rounded-lg border border-amber-200 bg-amber-50 p-4 text-sm text-amber-900">
          No accounts found. Go back and re-authorize to try again.
        </div>
      ) : (
        <>
          <div className="flex gap-4">
            <button
              type="button"
              onClick={onSelectAll}
              className="text-sm font-medium text-blue-600 hover:text-blue-800"
            >
              Select All
            </button>
            <button
              type="button"
              onClick={onDeselectAll}
              className="text-sm font-medium text-blue-600 hover:text-blue-800"
            >
              Deselect All
            </button>
          </div>

          <div className="flex flex-col gap-2">
            {accounts.map((account) => (
              <div
                key={account.id}
                className="rounded-lg border border-gray-200 bg-white p-3"
              >
                <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
                  <label className="flex items-start gap-3 cursor-pointer flex-1 min-w-0">
                    <input
                      type="checkbox"
                      className="mt-1 h-4 w-4 rounded border-gray-300 text-blue-600 focus:ring-blue-500"
                      checked={selectedAccountIds.includes(account.id)}
                      onChange={() => onToggleAccount(account.id)}
                    />
                    <span className="min-w-0">
                      <span className="block text-sm font-medium text-gray-900">{account.accountName}</span>
                      <span className="block text-xs text-gray-500">ID: {account.accountId}</span>
                    </span>
                  </label>
                  <div className="flex items-center gap-3 pl-7 sm:pl-0 shrink-0">
                    <span
                      className={cn(
                        'inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium',
                        account.isEnabled ? 'bg-green-100 text-green-800' : 'bg-gray-100 text-gray-700'
                      )}
                    >
                      {account.isEnabled ? 'Active' : 'Inactive'}
                    </span>
                    <span className="text-xs text-gray-500 whitespace-nowrap">
                      {formatSpend(account.last30dSpend)}
                    </span>
                  </div>
                </div>
              </div>
            ))}
          </div>
        </>
      )}

      <div className="rounded-lg border border-blue-200 bg-blue-50 p-4 text-sm text-blue-900">
        You can change this later in settings.
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
          disabled={selectedCount === 0}
          className="rounded-lg bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed"
        >
          {selectedCount > 0 ? `Connect (${selectedCount})` : 'Connect'} →
        </button>
      </div>
    </div>
  );
}
