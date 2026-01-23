{{
    config(
        materialized='view',
        schema='staging'
    )
}}

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
    from {{ ref('tenant_airbyte_connections') }}
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
        raw.order_data->>'email' as customer_email,
        raw.order_data->>'created_at' as created_at_raw,
        raw.order_data->>'updated_at' as updated_at_raw,
        raw.order_data->>'cancelled_at' as cancelled_at_raw,
        raw.order_data->>'closed_at' as closed_at_raw,
        raw.order_data->>'financial_status' as financial_status,
        raw.order_data->>'fulfillment_status' as fulfillment_status,
        raw.order_data->>'total_price' as total_price_raw,
        raw.order_data->>'subtotal_price' as subtotal_price_raw,
        raw.order_data->>'total_tax' as total_tax_raw,
        raw.order_data->>'currency' as currency_code,
        raw.order_data->>'customer' as customer_json,
        raw.order_data->>'line_items' as line_items_json,
        raw.order_data->>'billing_address' as billing_address_json,
        raw.order_data->>'shipping_address' as shipping_address_json,
        raw.order_data->>'tags' as tags_raw,
        raw.order_data->>'note' as note,
        raw.order_data->>'order_number' as order_number_raw
    from raw_orders raw
),

orders_normalized as (
    select
        -- Primary key: normalize order ID (remove gid:// prefix if present)
        case
            when order_id_raw like 'gid://shopify/Order/%' 
                then replace(order_id_raw, 'gid://shopify/Order/', '')
            else order_id_raw
        end as order_id,
        
        -- Order identifiers
        order_name,
        order_number_raw::integer as order_number,
        
        -- Customer information
        customer_email,
        case
            when customer_json is not null 
                then customer_json::json->>'id'
            else null
        end as customer_id_raw,
        
        -- Timestamps: normalize to UTC
        case
            when created_at_raw is not null 
                then (created_at_raw::timestamp with time zone) at time zone 'UTC'
            else null
        end as created_at,
        
        case
            when updated_at_raw is not null 
                then (updated_at_raw::timestamp with time zone) at time zone 'UTC'
            else null
        end as updated_at,
        
        case
            when cancelled_at_raw is not null 
                then (cancelled_at_raw::timestamp with time zone) at time zone 'UTC'
            else null
        end as cancelled_at,
        
        case
            when closed_at_raw is not null 
                then (closed_at_raw::timestamp with time zone) at time zone 'UTC'
            else null
        end as closed_at,
        
        -- Financial fields: convert to numeric, handle nulls
        case
            when total_price_raw is not null and total_price_raw != ''
                then total_price_raw::numeric
            else 0.0
        end as total_price,
        
        case
            when subtotal_price_raw is not null and subtotal_price_raw != ''
                then subtotal_price_raw::numeric
            else 0.0
        end as subtotal_price,
        
        case
            when total_tax_raw is not null and total_tax_raw != ''
                then total_tax_raw::numeric
            else 0.0
        end as total_tax,
        
        -- Currency: standardize to uppercase
        upper(coalesce(currency_code, 'USD')) as currency,
        
        -- Status fields
        coalesce(financial_status, 'unknown') as financial_status,
        coalesce(fulfillment_status, 'unfulfilled') as fulfillment_status,
        
        -- Additional fields
        tags_raw as tags,
        note,
        
        -- Metadata
        airbyte_record_id,
        airbyte_emitted_at
        
    from orders_extracted
),

-- Join to tenant mapping to get tenant_id
-- 
-- Tenant mapping strategy:
-- 1. If Airbyte uses connection-specific schemas, extract connection_id from current_schema()
-- 2. If connection_id is in table metadata, use that
-- 3. For single-tenant setups, use the first active Shopify connection
--
-- This implementation uses a subquery to get tenant_id. Adjust based on your Airbyte setup:
-- - If schemas are connection-specific: extract connection_id from schema name
-- - If you have a connection_id column: join on that
-- - For single connection per tenant: use the approach below
orders_with_tenant as (
    select
        ord.*,
        coalesce(
            -- Option 1: Extract from schema if connection_id is in schema name
            -- (select tenant_id from {{ ref('_tenant_airbyte_connections') }}
            --  where airbyte_connection_id = split_part(current_schema(), '_', 2)),
            
            -- Option 2: Use first active Shopify connection (for single-connection setups)
            (select tenant_id from {{ ref('_tenant_airbyte_connections') }} limit 1),
            
            -- Fallback: null if no connection found
            null
        ) as tenant_id
    from orders_normalized ord
)

select
    order_id,
    order_name,
    order_number,
    customer_email,
    customer_id_raw,
    created_at,
    updated_at,
    cancelled_at,
    closed_at,
    total_price,
    subtotal_price,
    total_tax,
    currency,
    financial_status,
    fulfillment_status,
    tags,
    note,
    airbyte_record_id,
    airbyte_emitted_at,
    tenant_id
from orders_with_tenant
where tenant_id is not null
