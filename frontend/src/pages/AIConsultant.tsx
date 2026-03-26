/**
 * AI Consultant Page
 *
 * Displays AI-generated recommendations from the backend.
 * Matches the Figma "AI Consultant" design.
 *
 * Data: GET /api/recommendations (via recommendationsApi)
 */

import { useState, useEffect, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  Sparkles,
  TrendingUp,
  AlertCircle,
  CheckCircle,
  Target,
  DollarSign,
  Lightbulb,
  ArrowRight,
  X,
  Clock,
  ExternalLink,
  ArrowUpRight,
  ArrowDownRight,
} from 'lucide-react';
import { listRecommendations, acceptRecommendation, dismissRecommendation } from '../services/recommendationsApi';
import { getInsight } from '../services/insightsApi';
import type { Recommendation, RecommendationPriority } from '../types/recommendations';
import { getRecommendationTypeLabel } from '../types/recommendations';
import type { Insight, SupportingMetric } from '../types/insights';

type FilterOption = 'all' | RecommendationPriority;

function getTypeIcon(type: string) {
  switch (type) {
    case 'adjust_bid':
    case 'increase_budget':
    case 'decrease_budget':
      return TrendingUp;
    case 'pause_campaign':
      return DollarSign;
    case 'expand_targeting':
    case 'narrow_targeting':
      return Target;
    case 'creative_refresh':
      return Lightbulb;
    case 'schedule_adjustment':
      return TrendingUp;
    default:
      return AlertCircle;
  }
}

function getTypeLabel(type: string): string {
  const labels: Record<string, string> = {
    pause_campaign: 'Budget',
    increase_budget: 'Budget',
    decrease_budget: 'Budget',
    adjust_bid: 'Bid Adjustment',
    expand_targeting: 'Targeting',
    narrow_targeting: 'Targeting',
    creative_refresh: 'Creative',
    schedule_adjustment: 'Scheduling',
  };
  return labels[type] ?? type;
}

function impactLabel(impact: string): string {
  const map: Record<string, string> = {
    minimal: '+5-10% improvement',
    moderate: '+15-25% improvement',
    significant: '+30%+ improvement',
  };
  return map[impact] ?? impact;
}

function impactLevel(impact: string): number {
  return impact === 'significant' ? 3 : impact === 'moderate' ? 2 : 1;
}

function formatMetricValue(value: number | null, metric: string): string {
  if (value === null) return '-';
  if (metric.toLowerCase().includes('spend') || metric.toLowerCase().includes('cost')) {
    return `$${value.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
  }
  if (metric.toLowerCase().includes('rate') || metric.toLowerCase().includes('roas') || metric.toLowerCase().includes('ctr')) {
    return `${value.toFixed(2)}%`;
  }
  return value.toLocaleString(undefined, { maximumFractionDigits: 2 });
}

function formatChange(changePct: number | null): string {
  if (changePct === null) return '-';
  const sign = changePct >= 0 ? '+' : '';
  return `${sign}${changePct.toFixed(1)}%`;
}

function isNegativeChange(changePct: number | null, metric: string): boolean {
  if (changePct === null) return false;
  const isCostMetric = metric.toLowerCase().includes('spend') ||
    metric.toLowerCase().includes('cost') ||
    metric.toLowerCase().includes('cpc');
  return isCostMetric ? changePct > 0 : changePct < 0;
}

function relativeTime(dateStr: string): string {
  const now = Date.now();
  const then = new Date(dateStr).getTime();
  const diffMin = Math.floor((now - then) / 60000);
  if (diffMin < 1) return 'Just now';
  if (diffMin < 60) return `${diffMin}m ago`;
  const diffHr = Math.floor(diffMin / 60);
  if (diffHr < 24) return `${diffHr}h ago`;
  const diffDay = Math.floor(diffHr / 24);
  if (diffDay < 7) return `${diffDay}d ago`;
  return new Date(dateStr).toLocaleDateString(undefined, { month: 'short', day: 'numeric' });
}

export function AIConsultant() {
  const navigate = useNavigate();
  const [recommendations, setRecommendations] = useState<Recommendation[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [filter, setFilter] = useState<FilterOption>('all');
  const [actionInProgress, setActionInProgress] = useState<string | null>(null);
  const [selectedRec, setSelectedRec] = useState<Recommendation | null>(null);
  const [relatedInsight, setRelatedInsight] = useState<Insight | null>(null);
  const [insightLoading, setInsightLoading] = useState(false);

  // Fetch related insight when a recommendation is selected
  useEffect(() => {
    if (!selectedRec) {
      setRelatedInsight(null);
      return;
    }
    let cancelled = false;
    setInsightLoading(true);
    setRelatedInsight(null);
    getInsight(selectedRec.related_insight_id)
      .then((data) => { if (!cancelled) setRelatedInsight(data); })
      .catch(() => { /* graceful — insight sections just won't show */ })
      .finally(() => { if (!cancelled) setInsightLoading(false); });
    return () => { cancelled = true; };
  }, [selectedRec]);

  const loadRecommendations = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await listRecommendations({ include_dismissed: false, limit: 50 });
      setRecommendations(data.recommendations);
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : 'Failed to load recommendations';
      setError(message);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadRecommendations();
  }, [loadRecommendations]);

  const handleAccept = async (id: string) => {
    setActionInProgress(id);
    try {
      await acceptRecommendation(id);
      setRecommendations((prev) =>
        prev.map((r) => (r.recommendation_id === id ? { ...r, is_accepted: true } : r))
      );
    } catch {
      // silently ignore for now
    } finally {
      setActionInProgress(null);
    }
  };

  const handleDismiss = async (id: string) => {
    setActionInProgress(id);
    try {
      await dismissRecommendation(id);
      setRecommendations((prev) => prev.filter((r) => r.recommendation_id !== id));
    } catch {
      // silently ignore for now
    } finally {
      setActionInProgress(null);
    }
  };

  const handleAcceptFromModal = async (id: string) => {
    await handleAccept(id);
    setSelectedRec(null);
  };

  const handleDismissFromModal = async (id: string) => {
    await handleDismiss(id);
    setSelectedRec(null);
  };

  const filtered =
    filter === 'all' ? recommendations : recommendations.filter((r) => r.priority === filter);

  const priorityCount = {
    high: recommendations.filter((r) => r.priority === 'high').length,
    medium: recommendations.filter((r) => r.priority === 'medium').length,
    low: recommendations.filter((r) => r.priority === 'low').length,
  };

  // Estimate potential impact based on significant count
  const significantCount = recommendations.filter((r) => r.estimated_impact === 'significant').length;
  const potentialImpact =
    significantCount > 2 ? '$10K+' : significantCount > 0 ? '$5-10K' : '$1-5K';

  return (
    <div className="p-8">
      {/* Header */}
      <div className="mb-8">
        <div className="flex items-center gap-3 mb-2">
          <div className="bg-gradient-to-br from-purple-600 to-blue-600 p-2 rounded-lg">
            <Sparkles className="w-6 h-6 text-white" />
          </div>
          <h1 className="text-3xl font-semibold text-gray-900">AI Consultant</h1>
        </div>
        <p className="text-gray-600">
          Get personalized recommendations to optimize your ad campaigns and increase ROAS
        </p>
      </div>

      {/* Overview Cards */}
      <div className="grid grid-cols-1 md:grid-cols-4 gap-6 mb-8">
        <div className="bg-white rounded-lg p-6 shadow-sm border border-gray-200">
          <div className="flex items-center justify-between mb-2">
            <span className="text-sm text-gray-600">Total Recommendations</span>
            <Sparkles className="w-5 h-5 text-purple-600" />
          </div>
          <p className="text-3xl font-semibold text-gray-900">{recommendations.length}</p>
        </div>
        <div className="bg-white rounded-lg p-6 shadow-sm border border-gray-200">
          <div className="flex items-center justify-between mb-2">
            <span className="text-sm text-gray-600">High Priority</span>
            <AlertCircle className="w-5 h-5 text-red-600" />
          </div>
          <p className="text-3xl font-semibold text-gray-900">{priorityCount.high}</p>
        </div>
        <div className="bg-white rounded-lg p-6 shadow-sm border border-gray-200">
          <div className="flex items-center justify-between mb-2">
            <span className="text-sm text-gray-600">Medium Priority</span>
            <AlertCircle className="w-5 h-5 text-yellow-600" />
          </div>
          <p className="text-3xl font-semibold text-gray-900">{priorityCount.medium}</p>
        </div>
        <div className="bg-white rounded-lg p-6 shadow-sm border border-gray-200">
          <div className="flex items-center justify-between mb-2">
            <span className="text-sm text-gray-600">Potential Impact</span>
            <DollarSign className="w-5 h-5 text-green-600" />
          </div>
          <p className="text-3xl font-semibold text-gray-900">{potentialImpact}</p>
          <p className="text-xs text-gray-500 mt-1">Estimated monthly</p>
        </div>
      </div>

      {/* Filter */}
      <div className="bg-white rounded-lg shadow-sm border border-gray-200 p-4 mb-6">
        <div className="flex items-center gap-4">
          <span className="text-sm font-medium text-gray-700">Filter by priority:</span>
          <div className="flex gap-2">
            {(['all', 'high', 'medium', 'low'] as FilterOption[]).map((f) => (
              <button
                key={f}
                onClick={() => setFilter(f)}
                className={`px-4 py-2 rounded-lg text-sm font-medium transition-colors ${
                  filter === f
                    ? 'bg-blue-600 text-white'
                    : 'bg-gray-100 text-gray-700 hover:bg-gray-200'
                }`}
              >
                {f.charAt(0).toUpperCase() + f.slice(1)}
              </button>
            ))}
          </div>
        </div>
      </div>

      {/* Content */}
      {loading ? (
        <div className="flex items-center justify-center py-16">
          <div className="text-center">
            <div className="w-8 h-8 border-4 border-blue-600 border-t-transparent rounded-full animate-spin mx-auto mb-4" />
            <p className="text-gray-500">Loading recommendations...</p>
          </div>
        </div>
      ) : error ? (
        <div className="bg-red-50 border border-red-200 rounded-lg p-6 text-center">
          <p className="text-red-700 font-medium mb-2">Failed to load recommendations</p>
          <p className="text-red-600 text-sm mb-4">{error}</p>
          <button
            onClick={loadRecommendations}
            className="px-4 py-2 bg-red-600 text-white rounded-lg hover:bg-red-700 transition-colors text-sm"
          >
            Retry
          </button>
        </div>
      ) : filtered.length === 0 ? (
        <div className="bg-white rounded-lg border border-gray-200 p-12 text-center">
          <Sparkles className="w-12 h-12 text-gray-300 mx-auto mb-4" />
          <p className="text-gray-500 font-medium">No recommendations found</p>
          <p className="text-gray-400 text-sm mt-1">
            {filter !== 'all'
              ? `No ${filter}-priority recommendations at this time.`
              : 'Your campaigns are performing well — no actions needed.'}
          </p>
        </div>
      ) : (
        <div className="space-y-4">
          {filtered.map((rec) => {
            const TypeIcon = getTypeIcon(rec.recommendation_type);
            const priorityBgClass =
              rec.priority === 'high'
                ? 'bg-red-100'
                : rec.priority === 'medium'
                ? 'bg-yellow-100'
                : 'bg-gray-100';
            const priorityIconClass =
              rec.priority === 'high'
                ? 'text-red-600'
                : rec.priority === 'medium'
                ? 'text-yellow-600'
                : 'text-gray-600';
            const priorityBadgeClass =
              rec.priority === 'high'
                ? 'bg-red-100 text-red-800'
                : rec.priority === 'medium'
                ? 'bg-yellow-100 text-yellow-800'
                : 'bg-gray-100 text-gray-800';

            return (
              <div
                key={rec.recommendation_id}
                className="bg-white rounded-lg shadow-sm border border-gray-200 p-6 hover:shadow-md transition-shadow"
              >
                <div className="flex items-start gap-4">
                  {/* Priority icon */}
                  <div
                    className={`flex-shrink-0 w-12 h-12 rounded-full flex items-center justify-center ${priorityBgClass}`}
                  >
                    <TypeIcon className={`w-6 h-6 ${priorityIconClass}`} />
                  </div>

                  {/* Content */}
                  <div className="flex-1">
                    <div className="flex items-start justify-between mb-2">
                      <div>
                        <div className="flex items-center gap-2 mb-1">
                          <h3 className="text-lg font-semibold text-gray-900">
                            {getTypeLabel(rec.recommendation_type)}
                          </h3>
                          <span
                            className={`px-2 py-0.5 rounded-full text-xs font-medium ${priorityBadgeClass}`}
                          >
                            {rec.priority.toUpperCase()}
                          </span>
                        </div>
                        <div className="flex items-center gap-3 text-sm text-gray-600">
                          <span className="inline-flex items-center gap-1 px-2 py-0.5 bg-gray-100 rounded">
                            {getTypeLabel(rec.recommendation_type)}
                          </span>
                          {rec.affected_entity && <span>• {rec.affected_entity}</span>}
                        </div>
                      </div>
                    </div>

                    <p className="text-gray-700 mb-4">{rec.recommendation_text}</p>

                    {rec.rationale && (
                      <p className="text-sm text-gray-500 mb-4 italic">{rec.rationale}</p>
                    )}

                    {/* Impact */}
                    <div className="flex items-center justify-between bg-gray-50 rounded-lg p-4 mb-4">
                      <div>
                        <p className="text-sm text-gray-600 mb-1">Expected Impact</p>
                        <p className="font-semibold text-green-600">
                          {impactLabel(rec.estimated_impact)}
                        </p>
                      </div>
                      <div className="flex items-center gap-2 text-sm">
                        <span className="text-gray-500">Risk: {rec.risk_level}</span>
                        <ArrowRight className="w-4 h-4 text-gray-400" />
                        <span className="font-medium text-blue-600">
                          Confidence: {Math.round(rec.confidence_score * 100)}%
                        </span>
                      </div>
                    </div>

                    {/* Actions */}
                    <div className="flex items-center gap-3">
                      {!rec.is_accepted ? (
                        <button
                          onClick={() => handleAccept(rec.recommendation_id)}
                          disabled={actionInProgress === rec.recommendation_id}
                          className="flex items-center gap-2 px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition-colors disabled:opacity-50"
                        >
                          <CheckCircle className="w-4 h-4" />
                          {actionInProgress === rec.recommendation_id ? 'Applying...' : 'Apply Recommendation'}
                        </button>
                      ) : (
                        <span className="flex items-center gap-2 px-4 py-2 bg-green-50 text-green-700 rounded-lg text-sm font-medium">
                          <CheckCircle className="w-4 h-4" />
                          Applied
                        </span>
                      )}
                      <button
                        onClick={() => setSelectedRec(rec)}
                        className="px-4 py-2 text-gray-700 hover:bg-gray-100 rounded-lg transition-colors text-sm"
                      >
                        View Details
                      </button>
                      <button
                        onClick={() => handleDismiss(rec.recommendation_id)}
                        disabled={actionInProgress === rec.recommendation_id}
                        className="ml-auto px-4 py-2 text-gray-500 hover:text-gray-700 transition-colors text-sm disabled:opacity-50"
                      >
                        Dismiss
                      </button>
                    </div>
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      )}

      {/* Modal keyframes */}
      <style>{`
        @keyframes modalFadeIn { from { opacity: 0; } to { opacity: 1; } }
        @keyframes modalScaleIn { from { opacity: 0; transform: scale(0.95) translateY(8px); } to { opacity: 1; transform: scale(1) translateY(0); } }
      `}</style>

      {/* Recommendation Detail Modal */}
      {selectedRec && (() => {
        const ModalIcon = getTypeIcon(selectedRec.recommendation_type);
        const confidencePct = Math.round(selectedRec.confidence_score * 100);
        const confidenceColor = confidencePct >= 70 ? '#2563eb' : confidencePct >= 40 ? '#d97706' : '#dc2626';
        const riskDotColor = selectedRec.risk_level === 'high' ? 'bg-red-500' : selectedRec.risk_level === 'medium' ? 'bg-yellow-500' : 'bg-green-500';
        const impactLvl = impactLevel(selectedRec.estimated_impact);
        // SVG confidence ring calculations
        const radius = 26;
        const circumference = 2 * Math.PI * radius;
        const strokeDashoffset = circumference - (confidencePct / 100) * circumference;

        return (
          <div
            className="fixed inset-0 bg-black/50 z-50 flex items-center justify-center"
            style={{ animation: 'modalFadeIn 150ms ease-out' }}
            onClick={() => setSelectedRec(null)}
            onKeyDown={(e) => { if (e.key === 'Escape') setSelectedRec(null); }}
          >
            <div
              className="bg-white rounded-xl max-w-2xl w-full mx-4 max-h-[90vh] overflow-y-auto shadow-2xl"
              style={{ animation: 'modalScaleIn 200ms ease-out' }}
              role="dialog"
              aria-modal="true"
              onClick={(e) => e.stopPropagation()}
            >
              {/* Header with gradient accent */}
              <div className="bg-gradient-to-r from-purple-600 to-blue-600 rounded-t-xl px-6 py-4">
                <div className="flex items-start justify-between">
                  <div className="flex items-center gap-3">
                    <div className="w-10 h-10 rounded-full bg-white/20 flex items-center justify-center">
                      <ModalIcon className="w-5 h-5 text-white" />
                    </div>
                    <div>
                      <h2 className="text-lg font-semibold text-white">
                        {getRecommendationTypeLabel(selectedRec.recommendation_type)}
                      </h2>
                      <div className="flex items-center gap-2 mt-1">
                        <span className={`px-2 py-0.5 rounded-full text-xs font-medium ${
                          selectedRec.priority === 'high' ? 'bg-red-400/30 text-red-100'
                            : selectedRec.priority === 'medium' ? 'bg-yellow-400/30 text-yellow-100'
                            : 'bg-white/20 text-white/80'
                        }`}>
                          {selectedRec.priority.toUpperCase()}
                        </span>
                        {selectedRec.affected_entity && (
                          <span className="text-white/70 text-xs">
                            {selectedRec.affected_entity_type && `${selectedRec.affected_entity_type.charAt(0).toUpperCase() + selectedRec.affected_entity_type.slice(1)}: `}
                            {selectedRec.affected_entity}
                          </span>
                        )}
                        {selectedRec.is_accepted && (
                          <span className="px-2 py-0.5 rounded-full text-xs font-medium bg-green-400/30 text-green-100">
                            Accepted
                          </span>
                        )}
                      </div>
                    </div>
                  </div>
                  <button
                    onClick={() => setSelectedRec(null)}
                    className="p-1 text-white/70 hover:text-white transition-colors"
                  >
                    <X className="w-5 h-5" />
                  </button>
                </div>
              </div>

              <div className="px-6 py-5 space-y-5">
                {/* Dollar Impact Hero (from related insight) */}
                {relatedInsight?.estimated_dollar_impact != null && (
                  <div className={`rounded-lg p-4 ${
                    relatedInsight.estimated_dollar_impact >= 0
                      ? 'bg-gradient-to-r from-green-50 to-emerald-50 border border-green-200'
                      : 'bg-gradient-to-r from-red-50 to-orange-50 border border-red-200'
                  }`}>
                    <div className="flex items-center gap-3">
                      <div className={`w-10 h-10 rounded-full flex items-center justify-center ${
                        relatedInsight.estimated_dollar_impact >= 0 ? 'bg-green-100' : 'bg-red-100'
                      }`}>
                        <DollarSign className={`w-5 h-5 ${
                          relatedInsight.estimated_dollar_impact >= 0 ? 'text-green-600' : 'text-red-600'
                        }`} />
                      </div>
                      <div>
                        <p className={`text-lg font-bold ${
                          relatedInsight.estimated_dollar_impact >= 0 ? 'text-green-700' : 'text-red-700'
                        }`}>
                          {relatedInsight.estimated_dollar_impact >= 0 ? '+' : ''}${Math.abs(relatedInsight.estimated_dollar_impact).toLocaleString(undefined, { maximumFractionDigits: 0 })}/mo estimated impact
                        </p>
                        {relatedInsight.dollar_impact_explanation && (
                          <p className="text-sm text-gray-600 mt-0.5">{relatedInsight.dollar_impact_explanation}</p>
                        )}
                      </div>
                    </div>
                  </div>
                )}

                {/* Insight loading skeleton for dollar impact */}
                {insightLoading && (
                  <div className="rounded-lg p-4 bg-gray-50 border border-gray-200 animate-pulse">
                    <div className="flex items-center gap-3">
                      <div className="w-10 h-10 rounded-full bg-gray-200" />
                      <div className="flex-1 space-y-2">
                        <div className="h-5 w-48 bg-gray-200 rounded" />
                        <div className="h-4 w-72 bg-gray-200 rounded" />
                      </div>
                    </div>
                  </div>
                )}

                {/* Recommendation */}
                <div>
                  <h3 className="text-sm font-medium text-gray-500 uppercase tracking-wide mb-2">Recommendation</h3>
                  <p className="text-gray-800 leading-relaxed">{selectedRec.recommendation_text}</p>
                </div>

                {/* Why This Matters (from related insight) */}
                {relatedInsight?.why_it_matters && (
                  <div className="bg-purple-50 border border-purple-100 rounded-lg p-4">
                    <div className="flex gap-3">
                      <Lightbulb className="w-5 h-5 text-purple-500 flex-shrink-0 mt-0.5" />
                      <div>
                        <h4 className="text-sm font-medium text-purple-800 mb-1">Why This Matters</h4>
                        <p className="text-sm text-purple-700 leading-relaxed">{relatedInsight.why_it_matters}</p>
                      </div>
                    </div>
                  </div>
                )}

                {/* Rationale */}
                {selectedRec.rationale && (
                  <div>
                    <h3 className="text-sm font-medium text-gray-500 uppercase tracking-wide mb-2">Rationale</h3>
                    <p className="text-gray-700 bg-gray-50 rounded-lg p-4 leading-relaxed">{selectedRec.rationale}</p>
                  </div>
                )}

                {/* Metrics Row: Impact / Risk / Confidence */}
                <div className="grid grid-cols-3 gap-4">
                  {/* Expected Impact */}
                  <div className="bg-gray-50 rounded-lg p-4 text-center">
                    <p className="text-xs text-gray-500 uppercase tracking-wide mb-2">Impact</p>
                    <p className="font-semibold text-green-600 text-sm mb-2">{impactLabel(selectedRec.estimated_impact)}</p>
                    <div className="flex justify-center gap-1">
                      {[1, 2, 3].map((dot) => (
                        <div key={dot} className={`w-2.5 h-2.5 rounded-full ${
                          dot <= impactLvl ? 'bg-green-500' : 'bg-gray-200'
                        }`} />
                      ))}
                    </div>
                  </div>

                  {/* Risk Level */}
                  <div className="bg-gray-50 rounded-lg p-4 text-center">
                    <p className="text-xs text-gray-500 uppercase tracking-wide mb-2">Risk</p>
                    <div className="flex items-center justify-center gap-2">
                      <span className={`w-2.5 h-2.5 rounded-full ${riskDotColor}`} />
                      <span className="font-semibold text-gray-800 text-sm">
                        {selectedRec.risk_level.charAt(0).toUpperCase() + selectedRec.risk_level.slice(1)}
                      </span>
                    </div>
                  </div>

                  {/* Confidence Gauge */}
                  <div className="bg-gray-50 rounded-lg p-4 flex flex-col items-center">
                    <p className="text-xs text-gray-500 uppercase tracking-wide mb-2">Confidence</p>
                    <div className="relative w-16 h-16">
                      <svg className="w-16 h-16 -rotate-90" viewBox="0 0 64 64">
                        <circle cx="32" cy="32" r={radius} fill="none" stroke="#e5e7eb" strokeWidth="6" />
                        <circle
                          cx="32" cy="32" r={radius} fill="none"
                          stroke={confidenceColor} strokeWidth="6"
                          strokeLinecap="round"
                          strokeDasharray={circumference}
                          strokeDashoffset={strokeDashoffset}
                          style={{ transition: 'stroke-dashoffset 0.5s ease-out' }}
                        />
                      </svg>
                      <span className="absolute inset-0 flex items-center justify-center text-sm font-bold" style={{ color: confidenceColor }}>
                        {confidencePct}%
                      </span>
                    </div>
                  </div>
                </div>

                {/* Supporting Metrics Table (from related insight) */}
                {insightLoading && (
                  <div>
                    <h3 className="text-sm font-medium text-gray-500 uppercase tracking-wide mb-3">Supporting Metrics</h3>
                    <div className="space-y-2">
                      {[1, 2, 3].map((i) => (
                        <div key={i} className="animate-pulse flex items-center justify-between bg-gray-50 rounded-lg p-3">
                          <div className="h-4 w-24 bg-gray-200 rounded" />
                          <div className="h-4 w-40 bg-gray-200 rounded" />
                          <div className="h-5 w-16 bg-gray-200 rounded-full" />
                        </div>
                      ))}
                    </div>
                  </div>
                )}

                {relatedInsight && relatedInsight.supporting_metrics.length > 0 && (
                  <div>
                    <div className="flex items-center justify-between mb-3">
                      <h3 className="text-sm font-medium text-gray-500 uppercase tracking-wide">Supporting Metrics</h3>
                      {relatedInsight.timeframe && (
                        <span className="text-xs text-gray-400 flex items-center gap-1">
                          <Clock className="w-3 h-3" />
                          {relatedInsight.timeframe}
                        </span>
                      )}
                    </div>
                    <div className="border border-gray-200 rounded-lg overflow-hidden">
                      <table className="w-full text-sm">
                        <thead>
                          <tr className="bg-gray-50 text-gray-500 text-xs uppercase tracking-wide">
                            <th className="text-left px-4 py-2 font-medium">Metric</th>
                            <th className="text-right px-4 py-2 font-medium">Previous</th>
                            <th className="text-center px-2 py-2 font-medium" />
                            <th className="text-right px-4 py-2 font-medium">Current</th>
                            <th className="text-right px-4 py-2 font-medium">Change</th>
                          </tr>
                        </thead>
                        <tbody>
                          {relatedInsight.supporting_metrics.map((m: SupportingMetric, idx: number) => {
                            const negative = isNegativeChange(m.change_pct, m.metric);
                            return (
                              <tr key={idx} className={idx % 2 === 0 ? 'bg-white' : 'bg-gray-50/50'}>
                                <td className="px-4 py-2.5 text-gray-700 font-medium">{m.metric}</td>
                                <td className="px-4 py-2.5 text-right text-gray-500">{formatMetricValue(m.previous, m.metric)}</td>
                                <td className="px-1 py-2.5 text-center text-gray-300">
                                  <ArrowRight className="w-3 h-3 inline" />
                                </td>
                                <td className="px-4 py-2.5 text-right text-gray-800 font-medium">{formatMetricValue(m.current, m.metric)}</td>
                                <td className="px-4 py-2.5 text-right">
                                  <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium ${
                                    negative ? 'bg-red-50 text-red-700' : 'bg-green-50 text-green-700'
                                  }`}>
                                    {negative
                                      ? <ArrowDownRight className="w-3 h-3" />
                                      : <ArrowUpRight className="w-3 h-3" />
                                    }
                                    {formatChange(m.change_pct)}
                                  </span>
                                </td>
                              </tr>
                            );
                          })}
                        </tbody>
                      </table>
                    </div>
                  </div>
                )}

                {/* Additional Details */}
                <div className="flex items-center gap-4 text-xs text-gray-400 pt-2 border-t border-gray-100">
                  <span className="flex items-center gap-1" title={new Date(selectedRec.generated_at).toLocaleString()}>
                    <Clock className="w-3 h-3" />
                    Generated {relativeTime(selectedRec.generated_at)}
                  </span>
                  {selectedRec.currency && <span>Currency: {selectedRec.currency}</span>}
                  <button
                    onClick={() => { setSelectedRec(null); navigate('/insights'); }}
                    className="flex items-center gap-1 text-blue-500 hover:text-blue-700 transition-colors ml-auto"
                  >
                    <ExternalLink className="w-3 h-3" />
                    View source insight
                  </button>
                </div>
              </div>

              {/* Modal Actions */}
              <div className="px-6 py-4 border-t border-gray-200 bg-gray-50/50 rounded-b-xl">
                <div className="flex items-center gap-3">
                  {!selectedRec.is_accepted ? (
                    <button
                      onClick={() => handleAcceptFromModal(selectedRec.recommendation_id)}
                      disabled={actionInProgress === selectedRec.recommendation_id}
                      className="flex items-center gap-2 px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition-colors disabled:opacity-50 text-sm font-medium"
                    >
                      <CheckCircle className="w-4 h-4" />
                      {actionInProgress === selectedRec.recommendation_id ? 'Accepting...' : 'Accept Recommendation'}
                    </button>
                  ) : (
                    <span className="flex items-center gap-2 px-4 py-2 bg-green-50 text-green-700 rounded-lg text-sm font-medium">
                      <CheckCircle className="w-4 h-4" />
                      Accepted &mdash; action proposal will be generated
                    </span>
                  )}
                  <button
                    onClick={() => handleDismissFromModal(selectedRec.recommendation_id)}
                    disabled={actionInProgress === selectedRec.recommendation_id}
                    className="px-4 py-2 text-gray-500 hover:text-gray-700 transition-colors text-sm disabled:opacity-50"
                  >
                    Dismiss
                  </button>
                  <button
                    onClick={() => setSelectedRec(null)}
                    className="ml-auto px-4 py-2 bg-white border border-gray-200 text-gray-700 hover:bg-gray-50 rounded-lg transition-colors text-sm"
                  >
                    Close
                  </button>
                </div>
              </div>
            </div>
          </div>
        );
      })()}
    </div>
  );
}

export default AIConsultant;
