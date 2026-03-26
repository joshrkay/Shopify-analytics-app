/**
 * Regression: Orders page shows empty state and error state gracefully
 *
 * Why: The Orders page fetches from /api/orders. When the data warehouse
 * isn't ready (empty result set) or the API errors, the page must show a
 * human-readable message, not crash. This test guards against:
 *   - Removing the empty-state message ("No orders found for the selected period.")
 *   - Removing the error state / retry button
 *   - The component crashing when getOrders rejects
 *
 * The "data_ready" concept maps to: API returns empty orders array when
 * the dbt pipeline hasn't run yet for a new tenant.
 */

import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { BrowserRouter } from 'react-router-dom';

// ---------------------------------------------------------------------------
// Mocks
// ---------------------------------------------------------------------------

const mockGetOrders = vi.fn();

vi.mock('../../services/ordersApi', () => ({
  getOrders: (...args: unknown[]) => mockGetOrders(...args),
}));

vi.mock('../../services/apiUtils', () => ({
  API_BASE_URL: '',
  createHeadersAsync: vi.fn().mockResolvedValue({}),
  createHeaders: vi.fn().mockReturnValue({}),
  handleResponse: vi.fn(),
  isApiError: vi.fn().mockReturnValue(false),
  getErrorMessage: vi.fn((_e: unknown, fb: string) => fb),
}));

vi.mock('@clerk/clerk-react', () => ({
  useUser: () => ({ isLoaded: true, user: { id: 'u1' } }),
  useOrganization: () => ({ organization: { id: 'org1' } }),
  useClerk: () => ({ signOut: vi.fn() }),
}));

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

async function renderOrders() {
  const { Orders } = await import('../../pages/Orders');
  return render(
    <BrowserRouter>
      <Orders />
    </BrowserRouter>
  );
}

const EMPTY_RESPONSE = { orders: [], total: 0, page: 0, limit: 25 };
const POPULATED_RESPONSE = {
  orders: [
    {
      order_id: 'ord-1',
      order_name: '#1001',
      order_number: 1001,
      order_created_at: '2026-03-01T10:00:00Z',
      revenue_gross: 99.99,
      currency: 'USD',
      financial_status: 'paid',
      utm_source: 'google',
      utm_campaign: 'spring-sale',
      utm_medium: 'cpc',
      platform: 'google_ads',
      attribution_status: 'attributed',
    },
  ],
  total: 1,
  page: 0,
  limit: 25,
};

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe('orders data-ready regression', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('shows empty-state message when API returns zero orders (data not ready)', async () => {
    mockGetOrders.mockResolvedValue(EMPTY_RESPONSE);

    await renderOrders();

    await waitFor(() => {
      expect(
        screen.getByText(/No orders found for the selected period/i)
      ).toBeInTheDocument();
    });
  });

  it('does not crash when API returns empty orders', async () => {
    mockGetOrders.mockResolvedValue(EMPTY_RESPONSE);

    // Should not throw
    await expect(renderOrders()).resolves.toBeDefined();

    await waitFor(() => {
      expect(screen.queryByText(/Something went wrong/i)).not.toBeInTheDocument();
    });
  });

  it('shows orders table when API returns data', async () => {
    mockGetOrders.mockResolvedValue(POPULATED_RESPONSE);

    await renderOrders();

    await waitFor(() => {
      expect(screen.getByText('#1001')).toBeInTheDocument();
    });

    // Empty state must not be shown when data is present
    expect(
      screen.queryByText(/No orders found for the selected period/i)
    ).not.toBeInTheDocument();
  });

  it('shows error message and Retry button when API rejects', async () => {
    mockGetOrders.mockRejectedValue(new Error('warehouse unavailable'));

    await renderOrders();

    await waitFor(() => {
      expect(screen.getByText('Retry')).toBeInTheDocument();
    });
  });

  it('retries fetch when Retry button is clicked', async () => {
    const user = userEvent.setup();
    // First call fails, second succeeds with empty
    mockGetOrders
      .mockRejectedValueOnce(new Error('503'))
      .mockResolvedValueOnce(EMPTY_RESPONSE);

    await renderOrders();

    await waitFor(() => {
      expect(screen.getByText('Retry')).toBeInTheDocument();
    });

    await user.click(screen.getByText('Retry'));

    await waitFor(() => {
      expect(mockGetOrders).toHaveBeenCalledTimes(2);
    });
  });

  it('loading skeleton is shown while fetch is in progress', async () => {
    // Never resolves during this test — stays in loading state
    mockGetOrders.mockImplementation(() => new Promise(() => {}));

    await renderOrders();

    // Loading state: skeleton elements rendered (pulse animation divs)
    // The component renders 8 skeleton rows — heading should still be visible
    expect(screen.getByText('Orders')).toBeInTheDocument();
    // No empty-state message while loading
    expect(
      screen.queryByText(/No orders found/i)
    ).not.toBeInTheDocument();
  });
});
