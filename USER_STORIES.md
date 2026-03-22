# Shopify Analytics App - User Stories for AI Coder

## Project Context

Multi-tenant Shopify embedded SaaS application for analytics and insights.
- Backend: FastAPI (Python)
- Frontend: React + Shopify Polaris
- Database: PostgreSQL
- Deployment: Render

---

## User Story Format

Each story follows: As a [user], I want [feature], so that [benefit].

---

## SPRINT 1: Widget Wizard

### Story 1.1: Browse Widget Gallery
**As a** user creating a dashboard,
**I want** to browse a gallery of pre-built widgets,
**so that** I can quickly find relevant analytics for my store.

**Acceptance Criteria:**
- [ ] Widget gallery displays all available widgets
- [ ] Widgets are categorized (ROAS, Sales, Products, Customers, Campaigns)
- [ ] User can filter widgets by category
- [ ] Each widget shows name, description, and icon

### Story 1.2: Select Widgets
**As a** user,
**I want** to click to add widgets to my dashboard,
**so that** I can build my custom analytics view.

**Acceptance Criteria:**
- [ ] Clicking a widget adds it to selected widgets
- [ ] Selected widgets appear in sidebar
- [ ] User can see count of selected widgets
- [ ] Clicking selected widget removes it

### Story 1.3: Customize Widget Layout
**As a** user,
**I want** to resize and position widgets on a grid,
**so that** I can create my preferred dashboard layout.

**Acceptance Criteria:**
- [ ] Grid displays selected widgets
- [ ] User can resize widgets (small/medium/large/full)
- [ ] User can drag to reposition widgets
- [ ] Changes reflect in real-time

### Story 1.4: Preview Dashboard
**As a** user,
**I want** to preview my dashboard before publishing,
**so that** I can verify it looks correct.

**Acceptance Criteria:**
- [ ] Preview shows all widgets with mock data
- [ ] User can edit dashboard name
- [ ] Preview matches final output

### Story 1.5: Publish Dashboard
**As a** user,
**I want** to publish my dashboard to make it live,
**so that** I can start using my analytics.

**Acceptance Criteria:**
- [ ] Publish button creates Reports in backend
- [ ] Success message shows after publish
- [ ] User is redirected to dashboard view
- [ ] Dashboard appears in list

---

## SPRINT 2: Version History

### Story 2.1: View Version Timeline
**As a** user,
**I want** to see a timeline of my dashboard versions,
**so that** I can understand how it changed over time.

**Acceptance Criteria:**
- [ ] Timeline shows all historical versions
- [ ] Each version shows date/time and author
- [ ] User can click to view version details

### Story 2.2: Preview Historical Version
**As a** user,
**I want** to preview a historical version of my dashboard,
**so that** I can see what it looked like in the past.

**Acceptance Criteria:**
- [ ] Clicking a version shows preview
- [ ] Preview shows widget configuration
- [ ] Visual distinction from current version

### Story 2.3: Restore Previous Version
**As a** user,
**I want** to restore my dashboard to a previous version,
**so that** I can undo unwanted changes.

**Acceptance Criteria:**
- [ ] Restore button on each version
- [ ] Confirmation modal before restore
- [ ] After restore, dashboard matches selected version
- [ ] New version created (non-destructive)

---

## SPRINT 3: Sharing

### Story 3.1: Share Dashboard
**As a** user,
**I want** to share my dashboard with team members,
**so that** they can view my analytics.

**Acceptance Criteria:**
- [ ] Share button opens share modal
- [ ] User can enter email to share with
- [ ] Share creates access for that user
- [ ] Success confirmation shown

### Story 3.2: Manage Shared Access
**As a** user,
**I want** to see who has access to my dashboard,
**so that** I can manage permissions.

**Acceptance Criteria:**
- [ ] List shows all users with access
- [ ] Each user shows permission level
- [ ] Can revoke access for any user

### Story 3.3: View Shared Dashboard
**As a** shared user,
**I want** to view dashboards shared with me,
**so that** I can see team analytics.

**Automatically handled by existing auth.**

---

## SPRINT 4: Audit Trail

### Story 4.1: View Audit History
**As a** user,
**I want** to see a history of all changes to my dashboard,
**so that** I can track who made changes and when.

**Acceptance Criteria:**
- [ ] List shows all dashboard changes
- [ ] Each entry shows: action, user, timestamp
- [ ] Actions include: create, update, delete, restore, share

---

## Technical Notes

### API Endpoints (Already Exist)
- `GET /api/v1/dashboards/:id/versions` - List versions
- `POST /api/v1/dashboards/:id/restore/{version}` - Restore
- `GET/PUT/DELETE /api/v1/dashboards/:id/share` - Sharing
- `GET /api/v1/dashboards/:id/audit` - Audit trail

### Widget Categories
- ROAS & ROI
- Sales
- Products
- Customers
- Campaigns

### Widget Sizes
- Small: 3x2 grid
- Medium: 6x3 grid
- Large: 9x4 grid
- Full: 12x4 grid
