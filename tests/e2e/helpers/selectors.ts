/**
 * Shopify Polaris component selectors for E2E tests.
 *
 * Polaris renders custom class names and data attributes.
 * These selectors provide a stable API for finding Polaris components.
 */

/** Polaris Page component */
export const page = {
  title: '.Polaris-Page-Header__TitleWrapper h1, [class*="Header"] h1',
  primaryAction: '.Polaris-Page-Header__PrimaryActionWrapper button',
  content: '.Polaris-Page__Content',
};

/** Polaris Card component */
export const card = {
  root: '.Polaris-Card, .Polaris-LegacyCard',
  header: '.Polaris-Card__Header, .Polaris-LegacyCard__Header',
  section: '.Polaris-Card__Section, .Polaris-LegacyCard__Section',
};

/** Polaris DataTable */
export const dataTable = {
  root: '.Polaris-DataTable',
  row: '.Polaris-DataTable__TableRow',
  cell: '.Polaris-DataTable__Cell',
  header: '.Polaris-DataTable__Cell--header',
};

/** Polaris IndexTable (newer table component) */
export const indexTable = {
  root: '.Polaris-IndexTable',
  row: '.Polaris-IndexTable__TableRow',
  cell: '.Polaris-IndexTable__TableCell',
};

/** Polaris Modal */
export const modal = {
  root: '.Polaris-Modal-Dialog',
  title: '.Polaris-Modal-Header__Title',
  content: '.Polaris-Modal-Section',
  primaryAction: '.Polaris-Modal-Footer button.Polaris-Button--primary',
  secondaryAction: '.Polaris-Modal-Footer button:not(.Polaris-Button--primary)',
  closeButton: '.Polaris-Modal-CloseButton',
};

/** Polaris Banner */
export const banner = {
  root: '.Polaris-Banner',
  critical: '.Polaris-Banner--statusCritical',
  warning: '.Polaris-Banner--statusWarning',
  success: '.Polaris-Banner--statusSuccess',
  info: '.Polaris-Banner--statusInfo',
  title: '.Polaris-Banner__Heading',
  content: '.Polaris-Banner__Content',
};

/** Polaris Toast */
export const toast = {
  root: '.Polaris-Frame-ToastManager .Polaris-Frame-Toast',
  message: '.Polaris-Frame-Toast__Content',
  error: '.Polaris-Frame-Toast--error',
};

/** Polaris Button variants */
export const button = {
  primary: 'button.Polaris-Button--primary',
  destructive: 'button.Polaris-Button--destructive',
  plain: 'button.Polaris-Button--plain',
  any: 'button.Polaris-Button',
};

/** Polaris Form elements */
export const form = {
  textField: '.Polaris-TextField input',
  select: '.Polaris-Select select',
  checkbox: '.Polaris-Checkbox input',
  label: '.Polaris-Label',
  error: '.Polaris-InlineError',
};

/** Polaris Navigation (sidebar) */
export const navigation = {
  root: '.Polaris-Navigation',
  item: '.Polaris-Navigation__Item',
  activeItem: '.Polaris-Navigation__Item--selected',
};

/** Polaris Tabs */
export const tabs = {
  root: '.Polaris-Tabs',
  tab: '.Polaris-Tabs__Tab',
  activeTab: '.Polaris-Tabs__Tab--selected',
  panel: '.Polaris-Tabs__Panel',
};

/** Polaris Spinner / Loading */
export const loading = {
  spinner: '.Polaris-Spinner',
  skeletonPage: '.Polaris-SkeletonPage',
  skeletonBody: '.Polaris-SkeletonBodyText',
};

/** Polaris Badge */
export const badge = {
  root: '.Polaris-Badge',
  success: '.Polaris-Badge--statusSuccess',
  warning: '.Polaris-Badge--statusWarning',
  critical: '.Polaris-Badge--statusCritical',
  info: '.Polaris-Badge--statusInfo',
};

/** Polaris EmptyState */
export const emptyState = {
  root: '.Polaris-EmptyState',
  heading: '.Polaris-EmptyState__Section h2',
  action: '.Polaris-EmptyState__Actions button',
};

/** Polaris Pagination */
export const pagination = {
  root: '.Polaris-Pagination',
  previous: '.Polaris-Pagination button:first-child',
  next: '.Polaris-Pagination button:last-child',
};

/** App-specific data-testid selectors */
export const app = {
  kpiCard: '[data-testid="kpi-card"]',
  channelChart: '[data-testid="channel-chart"]',
  dateRangeSelector: '[data-testid="date-range-selector"]',
  sidebar: '[data-testid="sidebar"]',
  dashboardGrid: '[data-testid="dashboard-grid"]',
  connectSourceBtn: '[data-testid="connect-source"]',
  syncTriggerBtn: '[data-testid="trigger-sync"]',
  insightCard: '[data-testid="insight-card"]',
  orderRow: '[data-testid="order-row"]',
  alertRuleCard: '[data-testid="alert-rule"]',
  notificationBell: '[data-testid="notification-bell"]',
};
