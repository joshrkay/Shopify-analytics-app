# Webhook Testing Guide — Markinsight

**Purpose:** Document webhook implementation status and provide manual testing instructions.
**Generated:** February 8, 2026

---

## Code Review Summary

### HMAC Verification ✅ VERIFIED
The webhook handler at `backend/src/api/routes/webhooks_shopify.py` properly implements HMAC signature verification:
- Uses `hmac.compare_digest()` for constant-time comparison (prevents timing attacks)
- Validates `X-Shopify-Hmac-Sha256` header on all webhook endpoints
- Uses `SHOPIFY_API_SECRET` environment variable for signing key
- Returns 401 Unauthorized for invalid signatures

### GDPR Mandatory Webhooks ✅ IMPLEMENTED

| Webhook | Endpoint | Status | Notes |
|---------|----------|--------|-------|
| `customers/redact` | `/api/webhooks/shopify/customers-redact` | ✅ | Acknowledges request; app stores no customer PII |
| `shop/redact` | `/api/webhooks/shopify/shop-redact` | ✅ | Deletes all store data (usage records, billing events, subscriptions, store record) |
| `customers/data_request` | `/api/webhooks/shopify/customers-data-request` | ✅ | Acknowledges request; no customer data to export |

### App Lifecycle Webhooks ✅ IMPLEMENTED

| Webhook | Endpoint | Status | Notes |
|---------|----------|--------|-------|
| `app/uninstalled` | `/api/webhooks/shopify/app-uninstalled` | ✅ | Marks store as uninstalled, clears access token, cancels active subscriptions |
| `app_subscriptions/update` | `/api/webhooks/shopify/subscription-update` | ✅ | Handles ACTIVE, CANCELLED, FROZEN, DECLINED statuses |

---

## Manual Testing Instructions

### Prerequisites
1. **Shopify CLI** installed: `npm install -g @shopify/cli`
2. **App installed** on a development store
3. **Backend service running** on Render (may need to wake from sleep on Free tier)

### Wake Up Render Service
The Free tier service sleeps after 15 minutes of inactivity. To wake it:
```bash
# Visit the app URL in browser or curl the health endpoint
curl https://shopify-analytics-app-pmsl.onrender.com/health
# Wait up to 50 seconds for cold start
```

### Test GDPR Webhooks

```bash
# Navigate to your app directory
cd Shopify-analytics-app

# Test customers/redact webhook
shopify app webhook trigger --topic customers/redact --address https://shopify-analytics-app-pmsl.onrender.com/api/webhooks/shopify/customers-redact

# Test shop/redact webhook (WARNING: This will delete store data!)
# Only test on a development store you can recreate
shopify app webhook trigger --topic shop/redact --address https://shopify-analytics-app-pmsl.onrender.com/api/webhooks/shopify/shop-redact

# Test customers/data_request webhook
shopify app webhook trigger --topic customers/data_request --address https://shopify-analytics-app-pmsl.onrender.com/api/webhooks/shopify/customers-data-request
```

### Test Lifecycle Webhooks

```bash
# Test app/uninstalled webhook
shopify app webhook trigger --topic app/uninstalled --address https://shopify-analytics-app-pmsl.onrender.com/api/webhooks/shopify/app-uninstalled

# Test subscription update webhook
shopify app webhook trigger --topic app_subscriptions/update --address https://shopify-analytics-app-pmsl.onrender.com/api/webhooks/shopify/subscription-update
```

### Alternative: Test with cURL

If Shopify CLI is not available, you can test with curl (requires computing HMAC):

```bash
# Set your API secret
export SHOPIFY_API_SECRET="your_api_secret_here"

# Create test payload
PAYLOAD='{"shop_domain":"test-store.myshopify.com"}'

# Compute HMAC (requires openssl)
HMAC=$(echo -n "$PAYLOAD" | openssl dgst -sha256 -hmac "$SHOPIFY_API_SECRET" -binary | base64)

# Send test webhook
curl -X POST \
  https://shopify-analytics-app-pmsl.onrender.com/api/webhooks/shopify/customers-redact \
  -H "Content-Type: application/json" \
  -H "X-Shopify-Hmac-Sha256: $HMAC" \
  -H "X-Shopify-Shop-Domain: test-store.myshopify.com" \
  -H "X-Shopify-Topic: customers/redact" \
  -d "$PAYLOAD"
```

---

## Expected Responses

### Successful Webhook Processing
```json
{
  "received": true,
  "message": "Webhook processed"
}
```

### HMAC Verification Failure
```json
{
  "detail": "Invalid HMAC signature"
}
```
HTTP Status: 401 Unauthorized

### Missing Headers
```json
{
  "detail": "Missing HMAC signature"
}
```
HTTP Status: 401 Unauthorized

---

## Verification Checklist

### Before Submission to Shopify Review
- [ ] Verify Render service `SHOPIFY_API_SECRET` environment variable is set
- [ ] Test each webhook endpoint with Shopify CLI
- [ ] Verify 200 OK response for valid webhooks
- [ ] Verify 401 response for invalid HMAC
- [ ] Check Render logs for webhook processing entries
- [ ] Confirm shop/redact properly deletes all store data

### Logs to Check
In Render Dashboard → Logs, look for:
```
INFO - Customers redact webhook processed
INFO - Shop data deleted per GDPR request
INFO - Customers data request webhook processed
INFO - App uninstalled webhook received
INFO - Subscription update webhook received
```

---

## Troubleshooting

### Service Not Responding (Timeout)
- Free tier services sleep after 15 minutes
- First request takes 50+ seconds for cold start
- Solution: Upgrade to paid tier or accept cold start delays

### 401 Unauthorized Errors
- Check `SHOPIFY_API_SECRET` is set in Render environment variables
- Verify the secret matches your Shopify Partner Dashboard app secret
- Ensure webhook payload is sent as raw JSON (not form-encoded)

### 503 Service Unavailable
- Check Render deployment status
- Review deployment logs for errors
- Verify Docker container is building successfully

---

## Shopify App Review Requirements

Per Shopify's App Store requirements:
1. **All GDPR webhooks must respond within 5 seconds** — Implemented ✅
2. **Return 200 OK to acknowledge receipt** — Implemented ✅
3. **Handle duplicate webhook deliveries (idempotency)** — Implemented via database lookups ✅
4. **Log webhook processing for audit trail** — Implemented with structured logging ✅
