/**
 * Success Step Component
 *
 * Step 6 of the connection wizard.
 * Shows success confirmation and next steps.
 *
 * Phase 3 — Subphase 3.5: Connection Wizard Steps 4-6
 */

import type { DataSourceDefinition } from '../../../types/sourceConnection';

interface SuccessStepProps {
  platform: DataSourceDefinition;
  onConnectAnother?: () => void;
  onViewDashboard: () => void;
}

export function SuccessStep({ platform, onConnectAnother, onViewDashboard }: SuccessStepProps) {
  return (
    <div className="flex flex-col gap-8">
      <div className="rounded-lg border border-green-200 bg-green-50 p-4">
        <h3 className="text-sm font-semibold text-green-900 mb-1">Successfully Connected!</h3>
        <p className="text-sm text-green-800">
          {platform.displayName} is now connected and your data is syncing.
        </p>
      </div>

      <div className="flex flex-col gap-3">
        <h3 className="text-sm font-semibold text-gray-900">What&apos;s next?</h3>
        <ul className="list-disc pl-5 space-y-2 text-sm text-gray-700">
          <li>View your dashboard to see incoming data</li>
          <li>Connect another data source for richer insights</li>
          <li>Configure sync settings in the Data Sources page</li>
          <li>Set up alerts for data quality issues</li>
        </ul>
      </div>

      <div className="flex flex-wrap justify-end gap-2">
        {onConnectAnother && (
          <button
            type="button"
            onClick={onConnectAnother}
            className="rounded-lg border border-gray-300 bg-white px-4 py-2 text-sm font-medium text-gray-700 hover:bg-gray-50"
          >
            Connect Another Source
          </button>
        )}
        <button
          type="button"
          onClick={onViewDashboard}
          className="rounded-lg bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700"
        >
          Go to Dashboard
        </button>
      </div>
    </div>
  );
}
