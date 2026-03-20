-- Migration: Create webhook_order_events table for real-time order data from Shopify webhooks
-- Provides immediate order visibility without waiting for 60-min Airbyte sync

CREATE TABLE IF NOT EXISTS webhook_order_events (
    id                  VARCHAR(255) PRIMARY KEY DEFAULT gen_random_uuid()::text,
    tenant_id           VARCHAR(255) NOT NULL,
    shop_domain         VARCHAR(255) NOT NULL,
    shopify_order_id    VARCHAR(255) NOT NULL,
    order_name          VARCHAR(255),
    order_number        VARCHAR(50),
    total_price         NUMERIC(12, 2),
    subtotal_price      NUMERIC(12, 2),
    currency            VARCHAR(10),
    financial_status    VARCHAR(50),
    fulfillment_status  VARCHAR(50),
    utm_source          VARCHAR(255),
    utm_medium          VARCHAR(255),
    utm_campaign        VARCHAR(500),
    utm_term            VARCHAR(500),
    utm_content         VARCHAR(500),
    note_attributes_json JSONB,
    raw_payload         JSONB,
    event_type          VARCHAR(20) NOT NULL,
    order_created_at    TIMESTAMP WITH TIME ZONE,
    received_at         TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    created_at          TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
);

-- Indexes for tenant-scoped queries
CREATE INDEX IF NOT EXISTS ix_webhook_order_events_tenant_order
    ON webhook_order_events (tenant_id, shopify_order_id);
CREATE INDEX IF NOT EXISTS ix_webhook_order_events_tenant_received
    ON webhook_order_events (tenant_id, received_at);
CREATE INDEX IF NOT EXISTS ix_webhook_order_events_tenant_id
    ON webhook_order_events (tenant_id);

-- RLS policy for tenant isolation
ALTER TABLE webhook_order_events ENABLE ROW LEVEL SECURITY;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_policies
        WHERE tablename = 'webhook_order_events'
          AND policyname = 'tenant_isolation_webhook_order_events'
    ) THEN
        CREATE POLICY tenant_isolation_webhook_order_events
            ON webhook_order_events
            USING (tenant_id = current_setting('app.current_tenant_id', true));
    END IF;
END $$;
