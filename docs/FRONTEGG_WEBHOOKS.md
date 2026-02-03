# Frontegg Webhook Configuration Guide

## Overview

Frontegg webhooks enable automatic provisioning and cleanup of tenant resources when users sign up, change status, or delete their accounts.

## When to Configure Webhooks

- **Phase 1 (Current)**: NOT required - Basic authentication works without webhooks
- **Phase 2 (Multi-tenant Airbyte)**: CRITICAL - Webhooks trigger automatic workspace provisioning

## Required Webhook Events

### 1. Tenant Created / Organization Created ⭐ CRITICAL
**Event Name**: `tenant.created` or `organization.created`
**Webhook URL**: `https://your-domain.com/api/webhooks/frontegg/tenant-created`

**Purpose**: Automatically provision Airbyte workspace when new organization signs up

**Payload Example**:
```json
{
  "eventType": "tenant.created",
  "tenantId": "org-123-abc-456",
  "tenantName": "Acme Corporation",
  "timestamp": "2024-01-15T10:30:00Z",
  "metadata": {
    "email": "admin@acme.com",
    "plan": "professional"
  }
}
```

**Backend Handler**: `backend/src/api/routes/frontegg_webhooks.py::handle_tenant_created`

**What It Does**:
1. Creates dedicated Airbyte workspace for the tenant
2. Stores workspace mapping in `tenant_airbyte_workspaces` table
3. (Optional) Provisions default destinations (PostgreSQL, BigQuery, etc.)
4. (Optional) Sends welcome email
5. (Optional) Initializes default settings

**Implementation Status**: 🔴 Not yet implemented (Part 2 of plan)

---

### 2. Tenant Deleted / Organization Deleted ⭐ IMPORTANT
**Event Name**: `tenant.deleted` or `organization.deleted`
**Webhook URL**: `https://your-domain.com/api/webhooks/frontegg/tenant-deleted`

**Purpose**: Clean up tenant resources when organization is deleted

**Payload Example**:
```json
{
  "eventType": "tenant.deleted",
  "tenantId": "org-123-abc-456",
  "tenantName": "Acme Corporation",
  "timestamp": "2024-01-15T14:00:00Z"
}
```

**Backend Handler**: `backend/src/api/routes/frontegg_webhooks.py::handle_tenant_deleted`

**What It Does**:
1. Archives or deletes Airbyte workspace
2. Soft-delete tenant data (or hard delete based on policy)
3. Cancel active syncs
4. Remove OAuth connections
5. Log deletion for audit trail

**Implementation Status**: 🔴 Not yet implemented (Part 2 of plan)

---

### 3. User Activated 🟡 OPTIONAL
**Event Name**: `user.activated`
**Webhook URL**: `https://your-domain.com/api/webhooks/frontegg/user-activated`

**Purpose**: Send welcome email, trigger onboarding flows

**Payload Example**:
```json
{
  "eventType": "user.activated",
  "userId": "user-789-xyz",
  "tenantId": "org-123-abc-456",
  "email": "john@acme.com",
  "timestamp": "2024-01-15T10:35:00Z"
}
```

**What It Does**:
1. Send personalized welcome email
2. Trigger product tour
3. Create initial sample data
4. Assign default role/permissions

**Implementation Status**: 🔴 Not yet implemented

---

### 4. User Deactivated 🟡 OPTIONAL
**Event Name**: `user.deactivated`
**Webhook URL**: `https://your-domain.com/api/webhooks/frontegg/user-deactivated`

**Purpose**: Revoke access, cleanup user-specific resources

**Payload Example**:
```json
{
  "eventType": "user.deactivated",
  "userId": "user-789-xyz",
  "tenantId": "org-123-abc-456",
  "email": "john@acme.com",
  "timestamp": "2024-01-15T15:00:00Z"
}
```

**What It Does**:
1. Revoke API keys
2. Cancel scheduled reports
3. Remove user from Slack/email notifications
4. Log deactivation

**Implementation Status**: 🔴 Not yet implemented

---

### 5. SSO Configuration Changed 🟢 NICE-TO-HAVE
**Event Name**: `sso.configured` or `sso.updated`
**Webhook URL**: `https://your-domain.com/api/webhooks/frontegg/sso-changed`

**Purpose**: Update internal SSO settings, notify admins

**Payload Example**:
```json
{
  "eventType": "sso.configured",
  "tenantId": "org-123-abc-456",
  "ssoProvider": "okta",
  "timestamp": "2024-01-15T11:00:00Z"
}
```

**What It Does**:
1. Update internal SSO configuration
2. Notify tenant admins
3. Log security event

**Implementation Status**: 🔴 Not yet implemented

---

## Webhook Security

### 1. Signature Verification
Frontegg signs all webhook requests. Always verify the signature:

```python
import hmac
import hashlib

def verify_frontegg_signature(payload: bytes, signature: str, secret: str) -> bool:
    """Verify Frontegg webhook signature."""
    expected_signature = hmac.new(
        secret.encode('utf-8'),
        payload,
        hashlib.sha256
    ).hexdigest()

    return hmac.compare_digest(signature, expected_signature)
```

**Implementation**: `backend/src/api/routes/frontegg_webhooks.py`

### 2. Webhook Secret
Store in `.env`:
```bash
FRONTEGG_WEBHOOK_SECRET=<your-webhook-secret-from-frontegg-dashboard>
```

Get from: Frontegg Dashboard → Webhooks → Webhook Secret

---

## Configuration Steps (When Ready for Phase 2)

### 1. In Frontegg Dashboard

1. **Login to Frontegg Portal**: https://portal.frontegg.com
2. **Navigate to Webhooks**:
   - Settings → Webhooks → Add Webhook
3. **Configure Each Webhook**:
   - **Name**: "Tenant Created - Production"
   - **URL**: `https://your-app.com/api/webhooks/frontegg/tenant-created`
   - **Events**: Select `tenant.created`
   - **Active**: ✅ Enabled
   - **Secret**: Copy the generated secret (save to .env)
4. **Test Webhook**:
   - Use Frontegg's "Send Test Event" button
   - Verify your endpoint receives and processes it

### 2. In Your Application

1. **Implement Webhook Endpoints** (from plan):
   - `backend/src/api/routes/frontegg_webhooks.py`
2. **Register Routes** in `backend/main.py`:
   ```python
   from backend.src.api.routes import frontegg_webhooks

   app.include_router(
       frontegg_webhooks.router,
       tags=["webhooks"]
   )
   ```
3. **Add Webhook Secret to .env**:
   ```bash
   FRONTEGG_WEBHOOK_SECRET=<secret-from-dashboard>
   ```
4. **Deploy to Production**:
   - Webhooks require publicly accessible HTTPS endpoint
   - Cannot use localhost (use ngrok for local testing)

---

## Testing Webhooks Locally

### Option 1: ngrok (Recommended)
```bash
# Start ngrok tunnel
ngrok http 8000

# Use ngrok URL in Frontegg webhook config
# Example: https://abc123.ngrok.io/api/webhooks/frontegg/tenant-created
```

### Option 2: Frontegg Test Events
- In Frontegg Dashboard → Webhooks → Select webhook → "Send Test Event"
- Generates sample payload and sends to your endpoint
- Check backend logs to verify receipt

---

## Monitoring and Debugging

### 1. Webhook Delivery Logs
- Frontegg Dashboard → Webhooks → Delivery History
- Shows all webhook attempts, status codes, retries
- Use to debug failed deliveries

### 2. Backend Logging
```python
@router.post("/tenant-created")
async def handle_tenant_created(request: Request):
    """Handle Frontegg tenant creation webhook."""
    logger.info("Received tenant created webhook", extra={
        "headers": dict(request.headers),
        "source_ip": request.client.host
    })

    payload = await request.json()
    logger.info("Webhook payload", extra={"payload": payload})

    # Process webhook...
```

### 3. Webhook Retry Policy
Frontegg automatically retries failed webhooks:
- 1st retry: After 1 minute
- 2nd retry: After 5 minutes
- 3rd retry: After 15 minutes
- Max retries: 3

**Your endpoint should return**:
- `200 OK` - Success, no retry
- `4xx` - Client error, no retry (invalid payload)
- `5xx` - Server error, Frontegg will retry

---

## Current Implementation Status

### Implemented ✅
- None (webhooks not yet needed for Phase 1)

### Planned (Phase 2: Multi-tenant Airbyte) 🔴
1. `POST /api/webhooks/frontegg/tenant-created` - Provision workspace
2. `POST /api/webhooks/frontegg/tenant-deleted` - Cleanup workspace
3. Webhook signature verification middleware
4. Tenant provisioning service
5. Tests for webhook handlers

### Estimated Implementation Time
- Webhook endpoints: 2 hours
- Tenant provisioning service: 3 hours
- Testing and validation: 1 hour
- **Total: ~6 hours** (part of the 12-hour Phase 2 estimate)

---

## Recommendation

**For Now (Phase 1 - Authentication Only)**:
- ✅ **Skip webhook configuration** - Not needed yet
- ✅ **Focus on getting authentication working** - Current priority
- ✅ **Test login/logout manually** - Sufficient for Phase 1

**For Later (Phase 2 - Multi-tenant Airbyte)**:
- ⭐ **Configure `tenant.created` webhook** - CRITICAL for auto-provisioning
- ⭐ **Configure `tenant.deleted` webhook** - IMPORTANT for cleanup
- 🟡 **Consider `user.activated`** - If you want onboarding automation
- 🟢 **Skip others initially** - Add only if specific need arises

**Next Steps**:
1. Get authentication working (current blocker)
2. Test end-to-end login flow
3. Once auth is stable, proceed to Phase 2 (multi-tenant Airbyte)
4. Then configure webhooks for automatic provisioning

---

## Questions?

- **When should I configure webhooks?** - After Phase 1 authentication is working, before Phase 2 multi-tenant Airbyte
- **Can I test webhooks on localhost?** - No, use ngrok or deploy to staging environment
- **What if webhook fails?** - Frontegg retries 3 times, then logs failure in dashboard
- **Do I need all events?** - No, start with `tenant.created` only, add others as needed

---

**Documentation Updated**: 2024-01-15
**Related Plan**: `/home/user/Shopify-analytics-app/PLAN_EMBEDDED_LOGIN.md`
**Implementation Branch**: `claude/fix-docker-compose-version-2ncOV`
