import { describe, it, expect } from 'vitest';
import {
  MIN_GRID_DIMENSIONS,
  GRID_COLS,
  getChartTypeLabel,
  getTemplateCategoryLabel,
} from '../types/customDashboards';
import type { ChartType, TemplateCategory } from '../types/customDashboards';

describe('customDashboards type exports', () => {
  describe('MIN_GRID_DIMENSIONS', () => {
    const allChartTypes: ChartType[] = ['line', 'bar', 'area', 'pie', 'kpi', 'table'];

    it('has entries for all 6 chart types', () => {
      for (const chartType of allChartTypes) {
        expect(MIN_GRID_DIMENSIONS).toHaveProperty(chartType);
      }
      expect(Object.keys(MIN_GRID_DIMENSIONS)).toHaveLength(6);
    });

    it('has positive w and h values for every chart type', () => {
      for (const chartType of allChartTypes) {
        const dims = MIN_GRID_DIMENSIONS[chartType];
        expect(dims.w).toBeGreaterThan(0);
        expect(dims.h).toBeGreaterThan(0);
      }
    });

    it('has correct dimensions for kpi (w=3, h=2)', () => {
      expect(MIN_GRID_DIMENSIONS.kpi.w).toBe(3);
      expect(MIN_GRID_DIMENSIONS.kpi.h).toBe(2);
    });

    it('has correct dimensions for table (w=6, h=4)', () => {
      expect(MIN_GRID_DIMENSIONS.table.w).toBe(6);
      expect(MIN_GRID_DIMENSIONS.table.h).toBe(4);
    });
  });

  describe('GRID_COLS', () => {
    it('equals 12', () => {
      expect(GRID_COLS).toBe(12);
    });
  });

  describe('getChartTypeLabel', () => {
    it.each<[ChartType, string]>([
      ['line', 'Line Chart'],
      ['bar', 'Bar Chart'],
      ['area', 'Area Chart'],
      ['pie', 'Pie Chart'],
      ['kpi', 'KPI'],
      ['table', 'Table'],
    ])('returns correct label for %s', (type, expected) => {
      expect(getChartTypeLabel(type)).toBe(expected);
    });
  });

  describe('getTemplateCategoryLabel', () => {
    it('returns "Sales" for sales (not "Revenue")', () => {
      expect(getTemplateCategoryLabel('sales')).toBe('Sales');
      expect(getTemplateCategoryLabel('sales')).not.toBe('Revenue');
    });

    it.each<[TemplateCategory, string]>([
      ['sales', 'Sales'],
      ['marketing', 'Marketing'],
      ['customer', 'Customer'],
      ['product', 'Product'],
      ['operations', 'Operations'],
    ])('returns correct label for %s', (category, expected) => {
      expect(getTemplateCategoryLabel(category)).toBe(expected);
    });
  });
});
