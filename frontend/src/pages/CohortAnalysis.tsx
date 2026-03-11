/**
 * Cohort Analysis Page
 *
 * Customer retention cohort analysis with heatmap.
 * Matches the Figma "Cohort Analysis" design.
 *
 * Data: GET /api/cohort-analysis → getCohortRetention()
 */

import { useState, useEffect, useCallback, useRef } from 'react';
import { Users, RefreshCw } from 'lucide-react';
import { RetentionHeatmap } from '../components/charts/RetentionHeatmap';
import { getCohortRetention } from '../services/cohortAnalysisApi';
import type { CohortAnalysisResponse } from '../services/cohortAnalysisApi';

const TIMEFRAME_OPTIONS = [
  { label: '3 months', value: '3m' },
  { label: '6 months', value: '6m' },
  { label: '12 months', value: '12m' },
];

export function CohortAnalysis() {
  const [timeframe, setTimeframe] = useState('12m');
  const [data, setData] = useState<CohortAnalysisResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const cancelRef = useRef<boolean>(false);

  const fetchData = useCallback((tf: string) => {
    cancelRef.current = true; // cancel any in-flight request
    const cancelled = { value: false };
    cancelRef.current = false;

    setLoading(true);
    setError(null);

    getCohortRetention(tf)
      .then((result) => {
        if (!cancelled.value) {
          setData(result);
          setLoading(false);
        }
      })
      .catch((err) => {
        if (!cancelled.value) {
          setError(err.message || 'Failed to load cohort data');
          setLoading(false);
        }
      });

    return () => { cancelled.value = true; };
  }, []);

  useEffect(() => {
    const cancel = fetchData(timeframe);
    return cancel;
  }, [timeframe, fetchData]);

  return (
    <div className="p-8">
      {/* Header */}
      <div className="flex items-start justify-between mb-8">
        <div>
          <div className="flex items-center gap-3 mb-2">
            <div className="bg-purple-100 p-2 rounded-lg">
              <Users className="w-6 h-6 text-purple-600" />
            </div>
            <h1 className="text-3xl font-semibold text-gray-900">Cohort Analysis</h1>
          </div>
          <p className="text-gray-600">Customer retention by acquisition cohort</p>
        </div>

        {/* Timeframe selector */}
        <div className="flex gap-2">
          {TIMEFRAME_OPTIONS.map((opt) => (
            <button
              key={opt.value}
              onClick={() => setTimeframe(opt.value)}
              className={`px-4 py-2 rounded-lg text-sm font-medium transition-colors ${
                timeframe === opt.value
                  ? 'bg-blue-600 text-white'
                  : 'bg-white border border-gray-300 text-gray-700 hover:bg-gray-50'
              }`}
            >
              {opt.label}
            </button>
          ))}
        </div>
      </div>

      {/* Error banner (shown alongside existing data so user knows a refresh failed) */}
      {error && data && (
        <div className="mb-6 flex items-center justify-between bg-red-50 border border-red-200 rounded-lg px-4 py-3">
          <p className="text-sm text-red-700">{error}</p>
          <button
            onClick={() => fetchData(timeframe)}
            className="ml-4 shrink-0 flex items-center gap-1.5 px-3 py-1.5 bg-red-600 text-white rounded-lg hover:bg-red-700 transition-colors text-xs font-medium"
          >
            <RefreshCw className="w-3 h-3" />
            Retry
          </button>
        </div>
      )}

      {/* Loading */}
      {loading && !data && (
        <div className="flex items-center justify-center py-16">
          <div className="text-center">
            <div className="w-8 h-8 border-4 border-blue-600 border-t-transparent rounded-full animate-spin mx-auto mb-4" />
            <p className="text-gray-500">Loading cohort data...</p>
          </div>
        </div>
      )}

      {/* Error with no data — show a full empty-state card so the page isn't blank */}
      {error && !data && !loading && (
        <div className="bg-white rounded-lg border border-red-200 p-12 text-center">
          <Users className="w-12 h-12 text-red-300 mx-auto mb-4" />
          <p className="text-gray-700 font-medium mb-1">Could not load cohort data</p>
          <p className="text-gray-400 text-sm mb-6">{error}</p>
          <button
            onClick={() => fetchData(timeframe)}
            className="inline-flex items-center gap-2 px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition-colors text-sm font-medium"
          >
            <RefreshCw className="w-4 h-4" />
            Try again
          </button>
        </div>
      )}

      {/* Data loaded */}
      {data && data.cohorts.length > 0 && (
        <>
          {/* Summary cards */}
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-8">
            <div className="bg-white rounded-lg border border-gray-200 p-4 shadow-sm">
              <p className="text-xs text-gray-500 mb-1">Avg Retention (M1)</p>
              <p className="text-2xl font-semibold text-gray-900">
                {(data.summary.avg_retention_month_1 * 100).toFixed(1)}%
              </p>
            </div>
            <div className="bg-white rounded-lg border border-gray-200 p-4 shadow-sm">
              <p className="text-xs text-gray-500 mb-1">Best Cohort</p>
              <p className="text-2xl font-semibold text-green-600">
                {data.summary.best_cohort.slice(0, 7) || '—'}
              </p>
            </div>
            <div className="bg-white rounded-lg border border-gray-200 p-4 shadow-sm">
              <p className="text-xs text-gray-500 mb-1">Worst Cohort</p>
              <p className="text-2xl font-semibold text-red-600">
                {data.summary.worst_cohort.slice(0, 7) || '—'}
              </p>
            </div>
            <div className="bg-white rounded-lg border border-gray-200 p-4 shadow-sm">
              <p className="text-xs text-gray-500 mb-1">Total Cohorts</p>
              <p className="text-2xl font-semibold text-gray-900">
                {data.summary.total_cohorts}
              </p>
            </div>
          </div>

          {/* Retention heatmap */}
          <div className="bg-white rounded-lg border border-gray-200 p-6 shadow-sm">
            <h2 className="text-lg font-semibold text-gray-900 mb-4">Retention Heatmap</h2>
            <RetentionHeatmap cohorts={data.cohorts} />
          </div>
        </>
      )}

      {/* Empty state */}
      {data && data.cohorts.length === 0 && (
        <div className="bg-white rounded-lg border border-gray-200 p-12 text-center">
          <Users className="w-12 h-12 text-gray-300 mx-auto mb-4" />
          <p className="text-gray-500 font-medium">No cohort data yet</p>
          <p className="text-gray-400 text-sm mt-1">
            Connect data sources to see cohort analysis.
          </p>
        </div>
      )}
    </div>
  );
}

export default CohortAnalysis;
