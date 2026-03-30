/**
 * IncidentBanner Component
 *
 * Displays calm, scoped incident communication.
 * Shows at top of app when active incidents exist.
 *
 * Features:
 * - Severity-based tone (info/warning/critical)
 * - Scope messaging (which connector/data affected)
 * - ETA when available
 * - Status page link
 * - Dismissible (acknowledges incident)
 *
 * Story 9.6 - Incident Communication
 */

import { X } from 'lucide-react';
import { useActiveIncidents } from '../../contexts/DataHealthContext';
import { cn } from '../ui/utils';

interface IncidentBannerProps {
  /**
   * Callback when status page link is clicked.
   */
  onViewStatus?: () => void;
}

export function IncidentBanner({ onViewStatus }: IncidentBannerProps) {
  const { incidents, shouldShowBanner, mostSevereIncident, acknowledgeIncident } =
    useActiveIncidents();

  if (!shouldShowBanner || !mostSevereIncident) {
    return null;
  }

  const getTone = (): 'info' | 'warning' | 'critical' => {
    switch (mostSevereIncident.severity) {
      case 'critical':
        return 'critical';
      case 'high':
        return 'warning';
      default:
        return 'info';
    }
  };

  const getTitle = (): string => {
    if (mostSevereIncident.severity === 'critical') {
      return `${mostSevereIncident.scope} - Critical Issue`;
    }
    return `${mostSevereIncident.scope} may be delayed`;
  };

  const handleDismiss = async () => {
    try {
      await acknowledgeIncident(mostSevereIncident.id);
    } catch (err) {
      console.error('Failed to acknowledge incident:', err);
    }
  };

  const tone = getTone();
  const title = getTitle();

  const shell = {
    info: 'border-l-4 border-blue-500 bg-blue-50',
    warning: 'border-l-4 border-amber-500 bg-amber-50',
    critical: 'border-l-4 border-red-500 bg-red-50',
  }[tone];

  return (
    <div className={cn('relative rounded-r-md pr-10', shell)} role="status">
      <button
        type="button"
        className="absolute right-2 top-2 rounded p-1 text-gray-600 hover:bg-black/5"
        aria-label="Dismiss"
        onClick={handleDismiss}
      >
        <X className="h-4 w-4" aria-hidden />
      </button>
      <div className="p-4">
        <p className="font-semibold text-gray-900">{title}</p>
        <div className="mt-2 space-y-2 text-sm text-gray-800">
          <p>{mostSevereIncident.message}</p>
          {mostSevereIncident.eta && (
            <p className="text-gray-600">{mostSevereIncident.eta}</p>
          )}
          {mostSevereIncident.status_page_url && (
            <a
              href={mostSevereIncident.status_page_url}
              target="_blank"
              rel="noopener noreferrer"
              className="text-blue-700 underline"
              onClick={onViewStatus}
            >
              View status page
            </a>
          )}
          {incidents.length > 1 && (
            <p className="text-gray-600">
              {incidents.length - 1} other incident{incidents.length > 2 ? 's' : ''} active
            </p>
          )}
        </div>
      </div>
    </div>
  );
}

export default IncidentBanner;
