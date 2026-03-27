/**
 * Wizard Flow Component
 *
 * Main orchestrator for the 3-step dashboard creation wizard:
 * 1. Select Widgets - Browse and select from widget catalog
 * 2. Customize Layout - Edit name, description, and arrange widgets
 * 3. Preview & Save - Review with live or sample data and save the dashboard
 *
 * Phase 2.6 - Preview Step Live Data Integration
 */

import { useState, useMemo, useCallback, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  Page,
  BlockStack,
  InlineStack,
  Box,
  Text,
  Banner,
  Toast,
  Frame,
} from '@shopify/polaris';
import type { ChartType, WidgetCatalogItem } from '../../../types/customDashboards';
import { useDashboardBuilder } from '../../../contexts/DashboardBuilderContext';
import { useWidgetCatalog } from '../../../hooks/useWidgetCatalog';
import { BuilderStepNav } from './BuilderStepNav';
import { BuilderToolbar } from './BuilderToolbar';
import { WizardTopToolbar } from './WizardTopToolbar';
import { CategorySidebar } from './CategorySidebar';
import { WidgetGallery } from './WidgetGallery';
import { LayoutCustomizer } from '../../builder/LayoutCustomizer';
import { PreviewGrid } from './PreviewGrid';
import { PreviewControls } from './PreviewControls';
import { createTemplate } from '../../../services/templatesApi';
import { getErrorMessage } from '../../../services/apiUtils';

export function WizardFlow() {
  const navigate = useNavigate();

  // Context state
  const {
    wizardState,
    isSaving,
    setBuilderStep,
    setSelectedCategory,
    addCatalogWidget,
    removeWizardWidget,
    setWizardDashboardName,
    setPreviewDateRange,
    saveDashboard,
    exitWizardMode,
    enterWizardMode,
    canProceedToCustomize,
    canProceedToPreview,
    canSaveDashboard,
  } = useDashboardBuilder();

  // Widget catalog
  const { items, loading, error, refresh } = useWidgetCatalog();

  // Track completed steps
  const [completedSteps, setCompletedSteps] = useState<Set<'select' | 'customize' | 'preview'>>(
    new Set()
  );

  // Live data preview state (NEW)
  const [previewUseLiveData, setPreviewUseLiveData] = useState(false);
  const [refetchKey, setRefetchKey] = useState(0);
  const [isRefreshing, setIsRefreshing] = useState(false);

  // Toast state
  const [toastState, setToastState] = useState<{
    active: boolean;
    content: string;
    error: boolean;
  }>({
    active: false,
    content: '',
    error: false,
  });

  // Enter wizard mode on mount
  useEffect(() => {
    enterWizardMode();
  }, [enterWizardMode]);

  // Filter items by selected category
  const filteredItems = useMemo(() => {
    if (!wizardState.selectedCategory) return items;
    return items.filter((item) => item.category === wizardState.selectedCategory);
  }, [items, wizardState.selectedCategory]);

  // Calculate widget counts per category
  const widgetCounts = useMemo(() => {
    const counts: Record<ChartType | 'all', number> = {
      all: items.length,
      line: 0,
      bar: 0,
      area: 0,
      pie: 0,
      kpi: 0,
      table: 0,
    };

    items.forEach((item) => {
      counts[item.chart_type] = (counts[item.chart_type] || 0) + 1;
    });

    return counts;
  }, [items]);

  // Selected widget IDs for gallery
  const selectedWidgetIds = useMemo(() => {
    return new Set(wizardState.selectedWidgets.map((w) => w.id.split('::')[0]));
  }, [wizardState.selectedWidgets]);

  // Navigation handlers
  const handleNext = useCallback(() => {
    if (wizardState.currentStep === 'select' && canProceedToCustomize) {
      setCompletedSteps((prev) => new Set([...prev, 'select']));
      setBuilderStep('customize');
    } else if (wizardState.currentStep === 'customize' && canProceedToPreview) {
      setCompletedSteps((prev) => new Set([...prev, 'customize']));
      setBuilderStep('preview');
    }
  }, [wizardState.currentStep, canProceedToCustomize, canProceedToPreview, setBuilderStep]);

  const handleBack = useCallback(() => {
    if (wizardState.currentStep === 'preview') {
      setBuilderStep('customize');
    } else if (wizardState.currentStep === 'customize') {
      setBuilderStep('select');
    }
  }, [wizardState.currentStep, setBuilderStep]);

  const handleSave = useCallback(async () => {
    try {
      const newDashboardId = await saveDashboard();
      setToastState({
        active: true,
        content: 'Dashboard created successfully',
        error: false,
      });
      // Brief delay so the user sees the toast before navigation
      setTimeout(() => {
        if (newDashboardId) {
          navigate(`/dashboards/${newDashboardId}`);
        } else {
          navigate('/dashboards');
        }
      }, 800);
    } catch (err) {
      console.error('Failed to save dashboard:', err);
      // Error is handled by context
    }
  }, [saveDashboard, navigate]);

  const handleCancel = useCallback(() => {
    exitWizardMode();
    navigate('/dashboards');
  }, [exitWizardMode, navigate]);

  const handleSaveAsTemplate = useCallback(async () => {
    try {
      const templateName = wizardState.dashboardName.trim() || 'Untitled Dashboard Template';
      const templateDescription = wizardState.dashboardDescription.trim();

      await createTemplate({
        name: templateName,
        description: templateDescription || undefined,
        category: 'operations',
        min_billing_tier: 'free',
        config_json: {
          dashboard: {
            name: templateName,
            description: templateDescription || null,
          },
          reports: wizardState.selectedWidgets.map((widget) => ({
            name: widget.name,
            description: widget.description,
            chart_type: widget.chart_type,
            dataset_name: widget.dataset_name,
            config_json: widget.config_json,
            position_json: widget.position_json,
            sort_order: widget.sort_order,
          })),
        },
      });

      setToastState({
        active: true,
        content: 'Template saved successfully',
        error: false,
      });
    } catch (err) {
      console.error('Failed to save template:', err);
      setToastState({
        active: true,
        content: getErrorMessage(err, 'Failed to save template'),
        error: true,
      });
    }
  }, [
    wizardState.dashboardName,
    wizardState.dashboardDescription,
    wizardState.selectedWidgets,
  ]);

  const handleAddWidget = useCallback(
    (item: WidgetCatalogItem) => {
      addCatalogWidget(item);
    },
    [addCatalogWidget]
  );

  // Handle refresh preview (NEW)
  const handleRefresh = useCallback(() => {
    // Prevent rapid clicks (debounce)
    if (isRefreshing) return;

    setIsRefreshing(true);
    // Increment refetch key to trigger data refetch in all PreviewReportCards
    setRefetchKey(prev => (prev + 1) % 1000); // Wrap at 1000 to prevent overflow

    // Re-enable after 2 seconds
    setTimeout(() => setIsRefreshing(false), 2000);
  }, [isRefreshing]);

  // Render step content
  const renderStepContent = () => {
    switch (wizardState.currentStep) {
      case 'select':
        return (
          <InlineStack gap="400" align="start">
            {/* Category Sidebar */}
            <Box minWidth="260px">
              <CategorySidebar
                selectedCategory={wizardState.selectedCategory}
                onSelectCategory={setSelectedCategory}
                widgetCounts={widgetCounts}
                selectedWidgets={wizardState.selectedWidgets}
                onRemoveWidget={removeWizardWidget}
                onContinueToLayout={handleNext}
              />
            </Box>

            {/* Widget Gallery */}
            <div style={{ flex: 1 }}>
              <WidgetGallery
                items={filteredItems}
                selectedIds={selectedWidgetIds}
                onAddWidget={handleAddWidget}
                loading={loading}
                error={error?.message ?? null}
                onRetry={refresh}
              />
            </div>
          </InlineStack>
        );

      case 'customize':
        return <LayoutCustomizer />;

      case 'preview':
        return (
          <BlockStack gap="400">
            {/* Success Banner */}
            <Banner tone="success">
              <Text as="p" variant="bodyMd">
                Dashboard Preview — This is how your dashboard will look with{' '}
                {previewUseLiveData ? 'live' : 'sample'} data
              </Text>
            </Banner>

            {/* Dashboard Metadata */}
            <BlockStack gap="200">
              <Text as="h2" variant="headingLg">
                {wizardState.dashboardName || 'Untitled Dashboard'}
              </Text>
              <Text as="p" variant="bodySm" tone="subdued">
                {wizardState.dashboardDescription || 'No description'}
              </Text>
              <Text as="p" variant="bodySm" tone="subdued">
                Last {wizardState.previewDateRange || '30'} days • Updates every hour
              </Text>
            </BlockStack>

            {/* Preview Controls (date range, live data toggle, refresh) */}
            <PreviewControls
              dateRange={wizardState.previewDateRange || '30'}
              onDateRangeChange={setPreviewDateRange}
              useLiveData={previewUseLiveData}
              onUseLiveDataChange={setPreviewUseLiveData}
              onRefresh={handleRefresh}
              isRefreshing={isRefreshing}
            />

            {/* Visual Grid Preview with Live or Sample Data */}
            <PreviewGrid
              useLiveData={previewUseLiveData}
              dateRange={wizardState.previewDateRange || '30'}
              refetchKey={refetchKey}
            />
          </BlockStack>
        );

      default:
        return null;
    }
  };

  return (
    <Page
      title="Create Dashboard"
      backAction={{ content: 'Back to Dashboards', onAction: handleCancel }}
    >
      <BlockStack gap="600">
        {/* Top Toolbar - Dashboard name and action buttons */}
        <WizardTopToolbar
          dashboardName={wizardState.dashboardName}
          onDashboardNameChange={setWizardDashboardName}
          widgetCount={wizardState.selectedWidgets.length}
          currentStep={wizardState.currentStep}
          onSaveAsTemplate={handleSaveAsTemplate}
          onSaveDashboard={handleSave}
          canSave={canSaveDashboard}
          isSaving={isSaving}
        />

        {/* Step Navigator */}
        <BuilderStepNav
          currentStep={wizardState.currentStep}
          completedSteps={completedSteps}
          onChangeStep={setBuilderStep}
          canProceedToCustomize={canProceedToCustomize}
          canProceedToPreview={canProceedToPreview}
        />

        {/* Step Content */}
        {renderStepContent()}

        {/* Navigation Toolbar */}
        <BuilderToolbar
          currentStep={wizardState.currentStep}
          onBack={handleBack}
          onNext={handleNext}
          onSave={handleSave}
          onCancel={handleCancel}
          canGoBack={wizardState.currentStep !== 'select'}
          canProceed={
            wizardState.currentStep === 'select'
              ? canProceedToCustomize
              : canProceedToPreview
          }
          canSave={canSaveDashboard}
          isSaving={isSaving}
        />
      </BlockStack>

      {toastState.active && (
        <Frame>
          <Toast
            content={toastState.content}
            error={toastState.error}
            onDismiss={() => setToastState((prev) => ({ ...prev, active: false }))}
          />
        </Frame>
      )}
    </Page>
  );
}
