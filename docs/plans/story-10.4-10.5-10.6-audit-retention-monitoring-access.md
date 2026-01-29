# Implementation Plan: Stories 10.4, 10.5, 10.6
## Audit Log Retention, Monitoring & Access Controls

**Stories:** 10.4 (Retention Enforcement), 10.5 (Monitoring & Alerting), 10.6 (Access Controls)
**Total Story Points:** 8 SP (3 + 3 + 2)
**Dependencies:** Stories 10.1, 10.2, 10.3 (completed)

---

## Executive Summary

This plan covers the final three stories of the audit logging epic:
1. **Story 10.4** - Hard delete audit logs past retention window via daily scheduled job
2. **Story 10.5** - Monitoring and alerting for audit system failures and anomalies
3. **Story 10.6** - RBAC enforcement on audit log access (API + UI)

---

## Story 10.4 — Retention Enforcement (Hard Delete)

### User Story
> As a platform owner, I want audit logs to be permanently deleted after the retention window, so that we meet privacy requirements and minimize data risk.

### Locked Decisions
- **Hard delete only** — no soft delete, no archive
- **No legal holds** — out of scope
- **No archive** — deleted data is unrecoverable

### Acceptance Criteria
- [ ] Logs older than retention window are deleted automatically
- [ ] Deletions are irreversible
- [ ] Retention changes require admin approval
- [ ] Deletion job is idempotent (safe to re-run)
- [ ] Deletion is audited (meta-audit of the deletion itself)

### Human-Required Tasks
- [ ] Confirm retention duration per plan (default: 90 days? 365 days?)
- [ ] Approve deletion schedule (daily job at 02:00 UTC recommended)

### Technical Design

#### 1. Configuration (`backend/src/config/retention.py`)

```python
"""
Audit log retention configuration.

Retention periods are configurable per billing plan.
Changes to retention config require admin approval.
"""
from dataclasses import dataclass
from typing import Dict

@dataclass
class RetentionConfig:
    """Retention configuration for a billing plan."""
    plan_id: str
    retention_days: int  # Days to retain audit logs
    description: str

# Default retention periods per plan
# Human task: Confirm these values
PLAN_RETENTION_DEFAULTS: Dict[str, int] = {
    "free": 30,           # 30 days for free tier
    "starter": 90,        # 90 days for starter
    "professional": 180,  # 6 months for professional
    "enterprise": 365,    # 1 year for enterprise
}

# Global minimum (compliance floor)
MINIMUM_RETENTION_DAYS = 30

# Global maximum (storage constraint)
MAXIMUM_RETENTION_DAYS = 730  # 2 years

# Batch size for deletion (avoid long transactions)
DELETION_BATCH_SIZE = 1000

# Job schedule (cron format)
RETENTION_JOB_SCHEDULE = "0 2 * * *"  # Daily at 02:00 UTC
```

#### 2. Retention Job Worker (`backend/src/workers/audit_retention_job.py`)

```python
"""
Audit Log Retention Enforcement Job.

Runs daily to hard-delete audit logs past their retention window.
Follows the pattern established in src/jobs/retention_cleanup.py.

Key requirements:
- Hard delete only (no archive)
- Batch deletion to avoid long transactions
- Idempotent (safe to re-run)
- Self-auditing (logs its own deletions)
"""

class AuditRetentionJob:
    """
    Enforces audit log retention policy.

    Process:
    1. Query distinct tenant_ids from audit_logs
    2. For each tenant, get their plan's retention period
    3. Calculate cutoff date (now - retention_days)
    4. Delete logs older than cutoff in batches
    5. Log deletion stats as audit event (meta-audit)
    """

    def __init__(self, db_session):
        self.db = db_session
        self.stats = {
            "tenants_processed": 0,
            "total_deleted": 0,
            "errors": [],
        }

    def get_tenant_retention_days(self, tenant_id: str) -> int:
        """Get retention period for tenant based on their plan."""
        # Query tenant's billing plan
        # Return PLAN_RETENTION_DEFAULTS[plan_id] or default
        pass

    def delete_expired_logs(self, tenant_id: str, cutoff_date: datetime) -> int:
        """
        Delete audit logs older than cutoff_date for tenant.

        Uses batch deletion pattern from retention_cleanup.py:
        - Select IDs in batches
        - Delete by ID list
        - Commit after each batch
        """
        pass

    def run(self) -> Dict:
        """
        Execute retention enforcement for all tenants.

        Returns stats dictionary with deletion counts.
        """
        pass
```

#### 3. Database Considerations

The `audit_logs` table has an immutability trigger that prevents UPDATE/DELETE. We need to:

**Option A (Recommended):** Create a privileged deletion function that bypasses the trigger for retention only:

```sql
-- Migration: Add retention deletion function
CREATE OR REPLACE FUNCTION delete_expired_audit_logs(
    p_tenant_id TEXT,
    p_cutoff_date TIMESTAMP WITH TIME ZONE,
    p_batch_size INTEGER DEFAULT 1000
) RETURNS INTEGER AS $$
DECLARE
    deleted_count INTEGER := 0;
    batch_deleted INTEGER;
BEGIN
    -- Temporarily disable trigger for this session
    SET session_replication_role = replica;

    LOOP
        DELETE FROM audit_logs
        WHERE id IN (
            SELECT id FROM audit_logs
            WHERE tenant_id = p_tenant_id
            AND timestamp < p_cutoff_date
            LIMIT p_batch_size
        );

        GET DIAGNOSTICS batch_deleted = ROW_COUNT;
        deleted_count := deleted_count + batch_deleted;

        EXIT WHEN batch_deleted < p_batch_size;
    END LOOP;

    -- Re-enable trigger
    SET session_replication_role = DEFAULT;

    RETURN deleted_count;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

-- Only retention job service account can execute
REVOKE ALL ON FUNCTION delete_expired_audit_logs FROM PUBLIC;
GRANT EXECUTE ON FUNCTION delete_expired_audit_logs TO retention_job_role;
```

**Option B:** Modify the trigger to allow DELETE from specific application context.

#### 4. New Audit Actions

Add to `AuditAction` enum in `audit.py`:
```python
# Retention events (Story 10.4)
AUDIT_RETENTION_STARTED = "audit.retention.started"
AUDIT_RETENTION_COMPLETED = "audit.retention.completed"
AUDIT_RETENTION_FAILED = "audit.retention.failed"
```

#### 5. Files to Create/Modify

| File | Action | Description |
|------|--------|-------------|
| `backend/src/config/retention.py` | CREATE | Retention configuration |
| `backend/src/workers/audit_retention_job.py` | CREATE | Daily retention job |
| `backend/migrations/xxx_audit_retention_function.sql` | CREATE | DB function for deletion |
| `backend/src/platform/audit.py` | MODIFY | Add retention audit actions |
| `backend/tests/workers/test_audit_retention_job.py` | CREATE | Unit tests |
| `backend/tests/integration/test_audit_retention.py` | CREATE | Integration tests |

---

## Story 10.5 — Monitoring & Alerting for Audit System

### User Story
> As an on-call engineer, I want to be alerted when audit logging fails or anomalies occur, so that we never lose compliance visibility.

### Acceptance Criteria
- [ ] Alerts on audit logging failures
- [ ] Alerts on cross-tenant access attempts
- [ ] Alerts on excessive denied queries
- [ ] Integrated with existing monitoring stack (Slack, PagerDuty)
- [ ] Alerts include correlation IDs

### Human-Required Tasks
- [ ] Define alert thresholds (e.g., >5 failures/min, >10 cross-tenant attempts/hour)
- [ ] Approve escalation channels (which Slack channel, PagerDuty service)

### Technical Design

#### 1. Audit Alert Types (`backend/src/monitoring/audit_alerts.py`)

```python
"""
Audit system monitoring and alerting.

Extends the AlertManager pattern from monitoring/alerts.py
for audit-specific alerts.
"""

class AuditAlertType(str, Enum):
    """Types of audit system alerts."""
    # Logging failures
    AUDIT_LOGGING_FAILURE = "audit_logging_failure"
    AUDIT_FALLBACK_ACTIVATED = "audit_fallback_activated"

    # Security alerts
    CROSS_TENANT_ACCESS_ATTEMPT = "cross_tenant_access_attempt"
    EXCESSIVE_DENIED_QUERIES = "excessive_denied_queries"
    PERMISSION_ESCALATION_DETECTED = "permission_escalation_detected"

    # Volume anomalies
    AUDIT_VOLUME_SPIKE = "audit_volume_spike"
    AUDIT_VOLUME_DROP = "audit_volume_drop"

    # Retention alerts
    RETENTION_JOB_FAILED = "retention_job_failed"
    RETENTION_BACKLOG = "retention_backlog"


class AuditAlertManager:
    """
    Manages audit-specific alerts.

    Integrates with existing AlertManager for delivery
    but adds audit-specific logic:
    - Correlation ID inclusion
    - Tenant context
    - Compliance tagging
    """

    async def alert_logging_failure(
        self,
        error: str,
        correlation_id: str,
        tenant_id: Optional[str] = None,
    ) -> None:
        """Alert when audit logging fails."""
        pass

    async def alert_cross_tenant_access(
        self,
        requesting_tenant: str,
        target_tenant: str,
        user_id: str,
        action: str,
        correlation_id: str,
    ) -> None:
        """Alert on cross-tenant access attempt."""
        pass

    async def alert_excessive_denials(
        self,
        tenant_id: str,
        denial_count: int,
        time_window_minutes: int,
        correlation_id: str,
    ) -> None:
        """Alert when denial rate exceeds threshold."""
        pass
```

#### 2. Audit Metrics (`backend/src/monitoring/audit_metrics.py`)

```python
"""
Audit system metrics for monitoring dashboards.

Emits metrics compatible with Prometheus/StatsD.
"""

class AuditMetrics:
    """
    Collects and emits audit system metrics.

    Metrics emitted:
    - audit_events_total (counter): Total audit events by action, outcome
    - audit_events_by_tenant (counter): Events per tenant
    - audit_logging_failures (counter): Failed audit writes
    - audit_fallback_events (counter): Events written to fallback
    - audit_query_latency (histogram): Query response times
    - audit_export_count (counter): Export requests
    - audit_retention_deleted (counter): Records deleted by retention
    """

    def record_audit_event(
        self,
        action: str,
        outcome: str,
        tenant_id: str,
        source: str,
    ) -> None:
        """Record an audit event for metrics."""
        pass

    def record_logging_failure(
        self,
        error_type: str,
        tenant_id: Optional[str] = None,
    ) -> None:
        """Record an audit logging failure."""
        pass

    def record_query_latency(
        self,
        latency_ms: float,
        query_type: str,
    ) -> None:
        """Record audit query latency."""
        pass
```

#### 3. Alert Rules Configuration

Add to `backend/src/platform/alert_rules.yaml`:

```yaml
audit_alerts:
  # Logging failures
  audit_logging_failure:
    severity: critical
    threshold: 5
    time_window_minutes: 5
    message: "Audit logging failures detected"
    escalation:
      - slack: "#security-alerts"
      - pagerduty: audit-oncall
    context_fields:
      - correlation_id
      - error_message
      - tenant_id

  # Cross-tenant access
  cross_tenant_access:
    severity: critical
    threshold: 1  # Single attempt is critical
    message: "Cross-tenant access attempt detected"
    escalation:
      - slack: "#security-alerts"
      - pagerduty: security-oncall
    auto_actions:
      - log_security_incident
    context_fields:
      - requesting_tenant
      - target_tenant
      - user_id
      - correlation_id

  # Excessive denials
  excessive_denials:
    severity: high
    threshold: 50
    time_window_minutes: 10
    message: "Excessive access denials detected"
    escalation:
      - slack: "#security-alerts"
    context_fields:
      - tenant_id
      - denial_count
      - top_denied_actions

  # Volume anomalies
  audit_volume_spike:
    severity: medium
    threshold_multiplier: 3.0  # 3x normal volume
    baseline_window_hours: 24
    message: "Unusual audit event volume detected"
    escalation:
      - slack: "#platform-alerts"

  # Retention alerts
  retention_job_failed:
    severity: high
    message: "Audit retention job failed"
    escalation:
      - slack: "#platform-alerts"
      - pagerduty: platform-oncall
```

#### 4. Integration Points

Modify `backend/src/platform/audit.py` to emit metrics and trigger alerts:

```python
def write_audit_log_sync(db: Session, event: AuditEvent) -> Optional[AuditLog]:
    """Write audit event with metrics and alerting."""
    metrics = get_audit_metrics()

    try:
        # ... existing write logic ...

        # Emit success metric
        metrics.record_audit_event(
            action=event.action.value,
            outcome=event.outcome.value,
            tenant_id=event.tenant_id,
            source=event.source,
        )
        return audit_log

    except Exception as e:
        # Emit failure metric
        metrics.record_logging_failure(
            error_type=type(e).__name__,
            tenant_id=event.tenant_id,
        )

        # Trigger alert if threshold exceeded
        await get_audit_alert_manager().check_failure_threshold()

        # ... existing fallback logic ...
```

#### 5. Files to Create/Modify

| File | Action | Description |
|------|--------|-------------|
| `backend/src/monitoring/audit_alerts.py` | CREATE | Audit alert definitions |
| `backend/src/monitoring/audit_metrics.py` | CREATE | Audit metrics collection |
| `backend/src/platform/alert_rules.yaml` | MODIFY | Add audit alert rules |
| `backend/src/platform/audit.py` | MODIFY | Integrate metrics/alerts |
| `backend/tests/monitoring/test_audit_alerts.py` | CREATE | Alert tests |
| `backend/tests/monitoring/test_audit_metrics.py` | CREATE | Metrics tests |

---

## Story 10.6 — Audit Log Access Controls (UI + API)

### User Story
> As a platform user, I should only see audit logs I'm authorized to see, so that sensitive operational data isn't leaked.

### Acceptance Criteria
- [ ] Tenant admins see only their tenant's logs
- [ ] Super admins see all tenants
- [ ] Agency users see only allowed_tenants[]
- [ ] UI enforces same rules as API
- [ ] Cross-tenant queries are blocked and logged

### Technical Design

#### 1. Access Control Service (`backend/src/services/audit_access_control.py`)

```python
"""
Audit log access control service.

Enforces RBAC on audit log access for both API and UI.
Shared logic ensures consistent enforcement.

Role-based access:
- SUPER_ADMIN: All tenants
- MERCHANT_ADMIN/VIEWER: Own tenant only
- AGENCY_ADMIN/VIEWER: allowed_tenants[] only
"""

from dataclasses import dataclass
from typing import Optional, List, Set

@dataclass
class AuditAccessContext:
    """Context for audit log access control."""
    user_id: str
    role: str
    tenant_id: str  # User's primary tenant
    allowed_tenants: Set[str]  # For agency roles
    is_super_admin: bool

class AuditAccessControl:
    """
    Enforces access control on audit log queries.

    Key methods:
    - can_access_tenant(): Check if user can view tenant's logs
    - filter_query(): Add tenant filters to SQLAlchemy query
    - validate_export(): Check export permissions
    """

    def __init__(self, context: AuditAccessContext):
        self.context = context

    def can_access_tenant(self, target_tenant_id: str) -> bool:
        """
        Check if user can access audit logs for a tenant.

        Rules:
        1. Super admins can access all tenants
        2. Agency roles can access allowed_tenants[]
        3. Merchant roles can only access their own tenant
        """
        if self.context.is_super_admin:
            return True

        if target_tenant_id == self.context.tenant_id:
            return True

        if target_tenant_id in self.context.allowed_tenants:
            return True

        return False

    def get_accessible_tenants(self) -> Optional[Set[str]]:
        """
        Get set of tenants user can access.

        Returns None for super admins (unrestricted).
        """
        if self.context.is_super_admin:
            return None  # No restriction

        accessible = {self.context.tenant_id}
        accessible.update(self.context.allowed_tenants)
        return accessible

    def filter_query(self, query, tenant_id_column):
        """
        Add tenant filter to SQLAlchemy query.

        Args:
            query: SQLAlchemy query object
            tenant_id_column: Column to filter on

        Returns:
            Filtered query
        """
        accessible = self.get_accessible_tenants()

        if accessible is None:
            # Super admin - no filter
            return query

        if len(accessible) == 1:
            return query.filter(tenant_id_column == list(accessible)[0])

        return query.filter(tenant_id_column.in_(accessible))

    def validate_access(self, target_tenant_id: str) -> None:
        """
        Validate access and raise if denied.

        Raises:
            PermissionDenied: If access is not allowed

        Side effects:
            - Logs cross-tenant access attempt if denied
            - Triggers alert for suspicious patterns
        """
        if not self.can_access_tenant(target_tenant_id):
            # Log the attempt
            log_cross_tenant_access_attempt(
                user_id=self.context.user_id,
                requesting_tenant=self.context.tenant_id,
                target_tenant=target_tenant_id,
            )

            raise PermissionDenied(
                f"Access denied to tenant {target_tenant_id}"
            )


def get_audit_access_context(request: Request) -> AuditAccessContext:
    """
    Extract audit access context from request.

    Uses existing tenant_context and RBAC utilities.
    """
    from src.platform.tenant_context import get_tenant_context
    from src.platform.rbac import has_permission, is_super_admin
    from src.constants.permissions import ROLE_PERMISSIONS

    tenant_ctx = get_tenant_context(request)

    return AuditAccessContext(
        user_id=tenant_ctx.user_id,
        role=tenant_ctx.role,
        tenant_id=tenant_ctx.tenant_id,
        allowed_tenants=set(tenant_ctx.allowed_tenants or []),
        is_super_admin=is_super_admin(tenant_ctx),
    )
```

#### 2. API Integration (`backend/src/api/routes/audit.py`)

Update existing audit endpoints to use access control:

```python
@router.get("/logs")
async def list_audit_logs(
    request: Request,
    tenant_id: Optional[str] = None,  # Optional filter for super admins
    # ... other params ...
    db: Session = Depends(get_db),
):
    """
    List audit logs with RBAC enforcement.

    - Tenant admins: Only their tenant's logs
    - Agency users: Only allowed_tenants[]
    - Super admins: All tenants (can filter by tenant_id)
    """
    access_ctx = get_audit_access_context(request)
    access_control = AuditAccessControl(access_ctx)

    # If specific tenant requested, validate access
    if tenant_id:
        access_control.validate_access(tenant_id)
        query = query.filter(AuditLog.tenant_id == tenant_id)
    else:
        # Apply automatic tenant filtering
        query = access_control.filter_query(query, AuditLog.tenant_id)

    # ... rest of endpoint ...


@router.get("/logs/{log_id}")
async def get_audit_log(
    request: Request,
    log_id: str,
    db: Session = Depends(get_db),
):
    """Get single audit log with access validation."""
    access_ctx = get_audit_access_context(request)
    access_control = AuditAccessControl(access_ctx)

    log = db.query(AuditLog).filter(AuditLog.id == log_id).first()
    if not log:
        raise HTTPException(404, "Audit log not found")

    # Validate access to this log's tenant
    access_control.validate_access(log.tenant_id)

    return log
```

#### 3. UI Integration

The UI should call the same API endpoints. Access control is enforced server-side, but the UI can:

1. **Hide tenant selector** for non-super-admins
2. **Pre-filter dropdown** to only show accessible tenants
3. **Handle 403 errors** gracefully with user-friendly messages

Frontend changes (if applicable):
```typescript
// hooks/useAuditAccess.ts
export function useAuditAccess() {
  const { user } = useAuth();

  const canViewAllTenants = user.role === 'SUPER_ADMIN';
  const accessibleTenants = canViewAllTenants
    ? null  // All tenants
    : [user.tenant_id, ...(user.allowed_tenants || [])];

  return { canViewAllTenants, accessibleTenants };
}
```

#### 4. Cross-Tenant Access Logging

When access is denied, log it as an audit event AND check for alert threshold:

```python
def log_cross_tenant_access_attempt(
    user_id: str,
    requesting_tenant: str,
    target_tenant: str,
) -> None:
    """
    Log cross-tenant access attempt.

    This is a security event that:
    1. Creates an audit log entry
    2. Increments cross-tenant attempt counter
    3. May trigger an alert if threshold exceeded
    """
    # Log to audit system
    log_system_audit_event_sync(
        db=get_db_session(),
        tenant_id=requesting_tenant,
        action=AuditAction.CROSS_TENANT_ACCESS_DENIED,
        metadata={
            "target_tenant": target_tenant,
            "user_id": user_id,
        },
        outcome=AuditOutcome.DENIED,
    )

    # Check alert threshold
    asyncio.create_task(
        get_audit_alert_manager().check_cross_tenant_threshold(
            requesting_tenant=requesting_tenant,
            user_id=user_id,
        )
    )
```

#### 5. New Audit Actions

Add to `AuditAction` enum:
```python
# Access control events (Story 10.6)
AUDIT_LOG_ACCESSED = "audit.log.accessed"
AUDIT_LOG_QUERY_DENIED = "audit.log.query_denied"
CROSS_TENANT_ACCESS_DENIED = "audit.cross_tenant.denied"
```

#### 6. Files to Create/Modify

| File | Action | Description |
|------|--------|-------------|
| `backend/src/services/audit_access_control.py` | CREATE | Access control service |
| `backend/src/api/routes/audit.py` | MODIFY | Add RBAC to endpoints |
| `backend/src/platform/audit.py` | MODIFY | Add access control actions |
| `backend/tests/services/test_audit_access_control.py` | CREATE | Access control tests |
| `backend/tests/api/test_audit_rbac.py` | CREATE | API RBAC tests |

---

## Implementation Order

### Phase 1: Story 10.6 (Access Controls) — Foundation
**Why first:** Other stories depend on proper access control being in place.

1. Create `audit_access_control.py` service
2. Update API endpoints with RBAC
3. Add cross-tenant logging
4. Write tests

### Phase 2: Story 10.5 (Monitoring) — Observability
**Why second:** Needed to monitor the retention job.

1. Create `audit_metrics.py`
2. Create `audit_alerts.py`
3. Update `alert_rules.yaml`
4. Integrate metrics into audit.py
5. Write tests

### Phase 3: Story 10.4 (Retention) — Data Lifecycle
**Why last:** Depends on monitoring for visibility into job execution.

1. Create `config/retention.py`
2. Create database migration for deletion function
3. Create `audit_retention_job.py`
4. Add audit actions for retention events
5. Write tests
6. Set up cron schedule

---

## Testing Strategy

### Unit Tests
- Retention calculation logic
- Access control permission checks
- Alert threshold logic
- Metrics emission

### Integration Tests
- End-to-end retention job execution
- API RBAC enforcement
- Cross-tenant access blocking
- Alert triggering

### Security Tests
- Attempt to bypass tenant filtering
- Verify cross-tenant attempts are logged
- Verify super admin override works correctly

---

## Rollout Plan

### Stage 1: Dev/Staging
1. Deploy all code changes
2. Run retention job manually (dry-run mode)
3. Verify access controls work correctly
4. Test alert channels

### Stage 2: Production (Canary)
1. Enable monitoring/metrics first
2. Enable access controls
3. Run retention job in dry-run mode
4. Review deletion candidates

### Stage 3: Production (Full)
1. Enable retention job with actual deletion
2. Monitor metrics dashboards
3. Verify alert channels receive test alerts

---

## Open Questions / Human Decisions Needed

| Question | Default | Owner |
|----------|---------|-------|
| Retention period per plan? | free=30d, starter=90d, pro=180d, enterprise=365d | Product |
| Retention job schedule? | Daily at 02:00 UTC | Platform |
| Alert thresholds? | 5 failures/5min, 1 cross-tenant attempt | Security |
| Escalation channels? | #security-alerts, #platform-alerts | DevOps |
| Dry-run period before live deletion? | 1 week | Platform |

---

## Risks & Mitigations

| Risk | Impact | Mitigation |
|------|--------|------------|
| Accidental deletion of needed logs | High | Dry-run mode, confirmation period, backups |
| Alert fatigue | Medium | Careful threshold tuning, cooldown periods |
| Cross-tenant bypass | Critical | Defense in depth (API + DB level), audit logging |
| Retention job fails silently | High | Monitoring + alerts on job completion |

---

## Success Metrics

- **Retention:** Zero logs older than retention period after 1 week
- **Monitoring:** <5 min MTTR for audit system issues
- **Access Controls:** Zero cross-tenant data leaks, 100% attempt logging
