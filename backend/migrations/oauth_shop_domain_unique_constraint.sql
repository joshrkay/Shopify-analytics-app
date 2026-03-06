-- ============================================================================
-- Migration: OAuth Shop Domain Unique Constraint
-- ============================================================================
-- Version: 1.0.0
-- Date: 2026-01-31
-- Purpose: Prevent data leakage via duplicate shop_domain mappings
--
-- CRITICAL SECURITY FIX:
-- This migration prevents multiple tenants from connecting the same Shopify
-- shop_domain, which would cause DBT to duplicate data across tenants.
--
-- Background:
-- - DBT derives tenant_id by JOINing on shop_domain extracted from Airbyte data
-- - If two tenants have same shop_domain, JOIN returns duplicate rows
-- - This causes data leakage (Tenant B sees Tenant A's data)
--
-- Solution:
-- - Add UNIQUE constraint on normalized shop_domain for active connections
-- - Uses same normalization as DBT (lowercase, no protocol, no trailing slash)
-- - Only applies to active + enabled Shopify connections
--
-- Rollback:
-- DROP INDEX IF EXISTS ix_tenant_airbyte_connections_shop_domain_unique;
-- ============================================================================

-- =============================================================================
-- Pre-Migration Validation: Check for Existing Duplicates
-- =============================================================================

DO $$
DECLARE
    duplicate_count INTEGER;
    duplicate_rec RECORD;
BEGIN
    -- Find duplicate shop_domains in active connections
    SELECT COUNT(*) INTO duplicate_count
    FROM (
        SELECT
            lower(
                trim(
                    trailing '/' from
                    regexp_replace(
                        coalesce(configuration->>'shop_domain', ''),
                        '^https?://',
                        '',
                        'i'
                    )
                )
            ) as normalized_shop_domain,
            COUNT(*) as tenant_count
        FROM public.tenant_airbyte_connections
        WHERE source_type IN ('shopify', 'source-shopify')
          AND status = 'active'
          AND is_enabled = true
          AND configuration->>'shop_domain' IS NOT NULL
          AND configuration->>'shop_domain' != ''
        GROUP BY 1
        HAVING COUNT(*) > 1
    ) duplicates;

    IF duplicate_count > 0 THEN
        RAISE WARNING '╔════════════════════════════════════════════════════════════╗';
        RAISE WARNING '║ CRITICAL: Found % duplicate shop_domains               ║', duplicate_count;
        RAISE WARNING '║ These must be resolved before creating unique constraint  ║';
        RAISE WARNING '╚════════════════════════════════════════════════════════════╝';
        RAISE WARNING '';
        RAISE WARNING 'Duplicate shop_domains:';
        RAISE WARNING '─────────────────────────────────────────────────────────────';

        -- Log each duplicate with tenant details
        FOR duplicate_rec IN (
            SELECT
                lower(
                    trim(
                        trailing '/' from
                        regexp_replace(
                            coalesce(configuration->>'shop_domain', ''),
                            '^https?://',
                            '',
                            'i'
                        )
                    )
                ) as shop_domain,
                array_agg(tenant_id ORDER BY tenant_id) as tenant_ids,
                array_agg(connection_name ORDER BY connection_name) as connection_names,
                array_agg(id ORDER BY id) as connection_ids,
                COUNT(*) as count
            FROM public.tenant_airbyte_connections
            WHERE source_type IN ('shopify', 'source-shopify')
              AND status = 'active'
              AND is_enabled = true
              AND configuration->>'shop_domain' IS NOT NULL
              AND configuration->>'shop_domain' != ''
            GROUP BY 1
            HAVING COUNT(*) > 1
            ORDER BY COUNT(*) DESC
        ) LOOP
            RAISE WARNING 'Shop: %', duplicate_rec.shop_domain;
            RAISE WARNING '  Tenant IDs: %', duplicate_rec.tenant_ids;
            RAISE WARNING '  Connection Names: %', duplicate_rec.connection_names;
            RAISE WARNING '  Connection IDs: %', duplicate_rec.connection_ids;
            RAISE WARNING '';
        END LOOP;

        RAISE WARNING '─────────────────────────────────────────────────────────────';
        RAISE WARNING 'ACTION REQUIRED:';
        RAISE WARNING '1. Review which tenant legitimately owns each shop';
        RAISE WARNING '2. Disable or delete duplicate connections:';
        RAISE WARNING '   UPDATE public.tenant_airbyte_connections';
        RAISE WARNING '   SET is_enabled = false WHERE id = ''<connection_id>'';';
        RAISE WARNING '3. Re-run this migration after cleanup';
        RAISE WARNING '─────────────────────────────────────────────────────────────';

        RAISE EXCEPTION 'Cannot create unique index with % existing duplicates. Resolve conflicts first.', duplicate_count;
    ELSE
        RAISE NOTICE '✓ No duplicate shop_domains found';
        RAISE NOTICE '✓ Safe to create unique constraint';
    END IF;
END $$;

-- =============================================================================
-- Create Unique Index on shop_domain
-- =============================================================================

-- Partial unique index: Ensures no two ACTIVE Shopify connections can have the same shop_domain
-- This prevents data leakage via duplicate shop_domain mappings in DBT
--
-- Normalization matches DBT staging models exactly:
-- - lowercase
-- - strip leading https:// or http://
-- - strip trailing /
--
-- Note: Cannot use CREATE INDEX CONCURRENTLY inside a transaction, so we use
-- a regular CREATE UNIQUE INDEX here.
CREATE UNIQUE INDEX IF NOT EXISTS ix_tenant_airbyte_connections_shop_domain_unique
    ON public.tenant_airbyte_connections (
        lower(
            trim(
                trailing '/' from
                regexp_replace(
                    coalesce(configuration->>'shop_domain', ''),
                    '^https?://',
                    '',
                    'i'
                )
            )
        )
    )
    WHERE source_type IN ('shopify', 'source-shopify')
      AND status = 'active'
      AND is_enabled = true
      AND configuration->>'shop_domain' IS NOT NULL
      AND configuration->>'shop_domain' != '';

-- =============================================================================
-- Post-Migration Validation
-- =============================================================================

DO $$
DECLARE
    index_exists BOOLEAN;
    active_shopify_count INTEGER;
BEGIN
    -- Verify index was created
    SELECT EXISTS (
        SELECT 1
        FROM pg_indexes
        WHERE schemaname = 'public'
          AND tablename = 'tenant_airbyte_connections'
          AND indexname = 'ix_tenant_airbyte_connections_shop_domain_unique'
    ) INTO index_exists;

    IF index_exists THEN
        RAISE NOTICE '✓ Index verified: ix_tenant_airbyte_connections_shop_domain_unique';
    ELSE
        RAISE EXCEPTION 'Index creation failed: ix_tenant_airbyte_connections_shop_domain_unique not found';
    END IF;

    -- Count active Shopify connections
    SELECT COUNT(*) INTO active_shopify_count
    FROM public.tenant_airbyte_connections
    WHERE source_type IN ('shopify', 'source-shopify')
      AND status = 'active'
      AND is_enabled = true
      AND configuration->>'shop_domain' IS NOT NULL;

    RAISE NOTICE '✓ Active Shopify connections protected: %', active_shopify_count;
    RAISE NOTICE '';
    RAISE NOTICE '═══════════════════════════════════════════════════════════════';
    RAISE NOTICE 'Migration completed successfully';
    RAISE NOTICE '═══════════════════════════════════════════════════════════════';
END $$;
