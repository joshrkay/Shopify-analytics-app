{{
    config(
        materialized='incremental',
        schema='staging',
        unique_key='order_id',
        incremental_strategy='delete+insert'
    )
}}

{#
    Staging model for Shopify orders.

    PII Policy: No PII fields (names, emails, phones, addresses) are exposed.
    Only IDs and metrics are included.

    Required contract fields:
    - tenant_id
    - report_date (date grain)
    - order_id (primary key)
#}

with raw_orders as (
    select
        _airbyte_ab_id as airbyte_record_id,
        _airbyte_emitted_at as airbyte_emitted_at,
        _airbyte_data as order_data
    from {{ source('airbyte_raw', '_airbyte_raw_shopify_orders') }}
),

tenant_mapping as (
    select
        airbyte_connection_id,
        tenant_id,
        source_type
    from {{ ref('_tenant_airbyte_connections') }}
    where source_type = 'shopify'
        and status = 'active'
        and is_enabled = true
),

orders_extracted as (
    select
        raw.airbyte_record_id,
        raw.airbyte_emitted_at,
        raw.order_data->>'id' as order_id_raw,
        raw.order_data->>'name' as order_name,
        -- PII EXCLUDED: email, name, phone, address fields are not extracted
        raw.order_data->>'created_at' as created_at_raw,
        raw.order_data->>'updated_at' as updated_at_raw,
        raw.order_data->>'cancelled_at' as cancelled_at_raw,
        raw.order_data->>'closed_at' as closed_at_raw,
        raw.order_data->>'financial_status' as financial_status,
        raw.order_data->>'fulfillment_status' as fulfillment_status,
        raw.order_data->>'total_price' as total_price_raw,
        raw.order_data->>'subtotal_price' as subtotal_price_raw,
        raw.order_data->>'total_tax' as total_tax_raw,
        raw.order_data->>'total_shipping_price_set' as total_shipping_raw,
        raw.order_data->>'total_discounts' as total_discounts_raw,
        raw.order_data->>'currency' as currency_code,
        -- Extract customer ID only (no PII)
        raw.order_data->'customer'->>'id' as customer_id_raw,
        raw.order_data->>'tags' as tags_raw,
        raw.order_data->>'order_number' as order_number_raw,
        raw.order_data->'refunds' as refunds_json,
        -- Line items count for units_sold
        jsonb_array_length(coalesce(raw.order_data->'line_items', '[]'::jsonb)) as line_items_count,
        -- Source info for channel mapping
        raw.order_data->>'source_name' as source_name,
        raw.order_data->>'landing_site' as landing_site
    from raw_orders raw
),

orders_normalized as (
    select
        -- Primary key: normalize order ID (remove gid:// prefix if present)
        case
            when order_id_raw is null or trim(order_id_raw) = '' then null
            when order_id_raw like 'gid://shopify/Order/%'
                then replace(order_id_raw, 'gid://shopify/Order/', '')
            when order_id_raw like 'gid://shopify/Order%'
                then regexp_replace(order_id_raw, '^gid://shopify/Order/?', '', 'g')
            else trim(order_id_raw)
        end as order_id,

        -- Order identifiers
        order_name,
        case
            when order_number_raw is null or trim(order_number_raw) = '' then null
            when order_number_raw ~ '^[0-9]+$'
                then order_number_raw::integer
            else null
        end as order_number,

        -- Customer ID only (PII excluded)
        case
            when customer_id_raw is null or trim(customer_id_raw) = '' then null
            else trim(customer_id_raw)
        end as customer_id,

        -- Timestamps: normalize to UTC
        -- Edge case: Handle invalid timestamp formats gracefully
        case
            when created_at_raw is null or trim(created_at_raw) = '' then null
            when created_at_raw ~ '^\d{4}-\d{2}-\d{2}' 
                then (created_at_raw::timestamp with time zone) at time zone 'UTC'
            else null
        end as created_at,
        
        case
            when updated_at_raw is null or trim(updated_at_raw) = '' then null
            when updated_at_raw ~ '^\d{4}-\d{2}-\d{2}' 
                then (updated_at_raw::timestamp with time zone) at time zone 'UTC'
            else null
        end as updated_at,
        
        case
            when cancelled_at_raw is null or trim(cancelled_at_raw) = '' then null
            when cancelled_at_raw ~ '^\d{4}-\d{2}-\d{2}' 
                then (cancelled_at_raw::timestamp with time zone) at time zone 'UTC'
            else null
        end as cancelled_at,
        
        case
            when closed_at_raw is null or trim(closed_at_raw) = '' then null
            when closed_at_raw ~ '^\d{4}-\d{2}-\d{2}' 
                then (closed_at_raw::timestamp with time zone) at time zone 'UTC'
            else null
        end as closed_at,
        
        -- Financial fields: convert to numeric
        case
            when total_price_raw is null or trim(total_price_raw) = '' then 0.0
            when trim(total_price_raw) ~ '^-?[0-9]+\.?[0-9]*([eE][+-]?[0-9]+)?$'
                then least(greatest(trim(total_price_raw)::numeric, -999999999.99), 999999999.99)
            else 0.0
        end as total_price,

        case
            when subtotal_price_raw is null or trim(subtotal_price_raw) = '' then 0.0
            when trim(subtotal_price_raw) ~ '^-?[0-9]+\.?[0-9]*([eE][+-]?[0-9]+)?$'
                then least(greatest(trim(subtotal_price_raw)::numeric, -999999999.99), 999999999.99)
            else 0.0
        end as subtotal_price,

        case
            when total_tax_raw is null or trim(total_tax_raw) = '' then 0.0
            when trim(total_tax_raw) ~ '^-?[0-9]+\.?[0-9]*([eE][+-]?[0-9]+)?$'
                then least(greatest(trim(total_tax_raw)::numeric, -999999999.99), 999999999.99)
            else 0.0
        end as total_tax,

        case
            when total_shipping_raw is null or trim(total_shipping_raw) = '' then 0.0
            when trim(total_shipping_raw) ~ '^-?[0-9]+\.?[0-9]*([eE][+-]?[0-9]+)?$'
                then least(greatest(trim(total_shipping_raw)::numeric, -999999999.99), 999999999.99)
            else 0.0
        end as total_shipping,

        case
            when total_discounts_raw is null or trim(total_discounts_raw) = '' then 0.0
            when trim(total_discounts_raw) ~ '^-?[0-9]+\.?[0-9]*([eE][+-]?[0-9]+)?$'
                then least(greatest(trim(total_discounts_raw)::numeric, -999999999.99), 999999999.99)
            else 0.0
        end as total_discounts,

        -- Currency: standardize to uppercase
        case
            when currency_code is null or trim(currency_code) = '' then 'USD'
            when upper(trim(currency_code)) ~ '^[A-Z]{3}$'
                then upper(trim(currency_code))
            else 'USD'
        end as currency,

        -- Status fields
        coalesce(financial_status, 'unknown') as financial_status,
        coalesce(fulfillment_status, 'unfulfilled') as fulfillment_status,

        -- Additional fields
        tags_raw as tags,
        refunds_json,
        coalesce(line_items_count, 0) as units_sold,

        -- Source info for channel mapping
        source_name,
        landing_site,

        -- Metadata
        airbyte_record_id,
        airbyte_emitted_at

    from orders_extracted
),

-- Join to tenant mapping to get tenant_id
-- SECURITY FIX: Proper tenant isolation using connection metadata
-- 
-- This implementation attempts to extract connection_id from available metadata.
-- Airbyte raw tables typically don't include connection_id directly, so we use
-- one of these strategies based on your Airbyte configuration:
--
-- Strategy 1: Schema-based isolation (most common)
-- If Airbyte writes each connection to a separate schema, extract from current_schema()
--
-- Strategy 2: Table name prefixes
-- If table names include connection_id, extract from table metadata
--
-- Strategy 3: Custom extraction (requires Airbyte normalization customization)
-- If you've configured Airbyte to include connection_id in _airbyte_data
--
-- NOTE: This implementation uses Strategy 1 (schema-based) as the default.
-- If your setup is different, adjust the connection_id_from_source CTE below.
orders_with_connection as (
    select
        ord.*,
        -- Extract connection identifier from source
        -- Adjust this based on your Airbyte configuration:
        -- 
        -- For schema-based isolation (default):
        -- Assumes schema name format: airbyte_raw_<connection_id> or <connection_id>_raw
        case
            when current_schema() ~ '^airbyte_raw_[a-zA-Z0-9-]+$'
                then regexp_replace(current_schema(), '^airbyte_raw_', '')
            when current_schema() ~ '^[a-zA-Z0-9-]+_raw$'
                then regexp_replace(current_schema(), '_raw$', '')
            -- For connection-specific schemas with tenant prefix
            when current_schema() ~ '^[a-zA-Z0-9-]+_[a-zA-Z0-9-]+_raw$'
                then split_part(current_schema(), '_', 2)
            -- Fallback: use full schema name as identifier
            else current_schema()
        end as connection_identifier
    from orders_normalized ord
),

-- Map connection identifier to tenant_id
orders_with_tenant as (
    select
        ord.*,
        t.tenant_id
    from orders_with_connection ord
    left join {{ ref('_tenant_airbyte_connections') }} t
        on t.airbyte_connection_id = ord.connection_identifier
        and t.source_type = 'shopify'
        and t.status = 'active'
        and t.is_enabled = true
)

select
    -- Primary keys
    order_id,
    tenant_id,

    -- Date grain (required contract field)
    created_at::date as report_date,

    -- Order identifiers
    order_name,
    order_number,

    -- Customer (ID only, no PII)
    customer_id,

    -- Timestamps
    created_at,
    updated_at,
    cancelled_at,
    closed_at,

    -- Financial metrics (gross revenue)
    total_price as revenue_gross,
    subtotal_price,
    total_tax,
    total_shipping,
    total_discounts,
    -- Net revenue = gross - discounts (refunds handled separately)
    total_price - total_discounts as revenue_net,
    currency,

    -- Units
    units_sold,

    -- Status
    financial_status,
    fulfillment_status,

    -- Tags
    tags,

    -- Refunds JSON for downstream processing
    refunds_json,

    -- Source/channel info
    source_name as platform_channel,

    -- Metadata
    airbyte_record_id,
    airbyte_emitted_at

from orders_with_tenant
where tenant_id is not null
    and order_id is not null
    and trim(order_id) != ''

{{ incremental_filter_timestamp('airbyte_emitted_at', 'shopify_orders') }}
