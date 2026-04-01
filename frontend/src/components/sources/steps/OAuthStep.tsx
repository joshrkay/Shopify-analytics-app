/**
 * OAuth Step Component
 *
 * Step 2 of the connection wizard.
 * Shows OAuth authorization explanation, redirect button, loading state, and error handling.
 *
 * Phase 3 — Subphase 3.4: Connection Wizard Steps 1-3
 */

import { Loader2 } from 'lucide-react';
import type { DataSourceDefinition } from '../../../types/sourceConnection';

interface OAuthStepProps {
  platform: DataSourceDefinition;
  loading: boolean;
  error: string | null;
  onStartOAuth: () => Promise<void>;
  onCancel: () => void;
}

export function OAuthStep({ platform, loading, error, onStartOAuth, onCancel }: OAuthStepProps) {
  return (
    <div className="flex flex-col gap-8">
      <div className="flex flex-col gap-2 text-center">
        <h2 className="text-xl font-semibold text-gray-900">Authorize {platform.displayName}</h2>
        <p className="text-sm text-gray-600">
          {loading
            ? `Redirecting to ${platform.displayName}...`
            : `Connect your ${platform.displayName} account securely via OAuth.`}
        </p>
      </div>

      {loading && (
        <div className="flex justify-center py-4">
          <Loader2 className="h-10 w-10 animate-spin text-blue-600" aria-label="Loading" />
        </div>
      )}

      {error && (
        <div className="rounded-lg border border-red-200 bg-red-50 p-4">
          <h3 className="text-sm font-semibold text-red-900 mb-1">Authorization Failed</h3>
          <p className="text-sm text-red-800">{error}</p>
        </div>
      )}

      {!loading && (
        <div className="flex flex-col gap-3">
          <h3 className="text-sm font-semibold text-gray-900">How it works</h3>
          <ol className="list-decimal pl-5 space-y-2 text-sm text-gray-700">
            <li>Click &quot;Authorize&quot; below to open {platform.displayName}</li>
            <li>Sign in and grant read-only access</li>
            <li>You&apos;ll be redirected back here automatically</li>
            <li>Select which accounts to sync</li>
          </ol>
        </div>
      )}

      <div className="flex flex-wrap justify-end gap-2">
        <button
          type="button"
          onClick={onCancel}
          className="rounded-lg border border-gray-300 bg-white px-4 py-2 text-sm font-medium text-gray-700 hover:bg-gray-50"
        >
          Cancel
        </button>
        <button
          type="button"
          onClick={onStartOAuth}
          disabled={loading}
          className="inline-flex items-center justify-center gap-2 rounded-lg bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed"
        >
          {loading && <Loader2 className="h-4 w-4 animate-spin" />}
          {error ? 'Try Again' : `Authorize ${platform.displayName}`}
        </button>
      </div>
    </div>
  );
}
