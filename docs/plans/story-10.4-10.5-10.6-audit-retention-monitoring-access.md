# Implementation Plan: Stories 10.4, 10.5, 10.6
## Audit Log Retention, Monitoring & Access Controls

**Stories:** 10.4 (Retention Enforcement), 10.5 (Monitoring & Alerting), 10.6 (Access Controls)
**Total Story Points:** 8 SP (3 + 3 + 2)
**Dependencies:** Stories 10.1, 10.2, 10.3 (completed)

---

## Executive Summary

This plan covers the final three stories of the audit logging epic, broken into 5 implementation phases:

| Phase | Description | Story | Est. Effort |
|-------|-------------|-------|-------------|
| 1 | Access Control Service | 10.6 | 0.5 day |
| 2 | API RBAC Integration | 10.6 | 0.5 day |
| 3 | Audit Metrics | 10.5 | 0.5 day |
| 4 | Audit Alerts | 10.5 | 0.5 day |
| 5 | Retention Enforcement | 10.4 | 1 day |

---

# PHASE 1: Access Control Service (Story 10.6)

## Objective
Create the core access control service that enforces tenant isolation on audit log queries. This is foundational—all other phases depend on it.

## Files to Create

### 1.1 `backend/src/services/audit_access_control.py` (CREATE)

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
from typing import Optional, Set
from fastapi import Request, HTTPException

from src.platform.tenant_context import get_tenant_context
from src.constants.permissions import Roles


@dataclass
class AuditAccessContext:
    """Context for audit log access control."""
    user_id: str
    role: str
    tenant_id: str
    allowed_tenants: Set[str]
    is_super_admin: bool


class AuditAccessControl:
    """Enforces access control on audit log queries."""

    def __init__(self, context: AuditAccessContext):
        self.context = context

    def can_access_tenant(self, target_tenant_id: str) -> bool:
        """Check if user can access audit logs for a tenant."""
        if self.context.is_super_admin:
            return True
        if target_tenant_id == self.context.tenant_id:
            return True
        if target_tenant_id in self.context.allowed_tenants:
            return True
        return False

    def get_accessible_tenants(self) -> Optional[Set[str]]:
        """Get set of tenants user can access. None = unrestricted."""
        if self.context.is_super_admin:
            return None
        accessible = {self.context.tenant_id}
        accessible.update(self.context.allowed_tenants)
        return accessible

    def filter_query(self, query, tenant_id_column):
        """Add tenant filter to SQLAlchemy query."""
        accessible = self.get_accessible_tenants()
        if accessible is None:
            return query
        if len(accessible) == 1:
            return query.filter(tenant_id_column == list(accessible)[0])
        return query.filter(tenant_id_column.in_(accessible))

    def validate_access(self, target_tenant_id: str) -> None:
        """Validate access and raise HTTPException if denied."""
        if not self.can_access_tenant(target_tenant_id):
            raise HTTPException(
                status_code=403,
                detail=f"Access denied to tenant {target_tenant_id}"
            )


def get_audit_access_context(request: Request) -> AuditAccessContext:
    """Extract audit access context from request."""
    tenant_ctx = get_tenant_context(request)

    is_super_admin = tenant_ctx.role in (
        Roles.SUPER_ADMIN.value,
        "SUPER_ADMIN",
    )

    return AuditAccessContext(
        user_id=tenant_ctx.user_id,
        role=tenant_ctx.role,
        tenant_id=tenant_ctx.tenant_id,
        allowed_tenants=set(tenant_ctx.allowed_tenants or []),
        is_super_admin=is_super_admin,
    )
```

### 1.2 `backend/tests/services/test_audit_access_control.py` (CREATE)

```python
"""Unit tests for audit access control service."""

import pytest
from src.services.audit_access_control import (
    AuditAccessContext,
    AuditAccessControl,
)


class TestAuditAccessControl:
    """Test suite for AuditAccessControl."""

    def test_super_admin_can_access_any_tenant(self):
        """Super admin should access all tenants."""
        ctx = AuditAccessContext(
            user_id="user-1",
            role="SUPER_ADMIN",
            tenant_id="tenant-1",
            allowed_tenants=set(),
            is_super_admin=True,
        )
        ac = AuditAccessControl(ctx)

        assert ac.can_access_tenant("tenant-1") is True
        assert ac.can_access_tenant("tenant-999") is True
        assert ac.get_accessible_tenants() is None

    def test_merchant_can_only_access_own_tenant(self):
        """Merchant should only access their own tenant."""
        ctx = AuditAccessContext(
            user_id="user-1",
            role="MERCHANT_ADMIN",
            tenant_id="tenant-1",
            allowed_tenants=set(),
            is_super_admin=False,
        )
        ac = AuditAccessControl(ctx)

        assert ac.can_access_tenant("tenant-1") is True
        assert ac.can_access_tenant("tenant-2") is False

    def test_agency_can_access_allowed_tenants(self):
        """Agency should access allowed_tenants list."""
        ctx = AuditAccessContext(
            user_id="user-1",
            role="AGENCY_ADMIN",
            tenant_id="agency-1",
            allowed_tenants={"tenant-1", "tenant-2"},
            is_super_admin=False,
        )
        ac = AuditAccessControl(ctx)

        assert ac.can_access_tenant("agency-1") is True
        assert ac.can_access_tenant("tenant-1") is True
        assert ac.can_access_tenant("tenant-2") is True
        assert ac.can_access_tenant("tenant-3") is False

    def test_validate_access_raises_on_denial(self):
        """validate_access should raise HTTPException on denial."""
        ctx = AuditAccessContext(
            user_id="user-1",
            role="MERCHANT_ADMIN",
            tenant_id="tenant-1",
            allowed_tenants=set(),
            is_super_admin=False,
        )
        ac = AuditAccessControl(ctx)

        # Should not raise
        ac.validate_access("tenant-1")

        # Should raise
        with pytest.raises(Exception) as exc_info:
            ac.validate_access("tenant-2")
        assert exc_info.value.status_code == 403
```

## Tasks

- [ ] Create `audit_access_control.py` with `AuditAccessContext` dataclass
- [ ] Implement `AuditAccessControl.can_access_tenant()`
- [ ] Implement `AuditAccessControl.get_accessible_tenants()`
- [ ] Implement `AuditAccessControl.filter_query()`
- [ ] Implement `AuditAccessControl.validate_access()`
- [ ] Implement `get_audit_access_context()` helper
- [ ] Create unit tests for all access control scenarios
- [ ] Run tests and verify passing

## Definition of Done

- [ ] All unit tests pass
- [ ] Access control logic handles: super admin, merchant, agency roles
- [ ] `filter_query()` correctly filters SQLAlchemy queries
- [ ] No linting errors

---

# PHASE 2: API RBAC Integration (Story 10.6)

## Objective
Integrate access control into existing audit API endpoints and add cross-tenant access logging.

## Dependencies
- Phase 1 complete

## Files to Modify

### 2.1 `backend/src/platform/audit.py` (MODIFY)

Add new audit actions for access control:

```python
# Add to AuditAction enum:

# Access control events (Story 10.6)
AUDIT_LOG_ACCESSED = "audit.log.accessed"
AUDIT_LOG_QUERY_DENIED = "audit.log.query_denied"
CROSS_TENANT_ACCESS_DENIED = "audit.cross_tenant.denied"
```

### 2.2 `backend/src/api/routes/audit.py` (MODIFY)

Update endpoints with RBAC:

```python
from src.services.audit_access_control import (
    AuditAccessControl,
    get_audit_access_context,
)

@router.get("/logs")
async def list_audit_logs(
    request: Request,
    tenant_id: Optional[str] = None,
    action: Optional[str] = None,
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
    limit: int = Query(default=100, le=1000),
    offset: int = 0,
    db: Session = Depends(get_db),
):
    """List audit logs with RBAC enforcement."""
    access_ctx = get_audit_access_context(request)
    access_control = AuditAccessControl(access_ctx)

    query = db.query(AuditLog)

    # Apply tenant filtering
    if tenant_id:
        access_control.validate_access(tenant_id)
        query = query.filter(AuditLog.tenant_id == tenant_id)
    else:
        query = access_control.filter_query(query, AuditLog.tenant_id)

    # Apply other filters...
    if action:
        query = query.filter(AuditLog.action == action)
    if start_date:
        query = query.filter(AuditLog.timestamp >= start_date)
    if end_date:
        query = query.filter(AuditLog.timestamp <= end_date)

    query = query.order_by(AuditLog.timestamp.desc())
    query = query.offset(offset).limit(limit)

    return query.all()


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

    access_control.validate_access(log.tenant_id)
    return log
```

### 2.3 `backend/src/services/audit_access_control.py` (MODIFY)

Add cross-tenant logging function:

```python
def log_cross_tenant_access_attempt(
    db: Session,
    user_id: str,
    requesting_tenant: str,
    target_tenant: str,
    correlation_id: Optional[str] = None,
) -> None:
    """Log cross-tenant access attempt as security event."""
    from src.platform.audit import (
        AuditAction, AuditOutcome, log_system_audit_event_sync
    )

    log_system_audit_event_sync(
        db=db,
        tenant_id=requesting_tenant,
        action=AuditAction.CROSS_TENANT_ACCESS_DENIED,
        metadata={
            "target_tenant": target_tenant,
            "user_id": user_id,
        },
        correlation_id=correlation_id,
        outcome=AuditOutcome.DENIED,
    )
```

## Files to Create

### 2.4 `backend/tests/api/test_audit_rbac.py` (CREATE)

```python
"""Integration tests for audit API RBAC."""

import pytest
from fastapi.testclient import TestClient


class TestAuditAPIRBAC:
    """Test RBAC enforcement on audit endpoints."""

    def test_merchant_sees_only_own_tenant_logs(self, client, merchant_token):
        """Merchant should only see their tenant's logs."""
        response = client.get(
            "/api/audit/logs",
            headers={"Authorization": f"Bearer {merchant_token}"}
        )
        assert response.status_code == 200
        for log in response.json():
            assert log["tenant_id"] == "merchant-tenant-id"

    def test_merchant_cannot_access_other_tenant(self, client, merchant_token):
        """Merchant should get 403 for other tenant."""
        response = client.get(
            "/api/audit/logs?tenant_id=other-tenant",
            headers={"Authorization": f"Bearer {merchant_token}"}
        )
        assert response.status_code == 403

    def test_super_admin_can_access_any_tenant(self, client, admin_token):
        """Super admin should access any tenant."""
        response = client.get(
            "/api/audit/logs?tenant_id=any-tenant",
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        assert response.status_code == 200

    def test_cross_tenant_attempt_is_logged(self, client, merchant_token, db):
        """Cross-tenant access attempt should create audit log."""
        response = client.get(
            "/api/audit/logs?tenant_id=other-tenant",
            headers={"Authorization": f"Bearer {merchant_token}"}
        )
        assert response.status_code == 403

        # Verify audit log was created
        # ... check db for CROSS_TENANT_ACCESS_DENIED event
```

## Tasks

- [ ] Add access control audit actions to `AuditAction` enum
- [ ] Update `GET /api/audit/logs` with RBAC filtering
- [ ] Update `GET /api/audit/logs/{log_id}` with access validation
- [ ] Update `GET /api/audit/summary` with RBAC filtering
- [ ] Update `GET /api/audit/correlation/{id}` with RBAC filtering
- [ ] Add `log_cross_tenant_access_attempt()` function
- [ ] Create integration tests for RBAC scenarios
- [ ] Test with merchant, agency, and super admin roles

## Definition of Done

- [ ] All audit endpoints enforce tenant isolation
- [ ] Cross-tenant access attempts return 403
- [ ] Cross-tenant attempts are logged as audit events
- [ ] Super admin can access all tenants
- [ ] Agency users can access allowed_tenants only
- [ ] All tests pass

---

# PHASE 3: Audit Metrics (Story 10.5)

## Objective
Add metrics collection for audit system observability.

## Dependencies
- Phase 1-2 complete (access control needed for metric labels)

## Files to Create

### 3.1 `backend/src/monitoring/audit_metrics.py` (CREATE)

```python
"""
Audit system metrics for monitoring dashboards.

Emits metrics compatible with Prometheus/StatsD.
"""

import logging
from typing import Optional
from datetime import datetime, timezone
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class AuditMetricsState:
    """In-memory metrics state (replace with Prometheus in production)."""
    events_total: dict = field(default_factory=dict)
    failures_total: int = 0
    fallback_total: int = 0
    retention_deleted: int = 0


class AuditMetrics:
    """
    Collects and emits audit system metrics.

    Metrics:
    - audit_events_total: Counter by action, outcome, source
    - audit_logging_failures_total: Counter of write failures
    - audit_fallback_events_total: Counter of fallback writes
    - audit_query_latency_seconds: Histogram of query times
    - audit_retention_deleted_total: Counter of deleted records
    """

    _instance: Optional["AuditMetrics"] = None

    def __init__(self):
        self._state = AuditMetricsState()

    @classmethod
    def get_instance(cls) -> "AuditMetrics":
        """Get singleton instance."""
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def record_audit_event(
        self,
        action: str,
        outcome: str,
        tenant_id: str,
        source: str,
    ) -> None:
        """Record an audit event for metrics."""
        key = f"{action}:{outcome}:{source}"
        self._state.events_total[key] = self._state.events_total.get(key, 0) + 1

        logger.debug(
            "Audit metric recorded",
            extra={
                "metric": "audit_events_total",
                "action": action,
                "outcome": outcome,
                "source": source,
                "tenant_id": tenant_id,
            }
        )

    def record_logging_failure(
        self,
        error_type: str,
        tenant_id: Optional[str] = None,
    ) -> None:
        """Record an audit logging failure."""
        self._state.failures_total += 1

        logger.warning(
            "Audit logging failure",
            extra={
                "metric": "audit_logging_failures_total",
                "error_type": error_type,
                "tenant_id": tenant_id,
            }
        )

    def record_fallback_event(self, tenant_id: Optional[str] = None) -> None:
        """Record an event written to fallback logger."""
        self._state.fallback_total += 1

        logger.warning(
            "Audit fallback event",
            extra={
                "metric": "audit_fallback_events_total",
                "tenant_id": tenant_id,
            }
        )

    def record_retention_deletion(self, count: int, tenant_id: str) -> None:
        """Record records deleted by retention job."""
        self._state.retention_deleted += count

        logger.info(
            "Audit retention deletion",
            extra={
                "metric": "audit_retention_deleted_total",
                "count": count,
                "tenant_id": tenant_id,
            }
        )

    def get_stats(self) -> dict:
        """Get current metrics state (for testing/debugging)."""
        return {
            "events_total": dict(self._state.events_total),
            "failures_total": self._state.failures_total,
            "fallback_total": self._state.fallback_total,
            "retention_deleted": self._state.retention_deleted,
        }


def get_audit_metrics() -> AuditMetrics:
    """Get the audit metrics singleton."""
    return AuditMetrics.get_instance()
```

### 3.2 `backend/src/platform/audit.py` (MODIFY)

Integrate metrics into write functions:

```python
# Add import at top:
from src.monitoring.audit_metrics import get_audit_metrics

# Modify write_audit_log_sync():
def write_audit_log_sync(db: Session, event: AuditEvent) -> Optional[AuditLog]:
    """Write an audit event to the database with metrics."""
    metrics = get_audit_metrics()
    audit_id = str(uuid.uuid4())

    try:
        audit_log = AuditLog(id=audit_id, **event.to_dict())
        db.add(audit_log)
        db.commit()

        # Record success metric
        metrics.record_audit_event(
            action=event.action.value if isinstance(event.action, AuditAction) else event.action,
            outcome=event.outcome.value if isinstance(event.outcome, AuditOutcome) else event.outcome,
            tenant_id=event.tenant_id,
            source=event.source,
        )

        logger.info("Audit event recorded", extra={...})
        return audit_log

    except Exception as e:
        # Record failure metric
        metrics.record_logging_failure(
            error_type=type(e).__name__,
            tenant_id=event.tenant_id,
        )

        try:
            db.rollback()
        except Exception:
            pass

        # Record fallback metric
        metrics.record_fallback_event(tenant_id=event.tenant_id)
        _write_fallback_log(event, audit_id, str(e))
        return None
```

### 3.3 `backend/tests/monitoring/test_audit_metrics.py` (CREATE)

```python
"""Unit tests for audit metrics."""

import pytest
from src.monitoring.audit_metrics import AuditMetrics


class TestAuditMetrics:
    """Test suite for AuditMetrics."""

    def test_record_audit_event_increments_counter(self):
        """Recording event should increment counter."""
        metrics = AuditMetrics()

        metrics.record_audit_event(
            action="auth.login",
            outcome="success",
            tenant_id="tenant-1",
            source="api",
        )

        stats = metrics.get_stats()
        assert stats["events_total"]["auth.login:success:api"] == 1

    def test_record_logging_failure_increments_counter(self):
        """Recording failure should increment counter."""
        metrics = AuditMetrics()

        metrics.record_logging_failure(
            error_type="DatabaseError",
            tenant_id="tenant-1",
        )

        stats = metrics.get_stats()
        assert stats["failures_total"] == 1

    def test_record_retention_deletion(self):
        """Recording retention deletion should track count."""
        metrics = AuditMetrics()

        metrics.record_retention_deletion(count=100, tenant_id="tenant-1")
        metrics.record_retention_deletion(count=50, tenant_id="tenant-2")

        stats = metrics.get_stats()
        assert stats["retention_deleted"] == 150
```

## Tasks

- [ ] Create `audit_metrics.py` with `AuditMetrics` class
- [ ] Implement `record_audit_event()` method
- [ ] Implement `record_logging_failure()` method
- [ ] Implement `record_fallback_event()` method
- [ ] Implement `record_retention_deletion()` method
- [ ] Integrate metrics into `write_audit_log_sync()`
- [ ] Integrate metrics into `_write_fallback_log()`
- [ ] Create unit tests for metrics
- [ ] Run tests and verify passing

## Definition of Done

- [ ] Metrics are recorded for every audit event write
- [ ] Failures are tracked separately from successes
- [ ] Fallback events are tracked
- [ ] All unit tests pass

---

# PHASE 4: Audit Alerts (Story 10.5)

## Objective
Add alerting for audit system failures and security events.

## Dependencies
- Phase 3 complete (metrics needed for threshold tracking)

## Files to Create

### 4.1 `backend/src/monitoring/audit_alerts.py` (CREATE)

```python
"""
Audit system alerting.

Extends AlertManager pattern for audit-specific alerts.
"""

import logging
from enum import Enum
from typing import Optional
from datetime import datetime, timezone, timedelta
from dataclasses import dataclass, field

from src.monitoring.alerts import Alert, AlertSeverity, AlertManager, get_alert_manager

logger = logging.getLogger(__name__)


class AuditAlertType(str, Enum):
    """Types of audit system alerts."""
    # Logging failures
    AUDIT_LOGGING_FAILURE = "audit_logging_failure"
    AUDIT_FALLBACK_ACTIVATED = "audit_fallback_activated"

    # Security alerts
    CROSS_TENANT_ACCESS_ATTEMPT = "cross_tenant_access_attempt"
    EXCESSIVE_DENIED_QUERIES = "excessive_denied_queries"

    # Retention alerts
    RETENTION_JOB_FAILED = "retention_job_failed"
    RETENTION_JOB_COMPLETED = "retention_job_completed"


@dataclass
class AuditAlertThresholds:
    """Configurable alert thresholds."""
    logging_failures_per_5min: int = 5
    cross_tenant_attempts_per_hour: int = 1
    denied_queries_per_10min: int = 50


class AuditAlertManager:
    """Manages audit-specific alerts."""

    _instance: Optional["AuditAlertManager"] = None

    def __init__(self):
        self._alert_manager = get_alert_manager()
        self._thresholds = AuditAlertThresholds()
        self._failure_counts: dict[str, list[datetime]] = {}
        self._cross_tenant_counts: dict[str, list[datetime]] = {}

    @classmethod
    def get_instance(cls) -> "AuditAlertManager":
        """Get singleton instance."""
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    async def check_and_alert_logging_failure(
        self,
        error: str,
        correlation_id: str,
        tenant_id: Optional[str] = None,
    ) -> bool:
        """Check failure threshold and alert if exceeded."""
        now = datetime.now(timezone.utc)
        window = timedelta(minutes=5)

        # Track failures
        key = tenant_id or "global"
        if key not in self._failure_counts:
            self._failure_counts[key] = []

        # Clean old entries
        self._failure_counts[key] = [
            ts for ts in self._failure_counts[key]
            if ts > now - window
        ]
        self._failure_counts[key].append(now)

        # Check threshold
        if len(self._failure_counts[key]) >= self._thresholds.logging_failures_per_5min:
            alert = Alert(
                alert_type=AuditAlertType.AUDIT_LOGGING_FAILURE,
                severity=AlertSeverity.CRITICAL,
                title="Audit Logging Failures Detected",
                message=f"Audit logging has failed {len(self._failure_counts[key])} times in 5 minutes",
                metadata={
                    "error": error,
                    "correlation_id": correlation_id,
                    "tenant_id": tenant_id,
                    "failure_count": len(self._failure_counts[key]),
                }
            )
            await self._alert_manager.send_alert(alert)
            return True

        return False

    async def alert_cross_tenant_access(
        self,
        requesting_tenant: str,
        target_tenant: str,
        user_id: str,
        correlation_id: str,
    ) -> None:
        """Alert on cross-tenant access attempt (always alerts)."""
        alert = Alert(
            alert_type=AuditAlertType.CROSS_TENANT_ACCESS_ATTEMPT,
            severity=AlertSeverity.CRITICAL,
            title="Cross-Tenant Access Attempt",
            message=f"User {user_id} from tenant {requesting_tenant} attempted to access tenant {target_tenant}",
            metadata={
                "requesting_tenant": requesting_tenant,
                "target_tenant": target_tenant,
                "user_id": user_id,
                "correlation_id": correlation_id,
            }
        )
        await self._alert_manager.send_alert(alert)

    async def alert_retention_job_failed(
        self,
        error: str,
        stats: dict,
    ) -> None:
        """Alert when retention job fails."""
        alert = Alert(
            alert_type=AuditAlertType.RETENTION_JOB_FAILED,
            severity=AlertSeverity.ERROR,
            title="Audit Retention Job Failed",
            message=f"Audit retention job failed: {error}",
            metadata={
                "error": error,
                **stats,
            }
        )
        await self._alert_manager.send_alert(alert)

    async def alert_retention_job_completed(
        self,
        stats: dict,
    ) -> None:
        """Alert when retention job completes (info level)."""
        alert = Alert(
            alert_type=AuditAlertType.RETENTION_JOB_COMPLETED,
            severity=AlertSeverity.INFO,
            title="Audit Retention Job Completed",
            message=f"Deleted {stats.get('total_deleted', 0)} audit logs",
            metadata=stats,
        )
        await self._alert_manager.send_alert(alert)


def get_audit_alert_manager() -> AuditAlertManager:
    """Get the audit alert manager singleton."""
    return AuditAlertManager.get_instance()
```

### 4.2 `backend/src/platform/alert_rules.yaml` (MODIFY)

Add audit alert rules section:

```yaml
# Add to existing alert_rules.yaml:

audit_alerts:
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

  cross_tenant_access:
    severity: critical
    threshold: 1
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

  retention_job_failed:
    severity: high
    message: "Audit retention job failed"
    escalation:
      - slack: "#platform-alerts"
      - pagerduty: platform-oncall
```

### 4.3 `backend/tests/monitoring/test_audit_alerts.py` (CREATE)

```python
"""Unit tests for audit alerts."""

import pytest
from unittest.mock import AsyncMock, patch
from datetime import datetime, timezone

from src.monitoring.audit_alerts import AuditAlertManager, AuditAlertType


class TestAuditAlertManager:
    """Test suite for AuditAlertManager."""

    @pytest.mark.asyncio
    async def test_logging_failure_alerts_after_threshold(self):
        """Should alert after 5 failures in 5 minutes."""
        manager = AuditAlertManager()
        manager._alert_manager = AsyncMock()

        # First 4 failures should not alert
        for i in range(4):
            result = await manager.check_and_alert_logging_failure(
                error="DB error",
                correlation_id=f"corr-{i}",
                tenant_id="tenant-1",
            )
            assert result is False

        # 5th failure should alert
        result = await manager.check_and_alert_logging_failure(
            error="DB error",
            correlation_id="corr-5",
            tenant_id="tenant-1",
        )
        assert result is True
        manager._alert_manager.send_alert.assert_called_once()

    @pytest.mark.asyncio
    async def test_cross_tenant_access_always_alerts(self):
        """Cross-tenant access should always trigger alert."""
        manager = AuditAlertManager()
        manager._alert_manager = AsyncMock()

        await manager.alert_cross_tenant_access(
            requesting_tenant="tenant-1",
            target_tenant="tenant-2",
            user_id="user-1",
            correlation_id="corr-1",
        )

        manager._alert_manager.send_alert.assert_called_once()
        alert = manager._alert_manager.send_alert.call_args[0][0]
        assert alert.alert_type == AuditAlertType.CROSS_TENANT_ACCESS_ATTEMPT
```

## Tasks

- [ ] Create `audit_alerts.py` with `AuditAlertManager` class
- [ ] Implement `check_and_alert_logging_failure()` with threshold
- [ ] Implement `alert_cross_tenant_access()` (always alerts)
- [ ] Implement `alert_retention_job_failed()`
- [ ] Implement `alert_retention_job_completed()`
- [ ] Add audit alert rules to `alert_rules.yaml`
- [ ] Integrate alerts into `write_audit_log_sync()` failure path
- [ ] Integrate alerts into access control denial path
- [ ] Create unit tests for alert logic
- [ ] Run tests and verify passing

## Definition of Done

- [ ] Logging failures alert after threshold exceeded
- [ ] Cross-tenant access attempts always alert
- [ ] Retention job failures alert
- [ ] Alert rules configured in YAML
- [ ] All unit tests pass

---

# PHASE 5: Retention Enforcement (Story 10.4)

## Objective
Implement hard delete of audit logs past retention window via daily scheduled job.

## Dependencies
- Phase 1-4 complete (access control, metrics, alerts all needed)

## Human Decisions Required (Before Starting)

| Decision | Options | Default |
|----------|---------|---------|
| Retention per plan | free=30d, starter=90d, pro=180d, enterprise=365d | Use defaults |
| Job schedule | Daily at 02:00 UTC | 02:00 UTC |
| Dry-run period | 1 week before live deletion | 1 week |

## Files to Create

### 5.1 `backend/src/config/retention.py` (CREATE)

```python
"""
Audit log retention configuration.

Retention periods are configurable per billing plan.
"""

import os
from typing import Dict

# Default retention periods per plan (in days)
PLAN_RETENTION_DEFAULTS: Dict[str, int] = {
    "free": 30,
    "starter": 90,
    "professional": 180,
    "enterprise": 365,
}

# Fallback for unknown plans
DEFAULT_RETENTION_DAYS = 90

# Compliance constraints
MINIMUM_RETENTION_DAYS = 30
MAXIMUM_RETENTION_DAYS = 730  # 2 years

# Batch size for deletion (avoid long transactions)
DELETION_BATCH_SIZE = int(os.getenv("AUDIT_DELETION_BATCH_SIZE", "1000"))

# Job configuration
RETENTION_JOB_SCHEDULE = os.getenv("AUDIT_RETENTION_SCHEDULE", "0 2 * * *")

# Dry-run mode (set to "false" to enable actual deletion)
RETENTION_DRY_RUN = os.getenv("AUDIT_RETENTION_DRY_RUN", "true").lower() == "true"


def get_retention_days(plan_id: str) -> int:
    """Get retention period for a billing plan."""
    days = PLAN_RETENTION_DEFAULTS.get(plan_id, DEFAULT_RETENTION_DAYS)
    return max(MINIMUM_RETENTION_DAYS, min(days, MAXIMUM_RETENTION_DAYS))
```

### 5.2 `backend/migrations/xxx_audit_retention_function.sql` (CREATE)

```sql
-- Migration: Add audit log retention deletion function
-- This function bypasses the immutability trigger for retention purposes only

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
        WITH to_delete AS (
            SELECT id FROM audit_logs
            WHERE tenant_id = p_tenant_id
            AND timestamp < p_cutoff_date
            LIMIT p_batch_size
            FOR UPDATE SKIP LOCKED
        )
        DELETE FROM audit_logs
        WHERE id IN (SELECT id FROM to_delete);

        GET DIAGNOSTICS batch_deleted = ROW_COUNT;
        deleted_count := deleted_count + batch_deleted;

        -- Commit each batch to avoid long locks
        COMMIT;

        EXIT WHEN batch_deleted < p_batch_size;
    END LOOP;

    -- Re-enable trigger
    SET session_replication_role = DEFAULT;

    RETURN deleted_count;
END;
$$ LANGUAGE plpgsql;

-- Add comment for documentation
COMMENT ON FUNCTION delete_expired_audit_logs IS
'Deletes audit logs older than cutoff date for retention enforcement.
Bypasses immutability trigger. Used only by retention job.';
```

### 5.3 `backend/src/workers/audit_retention_job.py` (CREATE)

```python
"""
Audit Log Retention Enforcement Job.

Runs daily to hard-delete audit logs past their retention window.
"""

import os
import sys
import logging
from datetime import datetime, timezone, timedelta
from typing import Dict, Optional

from sqlalchemy import text
from sqlalchemy.orm import Session

# Add backend to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.database.session import get_db_session_sync
from src.config.retention import (
    get_retention_days,
    DELETION_BATCH_SIZE,
    RETENTION_DRY_RUN,
    DEFAULT_RETENTION_DAYS,
)
from src.platform.audit import (
    AuditLog,
    AuditAction,
    AuditOutcome,
    log_system_audit_event_sync,
)
from src.monitoring.audit_metrics import get_audit_metrics
from src.monitoring.audit_alerts import get_audit_alert_manager

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class AuditRetentionJob:
    """
    Enforces audit log retention policy.

    Process:
    1. Query distinct tenant_ids from audit_logs
    2. For each tenant, get their plan's retention period
    3. Calculate cutoff date (now - retention_days)
    4. Delete logs older than cutoff in batches
    5. Log deletion stats as audit event
    """

    def __init__(self, db_session: Session, dry_run: bool = RETENTION_DRY_RUN):
        self.db = db_session
        self.dry_run = dry_run
        self.metrics = get_audit_metrics()
        self.stats = {
            "tenants_processed": 0,
            "total_deleted": 0,
            "dry_run": dry_run,
            "errors": [],
        }

    def get_distinct_tenants(self) -> list[str]:
        """Get list of distinct tenant IDs from audit logs."""
        result = self.db.execute(
            text("SELECT DISTINCT tenant_id FROM audit_logs")
        )
        return [row[0] for row in result]

    def get_tenant_plan(self, tenant_id: str) -> str:
        """Get billing plan for a tenant."""
        # Query tenant's subscription to get plan
        # For now, return default
        # TODO: Integrate with billing system
        return "professional"

    def count_expired_logs(self, tenant_id: str, cutoff_date: datetime) -> int:
        """Count logs that would be deleted."""
        result = self.db.execute(
            text("""
                SELECT COUNT(*) FROM audit_logs
                WHERE tenant_id = :tenant_id
                AND timestamp < :cutoff_date
            """),
            {"tenant_id": tenant_id, "cutoff_date": cutoff_date}
        )
        return result.scalar() or 0

    def delete_expired_logs(self, tenant_id: str, cutoff_date: datetime) -> int:
        """Delete audit logs older than cutoff_date for tenant."""
        if self.dry_run:
            count = self.count_expired_logs(tenant_id, cutoff_date)
            logger.info(
                f"[DRY RUN] Would delete {count} logs for tenant {tenant_id}"
            )
            return count

        # Use the database function for batch deletion
        result = self.db.execute(
            text("SELECT delete_expired_audit_logs(:tenant_id, :cutoff_date, :batch_size)"),
            {
                "tenant_id": tenant_id,
                "cutoff_date": cutoff_date,
                "batch_size": DELETION_BATCH_SIZE,
            }
        )
        deleted = result.scalar() or 0
        self.db.commit()

        # Record metric
        if deleted > 0:
            self.metrics.record_retention_deletion(deleted, tenant_id)

        return deleted

    def process_tenant(self, tenant_id: str) -> int:
        """Process retention for a single tenant."""
        try:
            plan = self.get_tenant_plan(tenant_id)
            retention_days = get_retention_days(plan)
            cutoff_date = datetime.now(timezone.utc) - timedelta(days=retention_days)

            deleted = self.delete_expired_logs(tenant_id, cutoff_date)

            logger.info(
                f"Processed tenant {tenant_id}: plan={plan}, "
                f"retention={retention_days}d, deleted={deleted}"
            )

            return deleted

        except Exception as e:
            error_msg = f"Error processing tenant {tenant_id}: {str(e)}"
            logger.error(error_msg, exc_info=True)
            self.stats["errors"].append(error_msg)
            return 0

    def run(self) -> Dict:
        """Execute retention enforcement for all tenants."""
        start_time = datetime.now(timezone.utc)
        logger.info(
            "Starting audit retention job",
            extra={"dry_run": self.dry_run}
        )

        # Log job start
        log_system_audit_event_sync(
            db=self.db,
            tenant_id="system",
            action=AuditAction.AUDIT_RETENTION_STARTED,
            metadata={"dry_run": self.dry_run},
            source="worker",
        )

        try:
            tenants = self.get_distinct_tenants()
            logger.info(f"Found {len(tenants)} tenants to process")

            for tenant_id in tenants:
                deleted = self.process_tenant(tenant_id)
                self.stats["total_deleted"] += deleted
                self.stats["tenants_processed"] += 1

            end_time = datetime.now(timezone.utc)
            self.stats["duration_seconds"] = (end_time - start_time).total_seconds()
            self.stats["completed_at"] = end_time.isoformat()

            # Log job completion
            log_system_audit_event_sync(
                db=self.db,
                tenant_id="system",
                action=AuditAction.AUDIT_RETENTION_COMPLETED,
                metadata=self.stats,
                source="worker",
            )

            logger.info("Audit retention job completed", extra=self.stats)
            return self.stats

        except Exception as e:
            self.stats["error"] = str(e)
            logger.error("Audit retention job failed", extra={"error": str(e)}, exc_info=True)

            # Log job failure
            log_system_audit_event_sync(
                db=self.db,
                tenant_id="system",
                action=AuditAction.AUDIT_RETENTION_FAILED,
                metadata=self.stats,
                source="worker",
                outcome=AuditOutcome.FAILURE,
            )

            # Send alert
            import asyncio
            asyncio.run(
                get_audit_alert_manager().alert_retention_job_failed(
                    error=str(e),
                    stats=self.stats,
                )
            )

            raise


def main():
    """Main entry point for retention job."""
    logger.info("Audit Retention Job starting")

    try:
        for session in get_db_session_sync():
            job = AuditRetentionJob(session)
            stats = job.run()
            logger.info("Audit Retention Job stats", extra=stats)
    except Exception as e:
        logger.error("Audit Retention Job failed", extra={"error": str(e)}, exc_info=True)
        sys.exit(1)

    logger.info("Audit Retention Job finished")


if __name__ == "__main__":
    main()
```

### 5.4 `backend/src/platform/audit.py` (MODIFY)

Add retention audit actions:

```python
# Add to AuditAction enum:

# Retention events (Story 10.4)
AUDIT_RETENTION_STARTED = "audit.retention.started"
AUDIT_RETENTION_COMPLETED = "audit.retention.completed"
AUDIT_RETENTION_FAILED = "audit.retention.failed"
```

### 5.5 `backend/tests/workers/test_audit_retention_job.py` (CREATE)

```python
"""Unit tests for audit retention job."""

import pytest
from datetime import datetime, timezone, timedelta
from unittest.mock import MagicMock, patch

from src.workers.audit_retention_job import AuditRetentionJob
from src.config.retention import get_retention_days


class TestAuditRetentionJob:
    """Test suite for AuditRetentionJob."""

    def test_get_retention_days_by_plan(self):
        """Should return correct retention for each plan."""
        assert get_retention_days("free") == 30
        assert get_retention_days("starter") == 90
        assert get_retention_days("professional") == 180
        assert get_retention_days("enterprise") == 365
        assert get_retention_days("unknown") == 90  # default

    def test_dry_run_does_not_delete(self):
        """Dry run should count but not delete."""
        mock_db = MagicMock()
        mock_db.execute.return_value.scalar.return_value = 100

        job = AuditRetentionJob(mock_db, dry_run=True)

        cutoff = datetime.now(timezone.utc) - timedelta(days=90)
        deleted = job.delete_expired_logs("tenant-1", cutoff)

        assert deleted == 100
        # Should not call the delete function
        calls = [str(c) for c in mock_db.execute.call_args_list]
        assert not any("delete_expired_audit_logs" in c for c in calls)

    def test_process_tenant_calculates_correct_cutoff(self):
        """Should calculate cutoff based on plan retention."""
        mock_db = MagicMock()
        mock_db.execute.return_value.scalar.return_value = 0

        job = AuditRetentionJob(mock_db, dry_run=True)
        job.get_tenant_plan = MagicMock(return_value="enterprise")

        job.process_tenant("tenant-1")

        # Verify cutoff is ~365 days ago
        job.get_tenant_plan.assert_called_with("tenant-1")

    def test_stats_accumulated_across_tenants(self):
        """Stats should accumulate across all tenants."""
        mock_db = MagicMock()
        mock_db.execute.return_value.scalar.return_value = 50
        mock_db.execute.return_value.__iter__ = lambda self: iter([
            ("tenant-1",), ("tenant-2",)
        ])

        job = AuditRetentionJob(mock_db, dry_run=True)
        stats = job.run()

        assert stats["tenants_processed"] == 2
        assert stats["total_deleted"] == 100  # 50 * 2
```

## Tasks

- [ ] Create `config/retention.py` with plan-based retention config
- [ ] Create database migration for `delete_expired_audit_logs` function
- [ ] Add retention audit actions to `AuditAction` enum
- [ ] Create `audit_retention_job.py` worker
- [ ] Implement `get_distinct_tenants()` method
- [ ] Implement `get_tenant_plan()` integration with billing
- [ ] Implement `count_expired_logs()` for dry-run
- [ ] Implement `delete_expired_logs()` using DB function
- [ ] Implement `run()` with audit logging and alerting
- [ ] Create unit tests for retention job
- [ ] Test dry-run mode
- [ ] Test actual deletion (in staging)
- [ ] Set up cron schedule

## Definition of Done

- [ ] Retention configuration is per-plan
- [ ] Dry-run mode works correctly
- [ ] Actual deletion works in staging
- [ ] Job self-audits (start, complete, fail events)
- [ ] Metrics recorded for deletions
- [ ] Alerts sent on failure
- [ ] All unit tests pass
- [ ] Cron schedule configured

---

# Summary: File Checklist

## Files to Create

| Phase | File | Status |
|-------|------|--------|
| 1 | `backend/src/services/audit_access_control.py` | ⬜ |
| 1 | `backend/tests/services/test_audit_access_control.py` | ⬜ |
| 2 | `backend/tests/api/test_audit_rbac.py` | ⬜ |
| 3 | `backend/src/monitoring/audit_metrics.py` | ⬜ |
| 3 | `backend/tests/monitoring/test_audit_metrics.py` | ⬜ |
| 4 | `backend/src/monitoring/audit_alerts.py` | ⬜ |
| 4 | `backend/tests/monitoring/test_audit_alerts.py` | ⬜ |
| 5 | `backend/src/config/retention.py` | ⬜ |
| 5 | `backend/migrations/xxx_audit_retention_function.sql` | ⬜ |
| 5 | `backend/src/workers/audit_retention_job.py` | ⬜ |
| 5 | `backend/tests/workers/test_audit_retention_job.py` | ⬜ |

## Files to Modify

| Phase | File | Changes |
|-------|------|---------|
| 2 | `backend/src/platform/audit.py` | Add access control actions |
| 2 | `backend/src/api/routes/audit.py` | Add RBAC to endpoints |
| 3 | `backend/src/platform/audit.py` | Integrate metrics |
| 4 | `backend/src/platform/alert_rules.yaml` | Add audit alert rules |
| 5 | `backend/src/platform/audit.py` | Add retention actions |

---

# Open Questions

| Question | Default | Status |
|----------|---------|--------|
| Retention period per plan? | free=30d, starter=90d, pro=180d, enterprise=365d | ⬜ Pending |
| Retention job schedule? | Daily at 02:00 UTC | ⬜ Pending |
| Alert thresholds? | 5 failures/5min, 1 cross-tenant | ⬜ Pending |
| Escalation channels? | #security-alerts, #platform-alerts | ⬜ Pending |
| Dry-run period? | 1 week | ⬜ Pending |
