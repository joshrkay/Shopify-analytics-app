/**
 * Hook tests for useWidgetCatalog and useWidgetPreview (Phase 2.2)
 *
 * Tests:
 * - useWidgetCatalog() hook behavior
 * - Client-side filtering
 * - Loading and error states
 * - useWidgetPreview() hook behavior
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook, waitFor } from '@testing-library/react';
import { useWidgetCatalog, useWidgetPreview } from '../hooks/useWidgetCatalog';
import type { WidgetCatalogItem, WidgetCategoryMeta } from '../types/customDashboards';

// Mock the widget catalog API
const mockGetWidgetCatalog = vi.fn();
const mockGetWidgetCategories = vi.fn();
const mockGetWidgetPreview = vi.fn();

vi.mock('../services/widgetCatalogApi', () => ({
  getWidgetCatalog: () => mockGetWidgetCatalog(),
  getWidgetCategories: () => mockGetWidgetCategories(),
  getWidgetPreview: (widgetId: string, datasetId?: string) =>
    mockGetWidgetPreview(widgetId, datasetId),
}));

// Mock apiUtils
vi.mock('../services/apiUtils', () => ({
  getErrorMessage: (err: Error, defaultMsg: string) => {
    return err.message || defaultMsg;
  },
}));

// Test data factories
function createMockWidget(overrides?: Partial<WidgetCatalogItem>): WidgetCatalogItem {
  return {
    id: 'test-widget',
    type: 'chart',
    title: 'Test Widget',
    description: 'Test description',
    icon: 'TestIcon',
    category: 'sales',
    defaultSize: 'medium',
    chartType: 'line',
    ...overrides,
  };
}

function createMockCategory(overrides?: Partial<WidgetCategoryMeta>): WidgetCategoryMeta {
  return {
    id: 'all',
    name: 'All Widgets',
    icon: 'LayoutGrid',
    ...overrides,
  };
}

describe('useWidgetCatalog', () => {
  beforeEach(() => {
    vi.clearAllMocks();

    // Default mock implementations
    mockGetWidgetCatalog.mockResolvedValue([
      createMockWidget({ id: 'sales-widget-1', category: 'sales' }),
      createMockWidget({ id: 'sales-widget-2', category: 'sales' }),
      createMockWidget({ id: 'roas-widget-1', category: 'roas' }),
      createMockWidget({ id: 'products-widget-1', category: 'products' }),
    ]);

    mockGetWidgetCategories.mockResolvedValue([
      createMockCategory({ id: 'all' }),
      createMockCategory({ id: 'sales', name: 'Sales' }),
      createMockCategory({ id: 'roas', name: 'ROAS & ROI' }),
      createMockCategory({ id: 'products', name: 'Products' }),
    ]);
  });

  describe('basic functionality', () => {
    it('returns full catalog on initial load', async () => {
      const { result } = renderHook(() => useWidgetCatalog());

      // Initially loading
      expect(result.current.loading).toBe(true);
      expect(result.current.widgets).toEqual([]);

      // Wait for data to load
      await waitFor(() => {
        expect(result.current.loading).toBe(false);
      });

      expect(result.current.widgets).toHaveLength(4);
      expect(result.current.categories).toHaveLength(4);
      expect(mockGetWidgetCatalog).toHaveBeenCalledTimes(1);
      expect(mockGetWidgetCategories).toHaveBeenCalledTimes(1);
    });

    it('exposes getFilteredWidgets function', async () => {
      const { result } = renderHook(() => useWidgetCatalog());

      await waitFor(() => {
        expect(result.current.loading).toBe(false);
      });

      expect(result.current.getFilteredWidgets).toBeDefined();
      expect(typeof result.current.getFilteredWidgets).toBe('function');
    });

    it('exposes refetch function', async () => {
      const { result } = renderHook(() => useWidgetCatalog());

      await waitFor(() => {
        expect(result.current.loading).toBe(false);
      });

      expect(result.current.refetch).toBeDefined();
      expect(typeof result.current.refetch).toBe('function');
    });

    it('categories array contains all category metadata', async () => {
      const { result } = renderHook(() => useWidgetCatalog());

      await waitFor(() => {
        expect(result.current.loading).toBe(false);
      });

      expect(result.current.categories).toHaveLength(4);
      expect(result.current.categories[0].id).toBe('all');
      expect(result.current.categories[1].id).toBe('sales');
    });
  });

  describe('filtering', () => {
    it('getFilteredWidgets("sales") returns only sales widgets', async () => {
      const { result } = renderHook(() => useWidgetCatalog());

      await waitFor(() => {
        expect(result.current.loading).toBe(false);
      });

      const salesWidgets = result.current.getFilteredWidgets('sales');
      expect(salesWidgets).toHaveLength(2);
      expect(salesWidgets.every((w) => w.category === 'sales')).toBe(true);
    });

    it('getFilteredWidgets("all") returns all widgets', async () => {
      const { result } = renderHook(() => useWidgetCatalog());

      await waitFor(() => {
        expect(result.current.loading).toBe(false);
      });

      const allWidgets = result.current.getFilteredWidgets('all');
      expect(allWidgets).toHaveLength(4);
    });

    it('getFilteredWidgets with empty category returns empty array when no data', async () => {
      mockGetWidgetCatalog.mockResolvedValue([]);

      const { result } = renderHook(() => useWidgetCatalog());

      await waitFor(() => {
        expect(result.current.loading).toBe(false);
      });

      const filtered = result.current.getFilteredWidgets('roas');
      expect(filtered).toEqual([]);
    });

    it('accepts category parameter to auto-filter', async () => {
      const { result } = renderHook(() => useWidgetCatalog('sales'));

      await waitFor(() => {
        expect(result.current.loading).toBe(false);
      });

      // widgets should already be filtered to sales category
      expect(result.current.widgets).toHaveLength(2);
      expect(result.current.widgets.every((w) => w.category === 'sales')).toBe(true);
    });

    it('filtering works for multiple categories', async () => {
      const { result } = renderHook(() => useWidgetCatalog());

      await waitFor(() => {
        expect(result.current.loading).toBe(false);
      });

      const salesWidgets = result.current.getFilteredWidgets('sales');
      const roasWidgets = result.current.getFilteredWidgets('roas');
      const productsWidgets = result.current.getFilteredWidgets('products');

      expect(salesWidgets).toHaveLength(2);
      expect(roasWidgets).toHaveLength(1);
      expect(productsWidgets).toHaveLength(1);
    });
  });

  describe('loading and error states', () => {
    it('loading state is true during fetch', async () => {
      const { result } = renderHook(() => useWidgetCatalog());

      // Should be loading initially
      expect(result.current.loading).toBe(true);
      expect(result.current.widgets).toEqual([]);
      expect(result.current.categories).toEqual([]);

      await waitFor(() => {
        expect(result.current.loading).toBe(false);
      });
    });

    it('error state populates on failure', async () => {
      mockGetWidgetCatalog.mockRejectedValue(new Error('Network error'));

      const { result } = renderHook(() => useWidgetCatalog());

      await waitFor(() => {
        expect(result.current.loading).toBe(false);
      });

      expect(result.current.error).toBeDefined();
      expect(result.current.error).toBe('Network error');
      expect(result.current.widgets).toEqual([]);
    });

    it('returns empty arrays when data is not yet loaded', async () => {
      const { result } = renderHook(() => useWidgetCatalog());

      // Before data loads
      expect(result.current.widgets).toEqual([]);
      expect(result.current.categories).toEqual([]);

      await waitFor(() => {
        expect(result.current.loading).toBe(false);
      });
    });
  });

  describe('refetch functionality', () => {
    it('refetch reloads the catalog', async () => {
      const { result } = renderHook(() => useWidgetCatalog());

      await waitFor(() => {
        expect(result.current.loading).toBe(false);
      });

      expect(mockGetWidgetCatalog).toHaveBeenCalledTimes(1);

      // Call refetch
      await result.current.refetch();

      expect(mockGetWidgetCatalog).toHaveBeenCalledTimes(2);
    });
  });
});

describe('useWidgetPreview', () => {
  beforeEach(() => {
    vi.clearAllMocks();

    mockGetWidgetPreview.mockResolvedValue({
      widgetId: 'revenue-kpi',
      chartType: 'kpi',
      sampleData: { value: 12458, change: 12.5, trend: 'up' },
      loading: false,
    });
  });

  describe('basic functionality', () => {
    it('returns preview data for a metric widget', async () => {
      const { result } = renderHook(() => useWidgetPreview('revenue-kpi'));

      // Initially loading
      expect(result.current.loading).toBe(true);
      expect(result.current.previewData).toBeNull();

      // Wait for data to load
      await waitFor(() => {
        expect(result.current.loading).toBe(false);
      });

      expect(result.current.previewData).toBeDefined();
      expect(result.current.previewData!.widgetId).toBe('revenue-kpi');
      expect(result.current.previewData!.chartType).toBe('kpi');
      expect(result.current.previewData!.sampleData).toBeDefined();
      expect(mockGetWidgetPreview).toHaveBeenCalledWith('revenue-kpi', undefined);
    });

    it('returns preview data for a chart widget', async () => {
      mockGetWidgetPreview.mockResolvedValue({
        widgetId: 'sales-trend',
        chartType: 'line',
        sampleData: { series: [{ name: 'Sales', data: [] }] },
        loading: false,
      });

      const { result } = renderHook(() => useWidgetPreview('sales-trend'));

      await waitFor(() => {
        expect(result.current.loading).toBe(false);
      });

      expect(result.current.previewData!.chartType).toBe('line');
      expect(result.current.previewData!.sampleData.series).toBeDefined();
    });

    it('accepts optional datasetId parameter', async () => {
      const { result } = renderHook(() =>
        useWidgetPreview('revenue-kpi', 'sales_metrics'),
      );

      await waitFor(() => {
        expect(result.current.loading).toBe(false);
      });

      expect(mockGetWidgetPreview).toHaveBeenCalledWith('revenue-kpi', 'sales_metrics');
    });

    it('exposes refetch function', async () => {
      const { result } = renderHook(() => useWidgetPreview('revenue-kpi'));

      await waitFor(() => {
        expect(result.current.loading).toBe(false);
      });

      expect(result.current.refetch).toBeDefined();
      expect(typeof result.current.refetch).toBe('function');
    });
  });

  describe('conditional fetching', () => {
    it('does not fetch when widgetId is empty string', async () => {
      const { result } = renderHook(() => useWidgetPreview(''));

      // Should not be loading and should not fetch
      await waitFor(() => {
        expect(result.current.loading).toBe(false);
      });

      expect(result.current.previewData).toBeNull();
      expect(mockGetWidgetPreview).not.toHaveBeenCalled();
    });

    it('fetches when widgetId is provided', async () => {
      const { result } = renderHook(() => useWidgetPreview('test-widget'));

      await waitFor(() => {
        expect(result.current.loading).toBe(false);
      });

      expect(mockGetWidgetPreview).toHaveBeenCalled();
    });
  });

  describe('error handling', () => {
    it('handles API errors gracefully', async () => {
      mockGetWidgetPreview.mockRejectedValue(new Error('Widget not found'));

      const { result } = renderHook(() => useWidgetPreview('invalid-widget'));

      await waitFor(() => {
        expect(result.current.loading).toBe(false);
      });

      expect(result.current.error).toBeDefined();
      expect(result.current.error).toBe('Widget not found');
      expect(result.current.previewData).toBeNull();
    });
  });

  describe('refetch functionality', () => {
    it('refetch reloads the preview data', async () => {
      const { result } = renderHook(() => useWidgetPreview('revenue-kpi'));

      await waitFor(() => {
        expect(result.current.loading).toBe(false);
      });

      expect(mockGetWidgetPreview).toHaveBeenCalledTimes(1);

      // Call refetch
      await result.current.refetch();

      expect(mockGetWidgetPreview).toHaveBeenCalledTimes(2);
    });
  });
});
