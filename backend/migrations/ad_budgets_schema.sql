-- Ad Budgets Schema
-- Version: 1.0.0
-- Date: 2026-03-04
--
-- Creates table for:
--   - ad_budgets: Monthly ad spend budgets per platform per tenant
--
-- SECURITY:
--   - tenant_id column for tenant isolation
--   - RLS policies should be applied separately if needed

-- Ensure uuid-ossp extension is available
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- =============================================================================
-- TABLE
-- =============================================================================

CREATE TABLE IF NOT EXISTS ad_budgets (
    -- Primary key
    id VARCHAR(255) PRIMARY KEY DEFAULT uuid_generate_v4()::TEXT,

    -- Tenant isolation (CRITICAL: never from client input, only from JWT)
    tenant_id VARCHAR(255) NOT NULL,

    -- Budget specification
    source_platform VARCHAR(100) NOT NULL,
    budget_monthly_cents BIGINT NOT NULL,
    start_date DATE NOT NULL,
    end_date DATE,
    enabled BOOLEAN NOT NULL DEFAULT TRUE,

    -- Timestamps (from TimestampMixin)
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
);

-- =============================================================================
-- INDEXES
-- =============================================================================

CREATE INDEX IF NOT EXISTS ix_ad_budgets_tenant_id
    ON ad_budgets(tenant_id);

CREATE INDEX IF NOT EXISTS ix_ad_budgets_source_platform
    ON ad_budgets(source_platform);

CREATE INDEX IF NOT EXISTS ix_ad_budget_tenant_platform
    ON ad_budgets(tenant_id, source_platform);

-- =============================================================================
-- TRIGGERS
-- =============================================================================

DROP TRIGGER IF EXISTS tr_ad_budgets_updated_at ON ad_budgets;
CREATE TRIGGER tr_ad_budgets_updated_at
    BEFORE UPDATE ON ad_budgets
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- =============================================================================
-- COMMENTS
-- =============================================================================

COMMENT ON TABLE ad_budgets IS 'Monthly ad spend budgets per platform. Used by Budget Pacing page.';
COMMENT ON COLUMN ad_budgets.tenant_id IS 'Tenant isolation key - ONLY from JWT, never client input';
COMMENT ON COLUMN ad_budgets.source_platform IS 'Ad platform: meta, google, tiktok, etc.';
COMMENT ON COLUMN ad_budgets.budget_monthly_cents IS 'Monthly budget in cents (e.g., 100000 = $1,000.00)';
