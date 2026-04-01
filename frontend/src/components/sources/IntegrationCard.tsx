/**
 * Integration Card Component
 *
 * Displays a data source platform in the catalog/browse grid on the sources page.
 * Shows platform name, description, and a Connect button.
 * Already-connected platforms show a "Connected" badge.
 *
 * Phase 3 — Subphase 3.3: Source Catalog Page
 */

import { cn } from '../ui/utils';
import type { DataSourceDefinition } from '../../types/sourceConnection';

interface IntegrationCardProps {
  platform: DataSourceDefinition;
  isConnected: boolean;
  onConnect: (platform: DataSourceDefinition) => void;
}

export function IntegrationCard({ platform, isConnected, onConnect }: IntegrationCardProps) {
  return (
    <div
      className={cn(
        'rounded-lg border border-gray-200 bg-white p-4',
        'flex flex-col gap-3'
      )}
    >
      <div className="flex items-start justify-between gap-2">
        <h3 className="text-base font-semibold text-gray-900">{platform.displayName}</h3>
        {isConnected && (
          <span className="shrink-0 inline-flex items-center rounded-full bg-green-100 px-2 py-0.5 text-xs font-medium text-green-800">
            Connected
          </span>
        )}
      </div>

      <p className="text-sm text-gray-600">{platform.description}</p>

      <button
        type="button"
        onClick={() => onConnect(platform)}
        disabled={isConnected || !platform.isEnabled}
        className={cn(
          'w-full rounded-lg px-4 py-2.5 text-sm font-medium transition-colors',
          isConnected || !platform.isEnabled
            ? 'cursor-not-allowed bg-gray-100 text-gray-400'
            : 'bg-blue-600 text-white hover:bg-blue-700'
        )}
      >
        {isConnected ? 'Connected' : platform.isEnabled ? 'Connect →' : 'Coming Soon'}
      </button>
    </div>
  );
}
