# Entitlements Implementation Gap Review & Remainder Plan

## Scope reviewed

This review compares the requested outcomes against the code currently present in:

- Backend entitlement dependency + routes
- Frontend entitlement hook and gate component
- Existing per-tenant override domain/service internals

## 1) Task: Enforce entitlements consistently across backend/frontend

### What is already implemented

#### Backend enforcement primitives exist
- A reusable FastAPI dependency factory `create_entitlement_check(...)` is implemented and returns `402 Payment Required` when a feature is not entitled. It is used to produce preconfigured checks (AI insights/recommendations/actions, LLM routing, custom reports).
- There is a read-only entitlement endpoint at `GET /api/billing/entitlements` that returns billing state and feature-by-feature entitlement information for the UI.

#### Frontend entitlement UX primitives exist
- `useEntitlements()` exists and fetches entitlements on load from `/billing/entitlements`.
- `FeatureGate` exists and can lock/hide feature content with a reason and optional upgrade CTA.
- API utilities already map status `402` and `403` to friendly user-facing messages.

### Gaps to close

1. **Inconsistent backend declaration of required feature keys.**
   - Some routes use shared dependency checks, but others perform inline/manual checks.
   - `llm_config` currently aliases `check_ai_insights_entitlement` as `check_llm_routing_entitlement`, which is semantically incorrect and risks policy drift.

2. **No single authoritative pattern that all protected routes must follow.**
   - There is no enforced contract that every protected endpoint declares required feature key(s) in one standard way.

3. **Frontend naming/contract mismatch vs requested files.**
   - Equivalent components exist (`FeatureGate` instead of `EntitlementGate`), but we should standardize around a single component/hook contract and ensure all protected UI entry points use it.

4. **Access denied UX should be explicitly wired for entitlement failures.**
   - Friendly error mapping exists, but entitlement-denied handling should be applied uniformly in feature views (not only globally available helper functions).

### Remainder implementation plan (Task 1)

#### Phase 1 — Backend contract hardening
1. Add/rename a canonical dependency helper module (`require_entitlement`) that accepts one-or-many feature keys and optional mode (`all`/`any`).
2. Ensure each protected route declares required feature key(s) via dependency metadata (no hidden inline checks).
3. Replace incorrect aliasing in LLM routes with a real LLM routing entitlement check.
4. Add route-level audit/telemetry tags for denied checks.

#### Phase 2 — Frontend contract alignment
1. Keep `/api/billing/entitlements` read-only and document response shape as a stable frontend contract.
2. Introduce/alias `EntitlementGate` (can wrap existing `FeatureGate`) to align naming and avoid duplicate patterns.
3. Apply gate usage to all entitlement-sensitive components; disable controls and hide unavailable flows.
4. Standardize entitlement denied handling (`402`) to show plan-upgrade guidance and preserve normal `403` permission-denied messaging.

#### Phase 3 — Test/verification
1. Backend tests verifying every protected route has required entitlement dependency.
2. API tests for `402` payload consistency and denied reasons.
3. Frontend tests for gate rendering (entitled vs not entitled), disabled CTA behavior, and denied-banner copy.

---

## 2) Task: Per-tenant entitlement overrides with governance

### What is already implemented

#### Data/domain/service groundwork is in place
- SQLAlchemy model `TenantEntitlementOverride` exists with required fields including `tenant_id`, `feature_key`, `enabled`, `expires_at` (non-null), and `reason`.
- Service methods exist for create/update (`create_override` upsert semantics), delete, and cleanup of expired overrides.
- A reconciliation worker already calls override cleanup (`cleanup_expired_overrides`) to remove expired rows.

### Gaps to close

1. **Admin API surface is missing.**
   - No dedicated `admin_overrides` route exists for create/update/delete/list operations.

2. **Governance authorization not enforced for override operations.**
   - Requirement says only **Super Admin + Support** may manage overrides; current service methods do not enforce this policy.

3. **Audit event taxonomy does not match required event names.**
   - Required events are:
     - `entitlement.override.created`
     - `entitlement.override.updated`
     - `entitlement.override.expired`
     - `entitlement.override.removed`
   - Current implementation logs override changes through generic denial-style audit logging and does not emit the required explicit event identifiers.

4. **Migration artifact is missing.**
   - Model exists, but no corresponding SQL migration file for entitlement overrides is present in migrations.

5. **Expiry governance needs explicit audit emission on automatic expiry removal.**
   - Cleanup runs, but required `entitlement.override.expired` / `removed` event semantics need explicit implementation.

### Remainder implementation plan (Task 2)

#### Phase 1 — Persistence + API scaffolding
1. Add SQL migration to create `tenant_entitlement_overrides` table, indexes, constraints, and audit-friendly columns.
2. Add admin route module for overrides CRUD/list.
3. Register router in API bootstrap.

#### Phase 2 — Governance controls
1. Add shared authorization guard enforcing **both** Super Admin and Support governance rules as required by product policy.
2. Validate request payload requires:
   - `feature_key`
   - `tenant_id`
   - `expiry_date` (required, future, timezone-aware)
   - `reason`
3. Reject invalid requests with clear 4xx messages.

#### Phase 3 — Audit compliance
1. Extend audit event catalog with the four required event names.
2. Emit:
   - `entitlement.override.created` on insert
   - `entitlement.override.updated` on update
   - `entitlement.override.removed` on explicit delete
   - `entitlement.override.expired` when cleanup removes expired overrides
3. Include actor identity, tenant_id, feature_key, old/new values, expiry, and reason.

#### Phase 4 — Expiry automation hardening
1. Keep reconcile job cleanup logic, but add idempotent event emission and metrics.
2. Ensure cleanup failures alert and retry without partial silent drops.

#### Phase 5 — End-to-end tests
1. API tests for authz matrix (allowed only for Super Admin + Support).
2. Validation tests for required fields and expiry constraints.
3. Audit tests verifying exact event names and required metadata.
4. Worker tests for expiry cleanup + emitted expired/removed events.

---

## Delivery order recommendation

1. **Migration + model parity check** (avoid runtime drift).
2. **Admin overrides API + governance enforcement**.
3. **Audit event contract implementation**.
4. **Backend protected-route standardization**.
5. **Frontend gate/error consistency pass**.
6. **Comprehensive tests and rollout checklist.**

This order minimizes risk by establishing durable persistence and governance first, then tightening route-level entitlement consistency and UX behavior.
