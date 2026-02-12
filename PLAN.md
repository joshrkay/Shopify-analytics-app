# Implementation Plan: Extend DashboardBuilderContext for Wizard State

## Overview

Extend the DashboardBuilderContext to support a three-step wizard flow for dashboard creation, as shown in the Figma wireframes. The wizard introduces a "widget selection" abstraction layer that allows users to pick pre-configured report templates before committing them as actual Report entities.

## Problem Statement

The current DashboardBuilder works directly with `Report` entities (backend database objects). The wireframe introduces a user-friendly wizard that:
1. Lets users browse and select "widgets" from a categorized gallery
2. Customize the layout of selected widgets
3. Preview the final dashboard before creating actual Report entities

We need to bridge the gap between:
- **Widget** (UI template/blueprint) → User selection → **Report** (backend entity)

## Key Concepts

### Widget vs Report Hierarchy

1. **WidgetDefinition** - Static template/blueprint
   - Describes a pre-configured report type (e.g., "ROAS Overview" KPI)
   - Contains: name, description, category, default chart type, size, icon
   - Similar to a "report template" but lighter weight and UI-focused

2. **WidgetSelection** - User's temporary selection
   - Instance of a WidgetDefinition that the user has selected
   - Has a temporary client-side ID (not persisted until wizard completes)
   - Can have customized position during step 2 (customize layout)

3. **Report** - Backend entity (existing type)
   - Created when wizard completes (step 3 → publish)
   - Persisted in database with full ChartConfig

### Wizard Flow

```
Step 1: Select Reports
├─ Browse widget gallery by category
├─ Click to add widgets to selection
└─ Selected widgets shown in sidebar

Step 2: Customize Layout
├─ Drag/drop selected widgets on grid
├─ Resize widgets (small/medium/large/full)
└─ Remove unwanted widgets

Step 3: Preview & Save
├─ Preview with mock data visualization
├─ Final dashboard name edit
└─ Publish → converts WidgetSelections to Reports
```

## Files to Modify

### 1. `/frontend/src/types/customDashboards.ts`

**Add new types:**

```typescript
// Widget size (maps to GridPosition dimensions)
export type WidgetSize = 'small' | 'medium' | 'large' | 'full';

// Widget category (for gallery filtering)
export type WidgetCategory = 'all' | 'roas' | 'sales' | 'products' | 'customers' | 'campaigns';

// Widget definition (static template)
export interface WidgetDefinition {
  id: string;                    // template ID (e.g., "roas-overview")
  name: string;                  // "ROAS Overview"
  description: string;           // "Track return on ad spend across all channels"
  category: WidgetCategory;      // "roas"
  defaultChartType: ChartType;   // "kpi"
  defaultSize: WidgetSize;       // "medium"
  iconName: string;              // For UI rendering (e.g., "TrendingUp")
  defaultConfig?: Partial<ChartConfig>; // Pre-filled config (optional)
  defaultDataset?: string;       // Default dataset_name
}

// Widget selection (user's selected widget instance)
export interface WidgetSelection {
  selectionId: string;           // Temporary client-side ID (UUID)
  definitionId: string;          // Reference to WidgetDefinition.id
  name: string;                  // Can be customized by user
  size: WidgetSize;              // Can be changed in step 2
  position?: GridPosition;       // Assigned in step 2
}

// Helper to map WidgetSize to GridPosition dimensions
export const WIDGET_SIZE_TO_GRID: Record<WidgetSize, { w: number; h: number }> = {
  small: { w: 3, h: 2 },    // Quarter width
  medium: { w: 6, h: 3 },   // Half width
  large: { w: 9, h: 4 },    // Three-quarters width
  full: { w: 12, h: 4 },    // Full width
};
```

### 2. `/frontend/src/contexts/DashboardBuilderContext.tsx`

**Extend DashboardBuilderState:**

```typescript
interface DashboardBuilderState {
  // ... existing fields ...

  // Wizard state (new)
  wizardStep: 'select' | 'customize' | 'preview' | null; // null = not in wizard mode
  selectedCategory: WidgetCategory;
  selectedWidgets: WidgetSelection[];
  isWizardMode: boolean; // true when creating new dashboard via wizard
}
```

**Extend DashboardBuilderActions:**

```typescript
interface DashboardBuilderActions {
  // ... existing actions ...

  // Wizard actions (new)
  startWizard: (dashboardName?: string) => void;
  exitWizard: (discard?: boolean) => void;
  setWizardStep: (step: 'select' | 'customize' | 'preview') => void;
  setSelectedCategory: (category: WidgetCategory) => void;
  selectWidget: (definition: WidgetDefinition) => void;
  removeSelectedWidget: (selectionId: string) => void;
  updateWidgetSelection: (selectionId: string, updates: Partial<WidgetSelection>) => void;
  publishWizardDashboard: () => Promise<void>; // Converts widgets → reports
}
```

**Implementation details:**

1. **startWizard()**
   - Sets `isWizardMode = true`
   - Sets `wizardStep = 'select'`
   - Initializes `selectedWidgets = []`
   - Optionally creates a draft dashboard or works with in-memory state

2. **selectWidget(definition)**
   - Generates a unique `selectionId` (e.g., `crypto.randomUUID()`)
   - Creates a `WidgetSelection` from the `WidgetDefinition`
   - Adds to `selectedWidgets` array
   - Does NOT create a backend Report yet

3. **setWizardStep(step)**
   - Validates transition (e.g., can't go to 'customize' if no widgets selected)
   - Updates `wizardStep` state

4. **updateWidgetSelection(selectionId, updates)**
   - Used in step 2 to update size or position
   - Updates the matching widget in `selectedWidgets` array

5. **publishWizardDashboard()**
   - Validates all selections have positions
   - Converts each `WidgetSelection` to a `CreateReportRequest`
   - Calls `addReport()` for each widget (creates backend Reports)
   - Exits wizard mode on success

### 3. Widget Catalog (Hardcoded for MVP)

**Create `/frontend/src/data/widgetCatalog.ts`:**

```typescript
import type { WidgetDefinition } from '../types/customDashboards';

export const WIDGET_CATALOG: WidgetDefinition[] = [
  {
    id: 'roas-overview',
    name: 'ROAS Overview',
    description: 'Track return on ad spend across all channels',
    category: 'roas',
    defaultChartType: 'kpi',
    defaultSize: 'medium',
    iconName: 'TrendingUp',
    defaultDataset: 'canonical_attributed_orders',
    defaultConfig: {
      metrics: [{ column: 'roas', aggregation: 'AVG', label: 'ROAS' }],
      dimensions: [],
      time_range: 'last_30_days',
      time_grain: 'P1D',
      filters: [],
      display: { show_legend: false },
    },
  },
  {
    id: 'revenue-chart',
    name: 'Revenue Trend',
    description: 'Daily/weekly revenue visualization',
    category: 'sales',
    defaultChartType: 'line',
    defaultSize: 'large',
    iconName: 'LineChart',
    defaultDataset: 'canonical_shopify_orders',
    defaultConfig: {
      metrics: [{ column: 'total_price', aggregation: 'SUM', label: 'Revenue' }],
      dimensions: ['order_date'],
      time_range: 'last_30_days',
      time_grain: 'P1D',
      filters: [],
      display: { show_legend: true, legend_position: 'bottom' },
    },
  },
  // ... (add remaining 14 widgets from wireframe)
];

export const WIDGET_CATEGORIES = [
  { id: 'all', name: 'All Reports', iconName: 'LayoutGrid' },
  { id: 'roas', name: 'ROAS & ROI', iconName: 'TrendingUp' },
  { id: 'sales', name: 'Sales', iconName: 'DollarSign' },
  { id: 'products', name: 'Products', iconName: 'ShoppingCart' },
  { id: 'customers', name: 'Customers', iconName: 'Users' },
  { id: 'campaigns', name: 'Campaigns', iconName: 'Target' },
];
```

## Implementation Steps

### Phase 1: Type Definitions (30 min)
1. Add `WidgetSize`, `WidgetCategory`, `WidgetDefinition`, `WidgetSelection` to `customDashboards.ts`
2. Add `WIDGET_SIZE_TO_GRID` constant
3. Create `widgetCatalog.ts` with 16 widget definitions (matching wireframe)

### Phase 2: Context State Extension (45 min)
1. Extend `DashboardBuilderState` with wizard fields
2. Update `initialState` to include wizard defaults
3. Add wizard state to context value

### Phase 3: Context Actions (1 hour)
1. Implement `startWizard()`
2. Implement `selectWidget()` with UUID generation
3. Implement `removeSelectedWidget()`
4. Implement `setWizardStep()` with validation
5. Implement `setSelectedCategory()`
6. Implement `updateWidgetSelection()`
7. Implement `publishWizardDashboard()` with widget → report conversion

### Phase 4: Conversion Logic (30 min)
1. Create helper function `convertWidgetToReportRequest(selection, definition, catalog): CreateReportRequest`
2. Handle position assignment (auto-layout algorithm or manual)
3. Merge default config from definition with any customizations

### Phase 5: Testing (30 min)
1. Manual testing of wizard state transitions
2. Verify widget selection/removal
3. Test publishWizardDashboard creates correct reports
4. Verify state cleanup on wizard exit

## Edge Cases & Considerations

### 1. Position Assignment
- **Step 2 (Customize)**: User drags widgets, positions stored in `WidgetSelection.position`
- **Auto-layout option**: If user skips step 2, auto-assign positions using a layout algorithm
  ```typescript
  function autoLayoutWidgets(widgets: WidgetSelection[]): WidgetSelection[] {
    let currentX = 0, currentY = 0;
    return widgets.map(w => {
      const { w: width, h: height } = WIDGET_SIZE_TO_GRID[w.size];
      if (currentX + width > GRID_COLS) {
        currentX = 0;
        currentY += height;
      }
      const position = { x: currentX, y: currentY, w: width, h: height };
      currentX += width;
      return { ...w, position };
    });
  }
  ```

### 2. Duplicate Widget Selection
- Allow users to select the same widget definition multiple times
- Each selection gets a unique `selectionId`
- Example: User adds 3 different KPI widgets for different metrics

### 3. Wizard Exit Confirmation
- If user exits wizard with unsaved widgets, show confirmation modal
- Use `isDirty` check: `selectedWidgets.length > 0`

### 4. Integration with Existing Builder
- **New Dashboard Flow**: User creates dashboard → enters wizard mode
- **Edit Dashboard Flow**: Skip wizard, go directly to DashboardBuilder
- Add a "wizard mode" toggle in the UI to switch between flows

### 5. Widget Catalog Evolution
- **MVP**: Hardcoded in `widgetCatalog.ts`
- **Future**: Backend endpoint `/api/v1/dashboards/widget-templates`
- **Migration**: Extend `ReportTemplate` to support widget metadata

## Success Criteria

- [ ] User can browse widget gallery filtered by category
- [ ] User can select/remove widgets in step 1
- [ ] User can see selected widget count in UI
- [ ] User can proceed to step 2 only if widgets are selected
- [ ] User can customize widget sizes in step 2
- [ ] User can assign positions to widgets (drag/drop)
- [ ] User can preview dashboard in step 3
- [ ] `publishWizardDashboard()` correctly converts widgets to reports
- [ ] All wizard state is properly cleaned up after publish/exit
- [ ] No breaking changes to existing DashboardBuilder flow

## Non-Goals (Out of Scope)

- Actual UI components (this plan focuses on context state only)
- Drag-and-drop implementation (handled by UI layer using `react-grid-layout`)
- Widget template backend API (use hardcoded catalog for now)
- Advanced widget customization (e.g., editing ChartConfig in wizard)
- Template saving ("Save as Template" button shown in wireframe)

## Testing Plan

### Unit Tests (Backend Context Logic)
1. Test `selectWidget()` generates unique IDs
2. Test `removeSelectedWidget()` removes correct widget
3. Test `setWizardStep()` validates transitions
4. Test `publishWizardDashboard()` conversion logic

### Integration Tests (Full Wizard Flow)
1. User completes wizard, reports are created
2. User exits wizard mid-flow, state is cleaned up
3. User selects duplicate widgets, each gets unique ID

### Manual Testing Checklist
- [ ] Browse widgets, filter by category
- [ ] Select 5+ widgets, verify count updates
- [ ] Remove a widget, verify it's removed from selection
- [ ] Proceed through all 3 steps
- [ ] Publish dashboard, verify reports appear in builder
- [ ] Exit wizard without publishing, verify clean state

## Rollout Strategy

1. **PR 1**: Add types and widget catalog (no behavior change)
2. **PR 2**: Extend context with wizard state and actions
3. **PR 3**: UI integration (separate from this plan)

This keeps changes incremental and reviewable.

## Questions for Product/Design

1. Should wizard support editing existing dashboards, or only new dashboard creation?
2. What's the UX for "Save as Template" button shown in step 3 preview?
3. Should widget gallery support search/filtering beyond categories?
4. Should we support bulk widget selection (checkboxes + "Add Selected")?

---

**Estimated Total Implementation Time**: ~3-4 hours
**Complexity**: Medium
**Risk**: Low (isolated to context, no backend changes)
