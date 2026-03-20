-- Migration: Create pixel_registrations table for tracking Web Pixel deployments
-- Links pixel installations to tenants/stores for audit and management

CREATE TABLE IF NOT EXISTS pixel_registrations (
    id                  VARCHAR(255) PRIMARY KEY DEFAULT gen_random_uuid()::text,
    tenant_id           VARCHAR(255) NOT NULL,
    shop_domain         VARCHAR(255) NOT NULL,
    pixel_id            VARCHAR(255) UNIQUE,
    shopify_pixel_gid   VARCHAR(255),
    status              VARCHAR(50) NOT NULL DEFAULT 'active',
    created_at          TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
);

-- Indexes
CREATE INDEX IF NOT EXISTS ix_pixel_registrations_tenant_id
    ON pixel_registrations (tenant_id);
CREATE INDEX IF NOT EXISTS ix_pixel_registrations_shop_domain
    ON pixel_registrations (shop_domain);
CREATE INDEX IF NOT EXISTS ix_pixel_registrations_pixel_id
    ON pixel_registrations (pixel_id);

-- RLS policy for tenant isolation
ALTER TABLE pixel_registrations ENABLE ROW LEVEL SECURITY;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_policies
        WHERE tablename = 'pixel_registrations'
          AND policyname = 'tenant_isolation_pixel_registrations'
    ) THEN
        CREATE POLICY tenant_isolation_pixel_registrations
            ON pixel_registrations
            USING (tenant_id = current_setting('app.current_tenant_id', true));
    END IF;
END $$;
