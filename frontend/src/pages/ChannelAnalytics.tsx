/**
 * ChannelAnalytics — per-channel deep-dive analytics page.
 *
 * Route: /channels/:platform
 *
 * Sections:
 * 1. Header: channel name + emoji icon + timeframe selector
 * 2. KPI cards: Revenue, Spend, ROAS, Orders, Clicks, CTR, Conv Rate
 * 3. Daily revenue trend — line chart
 * 4. Products table — top products driving revenue for this channel
 *
 * Data sources:
 * - GET /api/channels/{platform}/metrics — KPI cards + daily trend
 * - GET /api/datasets/channel-breakdown/{channel} — products table
 *   (reuses existing drilldown endpoint)
 */

import { useState, useEffect } from "react";
import { useParams, Link } from "react-router-dom";
import { TrendingUp, TrendingDown, Calendar, ChevronDown, ArrowLeft } from "lucide-react";
import {
  LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer,
} from "recharts";
import { getChannelMetrics, getChannelDrilldown, type ChannelMetricsResponse } from "../services/kpiApi";
import type { ChannelDrilldownResponse } from "../services/kpiApi";

// ---------------------------------------------------------------------------
// Channel display metadata
// ---------------------------------------------------------------------------

const CHANNEL_META: Record<string, { name: string; icon: string }> = {
  organic:       { name: "Organic",        icon: "🌱" },
  google_ads:    { name: "Google Ads",     icon: "🔍" },
  meta_ads:      { name: "Facebook Ads",   icon: "📘" },
  facebook_ads:  { name: "Facebook Ads",   icon: "📘" },
  instagram_ads: { name: "Instagram Ads",  icon: "📷" },
  tiktok_ads:    { name: "TikTok Ads",     icon: "🎵" },
  snapchat_ads:  { name: "Snapchat Ads",   icon: "👻" },
  pinterest_ads: { name: "Pinterest Ads",  icon: "📌" },
  twitter_ads:   { name: "Twitter/X Ads",  icon: "🐦" },
};

type TimeFrame = "7days" | "thisWeek" | "30days" | "thisMonth" | "90days" | "thisQuarter";

const TIMEFRAME_OPTIONS: { id: TimeFrame; label: string }[] = [
  { id: "7days",       label: "Last 7 days"    },
  { id: "thisWeek",    label: "This week"       },
  { id: "30days",      label: "Last 30 days"   },
  { id: "thisMonth",   label: "This month"     },
  { id: "90days",      label: "Last 90 days"   },
  { id: "thisQuarter", label: "This quarter"   },
];

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function fmtCurrency(v: number): string {
  if (v >= 1_000_000) return "$" + (v / 1_000_000).toFixed(1) + "M";
  if (v >= 1_000)     return "$" + (v / 1_000).toFixed(1) + "k";
  return "$" + v.toFixed(2);
}

function fmtPct(v: number): string {
  return (v * 100).toFixed(2) + "%";
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export function ChannelAnalytics() {
  const { platform = "google_ads" } = useParams<{ platform: string }>();
  const [timeframe, setTimeframe] = useState<TimeFrame>("30days");
  const [showTimeframeMenu, setShowTimeframeMenu] = useState(false);

  const [metrics, setMetrics] = useState<ChannelMetricsResponse | null>(null);
  const [drilldown, setDrilldown] = useState<ChannelDrilldownResponse | null>(null);
  const [loading, setLoading] = useState(false);

  const meta = CHANNEL_META[platform] ?? { name: platform.replace(/_/g, " "), icon: "📊" };
  const displayName = metrics?.display_name ?? meta.name;

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setMetrics(null);
    setDrilldown(null);

    Promise.all([
      getChannelMetrics(platform, timeframe),
      getChannelDrilldown(platform, timeframe),
    ])
      .then(([m, d]) => {
        if (!cancelled) {
          setMetrics(m);
          setDrilldown(d);
        }
      })
      .catch((err) => { console.error('Failed to fetch channel analytics:', err); })
      .finally(() => { if (!cancelled) setLoading(false); });

    return () => { cancelled = true; };
  }, [platform, timeframe]);

  const timeframeLabel = TIMEFRAME_OPTIONS.find(o => o.id === timeframe)?.label ?? "Last 30 days";

  return (
    <div className="max-w-7xl mx-auto p-4 sm:p-6">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between mb-6 gap-4">
        <div className="flex items-center gap-3">
          <Link
            to="/home"
            className="p-2 rounded-lg hover:bg-gray-100 text-gray-500 hover:text-gray-700 transition-colors"
            aria-label="Back to overview"
          >
            <ArrowLeft className="w-5 h-5" />
          </Link>
          <div>
            <div className="flex items-center gap-2">
              <span className="text-2xl">{meta.icon}</span>
              <h1 className="text-2xl font-bold text-gray-900">{displayName}</h1>
            </div>
            <p className="text-gray-500 text-sm mt-0.5">Channel analytics — {timeframeLabel}</p>
          </div>
        </div>

        {/* Timeframe picker */}
        <div className="relative">
          <button
            onClick={() => setShowTimeframeMenu(!showTimeframeMenu)}
            className="flex items-center gap-2 px-4 py-2 border border-gray-300 rounded-lg hover:bg-gray-50"
          >
            <Calendar className="w-4 h-4 text-gray-600" />
            <span className="text-sm font-medium text-gray-900">{timeframeLabel}</span>
            <ChevronDown className="w-4 h-4 text-gray-500" />
          </button>
          {showTimeframeMenu && (
            <>
              <div className="fixed inset-0 z-10" onClick={() => setShowTimeframeMenu(false)} />
              <div className="absolute right-0 mt-2 w-48 bg-white rounded-lg shadow-lg border border-gray-200 z-20 py-1">
                {TIMEFRAME_OPTIONS.map(opt => (
                  <button
                    key={opt.id}
                    onClick={() => { setTimeframe(opt.id); setShowTimeframeMenu(false); }}
                    className={`w-full text-left px-4 py-2 text-sm hover:bg-gray-50 ${timeframe === opt.id ? "text-blue-600 font-medium" : "text-gray-700"}`}
                  >
                    {opt.label}
                  </button>
                ))}
              </div>
            </>
          )}
        </div>
      </div>

      {/* KPI cards */}
      <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 gap-4 mb-6">
        {loading ? (
          Array.from({ length: 8 }).map((_, i) => (
            <div key={i} className="bg-white rounded-xl border border-gray-200 p-5 animate-pulse">
              <div className="h-3 bg-gray-200 rounded w-20 mb-3" />
              <div className="h-7 bg-gray-200 rounded w-24" />
            </div>
          ))
        ) : metrics ? (
          <>
            <KpiCard label="Revenue"    value={fmtCurrency(metrics.revenue)}  />
            <KpiCard label="Ad Spend"   value={fmtCurrency(metrics.spend)}    />
            <KpiCard label="ROAS"       value={metrics.roas.toFixed(2) + "x"} />
            <KpiCard label="Orders"     value={metrics.orders.toLocaleString()} />
            <KpiCard label="Clicks"     value={metrics.clicks.toLocaleString()} />
            <KpiCard label="Impressions" value={metrics.impressions.toLocaleString()} />
            <KpiCard label="CTR"        value={fmtPct(metrics.ctr)}           />
            <KpiCard label="Conv Rate"  value={fmtPct(metrics.conversion_rate)} />
          </>
        ) : (
          <div className="col-span-4 text-center py-8 text-gray-400 text-sm">
            No data available for this period
          </div>
        )}
      </div>

      {/* Daily revenue trend */}
      <div className="bg-white rounded-xl border border-gray-200 p-6 mb-6">
        <h2 className="font-semibold text-gray-900 mb-4">Daily Revenue Trend</h2>
        {loading ? (
          <div className="h-56 flex items-center justify-center">
            <div className="animate-pulse text-gray-300 text-sm">Loading chart…</div>
          </div>
        ) : metrics && metrics.daily_trend.length > 0 ? (
          <ResponsiveContainer width="100%" height={220}>
            <LineChart
              data={metrics.daily_trend}
              margin={{ top: 4, right: 16, bottom: 0, left: 24 }}
            >
              <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" />
              <XAxis
                dataKey="date"
                tick={{ fontSize: 10 }}
                tickFormatter={d => d.slice(5)}
              />
              <YAxis
                tickFormatter={v => "$" + (v >= 1000 ? (v / 1000).toFixed(0) + "k" : v)}
                tick={{ fontSize: 10 }}
              />
              <Tooltip
                formatter={(v: number) => ["$" + v.toLocaleString(), "Revenue"]}
                labelFormatter={l => "Date: " + l}
              />
              <Line
                type="monotone"
                dataKey="revenue"
                stroke="#1a56db"
                strokeWidth={2}
                dot={{ r: 2, fill: "#1a56db" }}
                activeDot={{ r: 5 }}
              />
            </LineChart>
          </ResponsiveContainer>
        ) : (
          <div className="h-56 flex items-center justify-center text-gray-400 text-sm">
            No daily trend data available for this period
          </div>
        )}
      </div>

      {/* Products table */}
      <div className="bg-white rounded-xl border border-gray-200 p-6">
        <h2 className="font-semibold text-gray-900 mb-4">Top Products</h2>
        {loading ? (
          <div className="space-y-3 animate-pulse">
            {Array.from({ length: 5 }).map((_, i) => (
              <div key={i} className="flex justify-between py-2">
                <div className="h-4 bg-gray-200 rounded w-48" />
                <div className="h-4 bg-gray-200 rounded w-20" />
              </div>
            ))}
          </div>
        ) : drilldown && drilldown.products.length > 0 ? (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-gray-200">
                  <th className="pb-3 text-left text-xs font-semibold text-gray-500 uppercase tracking-wide">Rank</th>
                  <th className="pb-3 text-left text-xs font-semibold text-gray-500 uppercase tracking-wide">Product</th>
                  <th className="pb-3 text-right text-xs font-semibold text-gray-500 uppercase tracking-wide">Revenue</th>
                  <th className="pb-3 text-right text-xs font-semibold text-gray-500 uppercase tracking-wide">Units</th>
                  <th className="pb-3 text-right text-xs font-semibold text-gray-500 uppercase tracking-wide">Avg Price</th>
                  <th className="pb-3 text-right text-xs font-semibold text-gray-500 uppercase tracking-wide">% of Channel</th>
                </tr>
              </thead>
              <tbody>
                {drilldown.products.map((row, i) => (
                  <tr key={i} className="border-b border-gray-50 hover:bg-gray-50 transition-colors">
                    <td className="py-3">
                      <span className="inline-flex w-7 h-7 rounded-full bg-blue-50 text-blue-700 text-xs font-bold items-center justify-center">
                        {row.rank}
                      </span>
                    </td>
                    <td className="py-3 font-medium text-gray-900">{row.product_name}</td>
                    <td className="py-3 text-right text-gray-900">{fmtCurrency(row.revenue)}</td>
                    <td className="py-3 text-right text-gray-600">{row.units_sold.toLocaleString()}</td>
                    <td className="py-3 text-right text-gray-600">{fmtCurrency(row.avg_price)}</td>
                    <td className="py-3 text-right">
                      <div className="flex items-center justify-end gap-2">
                        <div className="w-16 bg-gray-100 rounded-full h-1.5">
                          <div
                            className="bg-blue-500 h-1.5 rounded-full"
                            style={{ width: Math.min(100, row.pct_of_channel) + "%" }}
                          />
                        </div>
                        <span className="text-gray-500 text-xs w-10 text-right">
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
          <div className="text-center py-10 text-gray-400 text-sm bg-gray-50 rounded-xl">
            No product data available for this period
          </div>
        )}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// KPI card sub-component
// ---------------------------------------------------------------------------

function KpiCard({ label, value, trend }: { label: string; value: string; trend?: "up" | "down" }) {
  return (
    <div className="bg-white rounded-xl border border-gray-200 p-5">
      <p className="text-xs text-gray-500 font-medium mb-1">{label}</p>
      <p className="text-2xl font-bold text-gray-900 mb-1">{value}</p>
      {trend && (
        <div className={`flex items-center gap-1 text-xs ${trend === "up" ? "text-green-600" : "text-red-600"}`}>
          {trend === "up" ? <TrendingUp className="w-3 h-3" /> : <TrendingDown className="w-3 h-3" />}
        </div>
      )}
    </div>
  );
}

export default ChannelAnalytics;
