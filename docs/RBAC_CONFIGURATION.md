# Role-Based Access Control (RBAC) & Agency Views

## Overview

This document describes the Role-Based Access Control (RBAC) system for the AI Growth Analytics platform, including support for agency users managing multiple client stores.

## Table of Contents

1. [Role Definitions](#role-definitions)
2. [Permission Matrix](#permission-matrix)
3. [Data Visibility Rules](#data-visibility-rules)
4. [Billing Alignment](#billing-alignment)
5. [Row-Level Security (RLS)](#row-level-security-rls)
6. [JWT Claims Structure](#jwt-claims-structure)
7. [API Endpoints](#api-endpoints)
8. [Security Considerations](#security-considerations)

---

## Role Definitions

### Role Categories

| Category | Scope | Description |
|----------|-------|-------------|
| **Merchant** | Single tenant | Store owners and staff accessing their own store |
| **Agency** | Multi-tenant | Agencies managing multiple client stores |
| **Platform** | Legacy | Backward-compatible platform roles |

### Role Hierarchy

```
SUPER_ADMIN (platform-level, all access)
    │
    ├── MERCHANT_ADMIN (single tenant, full store access)
    │       └── MERCHANT_VIEWER (single tenant, read-only)
    │
    └── AGENCY_ADMIN (multi-tenant, full agency access)
            └── AGENCY_VIEWER (multi-tenant, limited dashboards)
```

### Role Capabilities Matrix

| Role | View Dashboards | Edit Dashboards | Explore Data | Export Data | Multi-Tenant | Manage Users |
|------|-----------------|-----------------|--------------|-------------|--------------|--------------|
| MERCHANT_ADMIN | ✅ | ✅ | ✅ | ❌ | ❌ | ✅ |
| MERCHANT_VIEWER | ✅ | ❌ | ❌ | ❌ | ❌ | ❌ |
| AGENCY_ADMIN | ✅ | ✅ | ✅ | ❌ | ✅ | ❌ |
| AGENCY_VIEWER | ✅ | ❌ | ❌ | ❌ | ✅ | ❌ |
| SUPER_ADMIN | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |

---

## Permission Matrix

### Permission Categories

```python
# Analytics permissions
ANALYTICS_VIEW = "analytics:view"
ANALYTICS_EXPORT = "analytics:export"
ANALYTICS_EXPLORE = "analytics:explore"

# Store permissions
STORE_VIEW = "store:view"
STORE_CREATE = "store:create"
STORE_UPDATE = "store:update"
STORE_DELETE = "store:delete"

# Agency-specific permissions
AGENCY_STORES_VIEW = "agency:stores:view"
AGENCY_STORES_SWITCH = "agency:stores:switch"
AGENCY_REPORTS_VIEW = "agency:reports:view"
MULTI_TENANT_ACCESS = "multi_tenant:access"
```

### Role to Permission Mapping

#### MERCHANT_ADMIN
```python
frozenset([
    Permission.ANALYTICS_VIEW,
    Permission.ANALYTICS_EXPLORE,
    Permission.STORE_VIEW,
    Permission.STORE_UPDATE,
    Permission.BILLING_VIEW,
    Permission.BILLING_MANAGE,
    Permission.TEAM_VIEW,
    Permission.TEAM_MANAGE,
    Permission.TEAM_INVITE,
    Permission.AI_INSIGHTS_VIEW,
    Permission.AI_ACTIONS_EXECUTE,
    Permission.AI_CONFIG_MANAGE,
    Permission.AUTOMATION_VIEW,
    Permission.AUTOMATION_CREATE,
    Permission.AUTOMATION_APPROVE,
    Permission.AUTOMATION_EXECUTE,
    Permission.SETTINGS_VIEW,
    Permission.SETTINGS_MANAGE,
])
```

#### MERCHANT_VIEWER
```python
frozenset([
    Permission.ANALYTICS_VIEW,
    Permission.STORE_VIEW,
    Permission.BILLING_VIEW,
    Permission.TEAM_VIEW,
    Permission.AI_INSIGHTS_VIEW,
    Permission.AUTOMATION_VIEW,
    Permission.SETTINGS_VIEW,
])
```

#### AGENCY_ADMIN
```python
frozenset([
    Permission.ANALYTICS_VIEW,
    Permission.ANALYTICS_EXPLORE,
    Permission.STORE_VIEW,
    Permission.TEAM_VIEW,
    Permission.AI_INSIGHTS_VIEW,
    Permission.AUTOMATION_VIEW,
    Permission.SETTINGS_VIEW,
    # Agency-specific
    Permission.AGENCY_STORES_VIEW,
    Permission.AGENCY_STORES_SWITCH,
    Permission.AGENCY_REPORTS_VIEW,
    Permission.MULTI_TENANT_ACCESS,
])
```

#### AGENCY_VIEWER
```python
frozenset([
    Permission.ANALYTICS_VIEW,
    Permission.STORE_VIEW,
    Permission.AI_INSIGHTS_VIEW,
    Permission.SETTINGS_VIEW,
    # Agency-specific (limited)
    Permission.AGENCY_STORES_VIEW,
    Permission.AGENCY_STORES_SWITCH,
    Permission.MULTI_TENANT_ACCESS,
])
```

---

## Data Visibility Rules

### Merchant Users

- **Scope**: Single `tenant_id` from JWT `org_id` claim
- **RLS Clause**: `tenant_id = '{{ current_user.tenant_id }}'`
- **Access**: Only data belonging to their store

### Agency Users

- **Scope**: List of `tenant_id`s from JWT `allowed_tenants[]` claim
- **RLS Clause**: `tenant_id IN ({{ current_user.allowed_tenants | tojson }})`
- **Access**: Data from all assigned client stores
- **No Wildcard Access**: Explicit tenant list required

### Tenant Mapping Model

```
agency_user_id → [tenant_id_1, tenant_id_2, tenant_id_3]
```

Applied via JWT claim:
```json
{
  "allowed_tenants": ["tenant_001", "tenant_002", "tenant_003"]
}
```

---

## Billing Alignment

### Tier to Role Mapping

| Billing Tier | Allowed Roles | Agency Access |
|--------------|---------------|---------------|
| **Free** | MERCHANT_ADMIN, MERCHANT_VIEWER | ❌ |
| **Growth** | + AGENCY_VIEWER | Limited (5 stores) |
| **Enterprise** | + AGENCY_ADMIN | Full (unlimited) |

### Feature Entitlements by Tier

| Feature | Free | Growth | Enterprise |
|---------|------|--------|------------|
| Agency Access | ❌ | ✅ (limited) | ✅ (full) |
| Multi-Tenant | ❌ | ✅ (5 stores) | ✅ (unlimited) |
| Advanced Dashboards | ❌ | ✅ | ✅ |
| Explore Mode | ❌ | ✅ | ✅ |
| Data Export | ❌ | ❌ | ✅ |

### Billing Events

- **Downgrade**: Access revoked IMMEDIATELY
- **Upgrade**: New roles become available
- **Cancellation**: Downgrade to Free tier

```python
# On billing downgrade
def on_billing_downgrade(user_id, old_tier, new_tier, current_roles):
    revoked_roles = get_revoked_roles(old_tier, new_tier)
    if revoked_roles:
        revoke_user_roles(user_id, revoked_roles)
        log_audit_event("roles_revoked", user_id, revoked_roles)
```

---

## Row-Level Security (RLS)

### RLS Rules by Role Type

#### Merchant Roles
```sql
-- Applied to all fact tables
tenant_id = '{{ current_user.tenant_id }}'
```

#### Agency Roles
```sql
-- Applied to all fact tables
tenant_id IN ({{ current_user.allowed_tenants | tojson }})
```

#### Super Admin
```sql
-- No filtering
1=1
```

### Protected Tables

- `fact_orders`
- `fact_marketing_spend`
- `fact_campaign_performance`
- `dim_products`
- `dim_customers`
- `fact_inventory`

### RLS Validation

```sql
-- Run as logged-in user to validate RLS
-- Expected result: 0 rows
SELECT COUNT(*) as unauthorized_rows
FROM fact_orders
WHERE tenant_id NOT IN ({{ current_user.allowed_tenants | tojson }});
```

---

## JWT Claims Structure

### Merchant User JWT
```json
{
  "sub": "user_123",
  "org_id": "tenant_456",
  "tenant_id": "tenant_456",
  "roles": ["merchant_admin"],
  "billing_tier": "growth",
  "iat": 1710000000,
  "exp": 1710003600
}
```

### Agency User JWT
```json
{
  "sub": "user_789",
  "org_id": "agency_org_001",
  "tenant_id": "tenant_456",
  "active_tenant_id": "tenant_456",
  "roles": ["agency_admin"],
  "allowed_tenants": ["tenant_456", "tenant_457", "tenant_458"],
  "billing_tier": "enterprise",
  "iat": 1710000000,
  "exp": 1710003600
}
```

### Key Claims

| Claim | Description |
|-------|-------------|
| `org_id` | User's organization (agency or merchant) |
| `tenant_id` | Currently active tenant for data access |
| `active_tenant_id` | Same as tenant_id, explicit for clarity |
| `allowed_tenants` | List of accessible tenant IDs (agency only) |
| `roles` | User's assigned roles |
| `billing_tier` | Current billing plan |

---

## API Endpoints

### Agency Store Management

#### List Assigned Stores
```
GET /api/v1/agency/stores

Response:
{
  "stores": [
    {
      "tenant_id": "tenant_456",
      "store_name": "Client Store A",
      "shop_domain": "store-a.myshopify.com",
      "status": "active"
    }
  ],
  "total_count": 3,
  "active_tenant_id": "tenant_456",
  "max_stores_allowed": 5
}
```

#### Switch Active Store
```
POST /api/v1/agency/stores/switch
{
  "tenant_id": "tenant_457"
}

Response:
{
  "success": true,
  "jwt_token": "new_jwt_token_with_updated_context",
  "active_tenant_id": "tenant_457",
  "store": { ... }
}
```

#### Check Store Access
```
GET /api/v1/agency/stores/{tenant_id}/access

Response:
{
  "has_access": true
}
```

#### Get User Context
```
GET /api/v1/agency/me

Response:
{
  "user_id": "user_789",
  "tenant_id": "tenant_456",
  "roles": ["agency_admin"],
  "allowed_tenants": ["tenant_456", "tenant_457"],
  "is_agency_user": true
}
```

---

## Security Considerations

### Critical Security Requirements

1. **Tenant Isolation**
   - `tenant_id` is ALWAYS extracted from JWT, NEVER from request body/query
   - All database queries are scoped by tenant_id
   - RLS is the last line of defense

2. **No Wildcard Access**
   - Agency users have explicit `allowed_tenants[]` list
   - Empty list = no access
   - No `*` or `ALL` patterns

3. **Server-Side Enforcement**
   - All permission checks are server-side
   - UI gating is UX only, NOT security
   - Decorators: `@require_permission()`, `@require_role()`

4. **Immediate Revocation**
   - On billing downgrade, access is revoked immediately
   - No grace period for security-sensitive features
   - Audit log for all revocations

### Validation Checklist

- [ ] Agency user can only see assigned stores
- [ ] Unauthorized tenant access returns 403
- [ ] Billing downgrade removes agency access
- [ ] RLS prevents cross-tenant data leakage
- [ ] JWT claims are properly validated
- [ ] Store switch generates new JWT token

### Audit Events

| Event | Description |
|-------|-------------|
| `agency.store.switch` | User switched active store |
| `agency.access.denied` | Unauthorized access attempt |
| `billing.downgrade` | Billing tier downgraded |
| `roles.revoked` | Roles removed due to downgrade |

---

## Implementation Files

| File | Purpose |
|------|---------|
| `backend/src/constants/permissions.py` | Role and permission definitions |
| `backend/src/platform/tenant_context.py` | JWT parsing and tenant context |
| `backend/src/platform/rbac.py` | RBAC enforcement decorators |
| `backend/src/services/billing_entitlements.py` | Billing tier integration |
| `backend/src/api/routes/agency.py` | Agency API endpoints |
| `docker/superset/rls_rules.py` | Superset RLS configuration |
| `frontend/src/components/AgencyStoreSelector.tsx` | Store selector UI |
| `frontend/src/contexts/AgencyContext.tsx` | Agency state management |

---

## Testing Guide

### Unit Tests

```python
# Test role validation
def test_agency_role_requires_paid_tier():
    assert not is_role_allowed_for_billing_tier("agency_admin", "free")
    assert is_role_allowed_for_billing_tier("agency_admin", "enterprise")

# Test tenant access
def test_agency_user_can_access_allowed_tenant():
    ctx = TenantContext(
        tenant_id="tenant_001",
        user_id="user_001",
        roles=["agency_admin"],
        org_id="org_001",
        allowed_tenants=["tenant_001", "tenant_002"],
    )
    assert ctx.can_access_tenant("tenant_001")
    assert ctx.can_access_tenant("tenant_002")
    assert not ctx.can_access_tenant("tenant_003")
```

### Integration Tests

```python
# Test store switch endpoint
async def test_switch_store_updates_jwt():
    response = await client.post(
        "/api/v1/agency/stores/switch",
        json={"tenant_id": "tenant_002"},
        headers={"Authorization": f"Bearer {agency_jwt}"}
    )
    assert response.status_code == 200
    data = response.json()
    assert data["success"]
    assert data["active_tenant_id"] == "tenant_002"
    assert "jwt_token" in data
```

### Security Tests

```python
# Test unauthorized access is denied
async def test_unauthorized_tenant_access_denied():
    response = await client.post(
        "/api/v1/agency/stores/switch",
        json={"tenant_id": "unauthorized_tenant"},
        headers={"Authorization": f"Bearer {agency_jwt}"}
    )
    assert response.status_code == 403
```
