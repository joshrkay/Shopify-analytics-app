/**
 * Cohort Analysis Page
 *
 * Customer retention cohort analysis with heatmap.
 * Matches the Figma "Cohort Analysis" design.
 *
 * Data: GET /api/cohort-analysis → getCohortRetention()
 */

import { useState, useEffect } from 'react';
import { Users } from 'lucide-react';
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

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);

    getCohortRetention(timeframe)
      .then((result) => {
        if (!cancelled) {
          setData(result);
          setLoading(false);
        }
      })
      .catch((err) => {
        if (!cancelled) {
          setError(err.message || 'Failed to load cohort data');
          setLoading(false);
        }
      });

    return () => { cancelled = true; };
  }, [timeframe]);

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

      {/* Error banner */}
      {error && (
        <div className="mb-6 bg-red-50 border border-red-200 rounded-lg px-4 py-3 text-sm text-red-700">
          {error}
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
