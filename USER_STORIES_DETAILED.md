# Shopify Analytics App - Detailed User Stories for AI Coder

## Project Context

Multi-tenant Shopify embedded SaaS application for analytics and insights.

### Tech Stack
- **Backend**: FastAPI (Python)
- **Frontend**: React + Shopify Polaris v12
- **Database**: PostgreSQL
- **Queue/Cache**: Redis
- **Routing**: react-router-dom v6
- **Grid**: react-grid-layout
- **Auth**: Clerk

### Existing Components to Reference
- `ShareModal.tsx` - Example of Polaris Modal
- `DeleteDashboardModal.tsx` - Example of confirmation modal
- `useShares.ts` - Example of API hook pattern
- `useDashboardMutations.ts` - Example of mutation patterns

---

## SPRINT 1: Widget Wizard

### Story 1.1: Browse Widget Gallery

**As a** user creating a dashboard,
**I want** to browse a gallery of pre-built widgets,
**so that** I can quickly find relevant analytics for my store.

#### Technical Implementation
- Create `/frontend/src/data/widgetCatalog.ts` with `WIDGET_CATALOG` array
- Create `/frontend/src/components/WidgetGallery.tsx`
- Use Polaris `Card` components for each widget
- Use Polaris `Tabs` for category filtering

#### Widget Catalog Data Structure
```typescript
interface WidgetDefinition {
  id: string;                    // 'roas-overview'
  name: string;                   // 'ROAS Overview'
  description: string;            // 'Track return on ad spend'
  category: WidgetCategory;       // 'roas'
  defaultChartType: ChartType;   // 'kpi'
  defaultSize: WidgetSize;       // 'medium'
  iconName: string;              // 'TrendingUp'
  defaultDataset: string;        // 'canonical_attributed_orders'
  defaultConfig: ChartConfig;    // Default chart settings
}

const WIDGET_CATALOG: WidgetDefinition[] = [
  {
    id: 'roas-overview',
    name: 'ROAS Overview',
    description: 'Track return on ad spend across all marketing channels',
    category: 'roas',
    defaultChartType: 'kpi',
    defaultSize: 'medium',
    iconName: 'TrendingUp',
    defaultDataset: 'canonical_attributed_orders',
    defaultConfig: {
      metrics: [{ column: 'roas', aggregation: 'AVG', label: 'ROAS' }],
      time_range: 'last_30_days',
    },
  },
  // ... 15 more widgets
];
```

#### Widget Categories
| Category ID | Display Name | Icon |
|-------------|--------------|------|
| all | All Reports | LayoutGrid |
| roas | ROAS & ROI | TrendingUp |
| sales | Sales | DollarSign |
| products | Products | ShoppingCart |
| customers | Customers | Users |
| campaigns | Campaigns | Target |

#### Acceptance Criteria
- [ ] Widget gallery displays all 16 widgets from catalog
- [ ] Polaris Tabs component shows 6 category filters
- [ ] Clicking a category filters the widget list
- [ ] Each widget card shows: icon, name, description
- [ ] Hover state indicates clickability
- [ ] Empty state if no widgets in category

---

### Story 1.2: Select Widgets

**As a** user,
**I want** to click to add widgets to my dashboard,
**so that** I can build my custom analytics view.

#### Technical Implementation
- Extend `DashboardBuilderContext` with `selectedWidgets: WidgetSelection[]`
- Add `selectWidget(definition: WidgetDefinition)` action
- Add `removeSelectedWidget(selectionId: string)` action

#### State Extension
```typescript
interface DashboardBuilderState {
  // ... existing state
  wizardStep: 'select' | 'customize' | 'preview' | null;
  selectedCategory: WidgetCategory;
  selectedWidgets: WidgetSelection[];
  isWizardMode: boolean;
}

interface WidgetSelection {
  selectionId: string;    // UUID
  definitionId: string;   // Reference to WidgetDefinition.id
  name: string;           // Can be customized
  size: WidgetSize;      // default from definition
  position?: GridPosition; // Assigned in step 2
}
```

#### Acceptance Criteria
- [ ] Clicking widget adds to selectedWidgets array
- [ ] Selected widgets appear in sidebar (show name + remove button)
- [ ] Selected count badge shows in UI (e.g., "3 selected")
- [ ] Clicking X on selected widget removes it
- [ ] Cannot select same widget twice (or allow duplicates with unique IDs)
- [ ] "Next" button enabled only when ≥1 widget selected

---

### Story 1.3: Customize Widget Layout

**As a** user,
**I want** to resize and position widgets on a grid,
**so that** I can create my preferred dashboard layout.

#### Technical Implementation
- Use `react-grid-layout` for drag/drop
- Implement `updateWidgetSelection(selectionId, updates)` action
- Add size selector (Polaris `ButtonGroup` or `Select`)

#### Widget Sizes
```typescript
const WIDGET_SIZE_TO_GRID = {
  small: { w: 3, h: 2 },    // Quarter width
  medium: { w: 6, h: 3 },   // Half width
  large: { w: 9, h: 4 },    // Three-quarters
  full: { w: 12, h: 4 },    // Full width
};
```

#### Grid Configuration
```typescript
const GRID_CONFIG = {
  cols: 12,
  rowHeight: 30,
  margin: [16, 16],
};
```

#### Acceptance Criteria
- [ ] Selected widgets render on grid
- [ ] Drag handle allows repositioning
- [ ] Resize handle allows changing size
- [ ] Size dropdown (small/medium/large/full) on each widget
- [ ] Position auto-calculates on size change
- [ ] "Back" button returns to Step 1
- [ ] "Next" button enabled only when all widgets have positions

---

### Story 1.4: Preview Dashboard

**As a** user,
**I want** to preview my dashboard before publishing,
**so that** I can verify it looks correct.

#### Technical Implementation
- Create `/frontend/src/components/WizardPreview.tsx`
- Mock data for each widget type
- Polaris `EmptyState` for widgets without data

#### Acceptance Criteria
- [ ] Preview shows all widgets with mock/sample data
- [ ] Dashboard name editable (inline edit)
- [ ] Shows widget titles and chart placeholders
- [ ] "Edit" button returns to Step 2
- [ ] "Back" button returns to Step 2
- [ ] Mobile-responsive preview option

---

### Story 1.5: Publish Dashboard

**As a** user,
**I want** to publish my dashboard to make it live,
**so that** I can start using my analytics.

#### Technical Implementation
- Call `POST /api/v1/dashboards/:id/reports` for each widget
- Implement `publishWizardDashboard()` action in context
- Handle success/error states

#### API Call
```typescript
async function publishWizardDashboard(selection: WidgetSelection, definition: WidgetDefinition) {
  const response = await fetch('/api/v1/reports', {
    method: 'POST',
    body: JSON.stringify({
      dashboard_id: dashboardId,
      name: selection.name,
      chart_type: definition.defaultChartType,
      dataset: definition.defaultDataset,
      config: definition.defaultConfig,
      grid_position: selection.position,
    }),
  });
  return response.json();
}
```

#### Acceptance Criteria
- [ ] "Publish" button triggers API calls
- [ ] Loading state while publishing
- [ ] Success toast on completion
- [ ] Redirect to dashboard view
- [ ] New dashboard appears in list
- [ ] Error handling with retry option

---

## SPRINT 2: Version History

### Story 2.1: View Version Timeline

**As a** user,
**I want** to see a timeline of my dashboard versions,
**so that** I can understand how it changed over time.

#### Technical Implementation
- Create `/frontend/src/components/VersionTimeline.tsx`
- Call `GET /api/v1/dashboards/:id/versions`
- Use Polaris `Card` or `Timeline` component

#### API Response
```typescript
interface DashboardVersion {
  id: string;
  version: number;
  created_at: string;
  created_by: string;
  snapshot: {
    widgets: WidgetSnapshot[];
    name: string;
  };
}
```

#### Acceptance Criteria
- [ ] "Version History" button in dashboard header
- [ ] Modal/panel shows version timeline
- [ ] Each version shows: version number, date, author
- [ ] Most recent version first
- [ ] Click version to view details
- [ ] Close button dismisses panel

---

### Story 2.2: Preview Historical Version

**As a** user,
**I want** to preview a historical version of my dashboard,
**so that** I can see what it looked like in the past.

#### Technical Implementation
- Pass version.snapshot to preview component
- Read-only view (no editing)

#### Acceptance Criteria
- [ ] Clicking version shows preview
- [ ] Preview shows widget configuration
- [ ] Visual badge says "Historical"
- [ ] Cannot edit in preview mode

---

### Story 2.3: Restore Previous Version

**As a** user,
**I want** to restore my dashboard to a previous version,
**so that** I can undo unwanted changes.

#### Technical Implementation
- Call `POST /api/v1/dashboards/:id/restore/{versionId}`
- Create confirmation modal
- Non-destructive: creates new version

#### Acceptance Criteria
- [ ] "Restore" button on each version
- [ ] Confirmation modal: "Restore to version X? This will create a new version."
- [ ] Cancel/Confirm buttons
- [ ] Loading state during restore
- [ ] Success: new version created, current = restored version
- [ ] Toast notification on success

---

## SPRINT 3: Sharing

### Story 3.1: Share Dashboard

**As a** user,
**I want** to share my dashboard with team members,
**so that** they can view my analytics.

#### Technical Implementation
- Enhance existing `/frontend/src/components/ShareModal.tsx`
- Call `POST /api/v1/dashboards/:id/share`

#### API Request
```typescript
interface ShareRequest {
  email: string;
  permission: 'view' | 'edit' | 'admin';
}
```

#### Acceptance Criteria
- [ ] "Share" button in dashboard header
- [ ] Modal with email input
- [ ] Permission dropdown (View/Edit/Admin)
- [ ] "Add" button shares dashboard
- [ ] Success toast on share
- [ ] Error handling for invalid email

---

### Story 3.2: Manage Shared Access

**As a** user,
**I want** to see who has access to my dashboard,
**so that** I can manage permissions.

#### Technical Implementation
- Call `GET /api/v1/dashboards/:id/share`
- Display in share modal list

#### API Response
```typescript
interface DashboardShare {
  id: string;
  user_id: string;
  email: string;
  permission: 'view' | 'edit' | 'admin';
  created_at: string;
}
```

#### Acceptance Criteria
- [ ] List shows all shared users
- [ ] Each row shows: email, permission, access date
- [ ] Dropdown to change permission
- [ ] "Remove" button to revoke access
- [ ] Confirm before removing

---

### Story 3.3: View Shared Dashboard

**As a** shared user,
**I want** to view dashboards shared with me,
**so that** I can see team analytics.

**Note:** Automatically handled by existing auth - shared dashboards appear in dashboard list.

---

## SPRINT 4: Audit Trail

### Story 4.1: View Audit History

**As a** user,
**I want** to see a history of all changes to my dashboard,
**so that** I can track who made changes and when.

#### Technical Implementation
- Create `/frontend/src/components/AuditTrail.tsx`
- Call `GET /api/v1/dashboards/:id/audit`

#### API Response
```typescript
interface AuditEntry {
  id: string;
  action: 'create' | 'update' | 'delete' | 'restore' | 'share_grant' | 'share_revoke';
  user_id: string;
  user_email: string;
  timestamp: string;
  details: Record<string, any>;
}
```

#### Acceptance Criteria
- [ ] "Audit Trail" in dashboard settings
- [ ] List shows all audit entries
- [ ] Each entry shows: action icon, user, timestamp
- [ ] Action types have visual indicators
- [ ] Expandable details for complex actions

---

## Component File Structure

```
frontend/src/
├── components/
│   ├── widgets/
│   │   ├── WidgetGallery.tsx       [NEW]
│   │   ├── WidgetCard.tsx         [NEW]
│   │   ├── WidgetSidebar.tsx       [NEW]
│   │   └── WizardPreview.tsx      [NEW]
│   ├── dashboard/
│   │   ├── VersionTimeline.tsx     [NEW]
│   │   ├── VersionPreview.tsx      [NEW]
│   │   ├── RestoreConfirmModal.tsx [NEW]
│   │   ├── ShareDashboardModal.tsx [ENHANCE]
│   │   └── AuditTrail.tsx          [NEW]
│   └── shared/
│       ├── SizeSelector.tsx        [NEW]
│       └── GridWidget.tsx           [NEW]
├── contexts/
│   └── DashboardBuilderContext.tsx  [MODIFY]
├── types/
│   └── customDashboards.ts         [MODIFY]
├── data/
│   └── widgetCatalog.ts           [NEW]
├── hooks/
│   ├── useDashboardVersions.ts     [NEW]
│   └── useDashboardAudit.ts       [NEW]
└── api/
    └── dashboardVersionsApi.ts    [NEW]
```

---

## API Endpoints (Already Exist)

### Versioning
- `GET /api/v1/dashboards/:id/versions` - List versions
- `GET /api/v1/dashboards/:id/versions/:versionId` - Get version
- `POST /api/v1/dashboards/:id/restore/:versionId` - Restore

### Sharing
- `GET /api/v1/dashboards/:id/share` - Get shares
- `POST /api/v1/dashboards/:id/share` - Create share
- `PUT /api/v1/dashboards/:id/share/:userId` - Update share
- `DELETE /api/v1/dashboards/:id/share/:userId` - Revoke share

### Audit
- `GET /api/v1/dashboards/:id/audit` - Get audit entries

### Reports (for wizard)
- `POST /api/v1/reports` - Create report (widget)
- `GET /api/v1/reports/:id` - Get report
- `PUT /api/v1/reports/:id` - Update report
- `DELETE /api/v1/reports/:id` - Delete report

---

## Testing Checklist

### Widget Wizard
- [ ] Can browse all 16 widgets
- [ ] Can filter by each category
- [ ] Can select multiple widgets
- [ ] Can remove selected widgets
- [ ] Can resize widgets (4 sizes)
- [ ] Can drag to reposition
- [ ] Can preview dashboard
- [ ] Can edit dashboard name
- [ ] Can publish successfully
- [ ] Error handling works

### Version History
- [ ] Timeline displays all versions
- [ ] Can preview historical version
- [ ] Can restore to previous version
- [ ] Restore creates new version (non-destructive)

### Sharing
- [ ] Can share with new user
- [ ] Can change permission level
- [ ] Can revoke access
- [ ] Shared user sees dashboard

### Audit Trail
- [ ] Shows all dashboard changes
- [ ] Shows user for each action
- [ ] Shows timestamp for each action

---

## Edge Cases to Handle

1. **Wizard exit with unsaved changes** - Show confirmation
2. **Network error during publish** - Retry button, preserve state
3. **Duplicate widget selection** - Allow or prevent (decision needed)
4. **Empty dashboard publish** - Prevent with validation
5. **Restore to current version** - Show "Already current" message
6. **Share with existing user** - Show "Already shared" message
7. **Revoke own access** - Prevent last admin from removing themselves

---

## Design Patterns to Follow

### From Existing Code
- Use Polaris components (`Modal`, `Card`, `Button`, `Banner`)
- Error handling with `Banner tone="critical"`
- Loading states with `Spinner`
- Form validation with error messages
- API hooks pattern from `useShares.ts`

### State Management
- Local `useState` in components
- Context for wizard state
- No Redux/Zustand needed

### Error Handling
```typescript
try {
  await publishWizardDashboard();
} catch (error) {
  // Show error banner
  // Allow retry
}
```
