/**
 * Sync Status Page
 *
 * Displays connector health and sync status.
 * Matches the Figma "Sync Status" design.
 *
 * Data: GET /api/sync-health/summary (via syncHealthApi)
 */

import { useState, useEffect, useCallback } from 'react';
import { RefreshCw, CheckCircle, AlertCircle, XCircle, Clock } from 'lucide-react';
import {
  getSyncHealthSummary,
  formatTimeSinceSync,
  type SyncHealthSummary,
  type ConnectorHealth,
} from '../services/syncHealthApi';

function StatusIcon({ status }: { status: ConnectorHealth['status'] }) {
  switch (status) {
    case 'healthy':
      return <CheckCircle className="w-5 h-5 text-green-600" />;
    case 'delayed':
      return <AlertCircle className="w-5 h-5 text-yellow-600" />;
    case 'error':
      return <XCircle className="w-5 h-5 text-red-600" />;
    default:
      return <AlertCircle className="w-5 h-5 text-gray-400" />;
  }
}

function StatusBadge({ status }: { status: ConnectorHealth['status'] }) {
  const classes = {
    healthy: 'bg-green-100 text-green-800',
    delayed: 'bg-yellow-100 text-yellow-800',
    error: 'bg-red-100 text-red-800',
  };
  return (
    <span className={`inline-flex px-2.5 py-0.5 rounded-full text-xs font-medium ${classes[status] ?? 'bg-gray-100 text-gray-800'}`}>
      {status.charAt(0).toUpperCase() + status.slice(1)}
    </span>
  );
}

export function SyncStatus() {
  const [summary, setSummary] = useState<SyncHealthSummary | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [lastRefreshed, setLastRefreshed] = useState<Date | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await getSyncHealthSummary();
      setSummary(data);
      setLastRefreshed(new Date());
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : 'Failed to load sync status';
      setError(message);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const overallBadgeClass = summary
    ? summary.overall_status === 'healthy'
      ? 'bg-green-100 text-green-800'
      : summary.overall_status === 'degraded'
      ? 'bg-yellow-100 text-yellow-800'
      : 'bg-red-100 text-red-800'
    : 'bg-gray-100 text-gray-800';

  return (
    <div className="p-8">
      {/* Header */}
      <div className="mb-8">
        <div className="flex items-center justify-between">
          <div>
            <div className="flex items-center gap-3 mb-2">
              <RefreshCw className="w-6 h-6 text-gray-700" />
              <h1 className="text-3xl font-semibold text-gray-900">Sync Status</h1>
            </div>
            <p className="text-gray-600">Monitor data connector health and sync activity</p>
          </div>
          <div className="flex items-center gap-3">
            {lastRefreshed && (
              <span className="text-sm text-gray-500">
                Updated {lastRefreshed.toLocaleTimeString()}
              </span>
            )}
            <button
              onClick={load}
              disabled={loading}
              className="flex items-center gap-2 px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition-colors disabled:opacity-50"
            >
              <RefreshCw className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`} />
              Refresh
            </button>
          </div>
        </div>
      </div>

      {loading && !summary ? (
        <div className="flex items-center justify-center py-16">
          <div className="text-center">
            <div className="w-8 h-8 border-4 border-blue-600 border-t-transparent rounded-full animate-spin mx-auto mb-4" />
            <p className="text-gray-500">Loading sync status...</p>
          </div>
        </div>
      ) : error && !summary ? (
        <div className="bg-red-50 border border-red-200 rounded-lg p-6 text-center">
          <p className="text-red-700 font-medium mb-2">Failed to load sync status</p>
          <p className="text-red-600 text-sm mb-4">{error}</p>
          <button
            onClick={load}
            className="px-4 py-2 bg-red-600 text-white rounded-lg hover:bg-red-700 transition-colors text-sm"
          >
            Retry
          </button>
        </div>
      ) : summary ? (
        <>
          {/* Summary Cards */}
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-6 mb-8">
            <div className="bg-white rounded-lg p-6 shadow-sm border border-gray-200">
              <div className="flex items-center justify-between mb-2">
                <span className="text-sm text-gray-600">Overall Status</span>
              </div>
              <span className={`inline-flex px-3 py-1 rounded-full text-sm font-medium ${overallBadgeClass}`}>
                {summary.overall_status.charAt(0).toUpperCase() + summary.overall_status.slice(1)}
              </span>
              <p className="text-sm text-gray-500 mt-2">Health score: {summary.health_score}%</p>
            </div>
            <div className="bg-white rounded-lg p-6 shadow-sm border border-gray-200">
              <div className="flex items-center justify-between mb-2">
                <span className="text-sm text-gray-600">Healthy Connectors</span>
                <CheckCircle className="w-5 h-5 text-green-600" />
              </div>
              <p className="text-3xl font-semibold text-gray-900">{summary.healthy_count}</p>
              <p className="text-sm text-gray-500 mt-1">of {summary.total_connectors} total</p>
            </div>
            <div className="bg-white rounded-lg p-6 shadow-sm border border-gray-200">
              <div className="flex items-center justify-between mb-2">
                <span className="text-sm text-gray-600">Delayed</span>
                <Clock className="w-5 h-5 text-yellow-600" />
              </div>
              <p className="text-3xl font-semibold text-gray-900">{summary.delayed_count}</p>
            </div>
            <div className="bg-white rounded-lg p-6 shadow-sm border border-gray-200">
              <div className="flex items-center justify-between mb-2">
                <span className="text-sm text-gray-600">Errors</span>
                <XCircle className="w-5 h-5 text-red-600" />
              </div>
              <p className="text-3xl font-semibold text-gray-900">{summary.error_count}</p>
              {summary.has_blocking_issues && (
                <p className="text-xs text-red-600 mt-1">⚠ Blocking issues detected</p>
              )}
            </div>
          </div>

          {/* Connector List */}
          <div className="bg-white rounded-lg shadow-sm border border-gray-200 overflow-hidden">
            <div className="px-6 py-4 border-b border-gray-200">
              <h2 className="text-lg font-semibold text-gray-900">Connectors</h2>
            </div>
            {summary.connectors.length === 0 ? (
              <div className="p-8 text-center text-gray-400">
                No connectors configured yet.
              </div>
            ) : (
              <div className="divide-y divide-gray-200">
                {summary.connectors.map((connector) => (
                  <div key={connector.connector_id} className="px-6 py-4 hover:bg-gray-50 transition-colors">
                    <div className="flex items-center justify-between">
                      <div className="flex items-center gap-3">
                        <StatusIcon status={connector.status} />
                        <div>
                          <p className="font-medium text-gray-900">{connector.connector_name}</p>
                          <p className="text-sm text-gray-500">
                            {connector.source_type ?? 'Unknown source'} •{' '}
                            Last sync: {formatTimeSinceSync(connector.minutes_since_sync)}
                          </p>
                        </div>
                      </div>
                      <div className="flex items-center gap-3">
                        {connector.last_rows_synced !== null && (
                          <span className="text-sm text-gray-500">
                            {connector.last_rows_synced.toLocaleString()} rows
                          </span>
                        )}
                        <StatusBadge status={connector.status} />
                      </div>
                    </div>
                    {connector.message && connector.status !== 'healthy' && (
                      <p className="mt-2 text-sm text-gray-600 ml-8">{connector.merchant_message || connector.message}</p>
                    )}
                    {connector.recommended_actions.length > 0 && connector.status !== 'healthy' && (
                      <ul className="mt-2 ml-8 space-y-1">
                        {connector.recommended_actions.map((action, i) => (
                          <li key={i} className="text-sm text-blue-600 flex items-center gap-1">
                            <span>→</span> {action}
                          </li>
                        ))}
                      </ul>
                    )}
                  </div>
                ))}
              </div>
            )}
          </div>
        </>
      ) : null}
    </div>
  );
}

export default SyncStatus;
