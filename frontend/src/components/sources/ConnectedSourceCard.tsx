/**
 * Connected Source Card Component
 *
 * Displays a connected data source with status indicator, sync info, and action buttons.
 * Extracted from the inline rendering in DataSources.tsx for reuse and testability.
 *
 * Phase 3 — Subphase 3.3: Source Catalog Page
 */

import { cn } from '../ui/utils';
import type { Source, SourceStatus } from '../../types/sources';
import { PLATFORM_DISPLAY_NAMES } from '../../types/sources';

interface ConnectedSourceCardProps {
  source: Source;
  onManage: (source: Source) => void;
  onDisconnect: (source: Source) => void;
  onTestConnection: (source: Source) => void;
  testing?: boolean;
}

function getStatusBadge(status: SourceStatus) {
  const base = 'inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium shrink-0';
  switch (status) {
    case 'active':
      return <span className={cn(base, 'bg-green-100 text-green-800')}>Active</span>;
    case 'pending':
      return <span className={cn(base, 'bg-amber-100 text-amber-800')}>Pending</span>;
    case 'failed':
      return <span className={cn(base, 'bg-red-100 text-red-800')}>Error</span>;
    case 'inactive':
      return <span className={cn(base, 'bg-gray-100 text-gray-800')}>Inactive</span>;
    default:
      return <span className={cn(base, 'bg-gray-100 text-gray-800')}>{status}</span>;
  }
}

function formatRelativeTime(dateString: string | null): string {
  if (!dateString) {
    return 'Never synced';
  }
  const date = new Date(dateString);
  const now = new Date();
  const diffMs = now.getTime() - date.getTime();
  const diffMinutes = Math.floor(diffMs / 60_000);

  if (diffMinutes < 1) return 'Just now';
  if (diffMinutes < 60) return `${diffMinutes} minute${diffMinutes === 1 ? '' : 's'} ago`;
  const diffHours = Math.floor(diffMinutes / 60);
  if (diffHours < 24) return `${diffHours} hour${diffHours === 1 ? '' : 's'} ago`;
  const diffDays = Math.floor(diffHours / 24);
  return `${diffDays} day${diffDays === 1 ? '' : 's'} ago`;
}

export function ConnectedSourceCard({
  source,
  onManage,
  onDisconnect,
  onTestConnection,
  testing = false,
}: ConnectedSourceCardProps) {
  return (
    <div className="rounded-lg border border-gray-200 bg-white p-3">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div className="flex flex-col gap-1 min-w-0">
          <span className="text-sm font-semibold text-gray-900 truncate">{source.displayName}</span>
          <span className="text-xs text-gray-500">
            {PLATFORM_DISPLAY_NAMES[source.platform] ?? source.platform}
          </span>
        </div>

        <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:gap-4">
          <div className="text-xs text-gray-500 sm:text-right whitespace-nowrap">
            Last sync: {formatRelativeTime(source.lastSyncAt)}
          </div>

          {getStatusBadge(source.status)}

          <div className="flex flex-wrap gap-2">
            <button
              type="button"
              onClick={() => onManage(source)}
              className="text-sm font-medium text-blue-600 hover:text-blue-800"
            >
              Manage
            </button>
            <button
              type="button"
              onClick={() => onTestConnection(source)}
              disabled={testing}
              className={cn(
                'text-sm font-medium text-blue-600 hover:text-blue-800',
                testing && 'opacity-50 cursor-wait'
              )}
            >
              Test
            </button>
            <button
              type="button"
              onClick={() => onDisconnect(source)}
              className="text-sm font-medium text-red-600 hover:text-red-800"
            >
              Disconnect
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
