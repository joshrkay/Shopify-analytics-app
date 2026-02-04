# Implementation Plan: Clerk-Backed Invite and Provisioning Flow

## Overview

This document outlines the implementation plan for a Clerk-backed invite and provisioning flow that allows tenant admins to invite users to their tenants via Clerk's organization invitation system.

**Key Features:**
- Tenant admins can invite users to a tenant
- Platform creates Clerk invitation via Clerk API
- Store pending invite locally with status tracking
- On first authenticated request, detect invite acceptance and provision access
- Prevent duplicate or stale invites
- Comprehensive audit logging

---

## Architecture Summary

### Current Codebase Patterns

Based on exploration of the existing codebase:

| Component | Pattern | Location |
|-----------|---------|----------|
| **Models** | SQLAlchemy ORM with `TimestampMixin` | `backend/src/models/` |
| **Services** | Session-injected classes | `backend/src/services/` |
| **API Routes** | FastAPI routers with Pydantic schemas | `backend/src/api/routes/` |
| **Migrations** | Raw SQL (not Alembic) | `db/migrations/` |
| **Audit Events** | `write_audit_log_sync()` with event registry | `backend/src/platform/audit.py` |
| **Clerk Integration** | Webhook handlers + JWT verification | `backend/src/services/clerk_webhook_handler.py` |
| **Testing** | pytest with fixtures | `backend/src/tests/` |

### Key Existing Components to Integrate With

1. **ClerkSyncService** (`backend/src/services/clerk_sync_service.py`): Syncs users/orgs from Clerk webhooks
2. **ClerkWebhookHandler** (`backend/src/services/clerk_webhook_handler.py`): Routes Clerk events
3. **TenantMembersService** (`backend/src/services/tenant_members_service.py`): Manages tenant access
4. **UserTenantRole** (`backend/src/models/user_tenant_roles.py`): User-tenant-role junction table
5. **AuditLog** (`backend/src/platform/audit.py`): Audit event persistence

---

## Implementation Phases

### Phase 1: Data Model & Migration

#### 1.1 Create TenantInvite Model

**File:** `backend/src/models/tenant_invite.py`

```python
# Model fields:
- id: UUID (primary key)
- clerk_invitation_id: str (unique, from Clerk webhook)
- tenant_id: UUID (FK -> tenants.id)
- email: str (invitee email, indexed)
- role: str (role to assign on acceptance)
- status: Enum (pending, accepted, expired, revoked)
- invited_by: str (clerk_user_id of inviter)
- invited_at: datetime
- expires_at: datetime (default: 30 days)
- accepted_at: datetime (nullable)
- accepted_by_user_id: UUID (FK -> users.id, nullable)
- created_at, updated_at: timestamps
```

**Status Lifecycle:**
```
pending -> accepted (user accepts via Clerk)
pending -> expired (expiration time passes)
pending -> revoked (admin revokes)
```

**Key Methods:**
- `is_expired` -> bool: Check if invite has expired
- `is_actionable` -> bool: Can still be accepted/rejected
- `accept(user_id)`: Transition to accepted
- `mark_expired()`: Transition to expired
- `revoke()`: Transition to revoked

#### 1.2 Database Migration

**File:** `db/migrations/add_tenant_invites.sql`

```sql
-- Create invitation status enum
CREATE TYPE invitation_status AS ENUM ('pending', 'accepted', 'expired', 'revoked');

-- Create tenant_invites table
CREATE TABLE tenant_invites (
    id VARCHAR(255) PRIMARY KEY DEFAULT uuid_generate_v4()::TEXT,
    clerk_invitation_id VARCHAR(255) UNIQUE,
    tenant_id VARCHAR(255) NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    email VARCHAR(255) NOT NULL,
    role VARCHAR(50) NOT NULL DEFAULT 'MERCHANT_VIEWER',
    status invitation_status NOT NULL DEFAULT 'pending',
    invited_by VARCHAR(255),
    invited_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    expires_at TIMESTAMP WITH TIME ZONE NOT NULL,
    accepted_at TIMESTAMP WITH TIME ZONE,
    accepted_by_user_id VARCHAR(255) REFERENCES users(id) ON DELETE SET NULL,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
);

-- Indexes for common queries
CREATE INDEX idx_tenant_invites_tenant_id ON tenant_invites(tenant_id);
CREATE INDEX idx_tenant_invites_email ON tenant_invites(email);
CREATE INDEX idx_tenant_invites_status ON tenant_invites(status);
CREATE INDEX idx_tenant_invites_expires_at ON tenant_invites(expires_at);
CREATE UNIQUE INDEX idx_tenant_invites_tenant_email_pending
    ON tenant_invites(tenant_id, email) WHERE status = 'pending';

-- RLS policy for tenant isolation
ALTER TABLE tenant_invites ENABLE ROW LEVEL SECURITY;
CREATE POLICY tenant_invites_tenant_isolation ON tenant_invites
    USING (tenant_id = current_setting('app.tenant_id', true));
```

---

### Phase 2: Service Layer

#### 2.1 InviteService

**File:** `backend/src/services/invite_service.py`

**Class Structure:**
```python
class InviteService:
    def __init__(self, session: Session, correlation_id: str = None):
        self.session = session
        self.correlation_id = correlation_id or str(uuid.uuid4())

    # Core operations
    def create_invite(tenant_id, email, role, invited_by) -> TenantInvite
    def accept_invite(invite_id, user_id) -> UserTenantRole
    def revoke_invite(invite_id, revoked_by) -> TenantInvite
    def expire_stale_invites() -> int  # For scheduled job

    # Queries
    def get_invite_by_id(invite_id) -> Optional[TenantInvite]
    def get_invite_by_clerk_id(clerk_invitation_id) -> Optional[TenantInvite]
    def get_pending_invite_by_email(tenant_id, email) -> Optional[TenantInvite]
    def list_invites(tenant_id, status=None) -> List[TenantInvite]

    # Validation
    def _validate_no_duplicate_pending(tenant_id, email)
    def _validate_user_not_already_member(tenant_id, email)
    def _validate_invite_actionable(invite)
```

**Key Logic - `create_invite()`:**
1. Validate tenant exists and is active
2. Check no duplicate pending invite exists
3. Check user doesn't already have access
4. Create Clerk invitation via API (optional - or let Clerk handle)
5. Create local TenantInvite record
6. Emit `identity.invite_sent` audit event
7. Return invite

**Key Logic - `accept_invite()`:**
1. Validate invite exists and is actionable
2. Validate invite not expired
3. Get or create User record (lazy sync if needed)
4. Create UserTenantRole with assigned role
5. Update invite status to accepted
6. Emit `identity.invite_accepted` audit event
7. Return role assignment

**Key Logic - `expire_stale_invites()`:**
1. Query all pending invites where expires_at < now()
2. Update status to expired
3. Emit `identity.invite_expired` for each
4. Return count of expired invites

#### 2.2 Clerk API Integration (Optional Enhancement)

**File:** `backend/src/services/clerk_api_client.py`

If we want to proactively create Clerk invitations (not just react to webhooks):

```python
class ClerkAPIClient:
    def __init__(self, api_key: str):
        self.api_key = api_key
        self.base_url = "https://api.clerk.com/v1"

    async def create_organization_invitation(
        self,
        organization_id: str,
        email: str,
        role: str = "org:member",
    ) -> Dict[str, Any]:
        """Create invitation in Clerk."""
        # POST /organizations/{org_id}/invitations
        pass

    async def revoke_organization_invitation(
        self,
        organization_id: str,
        invitation_id: str,
    ) -> None:
        """Revoke invitation in Clerk."""
        # DELETE /organizations/{org_id}/invitations/{inv_id}
        pass
```

---

### Phase 3: Webhook Handlers

#### 3.1 Update ClerkWebhookHandler

**File:** `backend/src/services/clerk_webhook_handler.py`

Add handlers for organization invitation events:

```python
# New event handlers to add:

def handle_organization_invitation_created(self, payload: Dict) -> Dict:
    """
    Event: organizationInvitation.created

    Triggered when invitation created in Clerk (via dashboard or API).
    Creates corresponding TenantInvite record.
    """
    pass

def handle_organization_invitation_accepted(self, payload: Dict) -> Dict:
    """
    Event: organizationInvitation.accepted

    Triggered when user accepts invitation.
    Calls InviteService.accept_invite() to provision access.
    """
    pass

def handle_organization_invitation_revoked(self, payload: Dict) -> Dict:
    """
    Event: organizationInvitation.revoked

    Triggered when invitation revoked in Clerk.
    Updates local invite status.
    """
    pass

# Update event routing in handle_event():
EVENT_HANDLERS = {
    # ... existing handlers ...
    "organizationInvitation.created": handle_organization_invitation_created,
    "organizationInvitation.accepted": handle_organization_invitation_accepted,
    "organizationInvitation.revoked": handle_organization_invitation_revoked,
}
```

**Webhook Payload Structure (Clerk):**
```json
{
  "type": "organizationInvitation.accepted",
  "data": {
    "id": "orginv_xxxxx",
    "organization_id": "org_xxxxx",
    "email_address": "user@example.com",
    "role": "org:member",
    "status": "accepted",
    "created_at": 1234567890,
    "updated_at": 1234567890
  }
}
```

---

### Phase 4: API Routes

#### 4.1 Invitation Routes

**File:** `backend/src/api/routes/invites.py`

```python
router = APIRouter(prefix="/api/tenants/{tenant_id}/invites", tags=["invites"])

# Endpoints:

@router.post("/")
@require_permission(Permission.TEAM_INVITE)
async def create_invite(
    tenant_id: str,
    request: CreateInviteRequest,  # email, role
    auth_context: TenantContext = Depends(get_tenant_context),
) -> InviteResponse:
    """Create invitation for user to join tenant."""
    pass

@router.get("/")
@require_permission(Permission.TEAM_VIEW)
async def list_invites(
    tenant_id: str,
    status: Optional[str] = None,
    auth_context: TenantContext = Depends(get_tenant_context),
) -> InviteListResponse:
    """List invitations for tenant."""
    pass

@router.get("/{invite_id}")
@require_permission(Permission.TEAM_VIEW)
async def get_invite(
    tenant_id: str,
    invite_id: str,
    auth_context: TenantContext = Depends(get_tenant_context),
) -> InviteResponse:
    """Get invitation details."""
    pass

@router.delete("/{invite_id}")
@require_permission(Permission.TEAM_INVITE)
async def revoke_invite(
    tenant_id: str,
    invite_id: str,
    auth_context: TenantContext = Depends(get_tenant_context),
) -> None:
    """Revoke pending invitation."""
    pass
```

#### 4.2 Request/Response Schemas

**File:** `backend/src/api/schemas/invites.py`

```python
class CreateInviteRequest(BaseModel):
    email: EmailStr
    role: str = "MERCHANT_VIEWER"

class InviteResponse(BaseModel):
    id: str
    email: str
    role: str
    status: str  # pending, accepted, expired, revoked
    invited_by: Optional[str]
    invited_at: datetime
    expires_at: datetime
    accepted_at: Optional[datetime]

class InviteListResponse(BaseModel):
    invites: List[InviteResponse]
    total_count: int
```

---

### Phase 5: Audit Events

#### 5.1 Define Audit Event Types

**File:** `backend/src/audit/invite_events.py`

```python
# Audit event definitions for invite lifecycle

INVITE_AUDIT_EVENTS = {
    "identity.invite_sent": {
        "description": "Invitation sent to user",
        "severity": "low",
        "fields": ["invite_id", "tenant_id", "email", "role", "invited_by"],
    },
    "identity.invite_accepted": {
        "description": "User accepted invitation",
        "severity": "medium",
        "fields": ["invite_id", "tenant_id", "email", "role", "user_id"],
    },
    "identity.invite_expired": {
        "description": "Invitation expired without acceptance",
        "severity": "low",
        "fields": ["invite_id", "tenant_id", "email"],
    },
    "identity.invite_revoked": {
        "description": "Admin revoked invitation",
        "severity": "medium",
        "fields": ["invite_id", "tenant_id", "email", "revoked_by"],
    },
}
```

#### 5.2 Emit Events in InviteService

```python
# In InviteService methods:

def _emit_invite_sent(self, invite: TenantInvite):
    write_audit_log_sync(
        session=self.session,
        event_type="identity.invite_sent",
        action=AuditAction.CREATE,
        outcome=AuditOutcome.SUCCESS,
        tenant_id=invite.tenant_id,
        user_id=invite.invited_by,
        correlation_id=self.correlation_id,
        metadata={
            "invite_id": str(invite.id),
            "email": invite.email,
            "role": invite.role,
        }
    )

def _emit_invite_accepted(self, invite: TenantInvite, user_id: str):
    write_audit_log_sync(
        session=self.session,
        event_type="identity.invite_accepted",
        action=AuditAction.UPDATE,
        outcome=AuditOutcome.SUCCESS,
        tenant_id=invite.tenant_id,
        user_id=user_id,
        correlation_id=self.correlation_id,
        metadata={
            "invite_id": str(invite.id),
            "email": invite.email,
            "role": invite.role,
        }
    )

def _emit_invite_expired(self, invite: TenantInvite):
    write_audit_log_sync(
        session=self.session,
        event_type="identity.invite_expired",
        action=AuditAction.UPDATE,
        outcome=AuditOutcome.SUCCESS,
        tenant_id=invite.tenant_id,
        user_id="system",
        correlation_id=self.correlation_id,
        metadata={
            "invite_id": str(invite.id),
            "email": invite.email,
        }
    )
```

---

### Phase 6: First-Request Detection

#### 6.1 Lazy Invite Detection

On first authenticated request, detect if user has pending accepted invite that wasn't processed:

**Update:** `backend/src/services/clerk_sync_service.py`

```python
def get_or_create_user(self, claims: Dict) -> User:
    """
    Called on first authenticated request to sync user.
    Enhanced to also check for pending invite acceptance.
    """
    user = self._sync_user(claims)

    # Check for any pending invites for this email
    self._process_pending_invites(user)

    return user

def _process_pending_invites(self, user: User):
    """
    Check if user has any accepted invites that need provisioning.
    Handles case where webhook was missed.
    """
    from src.services.invite_service import InviteService

    # Query Clerk API for user's organization memberships
    # Compare with local UserTenantRole records
    # If membership exists in Clerk but not locally, check for invite
    # and provision access
    pass
```

---

### Phase 7: Edge Case Handling

#### 7.1 User Exists in Clerk but Not Locally

**Scenario:** User accepts invite in Clerk but hasn't made first request yet.

**Solution:**
- `organizationInvitation.accepted` webhook receives event
- Webhook handler calls `InviteService.accept_invite()`
- `accept_invite()` uses `ClerkSyncService.get_or_create_user()` to lazy-create User
- Role assignment proceeds normally

#### 7.2 Invite Accepted After Expiration

**Scenario:** User accepts in Clerk after local expiration.

**Solution:**
- Store `expires_at` locally but honor Clerk as source of truth for status
- If Clerk sends `accepted` event, trust it and process
- Log warning for audit purposes
- Consider: Keep Clerk and local expiration in sync via API

#### 7.3 Same Email Invited to Multiple Tenants

**Scenario:** User invited to Tenant A and Tenant B.

**Solution:**
- Unique constraint on `(tenant_id, email)` for pending invites only
- User can have pending invites to multiple tenants
- Each acceptance processes independently
- User ends up with UserTenantRole in each tenant

```sql
-- Partial unique index (only for pending)
CREATE UNIQUE INDEX idx_tenant_invites_tenant_email_pending
    ON tenant_invites(tenant_id, email) WHERE status = 'pending';
```

---

### Phase 8: Scheduled Jobs

#### 8.1 Expire Stale Invites Job

**File:** `backend/src/jobs/expire_invites.py`

```python
async def expire_stale_invites_job():
    """
    Scheduled job to expire stale invitations.
    Run every hour via cron or task scheduler.
    """
    session = get_db_session_sync()
    try:
        service = InviteService(session)
        count = service.expire_stale_invites()
        logger.info(f"Expired {count} stale invites")
        session.commit()
    finally:
        session.close()
```

---

### Phase 9: Tests

#### 9.1 Test File Structure

**File:** `backend/src/tests/test_invite_flow.py`

```python
class TestInviteCreation:
    """Test invite creation scenarios."""

    def test_create_invite_success(self, db_session, sample_tenant, admin_user):
        """Successfully create invite."""
        pass

    def test_create_invite_duplicate_pending_fails(self, db_session, sample_tenant):
        """Cannot create duplicate pending invite for same email."""
        pass

    def test_create_invite_user_already_member_fails(self, db_session, sample_tenant, sample_user):
        """Cannot invite user who already has access."""
        pass

class TestInviteAcceptance:
    """Test invite acceptance scenarios."""

    def test_accept_invite_grants_role(self, db_session, sample_tenant, sample_invite):
        """Accepting invite creates UserTenantRole."""
        pass

    def test_accept_expired_invite_fails(self, db_session, expired_invite):
        """Cannot accept expired invite."""
        pass

    def test_accept_invite_lazy_creates_user(self, db_session, sample_tenant, sample_invite):
        """User record created if doesn't exist."""
        pass

class TestInviteExpiration:
    """Test invite expiration scenarios."""

    def test_expire_stale_invites(self, db_session, stale_invites):
        """Stale invites get expired by job."""
        pass

    def test_expired_invite_not_actionable(self, db_session, expired_invite):
        """Expired invite is_actionable returns False."""
        pass

class TestInviteAuditEvents:
    """Test audit event emission."""

    def test_invite_sent_emits_event(self, db_session, sample_tenant):
        """Creating invite emits identity.invite_sent."""
        pass

    def test_invite_accepted_emits_event(self, db_session, sample_invite, sample_user):
        """Accepting invite emits identity.invite_accepted."""
        pass

    def test_invite_expired_emits_event(self, db_session, stale_invites):
        """Expiring invite emits identity.invite_expired."""
        pass

class TestMultiTenantInvites:
    """Test multi-tenant invite scenarios."""

    def test_same_email_multiple_tenants(self, db_session, tenant_a, tenant_b):
        """Same email can be invited to multiple tenants."""
        pass

    def test_accept_one_doesnt_affect_other(self, db_session, invite_a, invite_b):
        """Accepting invite to tenant A doesn't affect invite to tenant B."""
        pass
```

---

## File Generation Summary

| File | Purpose |
|------|---------|
| `backend/src/models/tenant_invite.py` | TenantInvite SQLAlchemy model |
| `backend/src/services/invite_service.py` | Core invite business logic |
| `backend/src/api/routes/invites.py` | REST API endpoints |
| `backend/src/api/schemas/invites.py` | Pydantic request/response models |
| `backend/src/audit/invite_events.py` | Audit event definitions |
| `db/migrations/add_tenant_invites.sql` | Database migration |
| `backend/src/tests/test_invite_flow.py` | Comprehensive test suite |
| `backend/src/jobs/expire_invites.py` | Scheduled expiration job |

---

## Integration Points

### Update Existing Files

1. **`backend/src/services/clerk_webhook_handler.py`**
   - Add invitation event handlers
   - Update event routing

2. **`backend/src/platform/audit_events.py`**
   - Add invite events to registry
   - Add to EVENT_CATEGORIES["identity"]

3. **`backend/src/api/routes/__init__.py`**
   - Include invites router

4. **`backend/src/models/__init__.py`**
   - Export TenantInvite model

5. **`backend/src/constants/permissions.py`**
   - Add `TEAM_INVITE` permission if not exists

---

## Security Considerations

1. **Tenant Isolation**: All queries filter by tenant_id via RLS
2. **Permission Checks**: TEAM_INVITE required for create/revoke
3. **Email Validation**: Pydantic EmailStr validates format
4. **Expiration**: Invites auto-expire after 30 days
5. **Duplicate Prevention**: Unique constraint prevents spam
6. **Audit Trail**: All actions logged for compliance

---

## Rollout Plan

1. **Phase 1**: Deploy migration and model (no user impact)
2. **Phase 2**: Deploy service layer and webhook handlers
3. **Phase 3**: Deploy API routes (feature flag if needed)
4. **Phase 4**: Deploy scheduled job for expiration
5. **Phase 5**: Enable in production, monitor audit logs

---

## Success Metrics

- Invite creation success rate > 99%
- Invite acceptance latency < 500ms
- Zero orphaned invites (all tracked and expired)
- Audit events captured for 100% of invite actions
