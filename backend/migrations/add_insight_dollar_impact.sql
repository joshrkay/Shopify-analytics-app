-- Migration: Add estimated_dollar_impact and dollar_impact_explanation to ai_insights
-- Adds LLM-generated dollar impact estimation fields to AI insights.
-- Both columns are nullable so existing insights are unaffected.

ALTER TABLE ai_insights
    ADD COLUMN IF NOT EXISTS estimated_dollar_impact NUMERIC(15, 2),
    ADD COLUMN IF NOT EXISTS dollar_impact_explanation TEXT;
