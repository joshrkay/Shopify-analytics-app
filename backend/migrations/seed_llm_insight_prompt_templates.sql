-- Seed system prompt templates for LLM-enhanced insight narratives.
--
-- Consumed by insight_generation_service._enhance_with_llm() via
-- enhance_pair_with_llm_sync(template_key_a="insight_summary",
--                            template_key_b="insight_why_it_matters")
--
-- Variables injected at render time ({{variable}} syntax):
--   insight_type  - InsightType enum value (e.g., "roas_change", "spend_anomaly")
--   severity      - InsightSeverity value ("info", "warning", "critical")
--   metrics       - Serialized list of metric objects with current_value, prior_value, delta_pct
--   period_type   - Period string (e.g., "last_30_days", "weekly")
--   platform      - Ad channel name or "all" (e.g., "meta_ads", "google_ads")
--
-- Both templates fall back gracefully to deterministic insight_templates.py strings
-- when the LLM is unavailable or the tenant lacks LLM_ROUTING entitlement.
-- Safe to re-run: ON CONFLICT DO NOTHING.

INSERT INTO llm_prompt_template (tenant_id, template_key, version, template_content, variables, is_active, is_system)
VALUES
    (NULL, 'insight_summary', 1,
     'You are an analytics assistant for a Shopify merchant. Generate a single sentence (max 25 words) summarizing this marketing insight. Be specific and data-driven. Use plain English. No markdown, no preamble — respond with the sentence only.

Insight type: {{insight_type}}
Severity: {{severity}}
Platform: {{platform}}
Period: {{period_type}}
Metrics: {{metrics}}',
     '["insight_type", "severity", "metrics", "period_type", "platform"]',
     true, true),

    (NULL, 'insight_why_it_matters', 1,
     'You are an analytics assistant for a Shopify merchant. Write 1-2 sentences explaining why this marketing insight matters for the merchant''s business. Focus on the revenue or profitability implication. Use conditional language (e.g., "may indicate", "could suggest"). No markdown, no preamble — respond with the sentences only.

Insight type: {{insight_type}}
Severity: {{severity}}
Platform: {{platform}}
Period: {{period_type}}
Metrics: {{metrics}}',
     '["insight_type", "severity", "metrics", "period_type", "platform"]',
     true, true)

ON CONFLICT (tenant_id, template_key, version) DO NOTHING;
