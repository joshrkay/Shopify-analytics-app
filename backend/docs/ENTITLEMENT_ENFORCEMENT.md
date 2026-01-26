# Entitlement Enforcement Documentation

## Overview

Runtime entitlement enforcement for Shopify embedded SaaS based on billing state and premium categories. This system enforces access control deterministically based on subscription status and endpoint categories.

## Source of Truth

- **billing_state**: Derived locally but reconciled from Shopify (Shopify is authoritative)
- **Entitlements**: Loaded from `config/plans.json` (no hardcoded plan logic)

## Billing States

The system recognizes the following billing states:

- `active`: Subscription is active and paid
- `past_due`: Payment failed but within retry window
- `grace_period`: Payment failed, in 3-day grace period
- `canceled`: Subscription canceled by merchant
- `expired`: Subscription expired (trial ended or payment failed beyond grace)

## Premium Categories

Endpoints are categorized for enforcement:

- `exports`: Data export endpoints (CSV, Excel, API exports)
- `ai`: AI-powered features (insights, recommendations, actions)
- `heavy_recompute`: Resource-intensive operations (attribution, backfills)
- `other`: Non-premium endpoints (always allowed if billing_state allows)

## Enforcement Matrix

| Billing State | Premium Categories | Non-Premium | Notes |
|--------------|-------------------|-------------|-------|
| `active` | ✅ Full access | ✅ Full access | No restrictions |
| `past_due` | ✅ Allowed with warning | ✅ Allowed with warning | Warning headers added |
| `grace_period` | ❌ Blocked | ✅ Read-only | Blocks write/export/ai/heavy recompute |
| `canceled` | ❌ Blocked (until period_end) | ✅ Read-only (until period_end) | Read-only until `current_period_end` |
| `expired` | ❌ Hard block (402) | ✅ Read-only | Premium endpoints return HTTP 402 |

### Detailed Rules

#### Active
- **Full access** to all categories and HTTP methods
- No restrictions

#### Past Due
- **All requests allowed** but with warning headers
- `X-Billing-State: past_due`
- `X-Billing-Action-Required: update_payment`
- Audit event: `entitlement.degraded_access_used`

#### Grace Period
- **READ-ONLY** for non-premium categories
- **Blocked** for premium categories (exports, ai, heavy_recompute)
- Blocks all write methods (POST, PUT, PATCH, DELETE) for non-premium
- `X-Billing-State: grace_period`
- `X-Grace-Period-Remaining: <days>`
- `X-Billing-Action-Required: update_payment`
- Audit event: `entitlement.denied` (premium) or `entitlement.degraded_access_used` (non-premium)

#### Canceled
- **READ-ONLY** for non-premium until `current_period_end`
- **Blocked** for premium categories until `current_period_end`
- After `current_period_end`: same as expired
- `X-Billing-State: canceled`
- `X-Billing-Action-Required: update_payment`
- Audit event: `entitlement.denied` (premium) or `entitlement.degraded_access_used` (non-premium)

#### Expired
- **Hard block** premium endpoints with HTTP 402
- **Read-only** for non-premium categories
- `X-Billing-State: expired`
- `X-Billing-Action-Required: update_payment`
- Response body includes `code: BILLING_EXPIRED`
- Audit event: `entitlement.denied`

## Response Headers

All responses include billing state headers:

- `X-Billing-State`: Current billing state (`active`, `past_due`, `grace_period`, `canceled`, `expired`)
- `X-Grace-Period-Remaining`: Integer days remaining (only if in grace_period)
- `X-Billing-Action-Required`: Action required (`update_payment`, `upgrade`, `contact_support`)

## HTTP 402 Response (Expired)

When a premium endpoint is blocked due to expired subscription:

```json
{
  "error": "entitlement_denied",
  "code": "BILLING_EXPIRED",
  "category": "exports",
  "billing_state": "expired",
  "plan_id": "plan_growth",
  "reason": "Subscription has expired. Premium features require active subscription.",
  "machine_readable": {
    "code": "BILLING_EXPIRED",
    "billing_state": "expired",
    "category": "exports"
  }
}
```

Headers:
- `X-Billing-State: expired`
- `X-Billing-Action-Required: update_payment`

## Usage

### Route Annotation

Use the `@require_category` decorator to mark premium endpoints:

```python
from fastapi import APIRouter, Request
from src.entitlements.middleware import require_category
from src.entitlements.categories import PremiumCategory

router = APIRouter()

@router.get("/api/export")
@require_category(PremiumCategory.EXPORTS)
async def export_data(request: Request):
    """Export endpoint - requires exports category."""
    return {"data": "exported"}
```

### Dependency Injection

Alternatively, use FastAPI dependency:

```python
from fastapi import Depends, Request
from src.entitlements.middleware import require_category_dependency
from src.entitlements.categories import PremiumCategory

@router.post("/api/ai/insight")
async def ai_insight(
    request: Request,
    _: None = Depends(require_category_dependency(PremiumCategory.AI))
):
    """AI endpoint - requires ai category."""
    return {"insight": "generated"}
```

### Automatic Category Inference

If no category is explicitly declared, the middleware attempts to infer from route path:

- `/export`, `/download` → `exports`
- `/ai`, `/insight`, `/recommendation` → `ai`
- `/backfill`, `/attribution`, `/recompute` → `heavy_recompute`
- Other → `other`

**Note**: Explicit category declaration is recommended for clarity.

## Audit Logging

### Entitlement Denied

Emitted when access is denied:

```python
{
  "action": "entitlement.denied",
  "tenant_id": "tenant_123",
  "user_id": "user_456",
  "category": "exports",
  "billing_state": "expired",
  "plan_id": "plan_growth",
  "reason": "Subscription has expired"
}
```

### Degraded Access Used

Emitted when access is allowed but in degraded mode:

```python
{
  "action": "entitlement.degraded_access_used",
  "tenant_id": "tenant_123",
  "user_id": "user_456",
  "category": "other",
  "billing_state": "grace_period",
  "plan_id": "plan_growth",
  "degraded_mode": true
}
```

## Performance

- **Target**: <10ms typical latency
- **Caching**: Config cache (invalidated on state change)
- **Idempotent**: All checks are idempotent (no side effects)

## Implementation Details

### Files

- `entitlements/categories.py`: Category definitions and inference
- `entitlements/policy.py`: Category-based entitlement evaluation
- `entitlements/middleware.py`: FastAPI middleware for enforcement
- `entitlements/errors.py`: Error classes with machine-readable codes
- `entitlements/audit.py`: Audit logging for entitlements

### Policy Evaluation Flow

1. Extract category from route metadata or infer from path
2. Fetch subscription for tenant
3. Determine billing_state from subscription
4. Evaluate category entitlement based on matrix
5. Add response headers
6. Emit audit events
7. Allow or deny request

### Grace Period Calculation

Grace period remaining days calculated as:

```python
if subscription.grace_period_ends_on:
    now = datetime.now(timezone.utc)
    if now <= subscription.grace_period_ends_on:
        delta = subscription.grace_period_ends_on - now
        grace_period_remaining = max(0, delta.days)
```

### Canceled Period End Check

Canceled subscriptions allow read-only access until `current_period_end`:

```python
if subscription.current_period_end:
    now = datetime.now(timezone.utc)
    if now > subscription.current_period_end:
        # Period ended - hard block premium
    else:
        # Still within period - READ-ONLY access
```

## Testing

Comprehensive test suite covers:

- All billing state × category combinations
- Grace period boundary day changes
- Canceled until period_end behavior
- Expired 402 behavior with headers
- Audit log emission on deny and degraded allow

Run tests:

```bash
pytest backend/src/tests/test_entitlement_api_matrix.py -v
```

## Migration Notes

### From Feature-Based to Category-Based

The system supports both feature-based (`@require_feature`) and category-based (`@require_category`) enforcement. For new endpoints, prefer category-based enforcement.

### Backward Compatibility

Existing `@require_feature` decorators continue to work but use the legacy feature-based policy. Consider migrating to category-based enforcement for consistency.

## Troubleshooting

### Common Issues

1. **Missing X-Billing-State header**: Ensure middleware is registered in FastAPI app
2. **Category not enforced**: Verify route has `@require_category` decorator
3. **Grace period not calculated**: Check `subscription.grace_period_ends_on` is set
4. **Audit logs not emitted**: Verify database session is available in middleware

### Debugging

Enable debug logging:

```python
import logging
logging.getLogger("src.entitlements").setLevel(logging.DEBUG)
```

This will log:
- Category inference
- Billing state determination
- Entitlement check results
- Audit event emission
