/**
 * Widget Catalog API Service (Phase 2 Builder)
 *
 * Provides a static widget catalog for the 3-step wizard builder.
 * In v1, returns frontend-defined widgets. Future: could fetch from backend API.
 */

import type {
  WidgetCatalogItem,
  WidgetCategoryMeta,
  WidgetPreviewData,
} from '../types/customDashboards';

// =============================================================================
// Widget Catalog Data (16 Widgets across 6 Categories)
// =============================================================================

/**
 * Complete widget catalog - maps wireframe's 16 widgets to existing chart types.
 * Each widget maps to a ChartRenderer configuration.
 */
const WIDGET_CATALOG: WidgetCatalogItem[] = [
  // ========== ROAS & ROI Category (2 widgets) ==========
  {
    id: 'roas-overview',
    type: 'chart',
    title: 'ROAS Overview',
    description: 'Return on ad spend across all channels',
    icon: 'TrendingUp',
    category: 'roas',
    defaultSize: 'medium',
    chartType: 'kpi',
    dataSourceRequired: true,
    requiredDatasets: ['marketing_attribution'],
    tags: ['roas', 'marketing', 'kpi'],
  },
  {
    id: 'roi-by-channel',
    type: 'chart',
    title: 'ROI by Channel',
    description: 'Compare return on investment across marketing channels',
    icon: 'BarChart3',
    category: 'roas',
    defaultSize: 'large',
    chartType: 'bar',
    dataSourceRequired: true,
    requiredDatasets: ['marketing_attribution'],
    tags: ['roi', 'marketing', 'channels'],
  },

  // ========== Sales Category (4 widgets) ==========
  {
    id: 'sales-trend',
    type: 'chart',
    title: 'Sales Trend',
    description: 'Sales over time with trend line',
    icon: 'TrendingUp',
    category: 'sales',
    defaultSize: 'large',
    chartType: 'line',
    dataSourceRequired: true,
    requiredDatasets: ['sales_metrics', 'canonical_orders'],
    tags: ['sales', 'trend', 'time-series'],
  },
  {
    id: 'revenue-kpi',
    type: 'metric',
    title: 'Total Revenue',
    description: 'Total revenue for selected period',
    icon: 'DollarSign',
    category: 'sales',
    defaultSize: 'small',
    chartType: 'kpi',
    dataSourceRequired: true,
    requiredDatasets: ['sales_metrics'],
    tags: ['revenue', 'kpi', 'sales'],
  },
  {
    id: 'avg-order-value',
    type: 'metric',
    title: 'Average Order Value',
    description: 'Average value per order',
    icon: 'ShoppingCart',
    category: 'sales',
    defaultSize: 'small',
    chartType: 'kpi',
    dataSourceRequired: true,
    requiredDatasets: ['sales_metrics'],
    tags: ['aov', 'kpi', 'sales'],
  },
  {
    id: 'sales-by-category',
    type: 'chart',
    title: 'Sales by Product Category',
    description: 'Revenue breakdown by product category',
    icon: 'PieChart',
    category: 'sales',
    defaultSize: 'medium',
    chartType: 'pie',
    dataSourceRequired: true,
    requiredDatasets: ['product_analytics'],
    tags: ['sales', 'categories', 'breakdown'],
  },

  // ========== Products Category (3 widgets) ==========
  {
    id: 'top-products',
    type: 'table',
    title: 'Top Products',
    description: 'Best selling products by revenue',
    icon: 'Package',
    category: 'products',
    defaultSize: 'medium',
    chartType: 'table',
    dataSourceRequired: true,
    requiredDatasets: ['product_analytics'],
    tags: ['products', 'top-sellers', 'table'],
  },
  {
    id: 'product-performance',
    type: 'chart',
    title: 'Product Performance',
    description: 'Product sales comparison',
    icon: 'BarChart3',
    category: 'products',
    defaultSize: 'large',
    chartType: 'bar',
    dataSourceRequired: true,
    requiredDatasets: ['product_analytics'],
    tags: ['products', 'performance', 'comparison'],
  },
  {
    id: 'inventory-turnover',
    type: 'metric',
    title: 'Inventory Turnover',
    description: 'How quickly inventory is sold and replaced',
    icon: 'RefreshCw',
    category: 'products',
    defaultSize: 'small',
    chartType: 'kpi',
    dataSourceRequired: true,
    requiredDatasets: ['product_analytics'],
    tags: ['inventory', 'kpi', 'turnover'],
  },

  // ========== Customers Category (4 widgets) ==========
  {
    id: 'customer-segments',
    type: 'chart',
    title: 'Customer Segments',
    description: 'Customer distribution by segment',
    icon: 'PieChart',
    category: 'customers',
    defaultSize: 'medium',
    chartType: 'pie',
    dataSourceRequired: true,
    requiredDatasets: ['customer_analytics'],
    tags: ['customers', 'segments', 'distribution'],
  },
  {
    id: 'ltv-cohort',
    type: 'chart',
    title: 'LTV Cohort Analysis',
    description: 'Customer lifetime value by cohort',
    icon: 'Users',
    category: 'customers',
    defaultSize: 'large',
    chartType: 'line',
    dataSourceRequired: true,
    requiredDatasets: ['customer_analytics'],
    tags: ['ltv', 'cohort', 'customers'],
  },
  {
    id: 'new-vs-returning',
    type: 'chart',
    title: 'New vs Returning Customers',
    description: 'Comparison of new and returning customers',
    icon: 'UserPlus',
    category: 'customers',
    defaultSize: 'medium',
    chartType: 'bar',
    dataSourceRequired: true,
    requiredDatasets: ['customer_analytics'],
    tags: ['customers', 'retention', 'comparison'],
  },
  {
    id: 'retention-rate',
    type: 'metric',
    title: 'Customer Retention Rate',
    description: 'Percentage of customers who return',
    icon: 'Heart',
    category: 'customers',
    defaultSize: 'small',
    chartType: 'kpi',
    dataSourceRequired: true,
    requiredDatasets: ['customer_analytics'],
    tags: ['retention', 'kpi', 'customers'],
  },

  // ========== Campaigns Category (3 widgets) ==========
  {
    id: 'campaign-performance',
    type: 'chart',
    title: 'Campaign Performance',
    description: 'Marketing campaign effectiveness',
    icon: 'Megaphone',
    category: 'campaigns',
    defaultSize: 'large',
    chartType: 'bar',
    dataSourceRequired: true,
    requiredDatasets: ['marketing_attribution'],
    tags: ['campaigns', 'marketing', 'performance'],
  },
  {
    id: 'campaign-roi',
    type: 'metric',
    title: 'Campaign ROI',
    description: 'Overall campaign return on investment',
    icon: 'Target',
    category: 'campaigns',
    defaultSize: 'small',
    chartType: 'kpi',
    dataSourceRequired: true,
    requiredDatasets: ['marketing_attribution'],
    tags: ['roi', 'campaigns', 'kpi'],
  },
  {
    id: 'conversion-funnel',
    type: 'chart',
    title: 'Conversion Funnel',
    description: 'Campaign conversion stages',
    icon: 'Filter',
    category: 'campaigns',
    defaultSize: 'medium',
    chartType: 'bar',
    dataSourceRequired: true,
    requiredDatasets: ['marketing_attribution'],
    tags: ['funnel', 'conversion', 'campaigns'],
  },
];

/**
 * Category metadata for sidebar filtering.
 */
const WIDGET_CATEGORIES: WidgetCategoryMeta[] = [
  { id: 'all', name: 'All Widgets', icon: 'LayoutGrid' },
  {
    id: 'roas',
    name: 'ROAS & ROI',
    icon: 'TrendingUp',
    description: 'Return on ad spend metrics',
  },
  {
    id: 'sales',
    name: 'Sales',
    icon: 'DollarSign',
    description: 'Sales and revenue analytics',
  },
  {
    id: 'products',
    name: 'Products',
    icon: 'Package',
    description: 'Product performance metrics',
  },
  {
    id: 'customers',
    name: 'Customers',
    icon: 'Users',
    description: 'Customer insights and segments',
  },
  {
    id: 'campaigns',
    name: 'Campaigns',
    icon: 'Megaphone',
    description: 'Marketing campaign analytics',
  },
];

// =============================================================================
// API Functions
// =============================================================================

/**
 * Get all available widgets in the catalog.
 * In v1, returns static list. Future: fetch from backend API.
 */
export async function getWidgetCatalog(): Promise<WidgetCatalogItem[]> {
  // Simulate async fetch (for consistent API with future backend version)
  return Promise.resolve([...WIDGET_CATALOG]);
}

/**
 * Get all widget categories for sidebar filtering.
 */
export async function getWidgetCategories(): Promise<WidgetCategoryMeta[]> {
  return Promise.resolve([...WIDGET_CATEGORIES]);
}

/**
 * Get preview data for a specific widget.
 * Bridges to existing useChartPreview hook for real data in future.
 *
 * @param widgetId - Widget catalog ID
 * @param datasetId - Optional dataset ID for preview data binding
 */
export async function getWidgetPreview(
  widgetId: string,
  datasetId?: string,
): Promise<WidgetPreviewData> {
  const widget = WIDGET_CATALOG.find((w) => w.id === widgetId);

  if (!widget) {
    throw new Error(`Widget not found: ${widgetId}`);
  }

  // Generate sample data based on widget type
  const sampleData = generateSampleDataForWidget(widget, datasetId);

  return {
    widgetId,
    chartType: widget.chartType,
    sampleData,
    loading: false,
  };
}

// =============================================================================
// Helper Functions
// =============================================================================

/**
 * Helper: Generate sample preview data based on widget type.
 * TODO: Replace with real preview data from useChartPreview hook.
 */
function generateSampleDataForWidget(
  widget: WidgetCatalogItem,
  _datasetId?: string, // Reserved for future use
): Record<string, unknown> {
  // Placeholder implementation with realistic mock data
  switch (widget.chartType) {
    case 'kpi':
      return generateKpiSampleData(widget);
    case 'line':
      return generateLineSampleData(widget);
    case 'bar':
      return generateBarSampleData(widget);
    case 'pie':
      return generatePieSampleData(widget);
    case 'table':
      return generateTableSampleData(widget);
    case 'area':
      return generateAreaSampleData(widget);
    default:
      return {};
  }
}

function generateKpiSampleData(widget: WidgetCatalogItem): Record<string, unknown> {
  const valuesByWidget: Record<string, { value: number; change: number }> = {
    'roas-overview': { value: 3.45, change: 12.5 },
    'revenue-kpi': { value: 124580, change: 8.3 },
    'avg-order-value': { value: 87.5, change: 5.2 },
    'inventory-turnover': { value: 6.2, change: -2.1 },
    'retention-rate': { value: 68.4, change: 3.7 },
    'campaign-roi': { value: 2.8, change: 15.3 },
  };

  const data = valuesByWidget[widget.id] || { value: 100, change: 10 };
  return {
    ...data,
    trend: data.change > 0 ? 'up' : 'down',
  };
}

function generateLineSampleData(widget: WidgetCatalogItem): Record<string, unknown> {
  const months = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun'];
  const baseValue = widget.id === 'sales-trend' ? 50000 : 5000;

  return {
    series: [
      {
        name: widget.title,
        data: months.map((month, i) => ({
          x: month,
          y: baseValue + Math.random() * baseValue * 0.3 + i * (baseValue * 0.1),
        })),
      },
    ],
  };
}

function generateBarSampleData(widget: WidgetCatalogItem): Record<string, unknown> {
  const categories =
    widget.id === 'roi-by-channel'
      ? ['Google', 'Facebook', 'Instagram', 'Email']
      : widget.id === 'campaign-performance'
        ? ['Spring Sale', 'Summer Promo', 'Fall Campaign', 'Holiday Sale']
        : widget.id === 'product-performance'
          ? ['Product A', 'Product B', 'Product C', 'Product D']
          : ['Category A', 'Category B', 'Category C'];

  return {
    categories,
    series: [
      {
        name: widget.title,
        data: categories.map(() => Math.floor(Math.random() * 10000) + 1000),
      },
    ],
  };
}

function generatePieSampleData(widget: WidgetCatalogItem): Record<string, unknown> {
  const segments =
    widget.id === 'customer-segments'
      ? ['VIP', 'Regular', 'New', 'At Risk']
      : widget.id === 'sales-by-category'
        ? ['Electronics', 'Clothing', 'Home', 'Sports']
        : ['Segment A', 'Segment B', 'Segment C'];

  return {
    segments: segments.map((name) => ({
      name,
      value: Math.floor(Math.random() * 1000) + 100,
    })),
  };
}

function generateTableSampleData(widget: WidgetCatalogItem): Record<string, unknown> {
  const rows =
    widget.id === 'top-products'
      ? [
          { product: 'Wireless Headphones', revenue: 45000, units: 520 },
          { product: 'Smart Watch', revenue: 38000, units: 380 },
          { product: 'Laptop Stand', revenue: 28000, units: 700 },
          { product: 'USB-C Hub', revenue: 22000, units: 880 },
          { product: 'Phone Case', revenue: 18000, units: 1200 },
        ]
      : [
          { name: 'Item 1', value: 1000 },
          { name: 'Item 2', value: 900 },
          { name: 'Item 3', value: 800 },
        ];

  return { rows };
}

function generateAreaSampleData(widget: WidgetCatalogItem): Record<string, unknown> {
  return generateLineSampleData(widget); // Area charts use same data structure as line charts
}
