-- AI Safety Schema for Stories 8.6 and 8.7
-- Rate limiting, cooldowns, and safety event tracking
--
-- NO DOWN MIGRATION: Append-only schema design for compliance

-- Rate limit tracking per tenant
-- Uses sliding window pattern for counting operations per time period
CREATE TABLE IF NOT EXISTS ai_rate_limits (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id VARCHAR(255) NOT NULL,
    operation_type VARCHAR(50) NOT NULL,  -- 'action_execution', 'insight_generation', 'recommendation_generation'
    window_start TIMESTAMP WITH TIME ZONE NOT NULL,
    window_type VARCHAR(20) NOT NULL DEFAULT 'hourly',  -- 'hourly', 'daily', 'monthly'
    count INTEGER NOT NULL DEFAULT 0,
    limit_value INTEGER NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),

    UNIQUE(tenant_id, operation_type, window_start, window_type)
);

CREATE INDEX IF NOT EXISTS ix_ai_rate_limits_tenant_operation
    ON ai_rate_limits(tenant_id, operation_type);
CREATE INDEX IF NOT EXISTS ix_ai_rate_limits_window
    ON ai_rate_limits(window_start);

-- Cooldown tracking per entity
-- Prevents rapid consecutive actions on the same entity
CREATE TABLE IF NOT EXISTS ai_cooldowns (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id VARCHAR(255) NOT NULL,
    platform VARCHAR(50) NOT NULL,  -- 'meta', 'google', 'shopify'
    entity_type VARCHAR(50) NOT NULL,  -- 'campaign', 'ad_set', 'ad'
    entity_id VARCHAR(255) NOT NULL,
    action_type VARCHAR(50) NOT NULL,  -- 'pause_campaign', 'adjust_budget', etc.
    last_action_at TIMESTAMP WITH TIME ZONE NOT NULL,
    cooldown_until TIMESTAMP WITH TIME ZONE NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),

    UNIQUE(tenant_id, platform, entity_type, entity_id, action_type)
);

CREATE INDEX IF NOT EXISTS ix_ai_cooldowns_tenant_entity
    ON ai_cooldowns(tenant_id, platform, entity_id);
CREATE INDEX IF NOT EXISTS ix_ai_cooldowns_expires
    ON ai_cooldowns(cooldown_until);

-- Safety events log (append-only audit trail for safety-specific events)
-- Complements the main audit_logs table with safety-focused events
CREATE TABLE IF NOT EXISTS ai_safety_events (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id VARCHAR(255) NOT NULL,
    event_type VARCHAR(50) NOT NULL,  -- 'rate_limit_hit', 'cooldown_enforced', 'action_blocked', 'action_suppressed'
    operation_type VARCHAR(50) NOT NULL,  -- 'action_execution', 'insight_generation', etc.
    entity_id VARCHAR(255),  -- Optional: specific entity affected
    action_id VARCHAR(255),  -- Optional: related action ID
    reason TEXT NOT NULL,
    event_metadata JSONB DEFAULT '{}',
    correlation_id VARCHAR(255),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Indexes for querying safety events
CREATE INDEX IF NOT EXISTS ix_ai_safety_events_tenant
    ON ai_safety_events(tenant_id);
CREATE INDEX IF NOT EXISTS ix_ai_safety_events_type
    ON ai_safety_events(event_type);
CREATE INDEX IF NOT EXISTS ix_ai_safety_events_created
    ON ai_safety_events(created_at DESC);
CREATE INDEX IF NOT EXISTS ix_ai_safety_events_correlation
    ON ai_safety_events(correlation_id) WHERE correlation_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS ix_ai_safety_events_tenant_created
    ON ai_safety_events(tenant_id, created_at DESC);

-- Add index to audit_logs for efficient querying (Story 8.7)
CREATE INDEX IF NOT EXISTS ix_audit_logs_action_resource
    ON audit_logs(action, resource_type);
