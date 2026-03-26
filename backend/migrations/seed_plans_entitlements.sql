-- =============================================================================
-- Seed Production Plans and Entitlements (GL-3)
--
-- Aligns the plans and plan_features tables with the authoritative
-- BILLING_TIER_FEATURES dict in billing_entitlements.py.
--
-- Idempotent: uses INSERT ... ON CONFLICT DO UPDATE throughout.
-- =============================================================================

-- =============================================================================
-- 1. Upsert the four canonical plans
-- =============================================================================
INSERT INTO plans (id, name, display_name, description, price_monthly_cents, price_yearly_cents, is_active)
VALUES
    ('plan_free',       'free',       'Free',       'Basic analytics for small stores',                    0,     0,     TRUE),
    ('plan_growth',     'growth',     'Growth',     'For growing businesses with advanced analytics',      2900,  29000, TRUE),
    ('plan_pro',        'pro',        'Pro',        'Professional tier with all features',                 7900,  79000, TRUE),
    ('plan_enterprise', 'enterprise', 'Enterprise', 'Custom solutions with dedicated support',             NULL,  NULL,  TRUE)
ON CONFLICT (id) DO UPDATE SET
    name                = EXCLUDED.name,
    display_name        = EXCLUDED.display_name,
    description         = EXCLUDED.description,
    price_monthly_cents = EXCLUDED.price_monthly_cents,
    price_yearly_cents  = EXCLUDED.price_yearly_cents,
    is_active           = EXCLUDED.is_active,
    updated_at          = NOW();

-- =============================================================================
-- 2. Delete stale plan_features rows whose feature_key is not in BillingFeature
-- =============================================================================
DELETE FROM plan_features
WHERE plan_id IN ('plan_free', 'plan_growth', 'plan_pro', 'plan_enterprise')
  AND feature_key NOT IN (
    'agency_access', 'multi_tenant', 'advanced_dashboards', 'explore_mode',
    'data_export', 'ai_insights', 'ai_recommendations', 'ai_actions',
    'custom_reports', 'llm_routing', 'custom_prompts', 'cohort_analysis',
    'budget_pacing', 'alerts', 'warehouse_export', 'sheets_export',
    'scheduled_exports'
  );

-- =============================================================================
-- 3. Upsert plan_features for all 17 BillingFeature keys x 4 plans
--    Enabled/disabled and limits match BILLING_TIER_FEATURES exactly.
-- =============================================================================

-- ---- Free Plan ----
INSERT INTO plan_features (id, plan_id, feature_key, is_enabled, limit_value, limits)
VALUES
    (uuid_generate_v4()::TEXT, 'plan_free', 'agency_access',        FALSE, NULL, NULL),
    (uuid_generate_v4()::TEXT, 'plan_free', 'multi_tenant',         FALSE, NULL, NULL),
    (uuid_generate_v4()::TEXT, 'plan_free', 'advanced_dashboards',  FALSE, NULL, NULL),
    (uuid_generate_v4()::TEXT, 'plan_free', 'explore_mode',         FALSE, NULL, NULL),
    (uuid_generate_v4()::TEXT, 'plan_free', 'data_export',          FALSE, NULL, NULL),
    (uuid_generate_v4()::TEXT, 'plan_free', 'ai_insights',          TRUE,  NULL, '{"max_dashboard_access": 3, "max_users": 2, "max_alert_rules": 3}'),
    (uuid_generate_v4()::TEXT, 'plan_free', 'ai_recommendations',   TRUE,  NULL, '{"max_dashboard_access": 3, "max_users": 2, "max_alert_rules": 3}'),
    (uuid_generate_v4()::TEXT, 'plan_free', 'ai_actions',           FALSE, NULL, NULL),
    (uuid_generate_v4()::TEXT, 'plan_free', 'custom_reports',       FALSE, NULL, NULL),
    (uuid_generate_v4()::TEXT, 'plan_free', 'llm_routing',          FALSE, NULL, NULL),
    (uuid_generate_v4()::TEXT, 'plan_free', 'custom_prompts',       FALSE, NULL, NULL),
    (uuid_generate_v4()::TEXT, 'plan_free', 'cohort_analysis',      FALSE, NULL, NULL),
    (uuid_generate_v4()::TEXT, 'plan_free', 'budget_pacing',        FALSE, NULL, NULL),
    (uuid_generate_v4()::TEXT, 'plan_free', 'alerts',               FALSE, NULL, NULL),
    (uuid_generate_v4()::TEXT, 'plan_free', 'warehouse_export',     FALSE, NULL, NULL),
    (uuid_generate_v4()::TEXT, 'plan_free', 'sheets_export',        FALSE, NULL, NULL),
    (uuid_generate_v4()::TEXT, 'plan_free', 'scheduled_exports',    FALSE, NULL, NULL)
ON CONFLICT (plan_id, feature_key) DO UPDATE SET
    is_enabled  = EXCLUDED.is_enabled,
    limit_value = EXCLUDED.limit_value,
    limits      = EXCLUDED.limits,
    updated_at  = NOW();

-- ---- Growth Plan ----
INSERT INTO plan_features (id, plan_id, feature_key, is_enabled, limit_value, limits)
VALUES
    (uuid_generate_v4()::TEXT, 'plan_growth', 'agency_access',        TRUE,  NULL, '{"max_agency_stores": 5}'),
    (uuid_generate_v4()::TEXT, 'plan_growth', 'multi_tenant',         TRUE,  5,    '{"max_stores": 5}'),
    (uuid_generate_v4()::TEXT, 'plan_growth', 'advanced_dashboards',  TRUE,  NULL, '{"max_dashboard_access": 10, "max_dashboard_shares": 5}'),
    (uuid_generate_v4()::TEXT, 'plan_growth', 'explore_mode',         TRUE,  NULL, NULL),
    (uuid_generate_v4()::TEXT, 'plan_growth', 'data_export',          TRUE,  NULL, '{"format": "csv"}'),
    (uuid_generate_v4()::TEXT, 'plan_growth', 'ai_insights',          TRUE,  NULL, '{"max_dashboard_access": 10, "max_users": 10, "max_alert_rules": 10}'),
    (uuid_generate_v4()::TEXT, 'plan_growth', 'ai_recommendations',   TRUE,  NULL, NULL),
    (uuid_generate_v4()::TEXT, 'plan_growth', 'ai_actions',           TRUE,  NULL, '{"limited": true}'),
    (uuid_generate_v4()::TEXT, 'plan_growth', 'custom_reports',       TRUE,  NULL, NULL),
    (uuid_generate_v4()::TEXT, 'plan_growth', 'llm_routing',          TRUE,  NULL, NULL),
    (uuid_generate_v4()::TEXT, 'plan_growth', 'custom_prompts',       FALSE, NULL, NULL),
    (uuid_generate_v4()::TEXT, 'plan_growth', 'cohort_analysis',      TRUE,  NULL, NULL),
    (uuid_generate_v4()::TEXT, 'plan_growth', 'budget_pacing',        TRUE,  NULL, NULL),
    (uuid_generate_v4()::TEXT, 'plan_growth', 'alerts',               TRUE,  NULL, '{"max_alert_rules": 10}'),
    (uuid_generate_v4()::TEXT, 'plan_growth', 'warehouse_export',     FALSE, NULL, NULL),
    (uuid_generate_v4()::TEXT, 'plan_growth', 'sheets_export',        TRUE,  NULL, '{"limited": true}'),
    (uuid_generate_v4()::TEXT, 'plan_growth', 'scheduled_exports',    FALSE, NULL, NULL)
ON CONFLICT (plan_id, feature_key) DO UPDATE SET
    is_enabled  = EXCLUDED.is_enabled,
    limit_value = EXCLUDED.limit_value,
    limits      = EXCLUDED.limits,
    updated_at  = NOW();

-- ---- Pro Plan ----
INSERT INTO plan_features (id, plan_id, feature_key, is_enabled, limit_value, limits)
VALUES
    (uuid_generate_v4()::TEXT, 'plan_pro', 'agency_access',        TRUE,  NULL, '{"max_agency_stores": 10}'),
    (uuid_generate_v4()::TEXT, 'plan_pro', 'multi_tenant',         TRUE,  10,   '{"max_stores": 10}'),
    (uuid_generate_v4()::TEXT, 'plan_pro', 'advanced_dashboards',  TRUE,  NULL, '{"max_dashboard_access": 50, "max_dashboard_shares": 20}'),
    (uuid_generate_v4()::TEXT, 'plan_pro', 'explore_mode',         TRUE,  NULL, NULL),
    (uuid_generate_v4()::TEXT, 'plan_pro', 'data_export',          TRUE,  NULL, NULL),
    (uuid_generate_v4()::TEXT, 'plan_pro', 'ai_insights',          TRUE,  NULL, '{"max_dashboard_access": 50, "max_users": 20, "max_alert_rules": 50}'),
    (uuid_generate_v4()::TEXT, 'plan_pro', 'ai_recommendations',   TRUE,  NULL, NULL),
    (uuid_generate_v4()::TEXT, 'plan_pro', 'ai_actions',           TRUE,  NULL, NULL),
    (uuid_generate_v4()::TEXT, 'plan_pro', 'custom_reports',       TRUE,  NULL, NULL),
    (uuid_generate_v4()::TEXT, 'plan_pro', 'llm_routing',          TRUE,  NULL, NULL),
    (uuid_generate_v4()::TEXT, 'plan_pro', 'custom_prompts',       FALSE, NULL, NULL),
    (uuid_generate_v4()::TEXT, 'plan_pro', 'cohort_analysis',      TRUE,  NULL, NULL),
    (uuid_generate_v4()::TEXT, 'plan_pro', 'budget_pacing',        TRUE,  NULL, NULL),
    (uuid_generate_v4()::TEXT, 'plan_pro', 'alerts',               TRUE,  NULL, '{"max_alert_rules": 50}'),
    (uuid_generate_v4()::TEXT, 'plan_pro', 'warehouse_export',     TRUE,  1,    '{"max_warehouse_destinations": 1}'),
    (uuid_generate_v4()::TEXT, 'plan_pro', 'sheets_export',        TRUE,  NULL, NULL),
    (uuid_generate_v4()::TEXT, 'plan_pro', 'scheduled_exports',    TRUE,  NULL, NULL)
ON CONFLICT (plan_id, feature_key) DO UPDATE SET
    is_enabled  = EXCLUDED.is_enabled,
    limit_value = EXCLUDED.limit_value,
    limits      = EXCLUDED.limits,
    updated_at  = NOW();

-- ---- Enterprise Plan ----
INSERT INTO plan_features (id, plan_id, feature_key, is_enabled, limit_value, limits)
VALUES
    (uuid_generate_v4()::TEXT, 'plan_enterprise', 'agency_access',        TRUE,  NULL, '{"max_agency_stores": 999}'),
    (uuid_generate_v4()::TEXT, 'plan_enterprise', 'multi_tenant',         TRUE,  NULL, '{"max_stores": 999}'),
    (uuid_generate_v4()::TEXT, 'plan_enterprise', 'advanced_dashboards',  TRUE,  NULL, '{"max_dashboard_access": 999, "max_dashboard_shares": 999}'),
    (uuid_generate_v4()::TEXT, 'plan_enterprise', 'explore_mode',         TRUE,  NULL, NULL),
    (uuid_generate_v4()::TEXT, 'plan_enterprise', 'data_export',          TRUE,  NULL, NULL),
    (uuid_generate_v4()::TEXT, 'plan_enterprise', 'ai_insights',          TRUE,  NULL, '{"max_dashboard_access": 999, "max_users": 999, "max_alert_rules": -1}'),
    (uuid_generate_v4()::TEXT, 'plan_enterprise', 'ai_recommendations',   TRUE,  NULL, NULL),
    (uuid_generate_v4()::TEXT, 'plan_enterprise', 'ai_actions',           TRUE,  NULL, NULL),
    (uuid_generate_v4()::TEXT, 'plan_enterprise', 'custom_reports',       TRUE,  NULL, NULL),
    (uuid_generate_v4()::TEXT, 'plan_enterprise', 'llm_routing',          TRUE,  NULL, NULL),
    (uuid_generate_v4()::TEXT, 'plan_enterprise', 'custom_prompts',       TRUE,  NULL, NULL),
    (uuid_generate_v4()::TEXT, 'plan_enterprise', 'cohort_analysis',      TRUE,  NULL, NULL),
    (uuid_generate_v4()::TEXT, 'plan_enterprise', 'budget_pacing',        TRUE,  NULL, NULL),
    (uuid_generate_v4()::TEXT, 'plan_enterprise', 'alerts',               TRUE,  NULL, '{"max_alert_rules": -1}'),
    (uuid_generate_v4()::TEXT, 'plan_enterprise', 'warehouse_export',     TRUE,  NULL, NULL),
    (uuid_generate_v4()::TEXT, 'plan_enterprise', 'sheets_export',        TRUE,  NULL, NULL),
    (uuid_generate_v4()::TEXT, 'plan_enterprise', 'scheduled_exports',    TRUE,  NULL, NULL)
ON CONFLICT (plan_id, feature_key) DO UPDATE SET
    is_enabled  = EXCLUDED.is_enabled,
    limit_value = EXCLUDED.limit_value,
    limits      = EXCLUDED.limits,
    updated_at  = NOW();
