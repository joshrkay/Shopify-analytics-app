# Codebase Review Plan

**Prepared by:** Senior Principal Engineer
**Date:** 2026-01-29
**Codebase:** Shopify Analytics App (Multi-tenant SaaS Platform)

---

## Executive Summary

This document outlines a systematic review plan for the Shopify Analytics App codebase. The review follows strict priority ordering:

1. **Security & Data Protection** (CRITICAL)
2. **Tests + Backward Compatibility** (No Regressions)
3. **Build/CI Health**
4. **Simplicity/Maintainability**
5. **Performance**
6. **Nice-to-haves**

### Codebase Overview

| Component | Technology | Location |
|-----------|------------|----------|
| Backend API | FastAPI (Python 3.11) | `/backend/` |
| Frontend | React 18 + TypeScript | `/frontend/` |
| Data Pipeline | dbt + PostgreSQL | `/analytics/` |
| Infrastructure | Render, Docker | `/render.yaml`, `/docker/` |
| CI/CD | GitHub Actions | `/.github/workflows/` |

**Test Coverage:** 68+ test files across platform, unit, integration, and regression categories.

---

## Phase 1: Security & Data Protection (CRITICAL)

### 1.1 Authentication & Authorization

**Files to Review:**
```
backend/src/platform/rbac.py
backend/src/platform/tenant_context.py
backend/src/api/routes/embed.py
backend/src/constants/permissions.py
backend/src/services/agency_service.py
```

**Checklist:**
- [ ] JWT validation is strict (signature, expiry, issuer)
- [ ] Every API endpoint has explicit authorization checks
- [ ] Tenant isolation enforced at middleware level
- [ ] Agency cross-tenant access follows least privilege
- [ ] No authorization bypass paths exist

**Tests to Verify:**
- `backend/src/tests/platform/test_rbac.py`
- `backend/src/tests/platform/test_tenant_isolation.py`
- `backend/src/tests/test_rbac_agency.py`

---

### 1.2 Secrets Management

**Files to Review:**
```
backend/src/platform/secrets.py
backend/src/api/routes/webhooks_shopify.py (HMAC verification)
.env.example
```

**Checklist:**
- [ ] Encryption key rotation mechanism exists
- [ ] Secrets never logged (check structlog usage)
- [ ] HMAC verification on all Shopify webhooks
- [ ] No hardcoded secrets in codebase
- [ ] Database credentials only via env vars

**Tests to Verify:**
- `backend/src/tests/platform/test_secrets.py`
- HMAC tests in `backend/src/tests/regression/helpers/hmac_signing.py`

**Commands:**
```bash
# Scan for potential secret leakage
grep -r "API_KEY\|SECRET\|PASSWORD\|TOKEN" backend/src --include="*.py" | grep -v "os.getenv\|settings\."
```

---

### 1.3 SQL Injection Prevention

**Files to Review:**
```
backend/src/repositories/
backend/src/services/ (all database queries)
db/rls/*.sql
```

**Checklist:**
- [ ] All queries use parameterized statements (SQLAlchemy ORM)
- [ ] No string concatenation for SQL
- [ ] RLS policies enforce tenant isolation at database level
- [ ] Raw SQL (if any) uses bound parameters

**Tests to Verify:**
- `backend/src/tests/platform/test_raw_rls.py` (SQL injection blocked)

---

### 1.4 Input Validation

**Files to Review:**
```
backend/src/api/schemas/
backend/src/api/routes/*.py (request validation)
```

**Checklist:**
- [ ] All API endpoints use Pydantic schemas for validation
- [ ] Webhook payloads validated before processing
- [ ] File uploads (if any) have type/size restrictions
- [ ] No eval() or exec() on user input

---

### 1.5 Audit Logging

**Files to Review:**
```
backend/src/platform/audit.py
backend/src/platform/audit_events.py
backend/src/monitoring/audit_alerting.py
backend/src/monitoring/audit_metrics.py
backend/src/jobs/audit_retention_job.py
```

**Checklist:**
- [ ] Security-sensitive operations logged (auth, data access, mutations)
- [ ] Audit logs cannot be tampered with
- [ ] Retention policy enforced
- [ ] PII not stored in audit logs (or properly redacted)
- [ ] Alert rules defined for suspicious patterns

**Tests to Verify:**
- `backend/src/tests/platform/test_audit.py`
- `backend/src/tests/monitoring/test_audit_alerts.py`
- `backend/src/tests/jobs/test_audit_retention_job.py`

---

## Phase 2: Tests + Backward Compatibility

### 2.1 Test Coverage Analysis

**Test Directories:**
```
backend/src/tests/
├── platform/       # 7 files - Security & multi-tenancy
├── unit/           # 21 files - Core business logic
├── integration/    # 9 files - API & service integration
├── regression/     # 7 files - Critical path protection
├── monitoring/     # 2 files - Alerting & metrics
├── services/       # 1 file - Service layer
└── jobs/           # 1 file - Background jobs
```

**Coverage Priorities (must have high coverage):**
1. Billing logic (`test_billing_*.py`)
2. Authorization (`test_rbac*.py`, `test_tenant_isolation.py`)
3. AI action execution (`test_action_*.py`)
4. Data transformations
5. Webhook handlers

**Commands:**
```bash
# Run full test suite with coverage
cd backend && pytest --cov=src --cov-report=html

# Check coverage thresholds
pytest --cov=src --cov-fail-under=80
```

---

### 2.2 Regression Test Inventory

**Critical Regression Tests:**
```
backend/src/tests/regression/
├── test_billing_regression.py      # Billing state machine
├── test_api_contracts.py           # API response schemas
├── test_retry_and_dlq.py           # Failure handling
├── test_job_isolation.py           # Job tenant isolation
└── test_simplification_regression.py
```

**Checklist:**
- [ ] Every bug fix has a corresponding regression test
- [ ] API contracts tested for backward compatibility
- [ ] Billing state transitions have full coverage
- [ ] Cross-tenant data leakage tests exist

---

### 2.3 Database Migration Safety

**Files to Review:**
```
db/migrations/
backend/alembic/
```

**Checklist:**
- [ ] Migrations are backward compatible (expand/migrate/contract pattern)
- [ ] No destructive DDL without explicit approval
- [ ] Index creation uses CONCURRENTLY where applicable
- [ ] Rollback path documented for each migration

---

## Phase 3: Build/CI Health

### 3.1 CI Pipeline Review

**File:** `.github/workflows/ci.yml`

**Current Pipeline Stages:**
1. Quality Gates (Epic 0 platform tests)
2. Tenant Isolation Tests
3. Full Platform Test Suite
4. Billing Regression Tests (with ephemeral PostgreSQL)
5. Raw Warehouse RLS Tests
6. dbt Validation
7. PR Merge Gate

**Checklist:**
- [ ] All stages use `|| exit 1` for fail-fast behavior
- [ ] No `continue-on-error: true` except for known acceptable cases
- [ ] Secrets scanning enabled
- [ ] Dependency vulnerability scanning present
- [ ] Flaky tests documented and tracked

**Missing Pipeline Stages (to verify):**
- [ ] Lint check (`flake8` or `ruff`)
- [ ] Type check (`mypy` or `pyright`)
- [ ] Frontend tests (`vitest`)
- [ ] Frontend lint (`eslint`)
- [ ] Docker build validation
- [ ] Security scanning (Snyk, Trivy, etc.)

---

### 3.2 Build Reproducibility

**Files to Review:**
```
backend/requirements.txt
frontend/package.json
frontend/package-lock.json
analytics/packages.yml
```

**Checklist:**
- [ ] All dependencies have pinned versions
- [ ] Lock files committed
- [ ] No floating version ranges (`>=`, `^`) for critical deps
- [ ] Docker builds deterministic

---

## Phase 4: Simplicity/Maintainability

### 4.1 Code Structure Review

**Backend Structure Analysis:**
```
backend/src/
├── api/routes/          # 20 route modules
├── api/schemas/         # Request/response validation
├── models/              # 27 SQLAlchemy models
├── services/            # 44+ service files
├── repositories/        # 5 data access files
├── platform/            # Security & infrastructure
├── governance/          # AI guardrails
├── entitlements/        # Feature flags
├── monitoring/          # Alerting & metrics
├── integrations/        # External APIs
└── jobs/                # Background workers
```

**Checklist:**
- [ ] No "utils" or "helpers" dumping grounds
- [ ] Clear domain boundaries (billing, AI, sync, etc.)
- [ ] Services have single responsibility
- [ ] No circular imports
- [ ] Consistent naming conventions

---

### 4.2 Dead Code Detection

**Commands:**
```bash
# Find unused imports
cd backend && python -m pip install vulture && vulture src/

# Find unreferenced functions (manual review needed)
grep -r "def " backend/src --include="*.py" | wc -l
```

**Files to Audit for Dead Code:**
- [ ] `backend/src/services/` - look for unused service methods
- [ ] `backend/src/api/routes/` - check for deprecated endpoints
- [ ] `frontend/src/components/` - unused React components

---

### 4.3 Complexity Analysis

**High-Risk Files (likely complex):**
```
backend/src/services/billing_service.py
backend/src/services/sync_orchestrator.py
backend/src/services/action_execution_service.py
backend/src/platform/rbac.py
backend/src/governance/approval_gate.py
```

**Checklist:**
- [ ] Functions < 40 lines (or justified)
- [ ] Cyclomatic complexity < 10 per function
- [ ] No deeply nested conditionals (> 3 levels)
- [ ] Complex logic has explanatory comments

---

### 4.4 Abstraction Audit

**Questions to Answer:**
1. Are there abstractions that exist for only one use case?
2. Are there overly generic patterns that complicate reading?
3. Are there configuration-driven behaviors that could be simple code?

**Files to Review for Over-Engineering:**
```
config/governance/
backend/src/governance/
backend/src/entitlements/
```

---

## Phase 5: Performance

### 5.1 Database Query Patterns

**Files to Review:**
```
backend/src/repositories/
backend/src/services/ (look for DB queries)
```

**Checklist:**
- [ ] No N+1 query patterns
- [ ] Bulk operations use batch inserts
- [ ] Appropriate indexes exist
- [ ] Complex queries have EXPLAIN analysis
- [ ] Connection pooling configured properly

---

### 5.2 External API Calls

**Files to Review:**
```
backend/src/integrations/openrouter_client.py
backend/src/integrations/airbyte_client.py
backend/src/services/shopify_api.py
```

**Checklist:**
- [ ] All external calls have timeouts
- [ ] Retry logic uses exponential backoff
- [ ] Circuit breaker pattern for unreliable services
- [ ] Idempotency keys for mutations

**Tests to Verify:**
- `backend/src/tests/unit/test_billing_client_retry.py`
- `backend/src/tests/unit/integrations/test_airbyte_client.py`

---

### 5.3 Caching Strategy

**Files to Review:**
```
backend/src/entitlements/cached_entitlement_service.py
backend/src/services/ (Redis usage)
```

**Checklist:**
- [ ] Cache invalidation is correct
- [ ] TTLs appropriate for data freshness requirements
- [ ] No cache stampede vulnerabilities
- [ ] Tenant-scoped cache keys

---

## Phase 6: Nice-to-Haves

### 6.1 Documentation Completeness

**Files to Verify:**
```
docs/
README.md
.env.example
```

**Checklist:**
- [ ] API documentation complete
- [ ] Deployment runbook exists
- [ ] Environment variables documented
- [ ] Architecture diagrams up-to-date

---

### 6.2 Developer Experience

**Checklist:**
- [ ] Local development setup documented
- [ ] Hot reload working
- [ ] Test data fixtures available
- [ ] Debugging guide exists

---

## Review Execution Plan

### Week 1: Security (Phase 1)

| Day | Focus Area | Estimated Hours |
|-----|------------|-----------------|
| 1 | Auth & Authorization (1.1) | 4h |
| 2 | Secrets & HMAC (1.2) | 3h |
| 3 | SQL Injection & Input Validation (1.3, 1.4) | 4h |
| 4 | Audit Logging (1.5) | 3h |
| 5 | Security Issue Remediation | 4h |

### Week 2: Tests & CI (Phase 2-3)

| Day | Focus Area | Estimated Hours |
|-----|------------|-----------------|
| 1 | Test Coverage Analysis (2.1) | 4h |
| 2 | Regression Test Inventory (2.2) | 3h |
| 3 | Migration Safety (2.3) | 2h |
| 4 | CI Pipeline Review (3.1) | 4h |
| 5 | Build Reproducibility (3.2) | 2h |

### Week 3: Maintainability & Performance (Phase 4-5)

| Day | Focus Area | Estimated Hours |
|-----|------------|-----------------|
| 1 | Code Structure Review (4.1) | 4h |
| 2 | Dead Code Detection (4.2) | 3h |
| 3 | Complexity Analysis (4.3) | 4h |
| 4 | Database Performance (5.1) | 4h |
| 5 | External APIs & Caching (5.2, 5.3) | 3h |

---

## Risk Assessment Matrix

| Area | Current Risk | Notes |
|------|--------------|-------|
| Multi-tenant Isolation | LOW | Strong RLS + middleware |
| Billing Security | LOW | Regression tests exist |
| AI Action Safety | MEDIUM | Needs approval gate review |
| Secret Management | LOW | Encryption in place |
| Test Coverage | LOW | 68+ test files |
| CI Completeness | MEDIUM | Missing lint/type checks? |
| Dead Code | MEDIUM | Large codebase, needs audit |
| N+1 Queries | UNKNOWN | Needs investigation |

---

## Deliverables

After review completion:

1. **Security Report**
   - Vulnerabilities found (with severity)
   - Remediation timeline

2. **Technical Debt Inventory**
   - Dead code to remove
   - Refactoring candidates
   - Missing tests

3. **CI/CD Improvements**
   - Missing pipeline stages
   - Flaky test remediation

4. **Performance Recommendations**
   - Query optimization opportunities
   - Caching improvements

---

## Appendix A: Quick Reference Commands

```bash
# Run all backend tests
cd backend && pytest -v

# Run with coverage
cd backend && pytest --cov=src --cov-report=html

# Run specific test category
cd backend && pytest src/tests/platform/ -v
cd backend && pytest src/tests/regression/ -v -m regression

# Check for unused code
cd backend && pip install vulture && vulture src/

# Type checking (if mypy configured)
cd backend && mypy src/

# Frontend tests
cd frontend && npm test

# Frontend lint
cd frontend && npm run lint
```

---

## Appendix B: Key File Locations

| Concern | Primary File |
|---------|--------------|
| RBAC Logic | `backend/src/platform/rbac.py` |
| Tenant Context | `backend/src/platform/tenant_context.py` |
| Audit Logging | `backend/src/platform/audit.py` |
| Billing Service | `backend/src/services/billing_service.py` |
| AI Actions | `backend/src/services/action_execution_service.py` |
| Approval Gate | `backend/src/governance/approval_gate.py` |
| CI Pipeline | `.github/workflows/ci.yml` |
| Plans Config | `config/plans.json` |
| AI Restrictions | `config/governance/ai_restrictions.yaml` |

---

*Review plan generated based on codebase analysis. Adjust timelines based on team availability and findings.*
