/**
 * BreakdownModal — two-level channel breakdown modal.
 *
 * Level 1 (view='all-channels'):
 *   - Blue banner: total value + active channel count
 *   - Horizontal bar chart (revenue by channel)
 *   - Pie/donut chart (distribution)
 *   - Ranked table with "View Details >" row action
 *
 * Level 2 (view='channel-detail'):
 *   - Green summary banner (total revenue + unique products)
 *   - Daily revenue trend line chart
 *   - Products table with progress bars
 *
 * Both views share a single modal container; state.view controls which
 * is rendered. No page navigation is triggered.
 */

import { useState, useEffect } from 'react';
import { X, ArrowLeft } from 'lucide-react';
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer,
  PieChart, Pie, Cell,
  LineChart, Line,
} from 'recharts';
import {
  getChannelBreakdown,
  getChannelDrilldown,
  type ChannelBreakdownSummary,
  type ChannelDrilldownResponse,
} from '../../services/kpiApi';

// ---------------------------------------------------------------------------
// Channel metadata (display name, emoji icon, brand colour)
// ---------------------------------------------------------------------------

const CHANNEL_META: Record<string, { name: string; icon: string; color: string }> = {
  organic:       { name: 'Organic',        icon: '🌱', color: '#16a34a' },
  google_ads:    { name: 'Google Ads',     icon: '🔍', color: '#1a56db' },
  meta_ads:      { name: 'Facebook Ads',   icon: '📘', color: '#1877f2' },
  facebook_ads:  { name: 'Facebook Ads',   icon: '📘', color: '#1877f2' },
  instagram_ads: { name: 'Instagram Ads',  icon: '📷', color: '#e1306c' },
  tiktok_ads:    { name: 'TikTok Ads',     icon: '🎵', color: '#000000' },
  snapchat_ads:  { name: 'Snapchat Ads',   icon: '👻', color: '#fffc00' },
  pinterest_ads: { name: 'Pinterest Ads',  icon: '📌', color: '#e60023' },
  twitter_ads:   { name: 'Twitter/X Ads',  icon: '🐦', color: '#1da1f2' },
};

const PIE_COLORS = ['#1a56db', '#16a34a', '#f59e0b', '#ef4444', '#8b5cf6', '#06b6d4', '#ec4899'];

function fmtCurrency(v: number): string {
  if (v >= 1_000_000) return '$' + (v / 1_000_000).toFixed(1) + 'M';
  if (v >= 1_000) return '$' + (v / 1_000).toFixed(1) + 'k';
  return '$' + v.toFixed(2);
}

// ---------------------------------------------------------------------------
// Public interface
// ---------------------------------------------------------------------------

interface Props {
  open: boolean;
  onClose: () => void;
  /** API metric param: 'revenue' | 'spend' | 'roas' | 'conversions' */
  metric: string;
  timeframe: string;
  /** Modal title, e.g. "Revenue Breakdown" */
  title: string;
}

export function BreakdownModal({ open, onClose, metric, timeframe, title }: Props) {
  const [view, setView] = useState<'all-channels' | 'channel-detail'>('all-channels');
  const [selectedChannel, setSelectedChannel] = useState<string | null>(null);
  const [summary, setSummary] = useState<ChannelBreakdownSummary | null>(null);
  const [drilldown, setDrilldown] = useState<ChannelDrilldownResponse | null>(null);
  const [loadingL1, setLoadingL1] = useState(false);
  const [loadingL2, setLoadingL2] = useState(false);

  // Load L1 whenever the modal opens or metric/timeframe changes
  useEffect(() => {
    if (!open) return;
    setView('all-channels');
    setSelectedChannel(null);
    setSummary(null);
    setLoadingL1(true);
    getChannelBreakdown(metric, timeframe)
      .then(data => setSummary(data))
      .catch(() => {/* silently leave summary null — no data for period */})
      .finally(() => setLoadingL1(false));
  }, [open, metric, timeframe]);

  // Load L2 whenever a channel is selected
  useEffect(() => {
    if (!selectedChannel) return;
    setDrilldown(null);
    setLoadingL2(true);
    getChannelDrilldown(selectedChannel, timeframe)
      .then(data => setDrilldown(data))
      .catch(() => {/* silently leave drilldown null */})
      .finally(() => setLoadingL2(false));
  }, [selectedChannel, timeframe]);

  if (!open) return null;

  const channelMeta = selectedChannel
    ? (CHANNEL_META[selectedChannel] ?? { name: selectedChannel.replace(/_/g, ' '), icon: '📊', color: '#1a56db' })
    : null;

  const handleChannelClick = (channel: string) => {
    setSelectedChannel(channel);
    setView('channel-detail');
  };

  const handleBack = () => {
    setView('all-channels');
    setSelectedChannel(null);
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
      {/* Dark overlay */}
      <div className="absolute inset-0 bg-black/50" onClick={onClose} />

      {/* Modal panel */}
      <div className="relative bg-white rounded-2xl shadow-2xl w-full max-w-4xl max-h-[90vh] overflow-y-auto">
        {view === 'all-channels' ? (
          <Level1View
            title={title}
            summary={summary}
            loading={loadingL1}
            onClose={onClose}
            onChannelClick={handleChannelClick}
          />
        ) : (
          <Level2View
            channelMeta={channelMeta!}
            drilldown={drilldown}
            loading={loadingL2}
            onBack={handleBack}
            onClose={onClose}
          />
        )}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Level 1 — all-channels view
// ---------------------------------------------------------------------------

function Level1View({
  title,
  summary,
  loading,
  onClose,
  onChannelClick,
}: {
  title: string;
  summary: ChannelBreakdownSummary | null;
  loading: boolean;
  onClose: () => void;
  onChannelClick: (channel: string) => void;
}) {
  return (
    <div className="p-6">
      {/* Header */}
      <div className="flex items-center justify-between mb-4">
        <div>
          <h2 className="text-xl font-bold text-gray-900">{title}</h2>
          <span className="inline-block mt-1 px-3 py-1 bg-blue-600 text-white text-xs font-medium rounded-full">
            All Channels
          </span>
        </div>
        <button onClick={onClose} className="p-2 hover:bg-gray-100 rounded-lg transition-colors">
          <X className="w-5 h-5 text-gray-500" />
        </button>
      </div>

      {loading ? (
        <LoadingSkeleton />
      ) : summary ? (
        <>
          {/* Blue summary banner */}
          <div className="bg-blue-50 border border-blue-200 rounded-xl p-4 mb-5 flex items-center justify-between">
            <div>
              <p className="text-sm text-blue-700 font-medium">Total</p>
              <p className="text-2xl font-bold text-blue-900">{fmtCurrency(summary.total)}</p>
            </div>
            <div className="text-right">
              <p className="text-sm text-blue-700">Active Channels</p>
              <p className="text-2xl font-bold text-blue-900">{summary.active_channels}</p>
            </div>
          </div>

          {/* Charts row */}
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mb-5">
            {/* Horizontal bar chart — revenue by channel */}
            <div className="bg-gray-50 rounded-xl p-4">
              <h3 className="text-sm font-semibold text-gray-700 mb-3">Revenue by Channel</h3>
              <ResponsiveContainer width="100%" height={180}>
                <BarChart
                  data={summary.bar_chart.map(r => ({
                    name: CHANNEL_META[r.channel]?.name ?? r.channel.replace(/_/g, ' '),
                    value: r.revenue,
                  }))}
                  layout="vertical"
                  margin={{ top: 0, right: 24, bottom: 0, left: 80 }}
                >
                  <CartesianGrid strokeDasharray="3 3" horizontal={false} />
                  <XAxis
                    type="number"
                    tickFormatter={v => '$' + (v >= 1000 ? (v / 1000).toFixed(0) + 'k' : v)}
                    tick={{ fontSize: 10 }}
                  />
                  <YAxis type="category" dataKey="name" tick={{ fontSize: 10 }} width={76} />
                  <Tooltip formatter={(v: number) => ['$' + v.toLocaleString(), 'Revenue']} />
                  <Bar dataKey="value" fill="#1a56db" radius={[0, 3, 3, 0]} />
                </BarChart>
              </ResponsiveContainer>
            </div>

            {/* Pie / donut chart — distribution */}
            <div className="bg-gray-50 rounded-xl p-4">
              <h3 className="text-sm font-semibold text-gray-700 mb-3">Distribution</h3>
              <div className="flex items-center gap-4">
                <ResponsiveContainer width={140} height={140}>
                  <PieChart>
                    <Pie
                      data={summary.pie_chart.map(r => ({
                        name: CHANNEL_META[r.channel]?.name ?? r.channel.replace(/_/g, ' '),
                        value: r.value,
                      }))}
                      cx="50%"
                      cy="50%"
                      innerRadius={38}
                      outerRadius={62}
                      dataKey="value"
                    >
                      {summary.pie_chart.map((_, i) => (
                        <Cell key={i} fill={PIE_COLORS[i % PIE_COLORS.length]} />
                      ))}
                    </Pie>
                    <Tooltip formatter={(v: number) => ['$' + v.toLocaleString()]} />
                  </PieChart>
                </ResponsiveContainer>
                <div className="flex-1 space-y-1.5 overflow-y-auto max-h-32">
                  {summary.pie_chart.map((row, i) => (
                    <div key={row.channel} className="flex items-center gap-2 text-xs">
                      <span
                        className="w-2.5 h-2.5 rounded-full flex-shrink-0"
                        style={{ background: PIE_COLORS[i % PIE_COLORS.length] }}
                      />
                      <span className="text-gray-700 truncate flex-1">
                        {CHANNEL_META[row.channel]?.name ?? row.channel}
                      </span>
                      <span className="text-gray-500">{row.pct_of_total.toFixed(1)}%</span>
                    </div>
                  ))}
                </div>
              </div>
            </div>
          </div>

          {/* Ranked table */}
          <p className="text-xs text-gray-500 mb-2">Click a channel to drill down</p>
          <div className="overflow-hidden rounded-xl border border-gray-200">
            <table className="w-full text-sm">
              <thead>
                <tr className="bg-gray-50 border-b border-gray-200">
                  <th className="px-4 py-3 text-left text-xs font-semibold text-gray-500 uppercase tracking-wide">Rank</th>
                  <th className="px-4 py-3 text-left text-xs font-semibold text-gray-500 uppercase tracking-wide">Channel</th>
                  <th className="px-4 py-3 text-right text-xs font-semibold text-gray-500 uppercase tracking-wide">Revenue</th>
                  <th className="px-4 py-3 text-right text-xs font-semibold text-gray-500 uppercase tracking-wide">% of Total</th>
                  <th className="px-4 py-3 text-right text-xs font-semibold text-gray-500 uppercase tracking-wide">Action</th>
                </tr>
              </thead>
              <tbody>
                {summary.table.map((row, i) => {
                  const meta = CHANNEL_META[row.channel] ?? {
                    name: row.channel.replace(/_/g, ' '),
                    icon: '📊',
                    color: '#6b7280',
                  };
                  return (
                    <tr
                      key={row.channel}
                      onClick={() => onChannelClick(row.channel)}
                      className={`border-b border-gray-100 cursor-pointer transition-colors ${
                        i === 0 ? 'bg-blue-50 hover:bg-blue-100' : 'bg-white hover:bg-gray-50'
                      }`}
                    >
                      <td className="px-4 py-3">
                        <span className="inline-flex w-7 h-7 rounded-full bg-gray-200 text-gray-700 text-xs font-bold items-center justify-center">
                          {row.rank}
                        </span>
                      </td>
                      <td className="px-4 py-3">
                        <div className="flex items-center gap-2">
                          <span>{meta.icon}</span>
                          <span className="font-medium text-gray-900">{meta.name}</span>
                        </div>
                      </td>
                      <td className="px-4 py-3 text-right font-medium text-gray-900">
                        {fmtCurrency(row.value)}
                      </td>
                      <td className="px-4 py-3 text-right text-gray-600">
                        {row.pct_of_total.toFixed(1)}%
                      </td>
                      <td className="px-4 py-3 text-right">
                        <span className="text-blue-600 text-xs font-medium hover:underline">
                          View Details &gt;
                        </span>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </>
      ) : (
        <div className="text-center py-16 text-gray-400 text-sm">
          No breakdown data available for this period
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Level 2 — channel drill-down view
// ---------------------------------------------------------------------------

function Level2View({
  channelMeta,
  drilldown,
  loading,
  onBack,
  onClose,
}: {
  channelMeta: { name: string; icon: string; color: string };
  drilldown: ChannelDrilldownResponse | null;
  loading: boolean;
  onBack: () => void;
  onClose: () => void;
}) {
  return (
    <div className="p-6">
      {/* Breadcrumb header */}
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center gap-2 text-sm">
          <button
            onClick={onBack}
            className="text-gray-500 hover:text-gray-700 transition-colors"
          >
            All Channels
          </button>
          <span className="text-gray-400">&gt;</span>
          <span className="px-3 py-1 bg-green-600 text-white rounded-full font-medium text-xs">
            {channelMeta.name}
          </span>
        </div>
        <button onClick={onClose} className="p-2 hover:bg-gray-100 rounded-lg transition-colors">
          <X className="w-5 h-5 text-gray-500" />
        </button>
      </div>

      {loading ? (
        <LoadingSkeleton />
      ) : drilldown ? (
        <>
          {/* Green summary banner */}
          <div className="bg-green-50 border border-green-200 rounded-xl p-4 mb-5 flex items-center justify-between">
            <div className="flex items-center gap-3">
              <span className="text-3xl">{channelMeta.icon}</span>
              <div>
                <p className="text-sm text-green-700 font-medium">Total Revenue from Products</p>
                <p className="text-2xl font-bold text-green-900">
                  {fmtCurrency(drilldown.total_revenue)}
                </p>
              </div>
            </div>
            <div className="text-right">
              <p className="text-sm text-green-700">Unique Products</p>
              <p className="text-2xl font-bold text-green-900">{drilldown.unique_products}</p>
            </div>
          </div>

          {/* Daily revenue trend */}
          <div className="bg-gray-50 rounded-xl p-4 mb-5">
            <h3 className="text-sm font-semibold text-gray-700 mb-3">Daily Revenue Trend</h3>
            {drilldown.daily_trend.length > 0 ? (
              <ResponsiveContainer width="100%" height={180}>
                <LineChart
                  data={drilldown.daily_trend}
                  margin={{ top: 4, right: 16, bottom: 0, left: 24 }}
                >
                  <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" />
                  <XAxis
                    dataKey="date"
                    tick={{ fontSize: 10 }}
                    tickFormatter={d => d.slice(5)}
                  />
                  <YAxis
                    tickFormatter={v => '$' + (v >= 1000 ? (v / 1000).toFixed(1) + 'k' : v)}
                    tick={{ fontSize: 10 }}
                  />
                  <Tooltip
                    formatter={(v: number) => ['$' + v.toLocaleString(), 'Revenue']}
                    labelFormatter={l => 'Date: ' + l}
                  />
                  <Line
                    type="monotone"
                    dataKey="revenue"
                    stroke="#16a34a"
                    strokeWidth={2}
                    dot={{ r: 3, fill: '#16a34a' }}
                  />
                </LineChart>
              </ResponsiveContainer>
            ) : (
              <div className="h-44 flex items-center justify-center text-gray-400 text-sm">
                No daily trend data available
              </div>
            )}
          </div>

          {/* Products table */}
          <div className="mb-6">
            <h3 className="text-sm font-semibold text-gray-700 mb-3">Products Generating Revenue</h3>
            {drilldown.products.length > 0 ? (
              <div className="overflow-hidden rounded-xl border border-gray-200">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="bg-gray-50 border-b border-gray-200">
                      <th className="px-4 py-3 text-left text-xs font-semibold text-gray-500 uppercase tracking-wide">Rank</th>
                      <th className="px-4 py-3 text-left text-xs font-semibold text-gray-500 uppercase tracking-wide">Product Name</th>
                      <th className="px-4 py-3 text-right text-xs font-semibold text-gray-500 uppercase tracking-wide">Revenue</th>
                      <th className="px-4 py-3 text-right text-xs font-semibold text-gray-500 uppercase tracking-wide">Units</th>
                      <th className="px-4 py-3 text-right text-xs font-semibold text-gray-500 uppercase tracking-wide">Avg Price</th>
                      <th className="px-4 py-3 text-right text-xs font-semibold text-gray-500 uppercase tracking-wide">% of Channel</th>
                    </tr>
                  </thead>
                  <tbody>
                    {drilldown.products.map((row, i) => (
                      <tr key={i} className="border-b border-gray-100 hover:bg-gray-50 transition-colors">
                        <td className="px-4 py-3">
                          <span className="inline-flex w-7 h-7 rounded-full bg-green-100 text-green-700 text-xs font-bold items-center justify-center">
                            {row.rank}
                          </span>
                        </td>
                        <td className="px-4 py-3 font-medium text-gray-900">{row.product_name}</td>
                        <td className="px-4 py-3 text-right text-gray-900">{fmtCurrency(row.revenue)}</td>
                        <td className="px-4 py-3 text-right text-gray-600">{row.units_sold.toLocaleString()}</td>
                        <td className="px-4 py-3 text-right text-gray-600">{fmtCurrency(row.avg_price)}</td>
                        <td className="px-4 py-3 text-right">
                          <div className="flex items-center justify-end gap-2">
                            <div className="w-16 bg-gray-200 rounded-full h-1.5">
                              <div
                                className="bg-green-500 h-1.5 rounded-full"
                                style={{ width: Math.min(100, row.pct_of_channel) + '%' }}
                              />
                            </div>
                            <span className="text-gray-600 text-xs w-10 text-right">
                              {row.pct_of_channel.toFixed(1)}%
                            </span>
                          </div>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : (
              <div className="text-center py-8 text-gray-400 text-sm bg-gray-50 rounded-xl">
                No product data available
              </div>
            )}
          </div>
        </>
      ) : (
        <div className="text-center py-16 text-gray-400 text-sm">
          No drill-down data available
        </div>
      )}

      {/* Footer buttons */}
      <div className="flex justify-between border-t border-gray-100 pt-4">
        <button
          onClick={onBack}
          className="flex items-center gap-2 px-4 py-2 text-gray-600 hover:text-gray-900 hover:bg-gray-50 rounded-lg transition-colors"
        >
          <ArrowLeft className="w-4 h-4" />
          Back
        </button>
        <button
          onClick={onClose}
          className="px-4 py-2 bg-gray-100 text-gray-700 rounded-lg hover:bg-gray-200 transition-colors"
        >
          Close
        </button>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Shared loading skeleton
// ---------------------------------------------------------------------------

function LoadingSkeleton() {
  return (
    <div className="space-y-4 animate-pulse">
      <div className="h-16 bg-gray-100 rounded-xl" />
      <div className="grid grid-cols-2 gap-4">
        <div className="h-48 bg-gray-100 rounded-xl" />
        <div className="h-48 bg-gray-100 rounded-xl" />
      </div>
      <div className="h-48 bg-gray-100 rounded-xl" />
    </div>
  );
}
