/**
 * Chart Icons Utility
 *
 * Maps chart types to their corresponding Polaris icons.
 * Used in CategorySidebar and WidgetCatalogCard for visual consistency.
 *
 * Phase 2.3 - Category Icons & Widget Card Enhancements
 */

import {
  ChartVerticalIcon,
  ChartHorizontalIcon,
  ChartLineIcon,
  ChartDonutIcon,
  CheckCircleIcon,
  ListBulletedIcon,
} from '@shopify/polaris-icons';
import type { ChartType } from '../types/customDashboards';

/**
 * Get the Polaris icon for a given chart type
 */
export function getChartIcon(chartType: ChartType) {
  const iconMap = {
    line: ChartVerticalIcon,
    bar: ChartHorizontalIcon,
    area: ChartLineIcon,
    pie: ChartDonutIcon,
    kpi: CheckCircleIcon,
    table: ListBulletedIcon,
  };

  return iconMap[chartType] || ChartVerticalIcon;
}
