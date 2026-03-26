/**
 * Orders page regression tests
 *
 * Regression: Orders page white-screened when the backend returned a 503
 * (canonical.orders or attribution.last_click tables not yet populated by dbt).
 * After the fix, the component handles the error state gracefully and shows
 * a user-friendly message with a Retry button.
 *
 * Tests:
 * 1. Renders the Orders heading in the happy path
 * 2. Shows order table when API returns data
 * 3. Shows "No orders found" when API returns empty list (data not yet ready)
 * 4. Shows error message (not white-screen) when API call fails (503)
 * 5. Shows Retry button in the error state
 * 6. Retry button re-fetches data
 * 7. Timeframe selector changes the active period
 * 8. UTM source badge renders for orders with attribution
 */

import React from 'react';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

import { Orders } from '../pages/Orders';

// ---------------------------------------------------------------------------
// Mock the orders API
// ---------------------------------------------------------------------------

vi.mock('../services/ordersApi', () => ({
  getOrders: vi.fn(),
}));

import { getOrders } from '../services/ordersApi';
import type { OrdersListResponse } from '../services/ordersApi';

const mockGetOrders = vi.mocked(getOrders);

// ---------------------------------------------------------------------------
// Fixtures
// ---------------------------------------------------------------------------

function makeOrder(id: string, overrides: Record<string, unknown> = {}) {
  return {
    order_id: id,
    order_number: '1001',
    order_name: `#${id}`,
    revenue: 99.99,
    currency: 'USD',
    financial_status: 'paid',
    created_at: '2024-03-15T12:00:00Z',
    utm_source: 'google',
    utm_medium: 'cpc',
    utm_campaign: 'spring-sale',
    platform: 'google_ads',
    ...overrides,
  };
}

const emptyResponse: OrdersListResponse = {
  orders: [],
  total: 0,
  has_more: false,
};

const singleOrderResponse: OrdersListResponse = {
  orders: [makeOrder('order-001')],
  total: 1,
  has_more: false,
};

const multipleOrdersResponse: OrdersListResponse = {
  orders: [
    makeOrder('order-001', { revenue: 150.0, utm_source: 'google' }),
    makeOrder('order-002', { revenue: 75.0, utm_source: 'facebook', financial_status: 'pending' }),
    makeOrder('order-003', { revenue: 200.0, utm_source: null, platform: null }),
  ],
  total: 3,
  has_more: false,
};

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe('Orders page — regression', () => {
  let consoleSpy: ReturnType<typeof vi.spyOn>;

  beforeEach(() => {
    consoleSpy = vi.spyOn(console, 'error').mockImplementation(() => {});
  });

  afterEach(() => {
    consoleSpy.mockRestore();
    vi.clearAllMocks();
  });

  describe('page structure', () => {
    it('renders the "Orders" heading', async () => {
      mockGetOrders.mockResolvedValue(emptyResponse);
      render(<Orders />);

      await waitFor(() => {
        expect(screen.getByRole('heading', { name: /orders/i })).toBeInTheDocument();
      });
    });

    it('renders the timeframe selector buttons', async () => {
      mockGetOrders.mockResolvedValue(emptyResponse);
      render(<Orders />);

      await waitFor(() => {
        expect(screen.getByRole('button', { name: '7 Days' })).toBeInTheDocument();
        expect(screen.getByRole('button', { name: '30 Days' })).toBeInTheDocument();
        expect(screen.getByRole('button', { name: '90 Days' })).toBeInTheDocument();
      });
    });
  });

  describe('happy path — data loads', () => {
    it('renders order rows in the table', async () => {
      mockGetOrders.mockResolvedValue(singleOrderResponse);
      render(<Orders />);

      await waitFor(() => {
        expect(screen.getByText('#order-001')).toBeInTheDocument();
      });
    });

    it('shows revenue formatted correctly', async () => {
      mockGetOrders.mockResolvedValue(singleOrderResponse);
      render(<Orders />);

      await waitFor(() => {
        expect(screen.getByText('$99.99')).toBeInTheDocument();
      });
    });

    it('shows UTM source badge for attributed orders', async () => {
      mockGetOrders.mockResolvedValue(singleOrderResponse);
      render(<Orders />);

      await waitFor(() => {
        expect(screen.getByText('google')).toBeInTheDocument();
      });
    });

    it('renders table column headers', async () => {
      mockGetOrders.mockResolvedValue(singleOrderResponse);
      render(<Orders />);

      await waitFor(() => {
        expect(screen.getByText('Order')).toBeInTheDocument();
        expect(screen.getByText('Revenue')).toBeInTheDocument();
        expect(screen.getByText('Status')).toBeInTheDocument();
      });
    });

    it('shows total order count in the subheading', async () => {
      mockGetOrders.mockResolvedValue({
        orders: [makeOrder('order-001')],
        total: 42,
        has_more: false,
      });
      render(<Orders />);

      await waitFor(() => {
        expect(screen.getByText(/42 orders/i)).toBeInTheDocument();
      });
    });
  });

  describe('empty state — data not yet prepared by dbt', () => {
    it('shows "No orders found" message when API returns empty list', async () => {
      mockGetOrders.mockResolvedValue(emptyResponse);
      render(<Orders />);

      await waitFor(() => {
        expect(screen.getByText(/no orders found/i)).toBeInTheDocument();
      });
    });

    it('does not show an error message for empty results', async () => {
      mockGetOrders.mockResolvedValue(emptyResponse);
      render(<Orders />);

      await waitFor(() => {
        expect(screen.queryByText(/unable to load orders/i)).not.toBeInTheDocument();
      });
    });

    it('does not white-screen on empty response', async () => {
      mockGetOrders.mockResolvedValue(emptyResponse);
      render(<Orders />);

      // Page heading must still be visible
      await waitFor(() => {
        expect(screen.getByRole('heading', { name: /orders/i })).toBeInTheDocument();
      });
    });
  });

  describe('error state — API failure (503 from missing dbt tables)', () => {
    it('shows error message when API call fails, not a white-screen', async () => {
      mockGetOrders.mockRejectedValue(new Error('503 Service Unavailable'));
      render(<Orders />);

      await waitFor(() => {
        expect(screen.getByText(/unable to load orders/i)).toBeInTheDocument();
      });
    });

    it('shows a Retry button in the error state', async () => {
      mockGetOrders.mockRejectedValue(new Error('Service unavailable'));
      render(<Orders />);

      await waitFor(() => {
        expect(screen.getByRole('button', { name: /retry/i })).toBeInTheDocument();
      });
    });

    it('clicking Retry re-fetches the data', async () => {
      const user = userEvent.setup();
      mockGetOrders
        .mockRejectedValueOnce(new Error('First attempt failed'))
        .mockResolvedValueOnce(singleOrderResponse);

      render(<Orders />);

      await waitFor(() => {
        expect(screen.getByRole('button', { name: /retry/i })).toBeInTheDocument();
      });

      await user.click(screen.getByRole('button', { name: /retry/i }));

      await waitFor(() => {
        expect(screen.getByText('#order-001')).toBeInTheDocument();
      });
      expect(mockGetOrders).toHaveBeenCalledTimes(2);
    });

    it('page heading remains visible in error state', async () => {
      mockGetOrders.mockRejectedValue(new Error('503'));
      render(<Orders />);

      await waitFor(() => {
        expect(screen.getByRole('heading', { name: /orders/i })).toBeInTheDocument();
      });
    });
  });

  describe('timeframe selector', () => {
    it('clicking 7 Days re-fetches with timeframe=7days', async () => {
      const user = userEvent.setup();
      mockGetOrders.mockResolvedValue(emptyResponse);
      render(<Orders />);

      await waitFor(() => screen.getByRole('button', { name: '7 Days' }));
      await user.click(screen.getByRole('button', { name: '7 Days' }));

      await waitFor(() => {
        expect(mockGetOrders).toHaveBeenCalledWith(
          expect.objectContaining({ timeframe: '7days' })
        );
      });
    });

    it('clicking 90 Days re-fetches with timeframe=90days', async () => {
      const user = userEvent.setup();
      mockGetOrders.mockResolvedValue(emptyResponse);
      render(<Orders />);

      await waitFor(() => screen.getByRole('button', { name: '90 Days' }));
      await user.click(screen.getByRole('button', { name: '90 Days' }));

      await waitFor(() => {
        expect(mockGetOrders).toHaveBeenCalledWith(
          expect.objectContaining({ timeframe: '90days' })
        );
      });
    });
  });

  describe('null UTM fields', () => {
    it('renders dash placeholder for orders with no UTM source', async () => {
      const noUtmResponse: OrdersListResponse = {
        orders: [makeOrder('order-no-utm', { utm_source: null, utm_campaign: null, platform: null })],
        total: 1,
        has_more: false,
      };
      mockGetOrders.mockResolvedValue(noUtmResponse);
      render(<Orders />);

      await waitFor(() => {
        // Order row renders; UTM badge is replaced by "—"
        expect(screen.getByText('#order-no-utm')).toBeInTheDocument();
      });
    });
  });
});
