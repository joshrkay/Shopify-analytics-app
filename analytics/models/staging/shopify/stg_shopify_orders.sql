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
    from {{ source('raw_shopify', 'orders') }}
),

tenant_mapping as (
    select
        tenant_id,
        shop_domain
    from {{ ref('_tenant_airbyte_connections') }}
    where source_type in ('shopify', 'source-shopify')
        and status = 'active'
        and is_enabled = true
        and shop_domain is not null
        and shop_domain != ''
),

orders_extracted as (
    select
        raw.airbyte_record_id,
        raw.airbyte_emitted_at,
        -- Extract shop_url for tenant mapping (Airbyte includes this in order data)
        raw.order_data->>'shop_url' as shop_url,
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
        raw.order_data->>'order_number' as order_number_raw,
        raw.order_data->'refunds' as refunds_json
    from raw_orders raw
),

orders_normalized as (
    select
        -- Primary key: normalize order ID (remove gid:// prefix if present)
        -- Edge case: Handle null, empty, and various GID formats
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
        -- Edge case: Handle invalid integers, nulls, empty strings
        case
            when order_number_raw is null or trim(order_number_raw) = '' then null
            when order_number_raw ~ '^[0-9]+$' 
                then order_number_raw::integer
            else null
        end as order_number,
        
        -- Customer information
        customer_email,
        -- Edge case: Validate JSON before extraction to prevent casting errors
        case
            when customer_json is null or trim(customer_json) = '' then null
            when customer_json::text ~ '^\s*\{' 
                then (customer_json::json->>'id')
            else null
        end as customer_id_raw,
        
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
        
        -- Financial fields: convert to numeric, handle nulls and invalid values
        -- Edge case: Validate numeric format, handle negative, scientific notation
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
        
        -- Currency: standardize to uppercase, validate format
        -- Edge case: Handle null, empty, invalid currency codes
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
        note,
        refunds_json,
        
        -- Metadata
        airbyte_record_id,
        airbyte_emitted_at,

        -- Normalized shop_domain for tenant mapping
        -- Normalize: lowercase, strip protocol and trailing slash
        lower(
            trim(
                trailing '/' from
                regexp_replace(
                    coalesce(shop_url, ''),
                    '^https?://',
                    '',
                    'i'
                )
            )
        ) as shop_domain

    from orders_extracted
),

-- Join to tenant mapping on shop_domain for proper multi-tenant isolation
-- Each order is mapped to its tenant via the shop_url field from Airbyte
orders_with_tenant as (
    select
        ord.order_id,
        ord.order_name,
        ord.order_number,
        ord.customer_email,
        ord.customer_id_raw,
        ord.created_at,
        ord.updated_at,
        ord.cancelled_at,
        ord.closed_at,
        ord.total_price,
        ord.subtotal_price,
        ord.total_tax,
        ord.currency,
        ord.financial_status,
        ord.fulfillment_status,
        ord.tags,
        ord.note,
        ord.refunds_json,
        ord.airbyte_record_id,
        ord.airbyte_emitted_at,
        tm.tenant_id
    from orders_normalized ord
    inner join tenant_mapping tm
        on ord.shop_domain = tm.shop_domain
)

select
    tenant_id,
    order_id,
    order_name,
    order_number,
    -- report_date: Standard date field for staging contract consistency
    created_at::date as report_date,
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
    refunds_json,
    airbyte_record_id,
    airbyte_emitted_at
from orders_with_tenant
where order_id is not null
    and trim(order_id) != ''
