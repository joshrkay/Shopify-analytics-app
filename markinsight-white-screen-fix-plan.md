# MarkInsight White Screen Fix Plan

## Root Cause Summary

After auditing the full codebase (`main.tsx`, `App.tsx`, `render.yaml`, `backend/main.py`, `tenant_context.py`, `backend.Dockerfile`, `apiUtils.ts`, `DataHealthContext.tsx`), I've identified **4 blocking issues** that cause the white screen and **3 configuration gaps** that will break the app after sign-in.

---

## Issue 1 (CRITICAL): `VITE_CLERK_PUBLISHABLE_KEY` Not Available at Build Time

**What happens:** `main.tsx` line 9-11 does a hard `throw new Error(...)` if `VITE_CLERK_PUBLISHABLE_KEY` is missing. This fires before React mounts anything, so the user sees a blank white page with zero UI. The error only shows in the browser console.

**Why it's tricky:** Vite inlines `import.meta.env.VITE_*` variables at **build time**, not runtime. Setting the env var in the Render dashboard after the build has already run does nothing. The value must be present when `npm run build` (or `npx vite build`) executes.

**Where to check:**
- Render dashboard → `markinsight-frontend` static site → Environment → is `VITE_CLERK_PUBLISHABLE_KEY` set?
- Render dashboard → `markinsight-api` web service → Environment → is `VITE_CLERK_PUBLISHABLE_KEY` set? (the Docker multi-stage build also needs it as a build arg)

**Fix:**
1. In Render dashboard, set `VITE_CLERK_PUBLISHABLE_KEY` = your Clerk publishable key (starts with `pk_test_` or `pk_live_`) on **both** the frontend static site AND the API service.
2. Trigger a **manual redeploy** of both services so the build runs with the env var present.
3. Verify: open the deployed site, open browser DevTools Console, confirm no "Missing VITE_CLERK_PUBLISHABLE_KEY" error.

---

## Issue 2 (CRITICAL): `VITE_API_URL` Gets Hostname Instead of Full URL

**What happens:** In `render.yaml` line 29-33, `VITE_API_URL` is set using:
```yaml
fromService:
  type: web
  name: markinsight-api
  property: host
```

Render's `host` property returns just the hostname (e.g., `markinsight-api.onrender.com`), **not** a full URL with `https://`. So `VITE_API_URL` becomes `markinsight-api.onrender.com`.

In `apiUtils.ts` line 15:
```ts
export const API_BASE_URL = import.meta.env.VITE_API_URL || '';
```

API calls then go to `markinsight-api.onrender.com/api/health` which the browser interprets as a **relative path**, not a cross-origin URL. Every API call fails silently.

**Fix (two options):**

**Option A — Use the Docker single-service deployment (recommended):**
The `backend.Dockerfile` already builds the frontend and serves it from FastAPI's `/static` directory. In this architecture, the frontend and API share the same origin, so `VITE_API_URL` can be empty (`''`) and all `/api/*` calls work as relative paths. Remove the separate `markinsight-frontend` static site from `render.yaml` entirely and just use the `markinsight-api` service.

**Option B — Keep separate services, fix the URL:**
Change `render.yaml` to hardcode the full API URL or override `VITE_API_URL` manually:
```yaml
- key: VITE_API_URL
  sync: false  # Set manually in Render dashboard as https://markinsight-api.onrender.com
```
Then set `VITE_API_URL=https://markinsight-api.onrender.com` in the Render dashboard and redeploy.

---

## Issue 3 (CRITICAL): `CLERK_FRONTEND_API` Missing from render.yaml

**What happens:** The backend checks for `CLERK_FRONTEND_API` at startup (`main.py` line 77-91). If missing, it sets `app.state.auth_configured = False` and **every protected endpoint returns 503**. The frontend gets 503 errors on all API calls after sign-in, showing either a broken page or no data.

The variable is listed in `.env.example` but is **completely absent** from `render.yaml`'s API service env vars.

**Fix:**
1. Add to `render.yaml` under the API service's `envVars`:
```yaml
- key: CLERK_FRONTEND_API
  sync: false
```
2. In the Render dashboard, set `CLERK_FRONTEND_API` = your Clerk Frontend API domain.
   - Find it in Clerk Dashboard → your app → look at the URL (e.g., `welcome-lamb-37.clerk.accounts.dev`)
   - Based on the publishable key in your `backend/.env` (`pk_test_d2VsY29tZS1sYW1iLTM3...`), the base64 decodes to `welcome-lamb-37.clerk.accounts.dev`
3. Redeploy the API service.

---

## Issue 4 (CRITICAL): `CORS_ORIGINS` Not Configured for Production Domain

**What happens:** `main.py` line 118:
```python
cors_origins = os.getenv("CORS_ORIGINS", "http://localhost:3000").split(",")
```

In production, `CORS_ORIGINS` is not set in `render.yaml`, so it defaults to `http://localhost:3000`. If the frontend is served from a different Render domain (e.g., `https://markinsight-frontend.onrender.com`), the browser blocks every API call with a CORS error. The user sees either a white screen after sign-in or a broken dashboard with no data.

**Fix (depends on architecture choice):**

**If using single-service (Option A from Issue 2):** Frontend and API share the same origin, so CORS isn't an issue for same-origin requests. Still good practice to set it.

**If using separate services (Option B):** Add to `render.yaml` under the API service:
```yaml
- key: CORS_ORIGINS
  sync: false
```
Then set `CORS_ORIGINS=https://markinsight-frontend.onrender.com` in the Render dashboard.

---

## Issue 5 (HIGH): Dual Deployment Architecture Creates Confusion

**What's happening:** The codebase has **two** deployment paths that both serve the frontend:

1. **Static site** (`markinsight-frontend` in render.yaml) — Vite builds the frontend, Render serves the `dist/` folder as a static site.
2. **Docker backend** (`markinsight-api` in render.yaml) — `backend.Dockerfile` has a multi-stage build that builds the frontend AND copies `dist/` into `backend/static/`, where FastAPI serves it via the SPA catch-all route (main.py lines 261-291).

Both exist in `render.yaml` and both deploy. This means:
- Two copies of the frontend are deployed
- They may have different env vars baked in
- Confusing for debugging

**Recommendation:** Pick one and remove the other:
- **Single-service (recommended for simplicity):** Remove `markinsight-frontend` from `render.yaml`. The API service already serves the frontend. API calls work without CORS issues. One service to manage.
- **Separate services (better for scaling):** Keep both, but remove the frontend build stage from `backend.Dockerfile` so the API only serves the API.

---

## Issue 6 (MEDIUM): `DataHealthProvider` Fires API Calls Before Authentication

**What happens:** In `App.tsx`, `DataHealthProvider` wraps everything including `<SignedOut>`. It immediately calls `getCompactHealth()`, `getActiveIncidents()`, and `getMerchantDataHealth()` on mount — before the user is signed in. These all return 403/503 errors.

The provider catches the errors gracefully (doesn't crash), but it creates unnecessary network noise and error logs.

**Fix:** Move `DataHealthProvider` inside `AuthenticatedApp` so it only fetches data after sign-in:
```tsx
function AuthenticatedApp() {
  useClerkToken();
  const { entitlements } = useEntitlements();
  return (
    <DataHealthProvider>
      <AppHeader />
      <Routes>...</Routes>
    </DataHealthProvider>
  );
}
```

---

## Issue 7 (MEDIUM): Error Boundary Doesn't Catch the `throw` in `main.tsx`

**What happens:** The `throw new Error('Missing VITE_CLERK_PUBLISHABLE_KEY')` in `main.tsx` fires **before** React renders the `<ErrorBoundary>` in `App.tsx`. React error boundaries only catch errors during rendering, lifecycle methods, and constructors of the tree below them. A synchronous throw before `createRoot().render()` is never caught.

**Fix:** Replace the hard throw with a fallback UI:
```tsx
const PUBLISHABLE_KEY = import.meta.env.VITE_CLERK_PUBLISHABLE_KEY;

if (!PUBLISHABLE_KEY) {
  const root = document.getElementById('root')!;
  root.innerHTML = '<div style="padding:40px;text-align:center;font-family:sans-serif">'
    + '<h1>Configuration Error</h1>'
    + '<p>Missing VITE_CLERK_PUBLISHABLE_KEY environment variable.</p>'
    + '<p>Please check your deployment configuration.</p></div>';
} else {
  createRoot(document.getElementById('root')!).render(
    <StrictMode>
      <ClerkProvider publishableKey={PUBLISHABLE_KEY} afterSignOutUrl="/">
        <App />
      </ClerkProvider>
    </StrictMode>
  );
}
```

---

## Render Environment Checklist

### markinsight-api (Backend Web Service)

| Variable | Source | Status in render.yaml |
|----------|--------|----------------------|
| `ENV` | `production` (hardcoded) | Present |
| `DATABASE_URL` | Auto from `markinsight-db` | Present |
| `REDIS_URL` | Auto from `markinsight-redis` | Present |
| `CLERK_SECRET_KEY` | Manual (Render dashboard) | Present |
| `CLERK_WEBHOOK_SECRET` | Manual (Render dashboard) | Present |
| `SHOPIFY_API_KEY` | Manual (Render dashboard) | Present |
| `SHOPIFY_API_SECRET` | Manual (Render dashboard) | Present |
| `OPENROUTER_API_KEY` | Manual (Render dashboard) | Present |
| `ENCRYPTION_KEY` | Manual (Render dashboard) | Present |
| `VITE_CLERK_PUBLISHABLE_KEY` | Manual (Render dashboard) | Present |
| **`CLERK_FRONTEND_API`** | **Manual (Render dashboard)** | **MISSING — must add** |
| **`CORS_ORIGINS`** | **Manual (Render dashboard)** | **MISSING — must add** |

### markinsight-frontend (Static Site) — if keeping separate

| Variable | Source | Status in render.yaml |
|----------|--------|----------------------|
| `VITE_API_URL` | From API service `host` | Present but **returns hostname without https://** |
| `VITE_CLERK_PUBLISHABLE_KEY` | Manual (Render dashboard) | Present (sync: false) |

### Values to Set in Render Dashboard

Based on the Clerk publishable key in your `backend/.env` (`pk_test_d2VsY29tZS1sYW1iLTM3...`), your Clerk domain is `welcome-lamb-37.clerk.accounts.dev`.

| Variable | Value |
|----------|-------|
| `CLERK_FRONTEND_API` | `welcome-lamb-37.clerk.accounts.dev` |
| `VITE_CLERK_PUBLISHABLE_KEY` | `pk_test_d2VsY29tZS1sYW1iLTM3LmNsZXJrLmFjY291bnRzLmRldiQ` |
| `CLERK_SECRET_KEY` | (your sk_test_... key from Clerk dashboard) |
| `CORS_ORIGINS` | `https://markinsight-frontend.onrender.com` (or your actual frontend domain) |

---

## Recommended Fix Order

### Step 1: Choose Architecture (5 min)
Decide: single-service (API serves frontend) or separate services. Single-service is simpler and avoids CORS/URL issues entirely.

### Step 2: Fix render.yaml (10 min)
Add the missing `CLERK_FRONTEND_API` and `CORS_ORIGINS` env vars. Fix `VITE_API_URL` if using separate services.

### Step 3: Set Render Dashboard Values (5 min)
Set all `sync: false` variables in the Render dashboard for each service.

### Step 4: Improve Error Handling in main.tsx (5 min)
Replace the hard throw with a visible error message.

### Step 5: Move DataHealthProvider Inside AuthenticatedApp (5 min)
Prevent unauthenticated API calls on page load.

### Step 6: Redeploy (5 min)
Trigger manual redeployment of all services to pick up new env vars at build time.

### Step 7: Verify (10 min)
1. Open the deployed URL
2. Check browser console for errors
3. Sign in through Clerk
4. Verify the analytics dashboard loads with data
5. Check backend logs for any 503 or auth warnings
