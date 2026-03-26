# Shopify Analytics App - Code Implementation Guide

## Project Overview

Multi-tenant Shopify embedded SaaS application for analytics and insights.

**Tech Stack:**
- Backend: FastAPI (Python)
- Frontend: React + Shopify Polaris
- Database: PostgreSQL
- Queue/Cache: Redis
- Deployment: Render

---

## Current Status

| Component | Status |
|-----------|--------|
| Backend API | ✅ Complete |
| Database Models | ✅ Complete |
| Frontend Core | ⚠️ Partial |
| Dashboard Builder | ⚠️ In Progress |
| Phase 4 Features | ❌ Not Started |

---

## What Needs to Be Built

### PRIORITY 1: Widget Wizard (Frontend)

The dashboard builder needs a 3-step wizard for creating dashboards.

**Step 1: Select Widgets**
- Browse widget gallery by category (ROAS, Sales, Products, Customers, Campaigns)
- Click to add widgets to selection
- Show selected widgets in sidebar

**Step 2: Customize Layout**
- Drag/drop widgets on grid
- Resize widgets (small/medium/large/full)
- Remove unwanted widgets

**Step 3: Preview & Save**
- Preview with mock data
- Edit dashboard name
- Publish → creates Reports in backend

**Files to modify:**
- `/frontend/src/contexts/DashboardBuilderContext.tsx` - Add wizard state
- `/frontend/src/types/customDashboards.ts` - Add Widget types
- `/frontend/src/data/widgetCatalog.ts` - Create widget definitions

---

### PRIORITY 2: Version History UI

Let users browse version history, preview snapshots, restore previous versions.

**Features:**
- Timeline view of dashboard versions
- Preview historical snapshots
- Restore to previous version with confirmation

**Files to create:**
- `/frontend/src/components/VersionHistory.tsx`
- `/frontend/src/components/VersionTimeline.tsx`
- `/frontend/src/components/RestoreConfirmModal.tsx`

---

### PRIORITY 3: Sharing Controls

Allow users to share dashboards with team members.

**Features:**
- Share dashboard with other users
- View/manage shared access
- Revoke share access

**Already done (backend):**
- `GET/PUT/DELETE /api/v1/dashboards/:id/share`
- `DashboardShareService`

**Files to create:**
- `/frontend/src/components/ShareDashboardModal.tsx` - Enhanced version
- `/frontend/src/hooks/useDashboardShares.ts`

---

### PRIORITY 4: Audit Trail

Track all changes to dashboards.

**Features:**
- View history of all dashboard changes
- Who made changes
- What changed
- When

**Already done (backend):**
- `GET /api/v1/dashboards/:id/audit`
- `DashboardAuditService`

**Files to create:**
- `/frontend/src/components/AuditTrail.tsx`
- `/frontend/src/components/AuditEntryRow.tsx`

---

## Technical Details

### Widget Types (for catalog)

```typescript
type WidgetSize = 'small' | 'medium' | 'large' | 'full';
type WidgetCategory = 'all' | 'roas' | 'sales' | 'products' | 'customers' | 'campaigns';

interface WidgetDefinition {
  id: string;
  name: string;
  description: string;
  category: WidgetCategory;
  defaultChartType: ChartType;
  defaultSize: WidgetSize;
  iconName: string;
  defaultDataset?: string;
  defaultConfig?: Partial<ChartConfig>;
}

interface WidgetSelection {
  selectionId: string;
  definitionId: string;
  name: string;
  size: WidgetSize;
  position?: GridPosition;
}
```

### Wizard State

```typescript
interface DashboardBuilderState {
  // ... existing fields ...
  wizardStep: 'select' | 'customize' | 'preview' | null;
  selectedCategory: WidgetCategory;
  selectedWidgets: WidgetSelection[];
  isWizardMode: boolean;
}
```

---

## File Structure

```
Shopify-analytics-app/
├── frontend/
│   └── src/
│       ├── components/
│       │   ├── VersionHistory.tsx      [NEW]
│       │   ├── VersionTimeline.tsx     [NEW]
│       │   ├── RestoreConfirmModal.tsx [NEW]
│       │   ├── ShareDashboardModal.tsx [ENHANCE]
│       │   └── AuditTrail.tsx          [NEW]
│       ├── contexts/
│       │   └── DashboardBuilderContext.tsx [MODIFY]
│       ├── types/
│       │   └── customDashboards.ts     [MODIFY]
│       ├── data/
│       │   └── widgetCatalog.ts       [NEW]
│       └── hooks/
│           └── useDashboardShares.ts   [NEW/ENHANCE]
```

---

## Implementation Order

### Sprint 1: Widget Wizard
1. Add widget types to customDashboards.ts
2. Create widgetCatalog.ts with 16 widget definitions
3. Extend DashboardBuilderContext with wizard state
4. Implement wizard actions (selectWidget, removeWidget, publish)

### Sprint 2: Version History
1. Create VersionTimeline component
2. Create VersionHistory component
3. Create RestoreConfirmModal
4. Connect to existing API: GET /versions, POST /restore/{version}

### Sprint 3: Sharing & Audit
1. Enhance ShareDashboardModal
2. Create AuditTrail component
3. Connect to existing APIs: share CRUD, audit logs

---

## API Endpoints (Already Exist)

### Dashboard Versioning
- `GET /api/v1/dashboards/:id/versions` - List versions
- `POST /api/v1/dashboards/:id/restore/{version}` - Restore version

### Dashboard Sharing
- `GET /api/v1/dashboards/:id/share` - Get share info
- `POST /api/v1/dashboards/:id/share` - Create share
- `PUT /api/v1/dashboards/:id/share/:userId` - Update share
- `DELETE /api/v1/dashboards/:id/share/:userId` - Revoke share

### Audit Trail
- `GET /api/v1/dashboards/:id/audit` - Get audit entries

---

## Testing Checklist

- [ ] Wizard: Browse widgets, filter by category
- [ ] Wizard: Select/remove widgets
- [ ] Wizard: Customize widget sizes
- [ ] Wizard: Preview and publish
- [ ] Version: View timeline
- [ ] Version: Restore previous version
- [ ] Sharing: Create share
- [ ] Sharing: Revoke share
- [ ] Audit: View history

---

## Estimated Time

| Feature | Time |
|---------|------|
| Widget Wizard | 3-4 hours |
| Version History | 2-3 hours |
| Sharing | 1-2 hours |
| Audit Trail | 1-2 hours |
| **Total** | **~8 hours** |

---

## Ready for Code Implementation

This breakdown is ready to send to an AI coder (Claude Code, Cursor, etc.) to implement the remaining features.
