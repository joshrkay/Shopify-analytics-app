/**
 * Budget Pacing Page
 *
 * Displays monthly ad budget pacing across platforms.
 * Matches the Figma "Budget Pacing" design.
 *
 * Data:
 *   GET  /api/budget-pacing          → getPacing()
 *   GET  /api/budgets                → listBudgets()
 *   POST /api/budgets                → createBudget()
 */

import { useState, useEffect, useCallback } from 'react';
import { Gauge, Plus, X, TrendingUp, TrendingDown, Minus } from 'lucide-react';
import { getPacing, listBudgets, createBudget } from '../services/budgetPacingApi';
import type { PacingItem } from '../services/budgetPacingApi';

function formatCents(cents: number): string {
  return `$${(cents / 100).toLocaleString(undefined, {
    minimumFractionDigits: 0,
    maximumFractionDigits: 0,
  })}`;
}

function formatPlatformName(platform: string): string {
  return platform
    .replace(/_/g, ' ')
    .replace(/\b\w/g, (c) => c.toUpperCase());
}

const STATUS_CONFIG: Record<string, { bar: string; badge: string; text: string; icon: React.ElementType }> = {
  on_pace: {
    bar: 'bg-green-500',
    badge: 'bg-green-100 text-green-800',
    text: 'On Pace',
    icon: TrendingUp,
  },
  slightly_over: {
    bar: 'bg-yellow-500',
    badge: 'bg-yellow-100 text-yellow-800',
    text: 'Slightly Over',
    icon: Minus,
  },
  over_budget: {
    bar: 'bg-red-500',
    badge: 'bg-red-100 text-red-800',
    text: 'Over Budget',
    icon: TrendingDown,
  },
};

function PacingCard({ item }: { item: PacingItem }) {
  const barWidth = Math.min(item.pct_spent * 100, 100);
  const timeMarker = item.pct_time * 100;
  const config = STATUS_CONFIG[item.status] ?? STATUS_CONFIG.on_pace;
  const StatusIcon = config.icon;

  return (
    <div className="bg-white rounded-lg border border-gray-200 p-5 shadow-sm">
      {/* Header row */}
      <div className="flex items-center justify-between mb-4">
        <div>
          <h3 className="font-semibold text-gray-900">{formatPlatformName(item.platform)}</h3>
          <p className="text-sm text-gray-500 mt-0.5">
            {formatCents(item.spent_cents)} of {formatCents(item.budget_cents)} spent
          </p>
        </div>
        <span
          className={`inline-flex items-center gap-1 px-2.5 py-1 rounded-full text-xs font-medium ${config.badge}`}
        >
          <StatusIcon className="w-3 h-3" />
          {config.text}
        </span>
      </div>

      {/* Progress bar */}
      <div className="relative h-3 bg-gray-100 rounded-full overflow-hidden mb-2">
        <div
          className={`h-full rounded-full transition-all duration-500 ${config.bar}`}
          style={{ width: `${barWidth}%` }}
        />
        {/* Time marker */}
        <div
          className="absolute top-0 h-full w-0.5 bg-gray-600 opacity-50"
          style={{ left: `${timeMarker}%` }}
          title={`${timeMarker.toFixed(0)}% of month elapsed`}
        />
      </div>

      {/* Footer labels */}
      <div className="flex justify-between text-xs text-gray-500">
        <span>{(item.pct_spent * 100).toFixed(0)}% spent</span>
        <span>{(item.pct_time * 100).toFixed(0)}% of month</span>
      </div>
    </div>
  );
}

interface SetBudgetModalProps {
  open: boolean;
  onClose: () => void;
  onCreated: () => void;
}

const PLATFORM_OPTIONS = [
  { label: 'Meta Ads', value: 'meta_ads' },
  { label: 'Google Ads', value: 'google_ads' },
  { label: 'TikTok Ads', value: 'tiktok_ads' },
  { label: 'Snapchat Ads', value: 'snapchat_ads' },
  { label: 'Pinterest Ads', value: 'pinterest_ads' },
  { label: 'Twitter Ads', value: 'twitter_ads' },
];

function SetBudgetModal({ open, onClose, onCreated }: SetBudgetModalProps) {
  const [newPlatform, setNewPlatform] = useState('meta_ads');
  const [newBudget, setNewBudget] = useState('');
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  if (!open) return null;

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    const cents = Math.round(parseFloat(newBudget) * 100);
    if (isNaN(cents) || cents <= 0) return;
    setSaving(true);
    setError(null);
    try {
      await createBudget({
        source_platform: newPlatform,
        budget_monthly_cents: cents,
        start_date: new Date().toISOString().slice(0, 10),
      });
      setNewBudget('');
      onCreated();
      onClose();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to create budget');
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center">
      <div className="absolute inset-0 bg-black bg-opacity-40" onClick={onClose} />
      <div className="relative bg-white rounded-xl shadow-xl w-full max-w-sm mx-4 p-6">
        <div className="flex items-center justify-between mb-6">
          <h2 className="text-lg font-semibold text-gray-900">Set Monthly Budget</h2>
          <button onClick={onClose} className="p-1 hover:bg-gray-100 rounded-lg transition-colors">
            <X className="w-5 h-5 text-gray-500" />
          </button>
        </div>

        {error && (
          <div className="mb-4 bg-red-50 border border-red-200 rounded-lg px-4 py-3 text-sm text-red-700">
            {error}
          </div>
        )}

        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Platform</label>
            <select
              value={newPlatform}
              onChange={(e) => setNewPlatform(e.target.value)}
              className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
            >
              {PLATFORM_OPTIONS.map((opt) => (
                <option key={opt.value} value={opt.value}>
                  {opt.label}
                </option>
              ))}
            </select>
          </div>

          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">
              Monthly Budget ($)
            </label>
            <input
              type="number"
              step="any"
              min="1"
              value={newBudget}
              onChange={(e) => setNewBudget(e.target.value)}
              className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
              placeholder="e.g. 5000"
              required
            />
          </div>

          <div className="flex items-center justify-end gap-3 pt-2">
            <button
              type="button"
              onClick={onClose}
              className="px-4 py-2 text-sm text-gray-700 hover:bg-gray-100 rounded-lg transition-colors"
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={saving}
              className="px-4 py-2 text-sm bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition-colors disabled:opacity-50"
            >
              {saving ? 'Saving...' : 'Set Budget'}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}

export function BudgetPacing() {
  const [pacing, setPacing] = useState<PacingItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [modalOpen, setModalOpen] = useState(false);

  const now = new Date();
  const monthLabel = now.toLocaleString('default', { month: 'long', year: 'numeric' });

  const fetchData = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [pacingResult] = await Promise.all([
        getPacing(),
        listBudgets(),
      ]);
      setPacing(pacingResult.pacing);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load budget data');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  // Summary counts
  const onPaceCount = pacing.filter((p) => p.status === 'on_pace').length;
  const overCount = pacing.filter((p) => p.status !== 'on_pace').length;
  const totalBudget = pacing.reduce((sum, p) => sum + p.budget_cents, 0);
  const totalSpent = pacing.reduce((sum, p) => sum + p.spent_cents, 0);

  return (
    <div className="p-8">
      {/* Header */}
      <div className="flex items-center justify-between mb-8">
        <div>
          <div className="flex items-center gap-3 mb-2">
            <div className="bg-blue-100 p-2 rounded-lg">
              <Gauge className="w-6 h-6 text-blue-600" />
            </div>
            <h1 className="text-3xl font-semibold text-gray-900">Budget Pacing</h1>
          </div>
          <p className="text-gray-600">{monthLabel}</p>
        </div>
        <button
          onClick={() => setModalOpen(true)}
          className="flex items-center gap-2 px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition-colors text-sm font-medium"
        >
          <Plus className="w-4 h-4" />
          Set Budget
        </button>
      </div>

      {/* Error banner */}
      {error && (
        <div className="mb-6 bg-red-50 border border-red-200 rounded-lg px-4 py-3 text-sm text-red-700">
          {error}
        </div>
      )}

      {/* Summary cards */}
      {pacing.length > 0 && (
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-8">
          <div className="bg-white rounded-lg border border-gray-200 p-4 shadow-sm">
            <p className="text-xs text-gray-500 mb-1">Total Budget</p>
            <p className="text-xl font-semibold text-gray-900">{formatCents(totalBudget)}</p>
          </div>
          <div className="bg-white rounded-lg border border-gray-200 p-4 shadow-sm">
            <p className="text-xs text-gray-500 mb-1">Total Spent</p>
            <p className="text-xl font-semibold text-gray-900">{formatCents(totalSpent)}</p>
          </div>
          <div className="bg-white rounded-lg border border-gray-200 p-4 shadow-sm">
            <p className="text-xs text-gray-500 mb-1">On Pace</p>
            <p className="text-xl font-semibold text-green-600">{onPaceCount}</p>
          </div>
          <div className="bg-white rounded-lg border border-gray-200 p-4 shadow-sm">
            <p className="text-xs text-gray-500 mb-1">Needs Attention</p>
            <p className="text-xl font-semibold text-red-600">{overCount}</p>
          </div>
        </div>
      )}

      {/* Pacing list */}
      {loading ? (
        <div className="flex items-center justify-center py-16">
          <div className="text-center">
            <div className="w-8 h-8 border-4 border-blue-600 border-t-transparent rounded-full animate-spin mx-auto mb-4" />
            <p className="text-gray-500">Loading budget data...</p>
          </div>
        </div>
      ) : pacing.length === 0 ? (
        <div className="bg-white rounded-lg border border-gray-200 p-12 text-center">
          <Gauge className="w-12 h-12 text-gray-300 mx-auto mb-4" />
          <p className="text-gray-500 font-medium">No budgets configured</p>
          <p className="text-gray-400 text-sm mt-1">
            Set monthly ad spend budgets to track pacing across platforms.
          </p>
          <button
            onClick={() => setModalOpen(true)}
            className="mt-4 px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition-colors text-sm font-medium"
          >
            Set Budget
          </button>
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {pacing.map((item) => (
            <PacingCard key={item.budget_id} item={item} />
          ))}
        </div>
      )}

      <SetBudgetModal
        open={modalOpen}
        onClose={() => setModalOpen(false)}
        onCreated={fetchData}
      />
    </div>
  );
}

export default BudgetPacing;
