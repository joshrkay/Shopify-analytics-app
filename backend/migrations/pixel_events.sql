-- Migration: Create pixel_events table for Shopify Web Pixel customer journey tracking
-- Stores page views, product views, checkout events for multi-touch attribution

CREATE TABLE IF NOT EXISTS pixel_events (
    id                  VARCHAR(255) PRIMARY KEY DEFAULT gen_random_uuid()::text,
    tenant_id           VARCHAR(255) NOT NULL,
    shop_domain         VARCHAR(255) NOT NULL,
    session_id          VARCHAR(255) NOT NULL,
    event_type          VARCHAR(100) NOT NULL,
    event_data          JSONB,
    page_url            VARCHAR(2048),
    referrer            VARCHAR(2048),
    utm_source          VARCHAR(255),
    utm_medium          VARCHAR(255),
    utm_campaign        VARCHAR(500),
    utm_term            VARCHAR(500),
    utm_content         VARCHAR(500),
    event_timestamp     TIMESTAMP WITH TIME ZONE NOT NULL,
    created_at          TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
);

-- Indexes for tenant-scoped queries
CREATE INDEX IF NOT EXISTS ix_pixel_events_tenant_session
    ON pixel_events (tenant_id, session_id);
CREATE INDEX IF NOT EXISTS ix_pixel_events_tenant_type_ts
    ON pixel_events (tenant_id, event_type, event_timestamp);
CREATE INDEX IF NOT EXISTS ix_pixel_events_tenant_ts
    ON pixel_events (tenant_id, event_timestamp);
CREATE INDEX IF NOT EXISTS ix_pixel_events_tenant_id
    ON pixel_events (tenant_id);

-- RLS policy for tenant isolation
ALTER TABLE pixel_events ENABLE ROW LEVEL SECURITY;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_policies
        WHERE tablename = 'pixel_events'
          AND policyname = 'tenant_isolation_pixel_events'
    ) THEN
        CREATE POLICY tenant_isolation_pixel_events
            ON pixel_events
            USING (tenant_id = current_setting('app.current_tenant_id', true));
    END IF;
END $$;
