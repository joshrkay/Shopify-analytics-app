/**
 * Attribution Page
 *
 * UTM last-click attribution dashboard:
 * - Summary cards: Attribution Rate, Attributed Revenue, Total Campaigns
 * - Cross-channel ROAS bar chart (Recharts)
 * - Top campaigns table
 * - Attributed orders table with UTM fields
 */

import { useState, useEffect, useCallback } from 'react';
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  Legend,
} from 'recharts';
import {
  getAttributionSummary,
  getAttributedOrders,
  type AttributionSummaryResponse,
  type AttributedOrder,
} from '../services/attributionApi';

const TIMEFRAME_OPTIONS = [
  { value: '7days', label: '7 Days' },
  { value: '30days', label: '30 Days' },
  { value: '90days', label: '90 Days' },
];

const PLATFORM_DISPLAY: Record<string, string> = {
  meta_ads: 'Meta Ads',
  google_ads: 'Google Ads',
  tiktok_ads: 'TikTok Ads',
  snapchat_ads: 'Snapchat Ads',
  pinterest_ads: 'Pinterest Ads',
  twitter_ads: 'Twitter Ads',
  organic: 'Organic',
};

const PLATFORM_COLORS: Record<string, string> = {
  meta_ads: '#1877F2',
  google_ads: '#EA4335',
  tiktok_ads: '#010101',
  snapchat_ads: '#FFFC00',
  pinterest_ads: '#E60023',
  twitter_ads: '#1DA1F2',
  organic: '#16a34a',
};

function platformLabel(p: string | null): string {
  if (!p) return 'Unknown';
  return PLATFORM_DISPLAY[p] ?? p;
}

function fmtCurrency(v: number): string {
  if (v >= 1_000_000) return `$${(v / 1_000_000).toFixed(1)}M`;
  if (v >= 1_000) return `$${(v / 1_000).toFixed(1)}k`;
  return `$${v.toFixed(2)}`;
}

function utmBadgeColor(source: string | null): string {
  if (!source) return '#6b7280';
  const s = source.toLowerCase();
  if (s.includes('google')) return '#EA4335';
  if (s.includes('facebook') || s.includes('meta')) return '#1877F2';
  if (s.includes('tiktok')) return '#010101';
  if (s.includes('snapchat')) return '#FFFC00';
  if (s.includes('pinterest')) return '#E60023';
  if (s.includes('twitter') || s.includes('x.com')) return '#1DA1F2';
  return '#6b7280';
}

const PAGE_SIZE = 25;

export function Attribution() {
  const [timeframe, setTimeframe] = useState('30days');
  const [summary, setSummary] = useState<AttributionSummaryResponse | null>(null);
  const [summaryLoading, setSummaryLoading] = useState(true);

  const [orders, setOrders] = useState<AttributedOrder[]>([]);
  const [ordersTotal, setOrdersTotal] = useState(0);
  const [ordersPage, setOrdersPage] = useState(0);
  const [ordersLoading, setOrdersLoading] = useState(true);
  const [platformFilter, setPlatformFilter] = useState<string>('');

  const fetchSummary = useCallback(() => {
    let cancelled = false;
    setSummaryLoading(true);
    setSummary(null);
    getAttributionSummary(timeframe)
      .then((data) => { if (!cancelled) setSummary(data); })
      .catch(() => {})
      .finally(() => { if (!cancelled) setSummaryLoading(false); });
    return () => { cancelled = true; };
  }, [timeframe]);

  const fetchOrders = useCallback(() => {
    let cancelled = false;
    setOrdersLoading(true);
    getAttributedOrders({
      timeframe,
      platform: platformFilter || null,
      limit: PAGE_SIZE,
      offset: ordersPage * PAGE_SIZE,
    })
      .then((data) => {
        if (!cancelled) {
          setOrders(data.orders);
          setOrdersTotal(data.total);
        }
      })
      .catch(() => {})
      .finally(() => { if (!cancelled) setOrdersLoading(false); });
    return () => { cancelled = true; };
  }, [timeframe, platformFilter, ordersPage]);

  useEffect(fetchSummary, [fetchSummary]);
  useEffect(fetchOrders, [fetchOrders]);

  // Reset to page 0 when filters change
  useEffect(() => { setOrdersPage(0); }, [timeframe, platformFilter]);

  const roasData = (summary?.channel_roas ?? []).map((r) => ({
    platform: platformLabel(r.platform),
    ROAS: parseFloat(r.gross_roas.toFixed(2)),
    Revenue: r.revenue,
    Spend: r.spend,
  }));

  return (
    <div style={{ padding: '24px', background: '#f8f9fa', minHeight: '100vh' }}>
      {/* Header */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: '24px' }}>
        <div>
          <h1 style={{ fontSize: '24px', fontWeight: 700, color: '#111827', margin: 0 }}>Attribution</h1>
          <p style={{ color: '#6b7280', marginTop: '4px', marginBottom: 0 }}>UTM last-click attribution analysis</p>
        </div>
        <div style={{ display: 'flex', gap: '8px' }}>
          {TIMEFRAME_OPTIONS.map((opt) => (
            <button
              key={opt.value}
              onClick={() => setTimeframe(opt.value)}
              style={{
                padding: '6px 16px',
                borderRadius: '20px',
                border: '1px solid',
                borderColor: timeframe === opt.value ? '#1a56db' : '#e5e7eb',
                background: timeframe === opt.value ? '#1a56db' : '#fff',
                color: timeframe === opt.value ? '#fff' : '#374151',
                fontWeight: timeframe === opt.value ? 600 : 400,
                cursor: 'pointer',
                fontSize: '14px',
              }}
            >
              {opt.label}
            </button>
          ))}
        </div>
      </div>

      {/* Summary Cards */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: '16px', marginBottom: '24px' }}>
        {/* Attribution Rate */}
        <div style={{ background: '#fff', borderRadius: '12px', border: '1px solid #e5e7eb', padding: '20px' }}>
          <p style={{ color: '#6b7280', fontSize: '13px', margin: '0 0 8px' }}>Attribution Rate</p>
          {summaryLoading ? (
            <div style={{ height: '40px', background: '#f3f4f6', borderRadius: '6px', animation: 'pulse 1.5s infinite' }} />
          ) : (
            <p style={{ fontSize: '36px', fontWeight: 700, color: '#111827', margin: 0 }}>
              {summary ? `${summary.attribution_rate.toFixed(1)}%` : '—'}
            </p>
          )}
          {summary && !summaryLoading && (
            <p style={{ color: '#6b7280', fontSize: '12px', marginTop: '6px', marginBottom: 0 }}>
              {summary.attributed_orders.toLocaleString()} attributed of {(summary.attributed_orders + summary.unattributed_orders).toLocaleString()} total orders
            </p>
          )}
        </div>

        {/* Attributed Revenue */}
        <div style={{ background: '#fff', borderRadius: '12px', border: '1px solid #e5e7eb', padding: '20px' }}>
          <p style={{ color: '#6b7280', fontSize: '13px', margin: '0 0 8px' }}>Attributed Revenue</p>
          {summaryLoading ? (
            <div style={{ height: '40px', background: '#f3f4f6', borderRadius: '6px', animation: 'pulse 1.5s infinite' }} />
          ) : (
            <p style={{ fontSize: '36px', fontWeight: 700, color: '#111827', margin: 0 }}>
              {summary ? fmtCurrency(summary.total_attributed_revenue) : '—'}
            </p>
          )}
          {summary && !summaryLoading && (
            <p style={{ color: '#6b7280', fontSize: '12px', marginTop: '6px', marginBottom: 0 }}>
              From {summary.attributed_orders.toLocaleString()} attributed orders
            </p>
          )}
        </div>

        {/* Top Campaigns */}
        <div style={{ background: '#fff', borderRadius: '12px', border: '1px solid #e5e7eb', padding: '20px' }}>
          <p style={{ color: '#6b7280', fontSize: '13px', margin: '0 0 8px' }}>Active Campaigns</p>
          {summaryLoading ? (
            <div style={{ height: '40px', background: '#f3f4f6', borderRadius: '6px', animation: 'pulse 1.5s infinite' }} />
          ) : (
            <p style={{ fontSize: '36px', fontWeight: 700, color: '#111827', margin: 0 }}>
              {summary ? summary.top_campaigns.length : '—'}
            </p>
          )}
          {summary && !summaryLoading && summary.channel_roas.length > 0 && (
            <p style={{ color: '#6b7280', fontSize: '12px', marginTop: '6px', marginBottom: 0 }}>
              Best ROAS: {platformLabel(summary.channel_roas[0].platform)} ({summary.channel_roas[0].gross_roas.toFixed(2)}x)
            </p>
          )}
        </div>
      </div>

      {/* Channel ROAS Chart */}
      <div style={{ background: '#fff', borderRadius: '12px', border: '1px solid #e5e7eb', padding: '20px', marginBottom: '24px' }}>
        <h2 style={{ fontSize: '16px', fontWeight: 600, color: '#111827', marginTop: 0, marginBottom: '16px' }}>
          Cross-Channel ROAS
        </h2>
        {summaryLoading ? (
          <div style={{ height: '240px', background: '#f3f4f6', borderRadius: '6px', animation: 'pulse 1.5s infinite' }} />
        ) : roasData.length === 0 ? (
          <div style={{ height: '240px', display: 'flex', alignItems: 'center', justifyContent: 'center', color: '#9ca3af' }}>
            No ROAS data available
          </div>
        ) : (
          <ResponsiveContainer width="100%" height={240}>
            <BarChart data={roasData} margin={{ top: 5, right: 20, left: 0, bottom: 5 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="#f3f4f6" />
              <XAxis dataKey="platform" tick={{ fontSize: 12, fill: '#6b7280' }} />
              <YAxis tick={{ fontSize: 12, fill: '#6b7280' }} tickFormatter={(v) => `${v}x`} />
              <Tooltip formatter={(value: number) => [`${value.toFixed(2)}x`, 'ROAS']} />
              <Bar dataKey="ROAS" fill="#1a56db" radius={[4, 4, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        )}
      </div>

      {/* Top Campaigns Table */}
      <div style={{ background: '#fff', borderRadius: '12px', border: '1px solid #e5e7eb', padding: '20px', marginBottom: '24px' }}>
        <h2 style={{ fontSize: '16px', fontWeight: 600, color: '#111827', marginTop: 0, marginBottom: '16px' }}>
          Top Campaigns by Revenue
        </h2>
        {summaryLoading ? (
          <div style={{ height: '120px', background: '#f3f4f6', borderRadius: '6px', animation: 'pulse 1.5s infinite' }} />
        ) : !summary || summary.top_campaigns.length === 0 ? (
          <p style={{ color: '#9ca3af', textAlign: 'center', padding: '24px 0' }}>No campaign data available</p>
        ) : (
          <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '14px' }}>
            <thead>
              <tr style={{ borderBottom: '1px solid #e5e7eb' }}>
                {['Campaign', 'Platform', 'Revenue', 'Orders', 'Spend', 'ROAS'].map((h) => (
                  <th key={h} style={{ padding: '10px 12px', textAlign: 'left', color: '#6b7280', fontWeight: 500, fontSize: '12px', textTransform: 'uppercase' }}>{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {summary.top_campaigns.map((c, i) => (
                <tr key={i} style={{ borderBottom: '1px solid #f3f4f6' }}>
                  <td style={{ padding: '10px 12px', fontWeight: 500 }}>{c.campaign_name}</td>
                  <td style={{ padding: '10px 12px' }}>
                    {c.platform ? (
                      <span style={{
                        background: PLATFORM_COLORS[c.platform] ?? '#e5e7eb',
                        color: ['snapchat_ads'].includes(c.platform ?? '') ? '#111' : '#fff',
                        padding: '2px 8px', borderRadius: '4px', fontSize: '12px',
                      }}>{platformLabel(c.platform)}</span>
                    ) : '—'}
                  </td>
                  <td style={{ padding: '10px 12px' }}>{fmtCurrency(c.revenue)}</td>
                  <td style={{ padding: '10px 12px' }}>{c.orders.toLocaleString()}</td>
                  <td style={{ padding: '10px 12px' }}>{fmtCurrency(c.spend)}</td>
                  <td style={{ padding: '10px 12px', fontWeight: 600, color: '#16a34a' }}>
                    {c.roas !== null ? `${c.roas.toFixed(2)}x` : '—'}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      {/* Attributed Orders Table */}
      <div style={{ background: '#fff', borderRadius: '12px', border: '1px solid #e5e7eb', padding: '20px' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '16px' }}>
          <h2 style={{ fontSize: '16px', fontWeight: 600, color: '#111827', margin: 0 }}>
            Attributed Orders
            {ordersTotal > 0 && <span style={{ color: '#6b7280', fontWeight: 400, fontSize: '14px', marginLeft: '8px' }}>({ordersTotal.toLocaleString()} total)</span>}
          </h2>
          <select
            value={platformFilter}
            onChange={(e) => setPlatformFilter(e.target.value)}
            style={{ padding: '6px 12px', border: '1px solid #e5e7eb', borderRadius: '6px', fontSize: '14px', color: '#374151' }}
          >
            <option value="">All Platforms</option>
            {Object.entries(PLATFORM_DISPLAY).map(([k, v]) => (
              <option key={k} value={k}>{v}</option>
            ))}
          </select>
        </div>

        {ordersLoading ? (
          <div style={{ height: '160px', background: '#f3f4f6', borderRadius: '6px', animation: 'pulse 1.5s infinite' }} />
        ) : orders.length === 0 ? (
          <p style={{ color: '#9ca3af', textAlign: 'center', padding: '24px 0' }}>No attributed orders found</p>
        ) : (
          <>
            <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '14px' }}>
              <thead>
                <tr style={{ borderBottom: '1px solid #e5e7eb' }}>
                  {['Order', 'Date', 'Revenue', 'UTM Source', 'Campaign', 'Platform', 'Status'].map((h) => (
                    <th key={h} style={{ padding: '10px 12px', textAlign: 'left', color: '#6b7280', fontWeight: 500, fontSize: '12px', textTransform: 'uppercase' }}>{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {orders.map((o) => (
                  <tr key={o.order_id} style={{ borderBottom: '1px solid #f3f4f6' }}>
                    <td style={{ padding: '10px 12px', fontWeight: 500 }}>{o.order_name ?? `#${o.order_number ?? o.order_id}`}</td>
                    <td style={{ padding: '10px 12px', color: '#6b7280' }}>
                      {o.created_at ? new Date(o.created_at).toLocaleDateString() : '—'}
                    </td>
                    <td style={{ padding: '10px 12px' }}>{fmtCurrency(o.revenue)}</td>
                    <td style={{ padding: '10px 12px' }}>
                      {o.utm_source ? (
                        <span style={{
                          background: utmBadgeColor(o.utm_source) + '20',
                          color: utmBadgeColor(o.utm_source),
                          border: `1px solid ${utmBadgeColor(o.utm_source)}40`,
                          padding: '2px 8px', borderRadius: '4px', fontSize: '12px',
                        }}>{o.utm_source}</span>
                      ) : <span style={{ color: '#9ca3af' }}>—</span>}
                    </td>
                    <td style={{ padding: '10px 12px', color: '#374151', maxWidth: '180px', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                      {o.utm_campaign ?? '—'}
                    </td>
                    <td style={{ padding: '10px 12px' }}>
                      {o.platform ? platformLabel(o.platform) : <span style={{ color: '#9ca3af' }}>—</span>}
                    </td>
                    <td style={{ padding: '10px 12px' }}>
                      <span style={{
                        background: o.attribution_status === 'attributed' ? '#dcfce7' : '#f3f4f6',
                        color: o.attribution_status === 'attributed' ? '#16a34a' : '#6b7280',
                        padding: '2px 8px', borderRadius: '4px', fontSize: '12px',
                      }}>
                        {o.attribution_status === 'attributed' ? 'Attributed' : 'Unattributed'}
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>

            {/* Pagination */}
            {ordersTotal > PAGE_SIZE && (
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginTop: '16px' }}>
                <span style={{ color: '#6b7280', fontSize: '14px' }}>
                  Showing {ordersPage * PAGE_SIZE + 1}–{Math.min((ordersPage + 1) * PAGE_SIZE, ordersTotal)} of {ordersTotal.toLocaleString()}
                </span>
                <div style={{ display: 'flex', gap: '8px' }}>
                  <button
                    onClick={() => setOrdersPage((p) => Math.max(0, p - 1))}
                    disabled={ordersPage === 0}
                    style={{ padding: '6px 14px', border: '1px solid #e5e7eb', borderRadius: '6px', background: '#fff', cursor: ordersPage === 0 ? 'not-allowed' : 'pointer', opacity: ordersPage === 0 ? 0.5 : 1 }}
                  >
                    Previous
                  </button>
                  <button
                    onClick={() => setOrdersPage((p) => p + 1)}
                    disabled={(ordersPage + 1) * PAGE_SIZE >= ordersTotal}
                    style={{ padding: '6px 14px', border: '1px solid #e5e7eb', borderRadius: '6px', background: '#fff', cursor: (ordersPage + 1) * PAGE_SIZE >= ordersTotal ? 'not-allowed' : 'pointer', opacity: (ordersPage + 1) * PAGE_SIZE >= ordersTotal ? 0.5 : 1 }}
                  >
                    Next
                  </button>
                </div>
              </div>
            )}
          </>
        )}
      </div>
    </div>
  );
}

export default Attribution;
