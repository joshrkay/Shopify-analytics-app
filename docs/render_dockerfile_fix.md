# Fixing Render Dockerfile Path Issue

## Problem
Render error: `failed to read dockerfile: open Dockerfile: no such file or directory`

Render is:
1. Checking out wrong branch: `refactor/simplify-dockerfiles` instead of `main`
2. Looking for `Dockerfile` in root instead of `docker/backend.Dockerfile`

## Root Cause
The Render service was likely created manually or from a different branch, not from the `render.yaml` blueprint.

## Solution

### Option 1: Recreate Service from Blueprint (Recommended)

1. **Delete existing services** (if any)
   - Go to Render Dashboard
   - Delete `shopify-analytics-api` service
   - Delete `shopify-analytics-worker` service

2. **Deploy from Blueprint**
   - Go to Render Dashboard
   - Click **New +** → **Blueprint**
   - Connect repository: `joshrkay/Shopify-analytics-app`
   - Select branch: **main** (not refactor/simplify-dockerfiles)
   - Render will detect `render.yaml` automatically
   - Click **Apply** to create all services

3. **Verify Branch**
   - After creating, check service settings
   - Branch should be: `main`
   - Dockerfile path should be: `docker/backend.Dockerfile`

### Option 2: Fix Existing Service Settings

If you want to keep the existing service:

1. **Go to Service Settings**
   - Render Dashboard → Your service → Settings

2. **Update Branch**
   - Scroll to **Build & Deploy**
   - Branch: Change to `main`
   - Save

3. **Update Dockerfile Path**
   - Build Command: Leave empty (uses Dockerfile)
   - Dockerfile Path: `docker/backend.Dockerfile`
   - Docker Context: `.` (root)
   - Save

4. **Manual Deploy**
   - Click **Manual Deploy** → **Deploy latest commit**
   - Should now use correct branch and Dockerfile

### Option 3: Merge Branch to Main

If you want to deploy from the refactor branch:

1. **Merge PR to main**
   ```bash
   git checkout main
   git merge refactor/simplify-dockerfiles
   git push
   ```

2. **Update Render to use main**
   - Service settings → Branch → `main`

## Verify Configuration

After fixing, check:

1. **Service Settings**
   - Branch: `main` ✓
   - Dockerfile Path: `docker/backend.Dockerfile` ✓
   - Docker Context: `.` ✓

2. **Build Logs**
   - Should show: `Checking out commit ... in branch main`
   - Should show: `dockerfilePath: ./docker/backend.Dockerfile`
   - Should NOT show: `open Dockerfile: no such file or directory`

## Current render.yaml Configuration

Your `render.yaml` correctly specifies:
```yaml
dockerfilePath: ./docker/backend.Dockerfile
dockerContext: .
branch: main
```

If Render is not using these settings, the service was created manually.

## Recommended Action

**Delete and recreate from blueprint:**
1. This ensures all services use correct settings
2. All services created at once (API, Worker, DB, Redis, Cron)
3. Proper environment variable linking
4. Health checks configured correctly

## After Fixing

Once fixed:
- Service will deploy from `main` branch
- Dockerfile will be found at `docker/backend.Dockerfile`
- Build will succeed
- Health checks will work at `/health`