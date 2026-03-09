/**
 * AI Consultant Page
 *
 * Displays AI-generated recommendations from the backend.
 * Matches the Figma "AI Consultant" design.
 *
 * Data: GET /api/recommendations (via recommendationsApi)
 */

import { useState, useEffect, useCallback } from 'react';
import {
  Sparkles,
  TrendingUp,
  AlertCircle,
  CheckCircle,
  Target,
  DollarSign,
  Lightbulb,
  ArrowRight,
} from 'lucide-react';
import { listRecommendations, acceptRecommendation, dismissRecommendation } from '../services/recommendationsApi';
import type { Recommendation, RecommendationPriority } from '../types/recommendations';

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

export function AIConsultant() {
  const [recommendations, setRecommendations] = useState<Recommendation[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [filter, setFilter] = useState<FilterOption>('all');
  const [actionInProgress, setActionInProgress] = useState<string | null>(null);

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
                      <button className="px-4 py-2 text-gray-700 hover:bg-gray-100 rounded-lg transition-colors text-sm">
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
    </div>
  );
}

export default AIConsultant;
