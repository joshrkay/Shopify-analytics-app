/**
 * Widget Catalog Hooks (Phase 2 Builder)
 *
 * Custom hooks for fetching and filtering the widget catalog.
 */

import { useState, useEffect, useCallback } from 'react';
import {
  getWidgetCatalog,
  getWidgetCategories,
  getWidgetPreview,
} from '../services/widgetCatalogApi';
import { getErrorMessage } from '../services/apiUtils';
import type {
  WidgetCatalogItem,
  WidgetCategoryMeta,
  WidgetCategory,
  WidgetPreviewData,
} from '../types/customDashboards';

interface UseWidgetCatalogResult {
  widgets: WidgetCatalogItem[];
  categories: WidgetCategoryMeta[];
  loading: boolean;
  error: string | null;
  getFilteredWidgets: (category: WidgetCategory) => WidgetCatalogItem[];
  refetch: () => Promise<void>;
}

/**
 * Hook to fetch and filter the widget catalog.
 * Fetches catalog and categories on mount, with client-side filtering.
 *
 * @param category - Optional category to filter widgets by
 * @returns Widget catalog data with filtering utilities
 *
 * @example
 * ```tsx
 * // Fetch all widgets
 * const { widgets, categories, loading } = useWidgetCatalog();
 *
 * // Fetch only sales widgets
 * const { widgets } = useWidgetCatalog('sales');
 *
 * // Filter programmatically
 * const { getFilteredWidgets } = useWidgetCatalog();
 * const roasWidgets = getFilteredWidgets('roas');
 * ```
 */
export function useWidgetCatalog(category?: WidgetCategory): UseWidgetCatalogResult {
  const [allWidgets, setAllWidgets] = useState<WidgetCatalogItem[]>([]);
  const [categories, setCategories] = useState<WidgetCategoryMeta[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const loadCatalog = useCallback(async () => {
    try {
      setLoading(true);
      setError(null);
      const [catalogData, categoriesData] = await Promise.all([
        getWidgetCatalog(),
        getWidgetCategories(),
      ]);
      setAllWidgets(catalogData);
      setCategories(categoriesData);
    } catch (err) {
      console.error('Failed to fetch widget catalog:', err);
      setError(getErrorMessage(err, 'Failed to load widget catalog'));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadCatalog();
  }, [loadCatalog]);

  /**
   * Client-side filtering by category.
   * Filters the full catalog to only include widgets from the specified category.
   *
   * @param filterCategory - Category to filter by ('all' returns all widgets)
   * @returns Filtered array of widgets
   */
  const getFilteredWidgets = useCallback(
    (filterCategory: WidgetCategory): WidgetCatalogItem[] => {
      if (!allWidgets) return [];
      if (filterCategory === 'all') return allWidgets;
      return allWidgets.filter((w) => w.category === filterCategory);
    },
    [allWidgets],
  );

  // Apply category filter if provided
  const widgets = category ? getFilteredWidgets(category) : allWidgets;

  return {
    widgets,
    categories,
    loading,
    error,
    getFilteredWidgets,
    refetch: loadCatalog,
  };
}

interface UseWidgetPreviewResult {
  previewData: WidgetPreviewData | null;
  loading: boolean;
  error: string | null;
  refetch: () => Promise<void>;
}

/**
 * Hook to fetch preview data for a specific widget.
 * Used in the Preview step of the wizard.
 *
 * @param widgetId - Widget catalog ID
 * @param datasetId - Optional dataset ID for preview data binding
 * @returns Preview data for the widget
 *
 * @example
 * ```tsx
 * const { previewData, loading } = useWidgetPreview('roas-overview', 'marketing_attribution');
 *
 * if (loading) return <Spinner />;
 * if (previewData) {
 *   return <ChartRenderer data={previewData.sampleData} type={previewData.chartType} />;
 * }
 * ```
 */
export function useWidgetPreview(
  widgetId: string,
  datasetId?: string,
): UseWidgetPreviewResult {
  const [previewData, setPreviewData] = useState<WidgetPreviewData | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const loadPreview = useCallback(async () => {
    // Don't fetch if widgetId is empty
    if (!widgetId) {
      setPreviewData(null);
      setLoading(false);
      return;
    }

    try {
      setLoading(true);
      setError(null);
      const data = await getWidgetPreview(widgetId, datasetId);
      setPreviewData(data);
    } catch (err) {
      console.error('Failed to fetch widget preview:', err);
      setError(getErrorMessage(err, 'Failed to load widget preview'));
    } finally {
      setLoading(false);
    }
  }, [widgetId, datasetId]);

  useEffect(() => {
    loadPreview();
  }, [loadPreview]);

  return {
    previewData,
    loading,
    error,
    refetch: loadPreview,
  };
}
