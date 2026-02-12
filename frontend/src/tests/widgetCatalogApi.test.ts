/**
 * Unit tests for Widget Catalog API Service (Phase 2.2)
 *
 * Tests:
 * - getWidgetCatalog() returns complete catalog
 * - getWidgetCategories() returns all categories
 * - getWidgetPreview() generates appropriate sample data
 * - Error handling for invalid widget IDs
 */

import { describe, it, expect } from 'vitest';
import { getWidgetCatalog, getWidgetCategories, getWidgetPreview } from '../services/widgetCatalogApi';
import type { ChartType } from '../types/customDashboards';

describe('widgetCatalogApi', () => {
  describe('getWidgetCatalog', () => {
    it('returns all widgets in the catalog', async () => {
      const catalog = await getWidgetCatalog();

      expect(catalog).toBeDefined();
      expect(Array.isArray(catalog)).toBe(true);
      expect(catalog.length).toBeGreaterThanOrEqual(16); // Should have at least 16 widgets
    });

    it('each widget has required fields', async () => {
      const catalog = await getWidgetCatalog();

      catalog.forEach((widget) => {
        expect(widget.id).toBeDefined();
        expect(typeof widget.id).toBe('string');
        expect(widget.type).toBeDefined();
        expect(['metric', 'chart', 'table']).toContain(widget.type);
        expect(widget.title).toBeDefined();
        expect(widget.description).toBeDefined();
        expect(widget.icon).toBeDefined();
        expect(widget.category).toBeDefined();
        expect(widget.defaultSize).toBeDefined();
        expect(['small', 'medium', 'large', 'full']).toContain(widget.defaultSize);
      });
    });

    it('widget types match existing WidgetType enum', async () => {
      const catalog = await getWidgetCatalog();
      const validTypes = ['metric', 'chart', 'table'];

      catalog.forEach((widget) => {
        expect(validTypes).toContain(widget.type);
      });
    });

    it('chart types match existing ChartType enum', async () => {
      const catalog = await getWidgetCatalog();
      const validChartTypes: ChartType[] = ['line', 'bar', 'area', 'pie', 'kpi', 'table'];

      catalog.forEach((widget) => {
        if (widget.chartType) {
          expect(validChartTypes).toContain(widget.chartType);
        }
      });
    });

    it('includes widgets from all 6 categories', async () => {
      const catalog = await getWidgetCatalog();
      const categories = new Set(catalog.map((w) => w.category));

      expect(categories.has('roas')).toBe(true);
      expect(categories.has('sales')).toBe(true);
      expect(categories.has('products')).toBe(true);
      expect(categories.has('customers')).toBe(true);
      expect(categories.has('campaigns')).toBe(true);
      // 'all' is a filter category, not a widget category
      expect(categories.size).toBeGreaterThanOrEqual(5);
    });

    it('widget IDs are unique', async () => {
      const catalog = await getWidgetCatalog();
      const ids = catalog.map((w) => w.id);
      const uniqueIds = new Set(ids);

      expect(uniqueIds.size).toBe(ids.length);
    });

    it('widgets have appropriate data source requirements', async () => {
      const catalog = await getWidgetCatalog();

      catalog.forEach((widget) => {
        if (widget.dataSourceRequired === true) {
          expect(widget.requiredDatasets).toBeDefined();
          expect(Array.isArray(widget.requiredDatasets)).toBe(true);
          expect(widget.requiredDatasets!.length).toBeGreaterThan(0);
        }
      });
    });
  });

  describe('getWidgetCategories', () => {
    it('returns all 6 categories', async () => {
      const categories = await getWidgetCategories();

      expect(categories).toBeDefined();
      expect(Array.isArray(categories)).toBe(true);
      expect(categories.length).toBe(6);
    });

    it('includes "all" category for filtering', async () => {
      const categories = await getWidgetCategories();
      const allCategory = categories.find((c) => c.id === 'all');

      expect(allCategory).toBeDefined();
      expect(allCategory!.name).toBe('All Widgets');
      expect(allCategory!.icon).toBe('LayoutGrid');
    });

    it('each category has required fields', async () => {
      const categories = await getWidgetCategories();

      categories.forEach((category) => {
        expect(category.id).toBeDefined();
        expect(category.name).toBeDefined();
        expect(category.icon).toBeDefined();
        // description is optional
      });
    });

    it('category IDs match expected values', async () => {
      const categories = await getWidgetCategories();
      const categoryIds = categories.map((c) => c.id);

      expect(categoryIds).toContain('all');
      expect(categoryIds).toContain('roas');
      expect(categoryIds).toContain('sales');
      expect(categoryIds).toContain('products');
      expect(categoryIds).toContain('customers');
      expect(categoryIds).toContain('campaigns');
    });
  });

  describe('getWidgetPreview', () => {
    it('returns preview data for a valid metric widget', async () => {
      const preview = await getWidgetPreview('revenue-kpi');

      expect(preview).toBeDefined();
      expect(preview.widgetId).toBe('revenue-kpi');
      expect(preview.chartType).toBe('kpi');
      expect(preview.sampleData).toBeDefined();
      expect(preview.loading).toBe(false);
      expect(preview.error).toBeUndefined();
    });

    it('returns preview data for a valid chart widget', async () => {
      const preview = await getWidgetPreview('sales-trend');

      expect(preview).toBeDefined();
      expect(preview.widgetId).toBe('sales-trend');
      expect(preview.chartType).toBe('line');
      expect(preview.sampleData).toBeDefined();
      expect(typeof preview.sampleData).toBe('object');
    });

    it('returns preview data for a table widget', async () => {
      const preview = await getWidgetPreview('top-products');

      expect(preview).toBeDefined();
      expect(preview.widgetId).toBe('top-products');
      expect(preview.chartType).toBe('table');
      expect(preview.sampleData).toBeDefined();
      expect(preview.sampleData.rows).toBeDefined();
    });

    it('KPI widgets have value and change in sample data', async () => {
      const preview = await getWidgetPreview('roas-overview');

      expect(preview.chartType).toBe('kpi');
      expect(preview.sampleData.value).toBeDefined();
      expect(typeof preview.sampleData.value).toBe('number');
      expect(preview.sampleData.change).toBeDefined();
      expect(typeof preview.sampleData.change).toBe('number');
      expect(preview.sampleData.trend).toBeDefined();
    });

    it('line chart widgets have series data', async () => {
      const preview = await getWidgetPreview('sales-trend');

      expect(preview.chartType).toBe('line');
      expect(preview.sampleData.series).toBeDefined();
      expect(Array.isArray(preview.sampleData.series)).toBe(true);
      expect((preview.sampleData.series as unknown[]).length).toBeGreaterThan(0);
    });

    it('bar chart widgets have categories and series', async () => {
      const preview = await getWidgetPreview('roi-by-channel');

      expect(preview.chartType).toBe('bar');
      expect(preview.sampleData.categories).toBeDefined();
      expect(Array.isArray(preview.sampleData.categories)).toBe(true);
      expect(preview.sampleData.series).toBeDefined();
      expect(Array.isArray(preview.sampleData.series)).toBe(true);
    });

    it('pie chart widgets have segments data', async () => {
      const preview = await getWidgetPreview('customer-segments');

      expect(preview.chartType).toBe('pie');
      expect(preview.sampleData.segments).toBeDefined();
      expect(Array.isArray(preview.sampleData.segments)).toBe(true);
      expect((preview.sampleData.segments as unknown[]).length).toBeGreaterThan(0);
    });

    it('throws error for invalid widget ID', async () => {
      await expect(getWidgetPreview('invalid-widget-id')).rejects.toThrow(
        'Widget not found: invalid-widget-id',
      );
    });

    it('accepts optional datasetId parameter', async () => {
      const preview = await getWidgetPreview('revenue-kpi', 'sales_metrics');

      expect(preview).toBeDefined();
      expect(preview.widgetId).toBe('revenue-kpi');
      // datasetId is passed but not used in v1 implementation
    });
  });

  describe('Widget catalog integrity', () => {
    it('has exactly 16 widgets', async () => {
      const catalog = await getWidgetCatalog();
      expect(catalog.length).toBe(16);
    });

    it('ROAS category has 2 widgets', async () => {
      const catalog = await getWidgetCatalog();
      const roasWidgets = catalog.filter((w) => w.category === 'roas');
      expect(roasWidgets.length).toBe(2);
    });

    it('Sales category has 4 widgets', async () => {
      const catalog = await getWidgetCatalog();
      const salesWidgets = catalog.filter((w) => w.category === 'sales');
      expect(salesWidgets.length).toBe(4);
    });

    it('Products category has 3 widgets', async () => {
      const catalog = await getWidgetCatalog();
      const productsWidgets = catalog.filter((w) => w.category === 'products');
      expect(productsWidgets.length).toBe(3);
    });

    it('Customers category has 4 widgets', async () => {
      const catalog = await getWidgetCatalog();
      const customersWidgets = catalog.filter((w) => w.category === 'customers');
      expect(customersWidgets.length).toBe(4);
    });

    it('Campaigns category has 3 widgets', async () => {
      const catalog = await getWidgetCatalog();
      const campaignsWidgets = catalog.filter((w) => w.category === 'campaigns');
      expect(campaignsWidgets.length).toBe(3);
    });
  });
});
