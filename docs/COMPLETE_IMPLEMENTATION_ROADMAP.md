# Complete Implementation Roadmap
## Building the Shopify Analytics App Correctly

**Last Updated**: 2024-01-15
**Branch**: `claude/fix-docker-compose-version-2ncOV`
**Total Estimated Time**: 14-16 hours over 2-3 days

---

## Overview

This roadmap implements a complete, production-ready multi-tenant Shopify analytics platform with:
- ✅ Frontegg authentication (JWT-based)
- ✅ Per-tenant Airbyte workspace isolation
- ✅ Automatic tenant provisioning via webhooks
- ✅ Row-level security (RLS) for data isolation
- ✅ OAuth integrations (Shopify, Meta Ads, Google Ads)
- ✅ Comprehensive testing
- ✅ Zero regressions

---

## Phase 1: Fix Authentication (CURRENT) - 2 hours

### Status: 🔴 In Progress - Diagnostic screen deployed

### Objective
Get Frontegg embedded login working with JWT token storage.

### Current Blocker
White screen after login - authentication state not persisting.

### Diagnostic Steps (USER ACTION REQUIRED)

**Run these commands on your Mac**:
```bash
# Navigate to project
cd "/Users/joshuakay/Desktop/Shopify analytics app/Shopify-analytics-app"

# Pull latest diagnostic code
git pull origin claude/fix-docker-compose-version-2ncOV

# Restart frontend
docker compose restart frontend

# Wait for restart
sleep 15

# Open browser
open http://localhost:3000
```

**What to look for**:
1. **Diagnostic screen appears** - Shows authentication state in JSON format
2. **Check Environment Variables section**:
   - Should show: `VITE_FRONTEGG_BASE_URL: "https://markisight.frontegg.com"`
   - Should show: `VITE_FRONTEGG_CLIENT_ID: "9b77c0fb-2532-489b-a31c-3ac4ebe7b9d7"`
   - If "MISSING ❌" - .env file not being loaded
3. **Check Authentication State**:
   - `isAuthenticated`: Should change to "YES ✅" after login
   - `isLoading`: Should be "NO" after initial load
   - `hookError`: Should be "NONE" (if error, SDK is broken)
4. **Check localStorage**:
   - Should show `jwt_token: "EXISTS ✅"` after successful login

**Possible Outcomes**:

#### Outcome A: Environment Variables Missing ❌
**Symptoms**: VITE_FRONTEGG_BASE_URL shows "MISSING ❌"
**Fix**: Frontend .env file not being loaded by Docker
**Solution**:
```bash
# Create frontend/.env
cat > frontend/.env << 'EOF'
VITE_FRONTEGG_BASE_URL=https://markisight.frontegg.com
VITE_FRONTEGG_CLIENT_ID=9b77c0fb-2532-489b-a31c-3ac4ebe7b9d7
VITE_API_URL=http://localhost:8000
EOF

# Restart frontend
docker compose restart frontend
```

#### Outcome B: Hook Error ❌
**Symptoms**: hookError shows an error message
**Fix**: Frontegg SDK initialization failing
**Solution**: Check Frontegg credentials in portal, verify SDK version

#### Outcome C: isAuthenticated stays NO after login ❌
**Symptoms**: Can log in, but `isAuthenticated` never becomes YES
**Fix**: Frontegg embedded login not working correctly
**Solution**: Switch to hosted login or debug Frontegg SDK configuration

#### Outcome D: Everything Works ✅
**Symptoms**: `isAuthenticated: "YES ✅"`, `jwt_token: "EXISTS ✅"`
**Next**: Remove diagnostic screen, proceed to Phase 2

### Success Criteria
- ✅ User can log in via Frontegg
- ✅ `isAuthenticated` becomes true after login
- ✅ JWT token stored in localStorage
- ✅ Can navigate to /analytics page
- ✅ No white screen

### Deliverables
1. Working Frontegg authentication
2. JWT tokens stored correctly
3. Clean App.tsx (remove diagnostic code)
4. Git commit: "fix: Resolve Frontegg authentication issue - [description of fix]"

---

## Phase 2: Implement Webhook Infrastructure - 3 hours

### Status: 🔴 Not Started (waiting for Phase 1)

### Objective
Create webhook endpoints for automatic tenant provisioning.

### Tasks

#### Task 2.1: Create Webhook Endpoint File
**File**: `backend/src/api/routes/frontegg_webhooks.py`

```python
"""
Frontegg webhook handlers for tenant lifecycle events.

Handles:
- Tenant creation (auto-provision Airbyte workspace)
- Tenant deletion (cleanup resources)
- User activation/deactivation
"""

import hmac
import hashlib
from fastapi import APIRouter, Request, HTTPException, Depends, status
from sqlalchemy.orm import Session

from backend.src.database import get_db
from backend.src.services.tenant_provisioning import TenantProvisioningService
from backend.src.repositories.tenant_workspaces import TenantWorkspaceRepository
from backend.src.integrations.airbyte.client import AirbyteClient
import os
import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/webhooks/frontegg", tags=["webhooks"])

def verify_webhook_signature(payload: bytes, signature: str) -> bool:
    """Verify Frontegg webhook signature."""
    secret = os.getenv("FRONTEGG_WEBHOOK_SECRET")
    if not secret:
        logger.warning("FRONTEGG_WEBHOOK_SECRET not configured - skipping verification in development")
        return True  # Allow in development without secret

    expected = hmac.new(
        secret.encode('utf-8'),
        payload,
        hashlib.sha256
    ).hexdigest()

    return hmac.compare_digest(signature, expected)


@router.post("/tenant-created")
async def handle_tenant_created(
    request: Request,
    db: Session = Depends(get_db)
):
    """
    Handle Frontegg tenant creation webhook.

    Automatically provisions:
    1. Dedicated Airbyte workspace
    2. Database records for tenant

    Called by Frontegg when:
    - New organization signs up
    - New tenant is created via Frontegg admin

    Expected payload:
    {
        "eventType": "tenant.created",
        "tenantId": "org-123-abc",
        "tenantName": "Acme Corp",
        "metadata": {...}
    }
    """
    # Verify webhook signature
    body = await request.body()
    signature = request.headers.get("x-frontegg-signature", "")

    if not verify_webhook_signature(body, signature):
        logger.error("Invalid webhook signature", extra={
            "source_ip": request.client.host,
            "headers": dict(request.headers)
        })
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid webhook signature"
        )

    # Parse payload
    try:
        payload = await request.json()
    except Exception as e:
        logger.error(f"Failed to parse webhook payload: {e}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid JSON payload"
        )

    # Extract tenant info
    tenant_id = payload.get("tenantId") or payload.get("orgId")
    tenant_name = payload.get("tenantName") or payload.get("name", f"Tenant {tenant_id}")

    if not tenant_id:
        logger.error("Missing tenantId in webhook payload", extra={"payload": payload})
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Missing tenant ID in payload"
        )

    logger.info("Processing tenant creation webhook", extra={
        "tenant_id": tenant_id,
        "tenant_name": tenant_name
    })

    # Initialize services
    airbyte_client = AirbyteClient()
    workspace_repo = TenantWorkspaceRepository(db)
    provisioning_service = TenantProvisioningService(airbyte_client, workspace_repo)

    # Check if already provisioned
    existing = workspace_repo.get_workspace_for_tenant(tenant_id)
    if existing:
        logger.info("Tenant workspace already exists", extra={
            "tenant_id": tenant_id,
            "workspace_id": str(existing.airbyte_workspace_id)
        })
        return {
            "status": "already_exists",
            "tenant_id": tenant_id,
            "workspace_id": str(existing.airbyte_workspace_id)
        }

    # Provision tenant resources
    try:
        result = await provisioning_service.provision_tenant(tenant_id, tenant_name)

        logger.info("Tenant provisioned successfully", extra=result)

        return {
            "status": "success",
            **result
        }

    except Exception as e:
        logger.error(f"Failed to provision tenant: {e}", extra={
            "tenant_id": tenant_id,
            "error": str(e)
        }, exc_info=True)

        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to provision tenant: {str(e)}"
        )


@router.post("/tenant-deleted")
async def handle_tenant_deleted(
    request: Request,
    db: Session = Depends(get_db)
):
    """
    Handle Frontegg tenant deletion webhook.

    Cleans up:
    1. Airbyte workspace (archive or delete)
    2. Tenant database records (soft delete)
    3. Active syncs
    4. OAuth connections
    """
    # Verify signature
    body = await request.body()
    signature = request.headers.get("x-frontegg-signature", "")

    if not verify_webhook_signature(body, signature):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid webhook signature"
        )

    # Parse payload
    payload = await request.json()
    tenant_id = payload.get("tenantId") or payload.get("orgId")

    if not tenant_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Missing tenant ID"
        )

    logger.info("Processing tenant deletion webhook", extra={"tenant_id": tenant_id})

    # Get tenant workspace
    workspace_repo = TenantWorkspaceRepository(db)
    workspace = workspace_repo.get_workspace_for_tenant(tenant_id)

    if not workspace:
        logger.warning("Tenant workspace not found for deletion", extra={"tenant_id": tenant_id})
        return {"status": "not_found", "tenant_id": tenant_id}

    # Archive workspace (soft delete - don't destroy data immediately)
    try:
        workspace.status = "deleted"
        db.commit()

        logger.info("Tenant marked as deleted", extra={
            "tenant_id": tenant_id,
            "workspace_id": str(workspace.airbyte_workspace_id)
        })

        # TODO: Schedule Airbyte workspace deletion (after retention period)
        # TODO: Cancel active syncs
        # TODO: Archive data to cold storage

        return {
            "status": "success",
            "tenant_id": tenant_id,
            "workspace_id": str(workspace.airbyte_workspace_id),
            "action": "soft_deleted"
        }

    except Exception as e:
        logger.error(f"Failed to delete tenant: {e}", extra={"tenant_id": tenant_id}, exc_info=True)
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to delete tenant: {str(e)}"
        )
```

**Time**: 1.5 hours

#### Task 2.2: Register Webhook Routes
**File**: `backend/main.py`

Add webhook router registration:
```python
from backend.src.api.routes import frontegg_webhooks

# Register webhook routes (must be BEFORE tenant context middleware)
app.include_router(frontegg_webhooks.router, tags=["webhooks"])
```

**Time**: 10 minutes

#### Task 2.3: Add Webhook Secret to Environment
**File**: `.env`

```bash
# Frontegg Webhook Security
FRONTEGG_WEBHOOK_SECRET=<get-from-frontegg-dashboard-later>
```

**Time**: 5 minutes

#### Task 2.4: Update tenant_context.py
Exclude webhook endpoints from authentication:

**File**: `backend/src/platform/tenant_context.py`

Update line ~197:
```python
# Skip tenant check for health endpoint, webhooks, and API documentation (public)
if request.url.path in ("/health", "/docs", "/redoc", "/openapi.json") or \
   request.url.path.startswith("/api/webhooks/"):
    return await call_next(request)
```

**Time**: 15 minutes

### Success Criteria
- ✅ Webhook endpoint responds to POST requests
- ✅ Signature verification works (or skips in dev mode)
- ✅ Can receive test webhook from Frontegg
- ✅ Returns proper HTTP status codes

### Deliverables
1. `backend/src/api/routes/frontegg_webhooks.py`
2. Webhook routes registered in main.py
3. tenant_context.py updated
4. Git commit: "feat: Add Frontegg webhook endpoints for tenant provisioning"

---

## Phase 3: Multi-Tenant Airbyte Database Schema - 1 hour

### Status: 🔴 Not Started

### Objective
Create database table to map tenants to Airbyte workspaces.

### Tasks

#### Task 3.1: Create Migration SQL
**File**: `db/migrations/005_add_tenant_airbyte_workspaces.sql`

```sql
-- Migration 005: Add tenant Airbyte workspace mappings
--
-- Purpose: Map each tenant_id to a dedicated Airbyte workspace
-- Enables workspace-level isolation for OAuth connections and syncs

CREATE TABLE IF NOT EXISTS tenant_airbyte_workspaces (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id VARCHAR(255) NOT NULL UNIQUE,
    airbyte_workspace_id UUID NOT NULL UNIQUE,
    airbyte_workspace_name VARCHAR(255) NOT NULL,
    organization_id UUID,  -- Airbyte organization ID (for enterprise)
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP NOT NULL DEFAULT NOW(),
    status VARCHAR(50) DEFAULT 'active' CHECK (status IN ('active', 'suspended', 'deleted')),

    -- Indexes for fast lookups
    CONSTRAINT idx_tenant_workspace_tenant_id UNIQUE (tenant_id),
    CONSTRAINT idx_tenant_workspace_airbyte_id UNIQUE (airbyte_workspace_id)
);

-- Index for tenant_id lookups (most common query)
CREATE INDEX IF NOT EXISTS idx_tenant_airbyte_workspaces_tenant
    ON tenant_airbyte_workspaces(tenant_id)
    WHERE status = 'active';

-- Index for Airbyte workspace_id lookups
CREATE INDEX IF NOT EXISTS idx_tenant_airbyte_workspaces_workspace
    ON tenant_airbyte_workspaces(airbyte_workspace_id);

-- Index for finding deleted workspaces (for cleanup jobs)
CREATE INDEX IF NOT EXISTS idx_tenant_airbyte_workspaces_status
    ON tenant_airbyte_workspaces(status, created_at);

-- Add comment for documentation
COMMENT ON TABLE tenant_airbyte_workspaces IS
    'Maps tenant_id from Frontegg JWT to dedicated Airbyte workspace. Each tenant gets isolated workspace for OAuth connections and data syncs.';

COMMENT ON COLUMN tenant_airbyte_workspaces.tenant_id IS
    'Frontegg organization ID from JWT token (matches Tenant.tenant_id)';

COMMENT ON COLUMN tenant_airbyte_workspaces.airbyte_workspace_id IS
    'Airbyte workspace UUID from Airbyte Cloud API';

COMMENT ON COLUMN tenant_airbyte_workspaces.status IS
    'active: Normal operation | suspended: Billing issue | deleted: Soft delete (retain for 30 days)';
```

**Time**: 20 minutes

#### Task 3.2: Apply Migration
**Command** (user runs on Mac):
```bash
# Using docker compose exec
docker compose exec postgres psql -U shopify_analytics_user -d shopify_analytics -f /app/db/migrations/005_add_tenant_airbyte_workspaces.sql

# Or using local psql
psql postgresql://shopify_analytics_user:localdev123@localhost:5432/shopify_analytics -f db/migrations/005_add_tenant_airbyte_workspaces.sql
```

**Time**: 5 minutes

#### Task 3.3: Create SQLAlchemy Model
**File**: `backend/src/models/tenant_airbyte_workspace.py`

```python
"""SQLAlchemy model for tenant Airbyte workspace mappings."""

from sqlalchemy import Column, String, DateTime, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from backend.src.models.base import Base
import uuid
from datetime import datetime


class TenantAirbyteWorkspace(Base):
    """
    Maps tenant_id (from Frontegg JWT) to dedicated Airbyte workspace.

    Each tenant gets their own workspace for:
    - Isolated OAuth connections (Shopify, Meta, Google)
    - Separate source/destination configurations
    - Independent sync schedules
    - Workspace-level permissions

    Attributes:
        id: Primary key UUID
        tenant_id: Frontegg organization ID (matches JWT org_id)
        airbyte_workspace_id: Airbyte Cloud workspace UUID
        airbyte_workspace_name: Human-readable name in Airbyte
        organization_id: Airbyte organization ID (for multi-org deployments)
        created_at: Timestamp when workspace was provisioned
        updated_at: Last updated timestamp
        status: active | suspended | deleted
    """
    __tablename__ = "tenant_airbyte_workspaces"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id = Column(String(255), unique=True, nullable=False, index=True)
    airbyte_workspace_id = Column(UUID(as_uuid=True), unique=True, nullable=False, index=True)
    airbyte_workspace_name = Column(String(255), nullable=False)
    organization_id = Column(UUID(as_uuid=True), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    status = Column(String(50), default="active", nullable=False)

    def __repr__(self):
        return f"<TenantAirbyteWorkspace tenant={self.tenant_id} workspace={self.airbyte_workspace_id} status={self.status}>"
```

**Time**: 15 minutes

#### Task 3.4: Create Repository
**File**: `backend/src/repositories/tenant_workspaces.py`

```python
"""Repository for tenant Airbyte workspace mappings."""

from sqlalchemy.orm import Session
from backend.src.models.tenant_airbyte_workspace import TenantAirbyteWorkspace
from backend.src.repositories.base import BaseRepository
from typing import Optional
import uuid


class TenantWorkspaceRepository(BaseRepository):
    """Repository for managing tenant Airbyte workspace mappings."""

    def __init__(self, db: Session):
        super().__init__(db, TenantAirbyteWorkspace)

    def get_workspace_for_tenant(self, tenant_id: str) -> Optional[TenantAirbyteWorkspace]:
        """
        Get active Airbyte workspace for tenant.

        Args:
            tenant_id: Frontegg organization ID from JWT

        Returns:
            TenantAirbyteWorkspace if found and active, None otherwise
        """
        return self.db.query(TenantAirbyteWorkspace).filter(
            TenantAirbyteWorkspace.tenant_id == tenant_id,
            TenantAirbyteWorkspace.status == "active"
        ).first()

    def create_workspace(
        self,
        tenant_id: str,
        airbyte_workspace_id: str,
        workspace_name: str,
        organization_id: Optional[str] = None
    ) -> TenantAirbyteWorkspace:
        """
        Create new tenant workspace mapping.

        Args:
            tenant_id: Frontegg organization ID
            airbyte_workspace_id: Airbyte workspace UUID (from Airbyte API)
            workspace_name: Human-readable name
            organization_id: Airbyte org ID (optional, for enterprise)

        Returns:
            Created TenantAirbyteWorkspace instance

        Raises:
            IntegrityError: If tenant_id or workspace_id already exists
        """
        workspace = TenantAirbyteWorkspace(
            tenant_id=tenant_id,
            airbyte_workspace_id=uuid.UUID(airbyte_workspace_id) if isinstance(airbyte_workspace_id, str) else airbyte_workspace_id,
            airbyte_workspace_name=workspace_name,
            organization_id=uuid.UUID(organization_id) if organization_id and isinstance(organization_id, str) else organization_id,
            status="active"
        )
        self.db.add(workspace)
        self.db.commit()
        self.db.refresh(workspace)
        return workspace

    def mark_deleted(self, tenant_id: str) -> bool:
        """
        Soft delete workspace mapping.

        Args:
            tenant_id: Tenant to delete

        Returns:
            True if deleted, False if not found
        """
        workspace = self.get_workspace_for_tenant(tenant_id)
        if not workspace:
            return False

        workspace.status = "deleted"
        self.db.commit()
        return True

    def get_all_active_workspaces(self) -> list[TenantAirbyteWorkspace]:
        """Get all active tenant workspaces (for admin/monitoring)."""
        return self.db.query(TenantAirbyteWorkspace).filter(
            TenantAirbyteWorkspace.status == "active"
        ).all()
```

**Time**: 20 minutes

### Success Criteria
- ✅ Migration creates table successfully
- ✅ Model can be imported
- ✅ Repository CRUD operations work
- ✅ Indexes created for fast lookups

### Deliverables
1. Migration SQL file
2. TenantAirbyteWorkspace model
3. TenantWorkspaceRepository
4. Git commit: "feat: Add tenant Airbyte workspace database schema"

---

## Phase 4: Airbyte Client Enhancements - 1.5 hours

### Status: 🔴 Not Started

### Objective
Add workspace provisioning methods to Airbyte client.

### Tasks

#### Task 4.1: Add Workspace Management Methods
**File**: `backend/src/integrations/airbyte/client.py`

Add these methods to AirbyteClient class:

```python
async def create_workspace(
    self,
    name: str,
    organization_id: Optional[str] = None
) -> dict:
    """
    Create new Airbyte workspace.

    POST /v1/workspaces

    Args:
        name: Workspace name (e.g., "Acme Corp - org123")
        organization_id: Optional Airbyte organization ID

    Returns:
        {
            "workspaceId": "uuid-string",
            "name": "Acme Corp",
            "organizationId": "org-uuid",
            "dataResidency": "us"
        }

    Raises:
        AirbyteAPIError: If workspace creation fails
    """
    payload = {"name": name}
    if organization_id:
        payload["organizationId"] = organization_id

    response = await self._post("/workspaces", json=payload)
    return response.json()


async def get_workspace(self, workspace_id: str) -> dict:
    """
    Get workspace details.

    GET /v1/workspaces/{workspaceId}

    Args:
        workspace_id: Airbyte workspace UUID

    Returns:
        Workspace details including name, org, data residency
    """
    response = await self._get(f"/workspaces/{workspace_id}")
    return response.json()


async def list_workspaces(self) -> list[dict]:
    """
    List all workspaces (for current organization).

    GET /v1/workspaces

    Returns:
        List of workspace objects
    """
    response = await self._get("/workspaces")
    data = response.json()
    return data.get("data", [])


async def delete_workspace(self, workspace_id: str) -> bool:
    """
    Delete Airbyte workspace.

    DELETE /v1/workspaces/{workspaceId}

    WARNING: This permanently deletes all sources, destinations,
    and connections in the workspace.

    Args:
        workspace_id: Workspace to delete

    Returns:
        True if deleted successfully

    Raises:
        AirbyteAPIError: If deletion fails
    """
    try:
        await self._delete(f"/workspaces/{workspace_id}")
        return True
    except Exception as e:
        logger.error(f"Failed to delete workspace {workspace_id}: {e}")
        return False
```

**Time**: 1 hour

#### Task 4.2: Update create_source to Accept workspace_id
Modify existing `create_source` method:

```python
async def create_source(
    self,
    workspace_id: str,  # NEW: per-tenant workspace
    source_type: str,
    config: dict,
    name: str
) -> dict:
    """
    Create Airbyte source in specific workspace.

    Args:
        workspace_id: Tenant's dedicated workspace
        source_type: "shopify", "facebook-marketing", "google-ads", etc.
        config: Source-specific configuration
        name: Human-readable source name

    Returns:
        {
            "sourceId": "uuid",
            "workspaceId": "uuid",
            "sourceDefinitionId": "uuid",
            "connectionConfiguration": {...},
            "name": "Shopify - mystore"
        }
    """
    # Get source definition ID for source type
    source_def_id = await self.get_source_definition_id(source_type)

    payload = {
        "workspaceId": workspace_id,  # Use tenant's workspace
        "sourceDefinitionId": source_def_id,
        "connectionConfiguration": config,
        "name": name
    }

    response = await self._post("/sources", json=payload)
    return response.json()
```

**Time**: 30 minutes

### Success Criteria
- ✅ Can create new workspace via API
- ✅ Can get workspace details
- ✅ create_source uses workspace_id parameter
- ✅ Methods have proper error handling

### Deliverables
1. Updated `backend/src/integrations/airbyte/client.py`
2. Git commit: "feat: Add Airbyte workspace provisioning to client"

---

## Phase 5: Tenant Provisioning Service - 2 hours

### Status: 🔴 Not Started

### Objective
Create service that provisions all tenant resources automatically.

### Tasks

#### Task 5.1: Create Provisioning Service
**File**: `backend/src/services/tenant_provisioning.py`

```python
"""
Tenant provisioning service.

Handles automatic provisioning of all resources when new tenant signs up:
1. Airbyte workspace
2. Database records
3. (Future) Default destinations
4. (Future) Sample data
"""

from backend.src.integrations.airbyte.client import AirbyteClient
from backend.src.repositories.tenant_workspaces import TenantWorkspaceRepository
import logging

logger = logging.getLogger(__name__)


class TenantProvisioningService:
    """Handles provisioning of resources for new tenants."""

    def __init__(
        self,
        airbyte_client: AirbyteClient,
        workspace_repo: TenantWorkspaceRepository
    ):
        self.airbyte = airbyte_client
        self.workspace_repo = workspace_repo

    async def provision_tenant(self, tenant_id: str, tenant_name: str) -> dict:
        """
        Provision all resources for new tenant.

        Steps:
        1. Create dedicated Airbyte workspace
        2. Store workspace mapping in database
        3. (Future) Create default PostgreSQL destination
        4. (Future) Set up sample Shopify connection

        Args:
            tenant_id: Frontegg organization ID
            tenant_name: Organization name from Frontegg

        Returns:
            {
                "tenant_id": "org-123",
                "workspace_id": "uuid",
                "workspace_name": "Acme Corp - org123",
                "status": "provisioned"
            }

        Raises:
            Exception: If provisioning fails at any step
        """
        logger.info(f"Starting tenant provisioning for {tenant_id}")

        # 1. Create Airbyte workspace
        workspace_name = self._generate_workspace_name(tenant_name, tenant_id)

        logger.info(f"Creating Airbyte workspace: {workspace_name}")
        workspace_response = await self.airbyte.create_workspace(
            name=workspace_name,
            organization_id=None  # Use default Airbyte org
        )

        workspace_id = workspace_response["workspaceId"]
        logger.info(f"Airbyte workspace created: {workspace_id}")

        # 2. Store workspace mapping in database
        logger.info(f"Storing workspace mapping in database")
        workspace_mapping = self.workspace_repo.create_workspace(
            tenant_id=tenant_id,
            airbyte_workspace_id=workspace_id,
            workspace_name=workspace_name
        )

        logger.info(f"Tenant provisioned successfully: {tenant_id}")

        return {
            "tenant_id": tenant_id,
            "workspace_id": workspace_id,
            "workspace_name": workspace_name,
            "status": "provisioned",
            "database_record_id": str(workspace_mapping.id)
        }

    def _generate_workspace_name(self, tenant_name: str, tenant_id: str) -> str:
        """
        Generate human-readable workspace name.

        Format: "{TenantName} - {first-8-chars-of-id}"
        Example: "Acme Corporation - 9b77c0fb"

        Args:
            tenant_name: Organization name from Frontegg
            tenant_id: Full organization ID

        Returns:
            Formatted workspace name
        """
        # Take first 8 characters of tenant ID for brevity
        short_id = tenant_id[:8] if len(tenant_id) >= 8 else tenant_id

        # Clean tenant name (remove special characters, limit length)
        clean_name = tenant_name.strip()[:50]  # Max 50 chars for name

        return f"{clean_name} - {short_id}"

    async def deprovision_tenant(self, tenant_id: str) -> dict:
        """
        Clean up tenant resources (soft delete).

        Steps:
        1. Mark workspace as deleted in database
        2. (Future) Cancel active Airbyte syncs
        3. (Future) Archive data to cold storage
        4. (Future) Schedule hard delete after retention period

        Args:
            tenant_id: Tenant to deprovision

        Returns:
            {
                "tenant_id": "org-123",
                "status": "deprovisioned",
                "action": "soft_deleted"
            }

        NOTE: Does NOT immediately delete Airbyte workspace to allow
        for data recovery within retention period.
        """
        logger.info(f"Deprovisioning tenant: {tenant_id}")

        # Soft delete workspace mapping
        deleted = self.workspace_repo.mark_deleted(tenant_id)

        if not deleted:
            logger.warning(f"Tenant {tenant_id} not found for deprovisioning")
            return {
                "tenant_id": tenant_id,
                "status": "not_found"
            }

        logger.info(f"Tenant {tenant_id} marked as deleted")

        # TODO: Schedule hard delete after 30-day retention period
        # TODO: Cancel active syncs
        # TODO: Archive data

        return {
            "tenant_id": tenant_id,
            "status": "deprovisioned",
            "action": "soft_deleted",
            "retention_days": 30
        }
```

**Time**: 1.5 hours

#### Task 5.2: Add Tests
**File**: `backend/src/tests/test_tenant_provisioning.py`

```python
"""Tests for tenant provisioning service."""

import pytest
from unittest.mock import Mock, AsyncMock
from backend.src.services.tenant_provisioning import TenantProvisioningService


@pytest.mark.asyncio
async def test_provision_tenant_creates_workspace():
    """Test that provision_tenant creates Airbyte workspace and DB record."""
    # Mock Airbyte client
    airbyte_mock = Mock()
    airbyte_mock.create_workspace = AsyncMock(return_value={
        "workspaceId": "test-workspace-123",
        "name": "Test Org - 12345678"
    })

    # Mock workspace repository
    workspace_repo_mock = Mock()
    workspace_repo_mock.create_workspace = Mock(return_value=Mock(id="db-record-123"))

    # Create service
    service = TenantProvisioningService(airbyte_mock, workspace_repo_mock)

    # Provision tenant
    result = await service.provision_tenant("test-tenant-123", "Test Organization")

    # Verify workspace created
    airbyte_mock.create_workspace.assert_called_once()
    assert result["workspace_id"] == "test-workspace-123"
    assert result["status"] == "provisioned"

    # Verify DB record created
    workspace_repo_mock.create_workspace.assert_called_once_with(
        tenant_id="test-tenant-123",
        airbyte_workspace_id="test-workspace-123",
        workspace_name="Test Organization - test-ten"
    )


@pytest.mark.asyncio
async def test_deprovision_tenant_soft_deletes():
    """Test that deprovision marks tenant as deleted without hard delete."""
    airbyte_mock = Mock()
    workspace_repo_mock = Mock()
    workspace_repo_mock.mark_deleted = Mock(return_value=True)

    service = TenantProvisioningService(airbyte_mock, workspace_repo_mock)

    result = await service.deprovision_tenant("test-tenant-123")

    assert result["status"] == "deprovisioned"
    assert result["action"] == "soft_deleted"
    workspace_repo_mock.mark_deleted.assert_called_once_with("test-tenant-123")


def test_generate_workspace_name_format():
    """Test workspace name generation format."""
    service = TenantProvisioningService(Mock(), Mock())

    name = service._generate_workspace_name("Acme Corporation", "abc123def456")

    assert name == "Acme Corporation - abc123de"
    assert len(name) <= 60  # Reasonable length limit
```

**Time**: 30 minutes

### Success Criteria
- ✅ Service can provision tenant workspace
- ✅ Database record created correctly
- ✅ Tests pass
- ✅ Proper error handling and logging

### Deliverables
1. `backend/src/services/tenant_provisioning.py`
2. `backend/src/tests/test_tenant_provisioning.py`
3. Git commit: "feat: Add tenant provisioning service with Airbyte workspace creation"

---

## Phase 6: Update Existing Services to Use Per-Tenant Workspaces - 2 hours

### Status: 🔴 Not Started

### Objective
Modify AirbyteService, ShopifyIngestionService, etc. to use tenant's dedicated workspace.

### Tasks

#### Task 6.1: Update AirbyteService Constructor
**File**: `backend/src/services/airbyte_service.py`

```python
class AirbyteService:
    """Airbyte integration service - now with per-tenant workspace isolation."""

    def __init__(
        self,
        tenant_id: str,
        airbyte_client: AirbyteClient,
        workspace_repo: TenantWorkspaceRepository
    ):
        """
        Initialize Airbyte service for specific tenant.

        Args:
            tenant_id: Frontegg organization ID from JWT
            airbyte_client: Initialized Airbyte API client
            workspace_repo: Repository to fetch workspace mapping

        Raises:
            ValueError: If tenant has no workspace provisioned
        """
        self.tenant_id = tenant_id
        self.airbyte = airbyte_client

        # Get tenant's dedicated workspace
        workspace = workspace_repo.get_workspace_for_tenant(tenant_id)
        if not workspace:
            raise ValueError(
                f"No Airbyte workspace found for tenant {tenant_id}. "
                "Workspace must be provisioned via webhook before using Airbyte services."
            )

        self.workspace_id = str(workspace.airbyte_workspace_id)
        logger.info(f"AirbyteService initialized for tenant {tenant_id} with workspace {self.workspace_id}")

    async def create_shopify_source(self, store_domain: str, access_token: str) -> str:
        """
        Create Shopify source in tenant's workspace.

        Args:
            store_domain: Shopify store URL (e.g., "my-store.myshopify.com")
            access_token: Shopify access token from OAuth

        Returns:
            Source ID (UUID string)
        """
        source_response = await self.airbyte.create_source(
            workspace_id=self.workspace_id,  # Use tenant's workspace
            source_type="shopify",
            config={
                "shop": store_domain,
                "credentials": {
                    "auth_method": "access_token",
                    "access_token": access_token
                },
                "start_date": "2024-01-01"  # Or from tenant settings
            },
            name=f"Shopify - {store_domain}"
        )

        return source_response["sourceId"]

    # ... other methods updated similarly
```

**Time**: 1 hour

#### Task 6.2: Update ShopifyIngestionService
**File**: `backend/src/services/shopify_ingestion.py`

Update to pass workspace_id to Airbyte operations:

```python
from backend.src.repositories.tenant_workspaces import TenantWorkspaceRepository

class ShopifyIngestionService:
    def __init__(self, tenant_id: str, db: Session):
        self.tenant_id = tenant_id
        self.db = db
        self.airbyte = AirbyteClient()

        # Get tenant workspace
        workspace_repo = TenantWorkspaceRepository(db)
        workspace = workspace_repo.get_workspace_for_tenant(tenant_id)
        if not workspace:
            raise ValueError(f"No workspace for tenant {tenant_id}")

        self.workspace_id = str(workspace.airbyte_workspace_id)

    # ... methods updated to use self.workspace_id
```

**Time**: 30 minutes

#### Task 6.3: Update AdIngestionService (Meta, Google Ads)
**File**: `backend/src/services/ad_ingestion.py`

Similar updates as ShopifyIngestionService.

**Time**: 30 minutes

### Success Criteria
- ✅ Services load correct workspace for tenant
- ✅ Airbyte operations scoped to tenant workspace
- ✅ Tests verify workspace isolation
- ✅ Error handling when workspace missing

### Deliverables
1. Updated AirbyteService
2. Updated ShopifyIngestionService
3. Updated AdIngestionService
4. Git commit: "feat: Update ingestion services to use per-tenant Airbyte workspaces"

---

## Phase 7: End-to-End Testing - 2 hours

### Status: 🔴 Not Started

### Objective
Test complete tenant lifecycle: signup → provisioning → data sync → deletion.

### Testing Scenarios

#### Test 7.1: Tenant Signup Flow
**Manual Test**:
1. Create test tenant in Frontegg
2. Verify webhook triggers provisioning
3. Check database for workspace record
4. Verify workspace exists in Airbyte Cloud

**Expected Results**:
- Webhook received and processed
- Database record created
- Airbyte workspace visible in dashboard

**Time**: 30 minutes

#### Test 7.2: Shopify Integration with New Tenant
**Manual Test**:
1. Use provisioned tenant
2. Connect Shopify store via OAuth
3. Verify source created in correct workspace
4. Trigger sync
5. Check data isolated to tenant's database tables

**Expected Results**:
- Shopify source in tenant's workspace (not shared workspace)
- Sync completes successfully
- Data queryable via tenant-scoped endpoints

**Time**: 45 minutes

#### Test 7.3: Cross-Tenant Isolation
**Automated Test**:
```python
@pytest.mark.integration
async def test_tenant_a_cannot_access_tenant_b_sources():
    """Verify workspace-level isolation between tenants."""
    # Create two tenants
    tenant_a = await provision_tenant("tenant-a", "Tenant A")
    tenant_b = await provision_tenant("tenant-b", "Tenant B")

    # Create source for Tenant A
    airbyte_service_a = AirbyteService("tenant-a", airbyte_client, workspace_repo)
    source_a = await airbyte_service_a.create_shopify_source("store-a.myshopify.com", "token-a")

    # Try to access from Tenant B
    airbyte_service_b = AirbyteService("tenant-b", airbyte_client, workspace_repo)
    sources_b = await airbyte_service_b.list_sources()

    # Verify Tenant B cannot see Tenant A's source
    source_ids_b = [s["sourceId"] for s in sources_b]
    assert source_a not in source_ids_b
```

**Expected Results**:
- Tenant B cannot see Tenant A's sources
- Each tenant's sources isolated to their workspace

**Time**: 30 minutes

#### Test 7.4: Tenant Deletion Cleanup
**Manual Test**:
1. Delete tenant in Frontegg
2. Verify webhook triggers cleanup
3. Check workspace marked as deleted
4. Verify active syncs cancelled

**Expected Results**:
- Workspace soft-deleted
- Data retained for recovery period
- No active syncs

**Time**: 15 minutes

### Success Criteria
- ✅ Tenant provisioning works end-to-end
- ✅ Workspace isolation verified
- ✅ Data syncs work per tenant
- ✅ Cleanup process works
- ✅ All automated tests pass

### Deliverables
1. Integration test suite
2. Manual test results documented
3. Git commit: "test: Add end-to-end tests for multi-tenant architecture"

---

## Phase 8: Configure Production Webhooks - 30 minutes

### Status: 🔴 Not Started

### Objective
Configure Frontegg webhooks in production to trigger auto-provisioning.

### Tasks

#### Task 8.1: Get Webhook Secret from Frontegg
1. Login to https://portal.frontegg.com
2. Navigate to Settings → Webhooks
3. Copy webhook secret
4. Add to `.env`: `FRONTEGG_WEBHOOK_SECRET=<secret>`

**Time**: 5 minutes

#### Task 8.2: Configure Webhook in Frontegg Dashboard
1. Add webhook URL: `https://your-app.com/api/webhooks/frontegg/tenant-created`
2. Select event: `tenant.created`
3. Enable webhook
4. Send test event

**Time**: 10 minutes

#### Task 8.3: Verify Webhook Works
1. Create test tenant in Frontegg
2. Check backend logs for webhook receipt
3. Verify workspace created in Airbyte
4. Confirm database record

**Time**: 15 minutes

### Success Criteria
- ✅ Webhook configured in Frontegg
- ✅ Test event received successfully
- ✅ Tenant provisioned automatically
- ✅ Logs show successful processing

### Deliverables
1. Webhook configured in Frontegg production
2. Environment variable updated
3. Verification test passed

---

## Phase 9: Documentation and Cleanup - 1 hour

### Status: 🔴 Not Started

### Objective
Document the architecture, update README, clean up debug code.

### Tasks

#### Task 9.1: Remove Diagnostic Code from App.tsx
Restore clean production version (remove showDiagnostics state).

**Time**: 15 minutes

#### Task 9.2: Update README.md
Add sections:
- Multi-tenant architecture overview
- Airbyte workspace isolation
- Webhook configuration
- Deployment instructions

**Time**: 30 minutes

#### Task 9.3: Create Architecture Diagram
Document:
- Frontegg authentication flow
- Webhook-triggered provisioning
- Per-tenant workspace isolation
- Data flow (Shopify → Airbyte → PostgreSQL)

**Time**: 15 minutes

### Success Criteria
- ✅ Clean, production-ready codebase
- ✅ Comprehensive documentation
- ✅ Architecture clearly explained
- ✅ Deployment guide available

### Deliverables
1. Clean `frontend/src/App.tsx`
2. Updated `README.md`
3. Architecture documentation
4. Git commit: "docs: Add comprehensive architecture and deployment documentation"

---

## Final Deliverables Summary

### Code
1. ✅ Working Frontegg authentication (embedded login)
2. ✅ Webhook endpoints for tenant lifecycle
3. ✅ Database schema for tenant-workspace mappings
4. ✅ Enhanced Airbyte client with workspace methods
5. ✅ Tenant provisioning service
6. ✅ Updated ingestion services (per-tenant workspaces)
7. ✅ Comprehensive test suite
8. ✅ Production-ready, documented codebase

### Infrastructure
1. ✅ Per-tenant Airbyte workspaces
2. ✅ Webhook-based auto-provisioning
3. ✅ Row-level security (existing)
4. ✅ JWT authentication (Frontegg)

### Documentation
1. ✅ Architecture overview
2. ✅ Webhook configuration guide
3. ✅ Deployment instructions
4. ✅ Testing guide

### Git Commits
Expected commits (in order):
1. `fix: Resolve Frontegg authentication issue - [diagnosis]`
2. `feat: Add Frontegg webhook endpoints for tenant provisioning`
3. `feat: Add tenant Airbyte workspace database schema`
4. `feat: Add Airbyte workspace provisioning to client`
5. `feat: Add tenant provisioning service with Airbyte workspace creation`
6. `feat: Update ingestion services to use per-tenant Airbyte workspaces`
7. `test: Add end-to-end tests for multi-tenant architecture`
8. `docs: Add comprehensive architecture and deployment documentation`

---

## Total Time Estimate

| Phase | Description | Time |
|-------|-------------|------|
| 1 | Fix Authentication | 2 hours |
| 2 | Webhook Infrastructure | 3 hours |
| 3 | Database Schema | 1 hour |
| 4 | Airbyte Client Enhancements | 1.5 hours |
| 5 | Provisioning Service | 2 hours |
| 6 | Update Existing Services | 2 hours |
| 7 | End-to-End Testing | 2 hours |
| 8 | Production Webhooks | 0.5 hours |
| 9 | Documentation & Cleanup | 1 hour |
| **TOTAL** | **Complete Implementation** | **15 hours** |

**Timeline**: 2-3 days at ~6-8 hours per day

---

## Risk Mitigation

### Risk 1: Airbyte API Rate Limits
**Mitigation**: Implement exponential backoff, cache workspace lookups

### Risk 2: Webhook Delivery Failures
**Mitigation**: Frontegg retries automatically, log all failures, implement manual retry endpoint

### Risk 3: Database Migration Issues
**Mitigation**: Test migration on copy of production DB first, have rollback plan

### Risk 4: Frontend Authentication Still Broken
**Mitigation**: Diagnostic screen will identify issue, multiple fallback options planned

---

## Next Steps (USER ACTION)

**Immediate (Phase 1)**:
1. Pull latest code with diagnostic screen
2. Restart frontend container
3. Open http://localhost:3000
4. Share diagnostic output

**After Phase 1 Success**:
- Claude will implement Phases 2-9 automatically
- User reviews and tests each phase
- Deploy to production when ready

---

**Questions? Issues?**

If any phase fails:
1. Check logs: `docker compose logs -f [service]`
2. Review error messages
3. Consult phase-specific troubleshooting section
4. Ask for help with specific error

**Let's build this correctly!** 🚀
