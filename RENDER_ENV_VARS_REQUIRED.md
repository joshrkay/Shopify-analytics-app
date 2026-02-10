# Required Environment Variables for Render

**Date:** February 9, 2026
**Status:** Action Required

## Root Cause of "Authentication not configured" Error

The app requires `CLERK_FRONTEND_API` environment variable to enable authentication. Without it, all protected endpoints return 503.

---

## ✅ Variables to Add in Render Dashboard

Go to: https://dashboard.render.com/web/srv-d5o0936id0rc73cjtdp0/env

### 1. CLERK_FRONTEND_API (CRITICAL - Missing)
```
Key:   CLERK_FRONTEND_API
Value: welcome-lamb-37.clerk.accounts.dev
```

### 2. CLERK_SECRET_KEY
```
Key:   CLERK_SECRET_KEY
Value: sk_test_zHp3K6w0AciJu0itFGWSZhilNXQwRxJeYBFlhPfLlt
```

### 3. CLERK_ISSUER_URL
```
Key:   CLERK_ISSUER_URL
Value: https://welcome-lamb-37.clerk.accounts.dev
```

### 4. CLERK_PUBLISHABLE_KEY
```
Key:   CLERK_PUBLISHABLE_KEY
Value: pk_test_d2VsY29tZS1sYW1iLTM3LmNsZXJrLmFjY291bnRzLmRldiQ
```

---

## Already Configured (Verify Present)

- `DATABASE_URL` - PostgreSQL connection string
- `SHOPIFY_API_SECRET` - For webhook HMAC verification

---

## After Adding Variables

1. Click "Save Changes" in Render
2. Render will automatically redeploy the service
3. Wait for deployment to complete (~2-3 minutes)
4. Test the app in Shopify Admin

---

## Verification

After deployment, check the logs for:
```
INFO - Clerk authentication configured
INFO - Tenant context middleware ready {"auth_enabled": true}
```

If you still see "auth_configured: false", the variables weren't applied correctly.
