-- Baseline seed data for E2E tests.
--
-- This SQL runs when the PostgreSQL container starts for the first time.
-- It creates the minimal schema and seed data needed by the test suite.
--
-- NOTE: The full schema is created by Alembic migrations run by the backend.
-- This file only provides data that the /api/test/seed endpoint can't create
-- because it depends on schema objects that must exist first.
--
-- The backend's test_seed.py route handles most seeding via SQLAlchemy models.
-- This file is a fallback for bootstrapping the initial state.

-- Ensure the identity schema exists (created by Alembic, but just in case)
-- CREATE SCHEMA IF NOT EXISTS public;

-- Placeholder: The actual table creation is handled by Alembic migrations.
-- The backend startup runs migrations before serving requests.
-- This file seeds only the data that must exist before any API call.

-- Plans (baseline pricing tiers)
-- These are inserted via /api/test/seed, but we provide a fallback here
-- in case the seed endpoint isn't available during bootstrap.

DO $$
BEGIN
  -- Only insert if the plans table exists (created by Alembic)
  IF EXISTS (SELECT FROM information_schema.tables WHERE table_name = 'plans') THEN
    INSERT INTO plans (id, name, display_name, price_monthly_cents, is_active, created_at, updated_at)
    VALUES
      ('plan-free-001', 'free', 'Free', 0, true, NOW(), NOW()),
      ('plan-growth-001', 'growth', 'Growth', 4900, true, NOW(), NOW()),
      ('plan-pro-001', 'pro', 'Pro', 14900, true, NOW(), NOW()),
      ('plan-enterprise-001', 'enterprise', 'Enterprise', 49900, true, NOW(), NOW())
    ON CONFLICT (id) DO NOTHING;
  END IF;
END
$$;
