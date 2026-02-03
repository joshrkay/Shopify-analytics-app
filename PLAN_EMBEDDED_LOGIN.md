# Plan: Switch from Hosted Login to Embedded Login

## Executive Summary

Switch Frontegg authentication from **Hosted Login Box** (OAuth redirect to markisight.frontegg.com) to **Embedded Login** (login UI rendered directly on localhost:3000).

**Goal**: Eliminate OAuth redirect complexity causing white screen issue while maintaining zero regressions.

**Effort**: 30 minutes (low-risk, minimal code changes)

---

## Current State Analysis

### Files Using Hosted Login Features

**1. `frontend/src/main.tsx`**
- Line 12: `hostedLoginBox: true` ← **NEEDS CHANGE**
- FronteggProvider configuration

**2. `frontend/src/App.tsx`**
- Line 11: `import { useAuth, useLoginWithRedirect } from '@frontegg/react'` ← **NEEDS CHANGE**
- Line 27: `const loginWithRedirect = useLoginWithRedirect();` ← **NEEDS REMOVAL**
- Line 98: `onClick={() => loginWithRedirect()}` ← **NEEDS CHANGE**
- Line 139-147: Debug screen suggesting login redirect ← **NEEDS UPDATE**
- Current: Uses `useLoginWithRedirect` to trigger external redirect
- New: Will not need redirect hook (login UI embedded)

**3. `frontend/src/hooks/useTokenSync.ts`**
- Line 2: `import { useAuth } from '@frontegg/react'`
- ✅ **NO CHANGE NEEDED** - useAuth works same way in both modes

### Files NOT Affected (Zero Regression)

✅ **Backend**: No changes - still validates same Frontegg JWTs
✅ **Environment variables**: Same credentials, same .env files
✅ **Docker configuration**: No changes needed
✅ **Token storage**: Still uses `jwt_token` in localStorage
✅ **All other frontend components**: No authentication logic changes
✅ **API clients**: Still send same Authorization headers
✅ **Routing**: No changes to route structure

---

## What Changes (Detailed)

### Change 1: main.tsx Configuration

**File**: `frontend/src/main.tsx`
**Line**: 12

**Before (Hosted Login)**:
```typescript
const fronteggConfig = {
  contextOptions: {
    baseUrl: import.meta.env.VITE_FRONTEGG_BASE_URL,
    clientId: import.meta.env.VITE_FRONTEGG_CLIENT_ID,
    tokenStorageKey: 'jwt_token',
  },
  hostedLoginBox: true,  // ← External redirect to Frontegg domain
  authOptions: {
    keepSessionAlive: true,
  },
};
```

**After (Embedded Login)**:
```typescript
const fronteggConfig = {
  contextOptions: {
    baseUrl: import.meta.env.VITE_FRONTEGG_BASE_URL,
    clientId: import.meta.env.VITE_FRONTEGG_CLIENT_ID,
    tokenStorageKey: 'jwt_token',
  },
  hostedLoginBox: false,  // ← Login UI embedded in app
  authOptions: {
    keepSessionAlive: true,
  },
};
```

**Impact**:
- Login form now renders as React component on localhost:3000
- No more external redirects to markisight.frontegg.com
- Frontegg SDK handles UI rendering automatically

---

### Change 2: App.tsx - Remove Redirect Hook

**File**: `frontend/src/App.tsx`

**Step 2a: Update imports (Line 11)**

**Before**:
```typescript
import { useAuth, useLoginWithRedirect } from '@frontegg/react';
```

**After**:
```typescript
import { useAuth } from '@frontegg/react';
// useLoginWithRedirect not needed - Frontegg handles login UI automatically
```

**Step 2b: Remove loginWithRedirect hook (Line 27)**

**Before**:
```typescript
function App() {
  const { isAuthenticated, isLoading, user } = useAuth();
  const loginWithRedirect = useLoginWithRedirect();  // ← REMOVE THIS
```

**After**:
```typescript
function App() {
  const { isAuthenticated, isLoading, user } = useAuth();
  // No redirect hook needed - Frontegg shows login UI when !isAuthenticated
```

**Step 2c: Remove manual redirect button (Line 98-110)**

**Before (Debug Screen)**:
```typescript
<button
  onClick={() => loginWithRedirect()}  // ← REMOVE THIS
  style={{...}}
>
  🔐 Try Login Again
</button>
```

**After**:
```typescript
// No manual login button needed
// Frontegg automatically shows login form when !isAuthenticated
```

**Step 2d: Update debug screen messaging (Lines 139-147)**

**Before**:
```typescript
{!isAuthenticated && !isLoading && (
  <div style={{...}}>
    <h3 style={{ color: '#c62828' }}>❌ Not Authenticated</h3>
    <p>You should be redirected to Frontegg login. If not, click "Try Login Again" above.</p>
  </div>
)}
```

**After**:
```typescript
{!isAuthenticated && !isLoading && (
  <div style={{...}}>
    <h3 style={{ color: '#c62828' }}>❌ Not Authenticated</h3>
    <p>Frontegg login form should appear below. If not, refresh the page.</p>
  </div>
)}
```

---

### Change 3: Remove Debug Screen (Production-Ready)

**File**: `frontend/src/App.tsx`

**Current**: Entire App.tsx is debug screen (temporary)
**After**: Restore clean production version with embedded login support

**New Clean App.tsx**:
```typescript
import { useEffect } from 'react';
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import { AppProvider } from '@shopify/polaris';
import { useAuth } from '@frontegg/react';
import enTranslations from '@shopify/polaris/locales/en.json';
import '@shopify/polaris/build/esm/styles.css';

import { DataHealthProvider } from './contexts/DataHealthContext';
import { AppHeader } from './components/layout/AppHeader';
import { useTokenSync } from './hooks/useTokenSync';
import AdminPlans from './pages/AdminPlans';
import Analytics from './pages/Analytics';
import Paywall from './pages/Paywall';
import InsightsFeed from './pages/InsightsFeed';
import ApprovalsInbox from './pages/ApprovalsInbox';
import WhatsNew from './pages/WhatsNew';

function App() {
  const { isAuthenticated, isLoading } = useAuth();

  // Ensure JWT token is synced to localStorage
  useTokenSync();

  // Show loading state while checking authentication
  if (isLoading) {
    return (
      <AppProvider i18n={enTranslations}>
        <div style={{
          display: 'flex',
          justifyContent: 'center',
          alignItems: 'center',
          height: '100vh'
        }}>
          <p>Loading...</p>
        </div>
      </AppProvider>
    );
  }

  // If not authenticated, Frontegg will show embedded login form automatically
  // We just need to provide a container
  if (!isAuthenticated) {
    return (
      <AppProvider i18n={enTranslations}>
        <div style={{
          display: 'flex',
          justifyContent: 'center',
          alignItems: 'center',
          height: '100vh',
          backgroundColor: '#f4f6f8'
        }}>
          {/* Frontegg's embedded login form will render here automatically */}
          <div style={{ width: '400px' }}>
            {/* The FronteggProvider handles rendering the login form */}
          </div>
        </div>
      </AppProvider>
    );
  }

  // User is authenticated - render the app
  return (
    <AppProvider i18n={enTranslations}>
      <DataHealthProvider>
        <BrowserRouter>
          <AppHeader />
          <Routes>
            <Route path="/admin/plans" element={<AdminPlans />} />
            <Route path="/analytics" element={<Analytics />} />
            <Route path="/paywall" element={<Paywall />} />
            <Route path="/insights" element={<InsightsFeed />} />
            <Route path="/approvals" element={<ApprovalsInbox />} />
            <Route path="/whats-new" element={<WhatsNew />} />
            <Route path="/" element={<Navigate to="/analytics" replace />} />
          </Routes>
        </BrowserRouter>
      </DataHealthProvider>
    </AppProvider>
  );
}

export default App;
```

**Key Points**:
- ✅ No `useLoginWithRedirect` hook
- ✅ No manual login redirect logic
- ✅ Frontegg automatically renders login form when `!isAuthenticated`
- ✅ Clean, simple, production-ready code

---

## What DOESN'T Change (Zero Regression Guarantee)

### Backend (No Changes)
- ✅ `backend/src/platform/tenant_context.py` - JWT validation logic unchanged
- ✅ All API endpoints - Same authentication requirements
- ✅ Token validation - Same Frontegg JWKS validation
- ✅ Middleware - Same tenant context extraction

### Environment Variables (No Changes)
- ✅ `.env` - Same Frontegg credentials
- ✅ `frontend/.env` - Same VITE_ variables
- ✅ `docker-compose.yml` - Same environment configuration

### Token Management (No Changes)
- ✅ JWT tokens still stored in `localStorage.jwt_token`
- ✅ Token refresh logic still works
- ✅ Token sync hook (`useTokenSync`) unchanged
- ✅ API clients still read from same localStorage key

### Routing (No Changes)
- ✅ All app routes remain the same
- ✅ No OAuth callback routes needed (Frontegg handles internally)
- ✅ Navigation structure unchanged

### UI Components (No Changes)
- ✅ AppHeader - unchanged
- ✅ All page components - unchanged
- ✅ All other components - zero modifications

---

## Implementation Steps

### Step 1: Update main.tsx
**File**: `frontend/src/main.tsx`
**Change**: Line 12 - `hostedLoginBox: true` → `hostedLoginBox: false`
**Time**: 10 seconds

### Step 2: Update App.tsx
**File**: `frontend/src/App.tsx`
**Changes**:
- Remove `useLoginWithRedirect` import
- Remove `loginWithRedirect` hook usage
- Remove debug screen (replace with clean production version)
- Add container for embedded login form
**Time**: 5 minutes

### Step 3: Test Locally
**Commands**:
```bash
# Restart frontend container
docker compose restart frontend
sleep 10

# Open browser
open -a "Google Chrome" http://localhost:3000
```

**Expected Behavior**:
1. Page loads at localhost:3000
2. Frontegg login form appears **directly on the page** (no redirect)
3. User enters credentials
4. Login happens in place
5. App loads immediately - no white screen
6. localStorage has `jwt_token`

**Time**: 5 minutes

### Step 4: Verify Zero Regression
**Checklist**:
- [ ] Login form appears on localhost:3000 (no external redirect)
- [ ] User can successfully log in
- [ ] After login, app loads (no white screen)
- [ ] JWT token exists in localStorage: `localStorage.getItem('jwt_token')`
- [ ] Can navigate between pages: /analytics, /insights, etc.
- [ ] API calls include Authorization header
- [ ] Backend logs show successful authentication
- [ ] Logout works (clear localStorage and reload)

**Time**: 5 minutes

### Step 5: Commit Changes
```bash
git add frontend/src/main.tsx frontend/src/App.tsx
git commit -m "feat: Switch to Frontegg embedded login to fix OAuth redirect issue

Changed from hosted login box (external redirect) to embedded login (rendered in-app).

Changes:
- main.tsx: Set hostedLoginBox: false
- App.tsx: Remove useLoginWithRedirect hook (no longer needed)
- App.tsx: Remove debug screen, restore clean production code
- App.tsx: Add container for Frontegg embedded login form

Benefits:
- No OAuth redirect complexity
- Login happens directly on localhost:3000
- Eliminates white screen issue after login
- Simpler debugging
- Same backend, same JWTs, zero regressions

https://claude.ai/code/session_017w65QP3qg5ezeXj3SoxVzG"

git push -u origin claude/fix-docker-compose-version-2ncOV
```

**Time**: 2 minutes

---

## Rollback Plan (If Needed)

If embedded login doesn't work for any reason:

```bash
# Revert to hosted login
git revert HEAD
docker compose restart frontend
```

**Time to rollback**: 1 minute

---

## Testing Checklist

### Functional Testing
- [ ] **Login Flow**: Login form appears embedded on page
- [ ] **Authentication**: Successful login loads app
- [ ] **Token Storage**: JWT token in localStorage
- [ ] **Authorization**: API calls have Authorization header
- [ ] **Navigation**: All routes accessible after login
- [ ] **Logout**: Clears token and shows login form again

### Regression Testing
- [ ] **Backend API**: All endpoints still work
- [ ] **Token Validation**: Backend validates tokens correctly
- [ ] **Tenant Context**: Proper tenant_id extracted from JWT
- [ ] **CORS**: No CORS errors
- [ ] **Session Persistence**: Tokens persist across page reloads

### Browser Compatibility
- [ ] **Chrome**: Works correctly
- [ ] **Safari**: Works correctly
- [ ] **Firefox**: Works correctly (optional)

---

## Risk Assessment

### Low Risk Changes ✅

**1. Configuration Change (main.tsx)**
- Single boolean flag: `hostedLoginBox: false`
- Frontegg SDK handles all rendering
- No custom code needed
- **Risk**: Very Low

**2. Remove Unused Code (App.tsx)**
- Removing `useLoginWithRedirect` hook
- Hook is no longer needed with embedded login
- Clean removal, no side effects
- **Risk**: Very Low

**3. UI Simplification (App.tsx)**
- Replacing debug screen with clean production code
- Simpler code = fewer bugs
- **Risk**: Very Low

### No Risk (Unchanged) ✅

- Backend authentication logic
- JWT validation
- Token storage mechanism
- API client configuration
- All other frontend components
- Environment variables
- Docker configuration

---

## Success Criteria

### Must Have ✅
1. Login form appears on localhost:3000 (not external redirect)
2. User can successfully authenticate
3. After login, app loads without white screen
4. JWT token stored in localStorage
5. All API calls include valid Authorization header
6. Backend validates tokens successfully

### Nice to Have 🌟
1. Login UI looks polished (Frontegg provides this automatically)
2. Smooth transition between login and app
3. Clear error messages if login fails

---

## Timeline

| Task | Time | Cumulative |
|------|------|------------|
| Update main.tsx | 10 sec | 10 sec |
| Update App.tsx | 5 min | 5 min 10 sec |
| Restart Docker | 30 sec | 5 min 40 sec |
| Test login flow | 5 min | 10 min 40 sec |
| Verify zero regression | 5 min | 15 min 40 sec |
| Commit and push | 2 min | 17 min 40 sec |
| **Total** | **~18 minutes** | |

**Buffer for issues**: Add 10 minutes → **~30 minutes total**

---

## Summary of Changes

### Files Modified: 2
1. `frontend/src/main.tsx` - 1 line change
2. `frontend/src/App.tsx` - Complete refactor (remove debug, add clean production code)

### Files Unchanged: Everything Else
- Backend: 0 changes
- Environment: 0 changes
- Docker: 0 changes
- Other frontend files: 0 changes

### Lines of Code Changed: ~150
- Removed: ~130 lines (debug screen)
- Added: ~50 lines (clean production code)
- Modified: 1 line (hostedLoginBox flag)
- Net: -80 lines (simpler code!)

---

## Next Steps

**Ready to proceed?**

1. I'll make the changes to both files
2. You restart Docker and test
3. If it works, we commit and move on
4. If it doesn't, we can rollback instantly

**Estimated time to working authentication**: 18-30 minutes

---

**Status**: Plan complete. Ready for implementation on user approval.
