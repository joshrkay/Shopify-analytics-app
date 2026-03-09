-- ============================================================================
-- Migration: OAuth Shop Domain Unique Constraint
-- ============================================================================
-- Version: 1.1.0
-- Date: 2026-01-31 (fixed 2026-03-09: schema refs, syntax errors, CONCURRENTLY)
-- Purpose: Prevent data leakage via duplicate shop_domain mappings
--
-- CRITICAL SECURITY FIX:
-- This migration prevents multiple tenants from connecting the same Shopify
-- shop_domain, which would cause DBT to duplicate data across tenants.
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
        FROM tenant_airbyte_connections
        WHERE source_type IN ('shopify', 'source-shopify')
          AND status = 'active'
          AND is_enabled = true
          AND configuration->>'shop_domain' IS NOT NULL
          AND configuration->>'shop_domain' != ''
        GROUP BY 1
        HAVING COUNT(*) > 1
    ) duplicates;

    IF duplicate_count > 0 THEN
        RAISE WARNING 'CRITICAL: Found % duplicate shop_domains. Resolve before creating unique constraint.', duplicate_count;

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
            FROM tenant_airbyte_connections
            WHERE source_type IN ('shopify', 'source-shopify')
              AND status = 'active'
              AND is_enabled = true
              AND configuration->>'shop_domain' IS NOT NULL
              AND configuration->>'shop_domain' != ''
            GROUP BY 1
            HAVING COUNT(*) > 1
            ORDER BY COUNT(*) DESC
        ) LOOP
            RAISE WARNING 'Shop: % | Tenants: % | Connections: %',
                duplicate_rec.shop_domain, duplicate_rec.tenant_ids, duplicate_rec.connection_ids;
        END LOOP;

        RAISE EXCEPTION 'Cannot create unique index with % existing duplicates. Resolve conflicts first.', duplicate_count;
    ELSE
        RAISE NOTICE 'No duplicate shop_domains found — safe to create unique constraint';
    END IF;
END $$;

-- =============================================================================
-- Create Unique Index on shop_domain
-- =============================================================================
-- NOTE: Uses CONCURRENTLY so must run outside a transaction.
-- The migration runner detects CONCURRENTLY and sets autocommit=True.

CREATE UNIQUE INDEX CONCURRENTLY IF NOT EXISTS ix_tenant_airbyte_connections_shop_domain_unique
    ON tenant_airbyte_connections (
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

COMMENT ON INDEX ix_tenant_airbyte_connections_shop_domain_unique IS
    'SECURITY: Ensures each shop_domain can only be connected to one tenant at a time. '
    'Prevents data leakage via DBT JOIN on shop_domain. '
    'Uses same normalization as DBT staging models. '
    'Only applies to active, enabled Shopify connections.';

-- =============================================================================
-- Post-Migration Validation
-- =============================================================================

DO $$
DECLARE
    index_exists BOOLEAN;
    active_shopify_count INTEGER;
BEGIN
    SELECT EXISTS (
        SELECT 1
        FROM pg_indexes
        WHERE schemaname = 'public'
          AND tablename = 'tenant_airbyte_connections'
          AND indexname = 'ix_tenant_airbyte_connections_shop_domain_unique'
    ) INTO index_exists;

    IF index_exists THEN
        RAISE NOTICE 'Index verified: ix_tenant_airbyte_connections_shop_domain_unique';
    ELSE
        RAISE EXCEPTION 'Index creation failed: ix_tenant_airbyte_connections_shop_domain_unique not found';
    END IF;

    SELECT COUNT(*) INTO active_shopify_count
    FROM tenant_airbyte_connections
    WHERE source_type IN ('shopify', 'source-shopify')
      AND status = 'active'
      AND is_enabled = true
      AND configuration->>'shop_domain' IS NOT NULL;

    RAISE NOTICE 'Active Shopify connections protected: %', active_shopify_count;
    RAISE NOTICE 'Migration completed successfully';
END $$;
