# Debug Routes Security Runbook

## Overview

Debug routes expose operational diagnostics (environment variable configuration state, JWT/JWKS checks).  
Because these responses can disclose sensitive deployment metadata, debug routes are **disabled by default** and protected behind strict controls.

## Security Controls

Debug routes are only reachable when **all** of the following are true:

1. `DEBUG_ROUTES_ENABLED=true` (feature flag, default is `false`)
2. Caller is authenticated
3. Caller has `admin:system:config` permission

If the feature flag is not enabled, `/debug/*` returns `404 Not Found`.

## Default Configuration

Set this in all environments (local/dev/staging/prod):

```bash
DEBUG_ROUTES_ENABLED=false
```

Render and local Docker configuration should keep this value false by default.

## Temporary Enablement Procedure (Break-Glass)

Only enable for short-lived incident debugging:

1. Create an incident ticket with scope and owner.
2. Set `DEBUG_ROUTES_ENABLED=true` in the API environment.
3. Redeploy API service.
4. Access debug routes only with an authenticated admin account.
5. Collect required diagnostics.
6. Immediately set `DEBUG_ROUTES_ENABLED=false`.
7. Redeploy API service and verify `/debug/*` returns 404.
8. Close incident with notes on who accessed endpoints and why.

## Verification Checklist

After disabling:

```bash
curl -i https://<api-host>/debug/env-status
```

Expected: HTTP `404 Not Found`.

When enabled:

- unauthenticated request should return `401`
- authenticated non-admin should return `403`
- authenticated admin can access endpoints

## Do / Do Not

**Do**
- Keep debug routes disabled by default.
- Limit enablement window to the minimum needed.
- Use only admin accounts for access.

**Do Not**
- Leave `DEBUG_ROUTES_ENABLED=true` after incident resolution.
- Share debug output in public channels (contains environment metadata).
- Treat environment hiding (`ENV=production`) as sufficient protection.
