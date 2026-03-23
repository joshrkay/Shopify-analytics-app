import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { AppProvider } from '@shopify/polaris';

import { WizardFlow } from '../components/dashboards/wizard/WizardFlow';

const navigateMock = vi.fn();
const createTemplateMock = vi.fn();

vi.mock('react-router-dom', async () => {
  const actual = await vi.importActual<typeof import('react-router-dom')>('react-router-dom');
  return {
    ...actual,
    useNavigate: () => navigateMock,
  };
});

vi.mock('../services/templatesApi', () => ({
  createTemplate: (...args: unknown[]) => createTemplateMock(...args),
}));

const builderContextMock = {
  wizardState: {
    currentStep: 'preview',
    selectedCategory: undefined,
    selectedWidgets: [
      {
        id: 'r-1',
        name: 'Revenue',
        description: 'Revenue chart',
        chart_type: 'line',
        dataset_name: 'sales_daily',
        config_json: { metrics: [], dimensions: [] },
        position_json: { x: 0, y: 0, w: 6, h: 4 },
        sort_order: 0,
      },
    ],
    dashboardName: 'Q1 Dashboard',
    dashboardDescription: 'Quarterly KPIs',
    previewDateRange: '30',
  },
  isSaving: false,
  setBuilderStep: vi.fn(),
  setSelectedCategory: vi.fn(),
  addCatalogWidget: vi.fn(),
  removeWizardWidget: vi.fn(),
  setWizardDashboardName: vi.fn(),
  setPreviewDateRange: vi.fn(),
  saveDashboard: vi.fn(),
  exitWizardMode: vi.fn(),
  enterWizardMode: vi.fn(),
  canProceedToCustomize: true,
  canProceedToPreview: true,
  canSaveDashboard: true,
};

vi.mock('../contexts/DashboardBuilderContext', () => ({
  useDashboardBuilder: () => builderContextMock,
}));

vi.mock('../hooks/useWidgetCatalog', () => ({
  useWidgetCatalog: () => ({
    items: [],
    loading: false,
    error: null,
    refresh: vi.fn(),
  }),
}));

vi.mock('../components/dashboards/wizard/BuilderStepNav', () => ({
  BuilderStepNav: () => <div data-testid="step-nav" />,
}));

vi.mock('../components/dashboards/wizard/BuilderToolbar', () => ({
  BuilderToolbar: () => <div data-testid="builder-toolbar" />,
}));

vi.mock('../components/dashboards/wizard/CategorySidebar', () => ({
  CategorySidebar: () => <div data-testid="category-sidebar" />,
}));

vi.mock('../components/dashboards/wizard/WidgetGallery', () => ({
  WidgetGallery: () => <div data-testid="widget-gallery" />,
}));

vi.mock('../components/builder/LayoutCustomizer', () => ({
  LayoutCustomizer: () => <div data-testid="layout-customizer" />,
}));

vi.mock('../components/dashboards/wizard/PreviewGrid', () => ({
  PreviewGrid: () => <div data-testid="preview-grid" />,
}));

vi.mock('../components/dashboards/wizard/PreviewControls', () => ({
  PreviewControls: () => <div data-testid="preview-controls" />,
}));

const translations = {
  Polaris: { Common: { ok: 'OK', cancel: 'Cancel' } },
};

function renderWithProviders() {
  return render(
    <AppProvider i18n={translations as any}>
      <WizardFlow />
    </AppProvider>,
  );
}

describe('WizardFlow template save', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('shows success toast after saving template', async () => {
    createTemplateMock.mockResolvedValue({ id: 'tpl-1' });
    const alertSpy = vi.spyOn(window, 'alert').mockImplementation(() => {});

    renderWithProviders();

    await userEvent.click(screen.getByRole('button', { name: 'Save as Template' }));

    await waitFor(() => {
      expect(createTemplateMock).toHaveBeenCalledTimes(1);
    });

    expect(createTemplateMock).toHaveBeenCalledWith(
      expect.objectContaining({
        name: 'Q1 Dashboard',
        description: 'Quarterly KPIs',
        config_json: expect.objectContaining({
          reports: expect.arrayContaining([
            expect.objectContaining({
              name: 'Revenue',
              chart_type: 'line',
            }),
          ]),
        }),
      }),
    );

    expect(await screen.findByText('Template saved successfully')).toBeInTheDocument();
    expect(alertSpy).not.toHaveBeenCalled();

    alertSpy.mockRestore();
  });

  it('shows error toast when template save fails', async () => {
    createTemplateMock.mockRejectedValue(new Error('Template API unavailable'));

    renderWithProviders();

    await userEvent.click(screen.getByRole('button', { name: 'Save as Template' }));

    expect(await screen.findByText('Template API unavailable')).toBeInTheDocument();
    expect(navigateMock).not.toHaveBeenCalled();
  });
});
