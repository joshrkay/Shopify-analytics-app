# Story 8.8 — Model Routing & Prompt Governance

## Implementation Plan for LLM Routing via OpenRouter

**Created:** 2026-01-28
**Story:** 8.8 — Model Routing & Prompt Governance
**Context:** Enterprise customers want control over which LLM they trust

---

## Executive Summary

This plan details the implementation of LLM routing via OpenRouter, enabling:
- Organization-level model selection
- Versioned prompt templates
- Model usage logging
- Fallback model support

**Key Constraint:** No hardcoded model names - all models configured via database/configuration.

---

## Current State Analysis

### Existing Infrastructure (Ready to Use)

| Component | Location | Status |
|-----------|----------|--------|
| OpenRouter API Key | `.env.example:39` | ✅ Placeholder exists |
| Tenant Isolation | `models/base.py:42-57` | ✅ TenantScopedMixin ready |
| Audit Logging | `platform/audit_events.py` | ✅ Comprehensive, needs LLM events |
| Feature Gating | `services/billing_entitlements.py` | ✅ Pattern established |
| Safety Guardrails | `governance/ai_guardrails.py` | ✅ Can be extended |
| Migration Pattern | `migrations/ai_safety_schema.sql` | ✅ Append-only SQL |
| Template System | `services/*_templates.py` | ✅ Deterministic, needs LLM bridge |

### Gap Analysis

| Requirement | Current State | Gap |
|-------------|--------------|-----|
| Org-level model selection | None | Full implementation needed |
| Prompt template versioning | Hardcoded Python templates | Database-driven versioning needed |
| Model usage logging | No LLM usage | Full implementation needed |
| Fallback model support | None | Full implementation needed |
| OpenRouter client | None | Full implementation needed |

---

## Architecture Design

### Component Overview

```
┌─────────────────────────────────────────────────────────────────────┐
│                         API Layer                                    │
│  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────────┐  │
│  │ /api/llm/config │  │ /api/prompts    │  │ /api/llm/usage      │  │
│  └────────┬────────┘  └────────┬────────┘  └──────────┬──────────┘  │
└───────────┼────────────────────┼─────────────────────┼──────────────┘
            │                    │                     │
┌───────────┼────────────────────┼─────────────────────┼──────────────┐
│           ▼                    ▼                     ▼              │
│  ┌─────────────────────────────────────────────────────────────┐    │
│  │                    LLM Routing Service                       │    │
│  │  ┌──────────────┐ ┌──────────────┐ ┌─────────────────────┐  │    │
│  │  │ ModelRouter  │ │PromptManager │ │ FallbackOrchestrator│  │    │
│  │  └──────┬───────┘ └──────┬───────┘ └──────────┬──────────┘  │    │
│  └─────────┼────────────────┼────────────────────┼─────────────┘    │
│            │                │                    │                  │
│  ┌─────────▼────────────────▼────────────────────▼─────────────┐    │
│  │                 OpenRouter Client Adapter                    │    │
│  │  • Circuit breaker  • Retry logic  • Timeout handling        │    │
│  └─────────────────────────────────────────────────────────────┘    │
│                              │                                      │
│  ┌───────────────────────────▼─────────────────────────────────┐    │
│  │                     LLM Usage Logger                         │    │
│  │  • Request/response  • Tokens  • Latency  • Cost  • Errors   │    │
│  └─────────────────────────────────────────────────────────────┘    │
│                              │                                      │
│                    Service Layer                                    │
└──────────────────────────────┼──────────────────────────────────────┘
                               │
┌──────────────────────────────┼──────────────────────────────────────┐
│  ┌────────────────┐ ┌────────▼─────┐ ┌───────────────┐              │
│  │OrgLLMConfig    │ │PromptTemplate│ │ LLMUsageLog   │              │
│  │(org settings)  │ │(versioned)   │ │(audit trail)  │              │
│  └────────────────┘ └──────────────┘ └───────────────┘              │
│                       Database Layer                                 │
└─────────────────────────────────────────────────────────────────────┘
```

---

## Task Breakdown

### Phase 1: Database Models & Migrations

#### Task 1.1: Create LLM Configuration Migration
**File:** `backend/migrations/llm_routing_schema.sql`

```sql
-- Tables needed:
-- 1. org_llm_configs - Org-level model selection
-- 2. prompt_templates - Versioned prompt templates
-- 3. llm_usage_logs - Model usage audit trail
-- 4. llm_model_registry - Available models (not hardcoded)
```

**Fields for `org_llm_configs`:**
- `id` (UUID, PK)
- `tenant_id` (VARCHAR, FK to org, indexed)
- `primary_model_id` (VARCHAR, references model registry)
- `fallback_model_id` (VARCHAR, references model registry)
- `fallback_enabled` (BOOLEAN, default true)
- `max_tokens_per_request` (INTEGER, default 4096)
- `temperature` (DECIMAL, default 0.7)
- `monthly_budget_usd` (DECIMAL, nullable)
- `created_at`, `updated_at` (TIMESTAMP WITH TIME ZONE)

**Fields for `prompt_templates`:**
- `id` (UUID, PK)
- `tenant_id` (VARCHAR, indexed) - NULL for system templates
- `name` (VARCHAR, unique per tenant)
- `version` (INTEGER, auto-increment per name)
- `content` (TEXT)
- `variables` (JSONB) - expected variables
- `model_compatibility` (JSONB) - list of compatible models
- `status` (ENUM: draft, active, deprecated)
- `created_by` (VARCHAR)
- `approved_by` (VARCHAR, nullable)
- `approved_at` (TIMESTAMP, nullable)
- `created_at`, `updated_at` (TIMESTAMP WITH TIME ZONE)
- `UNIQUE(tenant_id, name, version)`

**Fields for `llm_usage_logs`:**
- `id` (UUID, PK)
- `tenant_id` (VARCHAR, indexed)
- `model_id` (VARCHAR) - model used
- `model_version` (VARCHAR)
- `prompt_template_id` (UUID, nullable)
- `prompt_template_version` (INTEGER, nullable)
- `input_tokens` (INTEGER)
- `output_tokens` (INTEGER)
- `total_tokens` (INTEGER)
- `latency_ms` (INTEGER)
- `estimated_cost_usd` (DECIMAL)
- `fallback_used` (BOOLEAN, default false)
- `fallback_reason` (VARCHAR, nullable)
- `error_code` (VARCHAR, nullable)
- `error_message` (TEXT, nullable)
- `correlation_id` (VARCHAR)
- `request_metadata` (JSONB) - operation type, entity context
- `created_at` (TIMESTAMP WITH TIME ZONE)

**Fields for `llm_model_registry`:**
- `id` (VARCHAR, PK) - e.g., "anthropic/claude-3-opus"
- `provider` (VARCHAR) - "anthropic", "openai", "meta"
- `display_name` (VARCHAR)
- `context_window` (INTEGER)
- `max_output_tokens` (INTEGER)
- `input_cost_per_1k_tokens` (DECIMAL)
- `output_cost_per_1k_tokens` (DECIMAL)
- `capabilities` (JSONB) - vision, function_calling, etc.
- `tier_required` (VARCHAR) - "free", "growth", "enterprise"
- `is_active` (BOOLEAN, default true)
- `created_at`, `updated_at` (TIMESTAMP WITH TIME ZONE)

#### Task 1.2: Create SQLAlchemy Models
**Files:**
- `backend/src/models/org_llm_config.py`
- `backend/src/models/prompt_template.py`
- `backend/src/models/llm_usage_log.py`
- `backend/src/models/llm_model_registry.py`

---

### Phase 2: OpenRouter Client Integration

#### Task 2.1: Create OpenRouter Client Adapter
**File:** `backend/src/integrations/openrouter_client.py`

**Requirements:**
- Async HTTP client (httpx or aiohttp)
- Circuit breaker pattern for resilience
- Retry with exponential backoff
- Timeout configuration
- Request/response logging (redacted)
- Cost estimation per request

**Interface:**
```python
class OpenRouterClient:
    async def complete(
        self,
        model_id: str,
        messages: list[dict],
        max_tokens: int = 4096,
        temperature: float = 0.7,
        **kwargs
    ) -> LLMResponse

    async def get_available_models(self) -> list[ModelInfo]

    async def health_check(self) -> bool
```

#### Task 2.2: Create LLM Response Models
**File:** `backend/src/api/schemas/llm.py`

```python
@dataclass
class LLMResponse:
    content: str
    model_id: str
    input_tokens: int
    output_tokens: int
    latency_ms: int
    finish_reason: str
    estimated_cost_usd: Decimal
```

---

### Phase 3: LLM Routing Service

#### Task 3.1: Create Model Router Service
**File:** `backend/src/services/llm_router_service.py`

**Responsibilities:**
- Load org's LLM config
- Select appropriate model based on config
- Handle fallback logic
- Enforce budget limits
- Track usage

**Key Methods:**
```python
class LLMRouterService:
    def __init__(self, db: Session, tenant_id: str):
        ...

    async def route_completion(
        self,
        messages: list[dict],
        operation_type: str,  # "insight", "recommendation", etc.
        **kwargs
    ) -> LLMResponse:
        """Route request to appropriate model with fallback."""

    def get_org_config(self) -> OrgLLMConfig:
        """Get cached org LLM configuration."""

    async def _try_with_fallback(
        self,
        primary_model: str,
        fallback_model: str,
        messages: list[dict],
        **kwargs
    ) -> LLMResponse:
        """Try primary, fall back if needed."""

    def _check_budget(self) -> bool:
        """Check if org is within budget."""
```

#### Task 3.2: Create Fallback Orchestrator
**File:** `backend/src/services/llm_fallback_service.py`

**Fallback Triggers:**
- Primary model unavailable (503)
- Primary model rate limited (429)
- Primary model timeout (>30s)
- Primary model context exceeded (400)

**Fallback Strategy:**
1. Log primary failure reason
2. Check fallback is configured and enabled
3. Route to fallback model
4. Mark response as fallback-routed
5. Continue logging for billing

---

### Phase 4: Prompt Template Management

#### Task 4.1: Create Prompt Template Service
**File:** `backend/src/services/prompt_template_service.py`

**Features:**
- CRUD operations for templates
- Version management (auto-increment)
- Variable validation
- Model compatibility checking
- Approval workflow support

**Key Methods:**
```python
class PromptTemplateService:
    def create_template(
        self,
        name: str,
        content: str,
        variables: list[str],
        model_compatibility: list[str] = None
    ) -> PromptTemplate:
        """Create new template version."""

    def get_active_template(
        self,
        name: str,
        tenant_id: str = None  # None = system template
    ) -> PromptTemplate:
        """Get active version of template."""

    def render_template(
        self,
        template: PromptTemplate,
        variables: dict
    ) -> str:
        """Render template with variables, validate."""

    def deprecate_template(
        self,
        template_id: str
    ) -> PromptTemplate:
        """Mark template as deprecated."""
```

#### Task 4.2: Create System Prompt Templates
**File:** `backend/src/services/system_prompts.py`

Define initial system prompts for:
- Insight generation enhancement
- Recommendation explanation
- Action proposal refinement
- Multi-language support

**Structure:**
```python
SYSTEM_PROMPTS = {
    "insight_enhancement": {
        "name": "insight_enhancement",
        "variables": ["insight_type", "metrics", "context"],
        "model_compatibility": ["anthropic/claude-3-opus", "anthropic/claude-3-sonnet"],
    },
    ...
}
```

---

### Phase 5: Usage Logging & Audit

#### Task 5.1: Create LLM Usage Logger
**File:** `backend/src/services/llm_usage_logger.py`

**Responsibilities:**
- Log every LLM request/response
- Calculate and record costs
- Track token usage per org
- Support querying for billing
- Integrate with audit events

**Key Methods:**
```python
class LLMUsageLogger:
    def log_request(
        self,
        tenant_id: str,
        model_id: str,
        response: LLMResponse,
        prompt_template_id: str = None,
        fallback_used: bool = False,
        fallback_reason: str = None,
        correlation_id: str = None,
        metadata: dict = None
    ) -> LLMUsageLog:
        """Log LLM usage with full context."""

    def get_usage_summary(
        self,
        tenant_id: str,
        start_date: datetime,
        end_date: datetime
    ) -> UsageSummary:
        """Get aggregated usage for billing."""

    def check_budget_remaining(
        self,
        tenant_id: str
    ) -> BudgetStatus:
        """Check remaining budget for org."""
```

#### Task 5.2: Add LLM Audit Events
**File:** Update `backend/src/platform/audit_events.py`

Add events:
```python
# LLM Routing Events (Story 8.8)
"llm.request_sent": [
    "tenant_id", "model_id", "prompt_template_name",
    "operation_type", "correlation_id"
],
"llm.response_received": [
    "tenant_id", "model_id", "input_tokens", "output_tokens",
    "latency_ms", "estimated_cost_usd", "correlation_id"
],
"llm.fallback_triggered": [
    "tenant_id", "primary_model", "fallback_model",
    "failure_reason", "correlation_id"
],
"llm.budget_exceeded": [
    "tenant_id", "monthly_budget_usd", "current_spend_usd",
    "action_taken"  # "blocked" or "warned"
],
"llm.model_config_changed": [
    "tenant_id", "changed_by", "previous_model", "new_model",
    "change_reason"
],
"prompt.template_created": [
    "tenant_id", "template_name", "version", "created_by"
],
"prompt.template_activated": [
    "tenant_id", "template_name", "version", "activated_by"
],
"prompt.template_deprecated": [
    "tenant_id", "template_name", "version", "deprecated_by"
],
```

---

### Phase 6: API Endpoints

#### Task 6.1: Create LLM Configuration API
**File:** `backend/src/api/routes/llm_config.py`

**Endpoints:**
```
GET  /api/v1/llm/config          - Get org's LLM configuration
PUT  /api/v1/llm/config          - Update org's LLM configuration
GET  /api/v1/llm/models          - List available models (filtered by tier)
GET  /api/v1/llm/models/{id}     - Get model details
```

**Access Control:**
- Requires `enterprise` or `growth` tier
- Requires `admin` or `owner` role for PUT
- `viewer` can GET configuration

#### Task 6.2: Create Prompt Template API
**File:** `backend/src/api/routes/prompts.py`

**Endpoints:**
```
GET    /api/v1/prompts                    - List templates (org + system)
POST   /api/v1/prompts                    - Create new template
GET    /api/v1/prompts/{name}             - Get active template
GET    /api/v1/prompts/{name}/versions    - List all versions
PUT    /api/v1/prompts/{name}/activate    - Activate specific version
DELETE /api/v1/prompts/{name}             - Deprecate template
```

**Access Control:**
- Requires `enterprise` tier for custom templates
- `growth` tier can view system templates only
- `admin` role required for modifications

#### Task 6.3: Create Usage Analytics API
**File:** `backend/src/api/routes/llm_usage.py`

**Endpoints:**
```
GET /api/v1/llm/usage                 - Get usage summary
GET /api/v1/llm/usage/daily           - Daily breakdown
GET /api/v1/llm/usage/by-model        - Usage by model
GET /api/v1/llm/usage/by-operation    - Usage by operation type
GET /api/v1/llm/budget                - Budget status
```

---

### Phase 7: Feature Flag & Entitlements

#### Task 7.1: Add LLM Feature Flags
**File:** Update `backend/src/platform/feature_flags.py`

```python
AI_LLM_ROUTING = "ai_llm_routing"       # Master flag
AI_CUSTOM_PROMPTS = "ai_custom_prompts" # Custom prompt templates
AI_MODEL_SELECTION = "ai_model_selection"  # Org model selection
```

#### Task 7.2: Add Billing Entitlements
**File:** Update `backend/src/services/billing_entitlements.py`

```python
class BillingFeature:
    ...
    LLM_ROUTING = "llm_routing"
    CUSTOM_PROMPTS = "custom_prompts"
    MODEL_SELECTION = "model_selection"

BILLING_TIER_FEATURES = {
    'free': {
        BillingFeature.LLM_ROUTING: False,
        BillingFeature.CUSTOM_PROMPTS: False,
        BillingFeature.MODEL_SELECTION: False,
    },
    'growth': {
        BillingFeature.LLM_ROUTING: True,
        BillingFeature.CUSTOM_PROMPTS: False,  # System templates only
        BillingFeature.MODEL_SELECTION: True,  # Limited models
    },
    'enterprise': {
        BillingFeature.LLM_ROUTING: True,
        BillingFeature.CUSTOM_PROMPTS: True,
        BillingFeature.MODEL_SELECTION: True,  # All models
    },
}
```

---

### Phase 8: Integration with Existing Services

#### Task 8.1: Create LLM-Enhanced Insight Service
**File:** `backend/src/services/llm_insight_service.py`

Bridge between existing `insight_generation_service.py` and LLM:
- Use deterministic detection (existing)
- Optionally enhance summaries with LLM
- Respect org's LLM preferences
- Fall back to templates if LLM unavailable

#### Task 8.2: Update Template Services
**Files:**
- `backend/src/services/insight_templates.py`
- `backend/src/services/recommendation_templates.py`

Add LLM enhancement hooks:
```python
def render_insight_summary(
    detected: DetectedInsight,
    use_llm: bool = False,
    llm_service: LLMRouterService = None
) -> str:
    """Render summary, optionally enhanced by LLM."""
    # Existing deterministic rendering
    base_summary = _render_deterministic(detected)

    if not use_llm or not llm_service:
        return base_summary

    # LLM enhancement (if enabled and available)
    return llm_service.enhance_summary(base_summary, detected)
```

---

### Phase 9: Testing

#### Task 9.1: Unit Tests
**Files:**
- `backend/src/tests/unit/test_llm_router_service.py`
- `backend/src/tests/unit/test_prompt_template_service.py`
- `backend/src/tests/unit/test_llm_usage_logger.py`
- `backend/src/tests/unit/test_openrouter_client.py`

**Test Cases:**
- Model selection based on org config
- Fallback triggered on primary failure
- Budget enforcement
- Template versioning
- Cost calculation accuracy

#### Task 9.2: Integration Tests
**Files:**
- `backend/src/tests/integration/test_llm_routing_api.py`
- `backend/src/tests/integration/test_prompt_management_api.py`

**Test Cases:**
- End-to-end routing flow
- Tenant isolation
- Billing tier enforcement
- Audit trail completeness

---

## Missing Tasks Identified

Based on the requirements analysis, the following tasks are **potentially missing** from a minimal implementation:

### Critical (Must Have)

| Task | Reason |
|------|--------|
| **Error Handling Strategy** | Need comprehensive error handling for OpenRouter API failures |
| **Rate Limiting for LLM** | Prevent abuse/runaway costs; integrate with existing `ai_rate_limits` |
| **Secrets Management** | Secure storage for OpenRouter API key per org (if multi-key needed) |
| **Cost Alerting** | Notify admins when approaching budget |

### Important (Should Have)

| Task | Reason |
|------|--------|
| **Model Warmup/Health Check** | Verify model availability before routing |
| **Prompt Injection Prevention** | Sanitize user inputs before sending to LLM |
| **Response Validation** | Validate LLM responses before using |
| **Caching Strategy** | Cache identical prompts to reduce costs |
| **Streaming Support** | For long-running generations |

### Nice to Have (Could Have)

| Task | Reason |
|------|--------|
| **A/B Testing Framework** | Test different prompts/models |
| **Prompt Playground** | Admin UI for testing prompts |
| **Cost Forecasting** | Predict monthly costs |
| **Model Performance Comparison** | Compare quality across models |

---

## Implementation Order

### Sprint 1: Foundation (Week 1-2)
1. ✅ Task 1.1: Database migration
2. ✅ Task 1.2: SQLAlchemy models
3. ✅ Task 2.1: OpenRouter client
4. ✅ Task 2.2: Response models
5. ✅ Task 5.2: Audit events

### Sprint 2: Core Services (Week 2-3)
6. ✅ Task 3.1: Model router service
7. ✅ Task 3.2: Fallback orchestrator
8. ✅ Task 5.1: Usage logger
9. ✅ Task 4.1: Prompt template service

### Sprint 3: API & Integration (Week 3-4)
10. ✅ Task 6.1: LLM config API
11. ✅ Task 6.2: Prompt template API
12. ✅ Task 6.3: Usage API
13. ✅ Task 7.1-7.2: Feature flags & entitlements

### Sprint 4: Polish & Testing (Week 4-5)
14. ✅ Task 4.2: System prompts
15. ✅ Task 8.1-8.2: Integration with existing services
16. ✅ Task 9.1-9.2: Testing

---

## Risk Assessment

| Risk | Impact | Mitigation |
|------|--------|------------|
| OpenRouter API instability | High | Circuit breaker, fallback models, retry logic |
| Cost overruns | High | Budget limits, alerts, kill switch |
| Prompt injection | Medium | Input sanitization, output validation |
| Model deprecation | Medium | Model registry with deprecation flags |
| Latency issues | Medium | Timeout config, caching, async processing |

---

## Configuration Reference

### Environment Variables
```bash
# OpenRouter Configuration
OPENROUTER_API_KEY=<api-key>
OPENROUTER_BASE_URL=https://openrouter.ai/api/v1
OPENROUTER_TIMEOUT_SECONDS=30
OPENROUTER_MAX_RETRIES=3

# LLM Defaults
LLM_DEFAULT_MODEL=anthropic/claude-3-sonnet-20240229
LLM_FALLBACK_MODEL=anthropic/claude-3-haiku-20240307
LLM_DEFAULT_MAX_TOKENS=4096
LLM_DEFAULT_TEMPERATURE=0.7

# Budget Defaults
LLM_DEFAULT_MONTHLY_BUDGET_USD=100.00
LLM_BUDGET_WARNING_THRESHOLD=0.8  # Warn at 80%
```

---

## Success Criteria

- [ ] Org admins can select their preferred LLM model
- [ ] Prompt templates are versioned and auditable
- [ ] All LLM usage is logged with token counts and costs
- [ ] Fallback models activate automatically on primary failure
- [ ] No model names are hardcoded in application code
- [ ] Usage stays within configured budget limits
- [ ] Complete audit trail for compliance

---

## Appendix: Model Registry Initial Data

```sql
INSERT INTO llm_model_registry (id, provider, display_name, context_window, max_output_tokens, input_cost_per_1k_tokens, output_cost_per_1k_tokens, capabilities, tier_required, is_active) VALUES
('anthropic/claude-3-opus', 'anthropic', 'Claude 3 Opus', 200000, 4096, 0.015, 0.075, '{"vision": true, "function_calling": true}', 'enterprise', true),
('anthropic/claude-3-sonnet', 'anthropic', 'Claude 3 Sonnet', 200000, 4096, 0.003, 0.015, '{"vision": true, "function_calling": true}', 'growth', true),
('anthropic/claude-3-haiku', 'anthropic', 'Claude 3 Haiku', 200000, 4096, 0.00025, 0.00125, '{"vision": true, "function_calling": true}', 'growth', true),
('openai/gpt-4-turbo', 'openai', 'GPT-4 Turbo', 128000, 4096, 0.01, 0.03, '{"vision": true, "function_calling": true}', 'enterprise', true),
('openai/gpt-4o', 'openai', 'GPT-4o', 128000, 4096, 0.005, 0.015, '{"vision": true, "function_calling": true}', 'growth', true),
('openai/gpt-3.5-turbo', 'openai', 'GPT-3.5 Turbo', 16385, 4096, 0.0005, 0.0015, '{"function_calling": true}', 'growth', true),
('meta-llama/llama-3-70b', 'meta', 'Llama 3 70B', 8192, 4096, 0.0008, 0.0008, '{}', 'growth', true);
```

---

## Related Stories

- **Story 8.6**: AI Safety Guardrails (completed) - Integrates with rate limiting
- **Story 8.7**: Audit System (completed) - Provides audit event patterns
- **Story 8.1-8.5**: AI Insights/Recommendations - Primary consumers of LLM routing

---

*Plan created by Claude Code. Ready for implementation.*
