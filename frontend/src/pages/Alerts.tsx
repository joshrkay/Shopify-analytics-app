/**
 * Automated Alerts Page
 *
 * Displays and manages alert rules and alert history.
 * Matches the Figma "Automated Alerts" design.
 *
 * Data:
 *   GET  /api/alert-rules            → listAlertRules()
 *   POST /api/alert-rules            → createAlertRule()
 *   DELETE /api/alert-rules/:id      → deleteAlertRule()
 *   PATCH /api/alert-rules/:id       → toggleAlertRule()
 *   GET  /api/alert-history          → getAlertHistory()
 */

import { useState, useEffect, useCallback } from 'react';
import {
  Bell,
  Plus,
  Trash2,
  ToggleLeft,
  ToggleRight,
  AlertTriangle,
  AlertCircle,
  Info,
  CheckCircle,
  X,
} from 'lucide-react';
import {
  listAlertRules,
  createAlertRule,
  deleteAlertRule,
  toggleAlertRule,
  getAlertHistory,
} from '../services/alertsApi';
import type { AlertRule, AlertExecution, RulesListResponse } from '../services/alertsApi';

const OPERATOR_LABELS: Record<string, string> = {
  gt: '>',
  lt: '<',
  eq: '=',
  gte: '≥',
  lte: '≤',
};

function SeverityBadge({ severity }: { severity: string }) {
  const classes: Record<string, string> = {
    info: 'bg-blue-100 text-blue-800',
    warning: 'bg-yellow-100 text-yellow-800',
    critical: 'bg-red-100 text-red-800',
  };
  const icons: Record<string, React.ReactNode> = {
    info: <Info className="w-3 h-3" />,
    warning: <AlertTriangle className="w-3 h-3" />,
    critical: <AlertCircle className="w-3 h-3" />,
  };
  return (
    <span
      className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium ${
        classes[severity] ?? 'bg-gray-100 text-gray-800'
      }`}
    >
      {icons[severity]}
      {severity.charAt(0).toUpperCase() + severity.slice(1)}
    </span>
  );
}

interface CreateAlertModalProps {
  open: boolean;
  onClose: () => void;
  onCreated: () => void;
}

function CreateAlertModal({ open, onClose, onCreated }: CreateAlertModalProps) {
  const [formName, setFormName] = useState('');
  const [formMetric, setFormMetric] = useState('roas');
  const [formOperator, setFormOperator] = useState('lt');
  const [formThreshold, setFormThreshold] = useState('');
  const [formPeriod, setFormPeriod] = useState('daily');
  const [formSeverity, setFormSeverity] = useState('warning');
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  if (!open) return null;

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    const threshold = parseFloat(formThreshold);
    if (!formName || isNaN(threshold)) return;
    setSaving(true);
    setError(null);
    try {
      await createAlertRule({
        name: formName,
        metric_name: formMetric,
        comparison_operator: formOperator,
        threshold_value: threshold,
        evaluation_period: formPeriod,
        severity: formSeverity,
      });
      setFormName('');
      setFormThreshold('');
      onCreated();
      onClose();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to create rule');
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center">
      <div className="absolute inset-0 bg-black bg-opacity-40" onClick={onClose} />
      <div className="relative bg-white rounded-xl shadow-xl w-full max-w-md mx-4 p-6">
        <div className="flex items-center justify-between mb-6">
          <h2 className="text-lg font-semibold text-gray-900">Create Alert Rule</h2>
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
            <label className="block text-sm font-medium text-gray-700 mb-1">Rule Name</label>
            <input
              type="text"
              value={formName}
              onChange={(e) => setFormName(e.target.value)}
              className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
              placeholder="e.g. Low ROAS Alert"
              required
            />
          </div>

          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Metric</label>
              <select
                value={formMetric}
                onChange={(e) => setFormMetric(e.target.value)}
                className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
              >
                <option value="roas">ROAS</option>
                <option value="spend">Ad Spend</option>
                <option value="revenue">Revenue</option>
              </select>
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Condition</label>
              <select
                value={formOperator}
                onChange={(e) => setFormOperator(e.target.value)}
                className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
              >
                <option value="gt">Greater than (&gt;)</option>
                <option value="lt">Less than (&lt;)</option>
                <option value="eq">Equal to (=)</option>
                <option value="gte">Greater or equal (≥)</option>
                <option value="lte">Less or equal (≤)</option>
              </select>
            </div>
          </div>

          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Threshold</label>
            <input
              type="number"
              step="any"
              value={formThreshold}
              onChange={(e) => setFormThreshold(e.target.value)}
              className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
              placeholder="e.g. 2.5"
              required
            />
          </div>

          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Evaluation Period</label>
              <select
                value={formPeriod}
                onChange={(e) => setFormPeriod(e.target.value)}
                className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
              >
                <option value="daily">Daily</option>
                <option value="weekly">Weekly</option>
                <option value="monthly">Monthly</option>
              </select>
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Severity</label>
              <select
                value={formSeverity}
                onChange={(e) => setFormSeverity(e.target.value)}
                className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
              >
                <option value="info">Info</option>
                <option value="warning">Warning</option>
                <option value="critical">Critical</option>
              </select>
            </div>
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
              {saving ? 'Creating...' : 'Create Rule'}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}

export function Alerts() {
  const [selectedTab, setSelectedTab] = useState<'rules' | 'history'>('rules');
  const [rulesData, setRulesData] = useState<RulesListResponse | null>(null);
  const [history, setHistory] = useState<AlertExecution[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [modalOpen, setModalOpen] = useState(false);
  const [togglingId, setTogglingId] = useState<string | null>(null);
  const [deletingId, setDeletingId] = useState<string | null>(null);

  const fetchRules = useCallback(async () => {
    try {
      const result = await listAlertRules();
      setRulesData(result);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load rules');
    }
  }, []);

  const fetchHistory = useCallback(async () => {
    try {
      const result = await getAlertHistory();
      setHistory(result);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load history');
    }
  }, []);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    Promise.all([fetchRules(), fetchHistory()]).then(() => {
      if (!cancelled) setLoading(false);
    });
    return () => { cancelled = true; };
  }, [fetchRules, fetchHistory]);

  const handleToggle = async (rule: AlertRule) => {
    setTogglingId(rule.id);
    try {
      await toggleAlertRule(rule.id, !rule.enabled);
      await fetchRules();
    } finally {
      setTogglingId(null);
    }
  };

  const handleDelete = async (ruleId: string) => {
    setDeletingId(ruleId);
    try {
      await deleteAlertRule(ruleId);
      await fetchRules();
    } finally {
      setDeletingId(null);
    }
  };

  const rules: AlertRule[] = rulesData?.rules ?? [];

  return (
    <div className="p-8">
      {/* Header */}
      <div className="flex items-center justify-between mb-8">
        <div>
          <div className="flex items-center gap-3 mb-2">
            <div className="bg-yellow-100 p-2 rounded-lg">
              <Bell className="w-6 h-6 text-yellow-600" />
            </div>
            <h1 className="text-3xl font-semibold text-gray-900">Automated Alerts</h1>
          </div>
          <p className="text-gray-600">
            Set threshold-based alerts for ROAS, spend, and revenue metrics
          </p>
        </div>
        <button
          onClick={() => setModalOpen(true)}
          className="flex items-center gap-2 px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition-colors text-sm font-medium"
        >
          <Plus className="w-4 h-4" />
          Create Alert
        </button>
      </div>

      {/* Error banner */}
      {error && (
        <div className="mb-6 bg-red-50 border border-red-200 rounded-lg px-4 py-3 text-sm text-red-700">
          {error}
        </div>
      )}

      {/* Tabs */}
      <div className="border-b border-gray-200 mb-6">
        <div className="flex gap-6">
          {(['rules', 'history'] as const).map((tab) => (
            <button
              key={tab}
              onClick={() => setSelectedTab(tab)}
              className={`pb-3 text-sm font-medium border-b-2 transition-colors ${
                selectedTab === tab
                  ? 'border-blue-600 text-blue-600'
                  : 'border-transparent text-gray-500 hover:text-gray-700'
              }`}
            >
              {tab === 'rules'
                ? `Rules (${rules.length})`
                : 'History'}
            </button>
          ))}
        </div>
      </div>

      {/* Content */}
      {loading && !rulesData ? (
        <div className="flex items-center justify-center py-16">
          <div className="text-center">
            <div className="w-8 h-8 border-4 border-blue-600 border-t-transparent rounded-full animate-spin mx-auto mb-4" />
            <p className="text-gray-500">Loading alerts...</p>
          </div>
        </div>
      ) : selectedTab === 'rules' ? (
        rules.length === 0 ? (
          <div className="bg-white rounded-lg border border-gray-200 p-12 text-center">
            <Bell className="w-12 h-12 text-gray-300 mx-auto mb-4" />
            <p className="text-gray-500 font-medium">No alert rules yet</p>
            <p className="text-gray-400 text-sm mt-1">
              Set up threshold alerts for ROAS, spend, and revenue.
            </p>
            <button
              onClick={() => setModalOpen(true)}
              className="mt-4 px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition-colors text-sm font-medium"
            >
              Create Alert
            </button>
          </div>
        ) : (
          <div className="space-y-4">
            {rules.map((rule) => (
              <div
                key={rule.id}
                className="bg-white rounded-lg border border-gray-200 p-5 shadow-sm flex items-center justify-between gap-4"
              >
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2 mb-1">
                    <span className="font-semibold text-gray-900">{rule.name}</span>
                    <SeverityBadge severity={rule.severity} />
                    {!rule.enabled && (
                      <span className="px-2 py-0.5 rounded-full text-xs font-medium bg-gray-100 text-gray-600">
                        Disabled
                      </span>
                    )}
                  </div>
                  <p className="text-sm text-gray-500">
                    {rule.metric_name}{' '}
                    <span className="font-mono font-bold">
                      {OPERATOR_LABELS[rule.comparison_operator] ?? rule.comparison_operator}
                    </span>{' '}
                    {rule.threshold_value} &bull; {rule.evaluation_period}
                  </p>
                </div>
                <div className="flex items-center gap-2 flex-shrink-0">
                  <button
                    onClick={() => handleToggle(rule)}
                    disabled={togglingId === rule.id}
                    className="flex items-center gap-1.5 px-3 py-1.5 text-sm text-gray-700 border border-gray-300 rounded-lg hover:bg-gray-50 transition-colors disabled:opacity-50"
                  >
                    {rule.enabled ? (
                      <>
                        <ToggleRight className="w-4 h-4 text-green-600" />
                        Disable
                      </>
                    ) : (
                      <>
                        <ToggleLeft className="w-4 h-4 text-gray-400" />
                        Enable
                      </>
                    )}
                  </button>
                  <button
                    onClick={() => handleDelete(rule.id)}
                    disabled={deletingId === rule.id}
                    className="flex items-center gap-1.5 px-3 py-1.5 text-sm text-red-600 border border-red-200 rounded-lg hover:bg-red-50 transition-colors disabled:opacity-50"
                  >
                    <Trash2 className="w-4 h-4" />
                    Delete
                  </button>
                </div>
              </div>
            ))}
          </div>
        )
      ) : (
        /* History tab */
        history.length === 0 ? (
          <div className="bg-white rounded-lg border border-gray-200 p-12 text-center">
            <Bell className="w-12 h-12 text-gray-300 mx-auto mb-4" />
            <p className="text-gray-500 font-medium">No alert history</p>
            <p className="text-gray-400 text-sm mt-1">
              Alert executions will appear here when rules are triggered.
            </p>
          </div>
        ) : (
          <div className="bg-white rounded-lg border border-gray-200 shadow-sm divide-y divide-gray-100">
            {history.map((exec) => (
              <div key={exec.id} className="flex items-center justify-between px-5 py-4">
                <div>
                  <p className="text-sm text-gray-900">
                    Metric value:{' '}
                    <span className="font-semibold">{exec.metric_value.toFixed(2)}</span>
                    {' '}(threshold: {exec.threshold_value.toFixed(2)})
                  </p>
                  <p className="text-xs text-gray-500 mt-0.5">
                    {new Date(exec.fired_at).toLocaleString()}
                  </p>
                </div>
                {exec.resolved_at && (
                  <span className="inline-flex items-center gap-1 px-2 py-0.5 bg-green-100 text-green-800 rounded-full text-xs font-medium">
                    <CheckCircle className="w-3 h-3" />
                    Resolved
                  </span>
                )}
              </div>
            ))}
          </div>
        )
      )}

      <CreateAlertModal
        open={modalOpen}
        onClose={() => setModalOpen(false)}
        onCreated={fetchRules}
      />
    </div>
  );
}

export default Alerts;
