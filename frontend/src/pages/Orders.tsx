/**
 * Orders Page
 *
 * Shopify order list with UTM attribution overlay:
 * - Paginated table: Order #, Date, Revenue, UTM Source, Campaign, Platform, Status
 * - UTM source shown as a colored badge
 * - Timeframe selector + pagination
 */

import { useState, useEffect, useCallback } from 'react';
import { getOrders, type Order } from '../services/ordersApi';

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

const UTM_SOURCE_COLORS: Record<string, string> = {
  google: '#EA4335',
  facebook: '#1877F2',
  meta: '#1877F2',
  tiktok: '#555',
  snapchat: '#FFAC33',
  pinterest: '#E60023',
  twitter: '#1DA1F2',
  email: '#16a34a',
  organic: '#16a34a',
};

function utmBadgeColor(source: string | null): string {
  if (!source) return '#6b7280';
  const s = source.toLowerCase();
  for (const [key, color] of Object.entries(UTM_SOURCE_COLORS)) {
    if (s.includes(key)) return color;
  }
  return '#6b7280';
}

function fmtCurrency(v: number): string {
  if (v >= 1_000_000) return `$${(v / 1_000_000).toFixed(1)}M`;
  if (v >= 1_000) return `$${(v / 1_000).toFixed(1)}k`;
  return `$${v.toFixed(2)}`;
}

function statusBadge(status: string | null) {
  const s = (status ?? '').toLowerCase();
  const config: Record<string, { bg: string; color: string; label: string }> = {
    paid: { bg: '#dcfce7', color: '#16a34a', label: 'Paid' },
    pending: { bg: '#fef9c3', color: '#ca8a04', label: 'Pending' },
    refunded: { bg: '#fee2e2', color: '#dc2626', label: 'Refunded' },
    partially_refunded: { bg: '#ffedd5', color: '#ea580c', label: 'Partial Refund' },
    voided: { bg: '#f3f4f6', color: '#6b7280', label: 'Voided' },
  };
  const style = config[s] ?? { bg: '#f3f4f6', color: '#6b7280', label: status ?? 'Unknown' };
  return (
    <span style={{
      background: style.bg, color: style.color,
      padding: '2px 8px', borderRadius: '4px', fontSize: '12px',
    }}>
      {style.label}
    </span>
  );
}

const PAGE_SIZE = 50;

export function Orders() {
  const [timeframe, setTimeframe] = useState('30days');
  const [page, setPage] = useState(0);
  const [orders, setOrders] = useState<Order[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetchOrders = useCallback(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    getOrders({ timeframe, limit: PAGE_SIZE, offset: page * PAGE_SIZE })
      .then((data) => {
        if (!cancelled) {
          setOrders(data.orders);
          setTotal(data.total);
        }
      })
      .catch(() => {
        if (!cancelled) setError('Unable to load orders. Please try again.');
      })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [timeframe, page]);

  useEffect(fetchOrders, [fetchOrders]);
  // Reset page when timeframe changes
  useEffect(() => { setPage(0); }, [timeframe]);

  return (
    <div style={{ padding: '24px', background: '#f8f9fa', minHeight: '100vh' }}>
      {/* Header */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: '24px' }}>
        <div>
          <h1 style={{ fontSize: '24px', fontWeight: 700, color: '#111827', margin: 0 }}>Orders</h1>
          <p style={{ color: '#6b7280', marginTop: '4px', marginBottom: 0 }}>
            Shopify orders with UTM attribution
            {total > 0 && ` — ${total.toLocaleString()} orders`}
          </p>
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

      {/* Table Card */}
      <div style={{ background: '#fff', borderRadius: '12px', border: '1px solid #e5e7eb', padding: '20px' }}>
        {error ? (
          <div style={{ padding: '24px', textAlign: 'center', color: '#dc2626' }}>{error}</div>
        ) : loading ? (
          <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
            {Array.from({ length: 8 }).map((_, i) => (
              <div key={i} style={{ height: '44px', background: '#f3f4f6', borderRadius: '6px', animation: 'pulse 1.5s infinite' }} />
            ))}
          </div>
        ) : orders.length === 0 ? (
          <p style={{ color: '#9ca3af', textAlign: 'center', padding: '40px 0' }}>
            No orders found for the selected period.
          </p>
        ) : (
          <>
            <div style={{ overflowX: 'auto' }}>
              <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '14px', minWidth: '800px' }}>
                <thead>
                  <tr style={{ borderBottom: '2px solid #e5e7eb' }}>
                    {['Order', 'Date', 'Revenue', 'Currency', 'UTM Source', 'Campaign', 'Platform', 'Status'].map((h) => (
                      <th key={h} style={{
                        padding: '10px 12px', textAlign: 'left',
                        color: '#6b7280', fontWeight: 500, fontSize: '12px',
                        textTransform: 'uppercase', whiteSpace: 'nowrap',
                      }}>{h}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {orders.map((o) => (
                    <tr
                      key={o.order_id}
                      style={{ borderBottom: '1px solid #f3f4f6' }}
                      onMouseEnter={(e) => (e.currentTarget.style.background = '#f9fafb')}
                      onMouseLeave={(e) => (e.currentTarget.style.background = 'transparent')}
                    >
                      <td style={{ padding: '10px 12px', fontWeight: 600, color: '#111827' }}>
                        {o.order_name ?? (o.order_number ? `#${o.order_number}` : o.order_id)}
                      </td>
                      <td style={{ padding: '10px 12px', color: '#6b7280', whiteSpace: 'nowrap' }}>
                        {o.created_at ? new Date(o.created_at).toLocaleDateString() : '—'}
                      </td>
                      <td style={{ padding: '10px 12px', fontWeight: 500 }}>{fmtCurrency(o.revenue)}</td>
                      <td style={{ padding: '10px 12px', color: '#6b7280' }}>{o.currency}</td>
                      <td style={{ padding: '10px 12px' }}>
                        {o.utm_source ? (
                          <span style={{
                            background: utmBadgeColor(o.utm_source) + '15',
                            color: utmBadgeColor(o.utm_source),
                            border: `1px solid ${utmBadgeColor(o.utm_source)}30`,
                            padding: '2px 8px', borderRadius: '4px', fontSize: '12px',
                            whiteSpace: 'nowrap',
                          }}>{o.utm_source}</span>
                        ) : <span style={{ color: '#d1d5db' }}>—</span>}
                      </td>
                      <td style={{ padding: '10px 12px', color: '#374151', maxWidth: '200px', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                        {o.utm_campaign ?? <span style={{ color: '#d1d5db' }}>—</span>}
                      </td>
                      <td style={{ padding: '10px 12px', color: '#374151' }}>
                        {o.platform
                          ? (PLATFORM_DISPLAY[o.platform] ?? o.platform)
                          : <span style={{ color: '#d1d5db' }}>—</span>}
                      </td>
                      <td style={{ padding: '10px 12px' }}>{statusBadge(o.financial_status)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            {/* Pagination */}
            {total > PAGE_SIZE && (
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginTop: '16px', paddingTop: '16px', borderTop: '1px solid #e5e7eb' }}>
                <span style={{ color: '#6b7280', fontSize: '14px' }}>
                  Showing {page * PAGE_SIZE + 1}–{Math.min((page + 1) * PAGE_SIZE, total)} of {total.toLocaleString()} orders
                </span>
                <div style={{ display: 'flex', gap: '8px' }}>
                  <button
                    onClick={() => setPage((p) => Math.max(0, p - 1))}
                    disabled={page === 0}
                    style={{
                      padding: '6px 16px', border: '1px solid #e5e7eb', borderRadius: '6px',
                      background: '#fff', cursor: page === 0 ? 'not-allowed' : 'pointer',
                      opacity: page === 0 ? 0.5 : 1, fontSize: '14px',
                    }}
                  >
                    ← Previous
                  </button>
                  <button
                    onClick={() => setPage((p) => p + 1)}
                    disabled={(page + 1) * PAGE_SIZE >= total}
                    style={{
                      padding: '6px 16px', border: '1px solid #e5e7eb', borderRadius: '6px',
                      background: '#fff', cursor: (page + 1) * PAGE_SIZE >= total ? 'not-allowed' : 'pointer',
                      opacity: (page + 1) * PAGE_SIZE >= total ? 0.5 : 1, fontSize: '14px',
                    }}
                  >
                    Next →
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

export default Orders;
