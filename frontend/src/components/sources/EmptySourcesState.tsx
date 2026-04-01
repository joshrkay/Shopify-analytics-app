/**
 * Empty Sources State Component
 *
 * Enhanced empty state for the Data Sources page when no connections exist.
 * Shows a hero CTA, a 2x2 grid of popular integrations, and a browse-all button.
 *
 * Phase 3 — Subphase 3.3: Source Catalog Page
 */

import { Database } from 'lucide-react';
import type { DataSourceDefinition } from '../../types/sourceConnection';
import { IntegrationCard } from './IntegrationCard';

interface EmptySourcesStateProps {
  catalog: DataSourceDefinition[];
  onConnect: (platform: DataSourceDefinition) => void;
  onBrowseAll: () => void;
}

export function EmptySourcesState({ catalog, onConnect, onBrowseAll }: EmptySourcesStateProps) {
  const popularSources = catalog.slice(0, 4);

  return (
    <div className="flex flex-col gap-10">
      <div className="rounded-xl border border-gray-200 bg-white overflow-hidden">
        <div className="flex flex-col md:flex-row md:items-stretch">
          <div className="flex flex-1 flex-col items-center justify-center gap-4 p-8 md:p-10 bg-gray-50 border-b md:border-b-0 md:border-r border-gray-200">
            <div className="flex h-16 w-16 items-center justify-center rounded-full bg-blue-100 text-blue-600">
              <Database className="h-8 w-8" aria-hidden />
            </div>
          </div>
          <div className="flex flex-1 flex-col justify-center gap-4 p-8 md:p-10">
            <h2 className="text-lg font-semibold text-gray-900">No data sources connected yet</h2>
            <p className="text-sm text-gray-600">
              Connect your Shopify store or ad platforms to start syncing data and unlocking
              insights.
            </p>
            <div>
              <button
                type="button"
                onClick={onBrowseAll}
                className="inline-flex items-center justify-center rounded-lg bg-blue-600 px-4 py-2.5 text-sm font-medium text-white hover:bg-blue-700"
              >
                Connect Your First Source
              </button>
            </div>
          </div>
        </div>
      </div>

      {popularSources.length > 0 && (
        <div className="flex flex-col gap-4">
          <h2 className="text-base font-semibold text-gray-900">Popular Integrations</h2>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            {popularSources.map((platform) => (
              <IntegrationCard
                key={platform.id}
                platform={platform}
                isConnected={false}
                onConnect={onConnect}
              />
            ))}
          </div>
        </div>
      )}

      {catalog.length > 4 && (
        <div className="flex justify-center">
          <button
            type="button"
            onClick={onBrowseAll}
            className="text-sm font-medium text-blue-600 hover:text-blue-800"
          >
            {`Browse all ${catalog.length}+ sources`}
          </button>
        </div>
      )}
    </div>
  );
}
