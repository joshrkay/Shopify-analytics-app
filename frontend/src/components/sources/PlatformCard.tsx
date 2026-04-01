/**
 * Platform Card Component
 *
 * Displays a data source platform option in the connection wizard.
 * Shows platform logo, name, description, category badge, and auth type.
 *
 * Phase 3 — Subphase 3.5: Connection Wizard UI
 */

import { cn } from '../ui/utils';
import type { DataSourceDefinition } from '../../types/sourceConnection';

interface PlatformCardProps {
  platform: DataSourceDefinition;
  onSelect: (platform: DataSourceDefinition) => void;
  disabled?: boolean;
}

/**
 * Card component for selecting a data source platform.
 *
 * Displays platform info and "Connect" button.
 * Disabled state grays out card and disables button.
 */
export function PlatformCard({ platform, onSelect, disabled = false }: PlatformCardProps) {
  const getCategoryBadge = (category: string) => {
    const base = 'inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium';
    switch (category) {
      case 'ecommerce':
        return <span className={cn(base, 'bg-green-100 text-green-800')}>E-commerce</span>;
      case 'ads':
        return <span className={cn(base, 'bg-blue-100 text-blue-800')}>Advertising</span>;
      case 'email':
        return <span className={cn(base, 'bg-amber-100 text-amber-800')}>Email</span>;
      case 'sms':
        return <span className={cn(base, 'bg-orange-100 text-orange-800')}>SMS</span>;
      default:
        return <span className={cn(base, 'bg-gray-100 text-gray-800')}>{category}</span>;
    }
  };

  const getAuthBadge = (authType: string) => {
    const base = 'inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium bg-gray-100 text-gray-800';
    switch (authType) {
      case 'oauth':
        return <span className={base}>OAuth</span>;
      case 'api_key':
        return <span className={base}>API Key</span>;
      default:
        return <span className={base}>{authType}</span>;
    }
  };

  return (
    <div className="rounded-lg border border-gray-200 bg-white p-4 shadow-sm flex flex-col gap-3">
      <div className="flex items-start justify-between gap-2">
        <div className="flex flex-col gap-2 min-w-0">
          <h3 className="text-base font-semibold text-gray-900">{platform.displayName}</h3>
          <div className="flex flex-wrap gap-2">
            {getCategoryBadge(platform.category)}
            {getAuthBadge(platform.authType)}
          </div>
        </div>
      </div>

      <p className="text-sm text-gray-600">{platform.description}</p>

      <button
        type="button"
        onClick={() => onSelect(platform)}
        disabled={disabled || !platform.isEnabled}
        className={cn(
          'w-full rounded-lg px-4 py-2.5 text-sm font-medium transition-colors',
          disabled || !platform.isEnabled
            ? 'cursor-not-allowed bg-gray-100 text-gray-400'
            : 'bg-blue-600 text-white hover:bg-blue-700'
        )}
      >
        {platform.isEnabled ? 'Connect' : 'Coming Soon'}
      </button>

      {!platform.isEnabled && (
        <p className="text-center text-sm text-gray-500">This integration is not yet available</p>
      )}
    </div>
  );
}
