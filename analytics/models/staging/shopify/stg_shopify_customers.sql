{{
    config(
        materialized='view',
        schema='staging'
    )
}}

with raw_customers as (
    select
        _airbyte_ab_id as airbyte_record_id,
        _airbyte_emitted_at as airbyte_emitted_at,
        _airbyte_data as customer_data
    from {{ source('airbyte_raw', '_airbyte_raw_shopify_customers') }}
),

customers_extracted as (
    select
        raw.airbyte_record_id,
        raw.airbyte_emitted_at,
        raw.customer_data->>'id' as customer_id_raw,
        raw.customer_data->>'email' as email,
        raw.customer_data->>'first_name' as first_name,
        raw.customer_data->>'last_name' as last_name,
        raw.customer_data->>'phone' as phone,
        raw.customer_data->>'created_at' as created_at_raw,
        raw.customer_data->>'updated_at' as updated_at_raw,
        raw.customer_data->>'accepts_marketing' as accepts_marketing_raw,
        raw.customer_data->>'orders_count' as orders_count_raw,
        raw.customer_data->>'total_spent' as total_spent_raw,
        raw.customer_data->>'currency' as currency_code,
        raw.customer_data->>'state' as state,
        raw.customer_data->>'tags' as tags_raw,
        raw.customer_data->>'note' as note,
        raw.customer_data->>'verified_email' as verified_email_raw,
        raw.customer_data->>'default_address' as default_address_json
    from raw_customers raw
),

customers_normalized as (
    select
        -- Primary key: normalize customer ID (remove gid:// prefix if present)
        case
            when customer_id_raw like 'gid://shopify/Customer/%' 
                then replace(customer_id_raw, 'gid://shopify/Customer/', '')
            else customer_id_raw
        end as customer_id,
        
        -- Customer information
        email,
        first_name,
        last_name,
        phone,
        coalesce(first_name || ' ' || last_name, first_name, last_name, email) as full_name,
        
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
        
        -- Boolean fields: convert to boolean
        case
            when accepts_marketing_raw in ('true', 'True', '1', 'yes') then true
            when accepts_marketing_raw in ('false', 'False', '0', 'no', '') then false
            else null
        end as accepts_marketing,
        
        case
            when verified_email_raw in ('true', 'True', '1', 'yes') then true
            when verified_email_raw in ('false', 'False', '0', 'no', '') then false
            else null
        end as verified_email,
        
        -- Numeric fields: convert to numeric, handle nulls
        case
            when orders_count_raw is not null and orders_count_raw != ''
                then orders_count_raw::integer
            else 0
        end as orders_count,
        
        case
            when total_spent_raw is not null and total_spent_raw != ''
                then total_spent_raw::numeric
            else 0.0
        end as total_spent,
        
        -- Currency: standardize to uppercase
        upper(coalesce(currency_code, 'USD')) as currency,
        
        -- Additional fields
        state,
        tags_raw as tags,
        note,
        
        -- Address information (extracted from JSON)
        case
            when default_address_json is not null
                then default_address_json::json->>'country'
            else null
        end as country_code,
        
        case
            when default_address_json is not null
                then default_address_json::json->>'city'
            else null
        end as city,
        
        -- Metadata
        airbyte_record_id,
        airbyte_emitted_at
        
    from customers_extracted
),

-- Join to tenant mapping to get tenant_id
-- Uses same strategy as stg_shopify_orders
customers_with_tenant as (
    select
        cust.*,
        coalesce(
            -- Option 1: Extract from schema if connection_id is in schema name
            -- (select tenant_id from {{ ref('_tenant_airbyte_connections') }}
            --  where airbyte_connection_id = split_part(current_schema(), '_', 2)),
            
            -- Option 2: Use first active Shopify connection (for single-connection setups)
            (select tenant_id from {{ ref('_tenant_airbyte_connections') }} limit 1),
            
            -- Fallback: null if no connection found
            null
        ) as tenant_id
    from customers_normalized cust
)

select
    customer_id,
    email,
    first_name,
    last_name,
    full_name,
    phone,
    created_at,
    updated_at,
    accepts_marketing,
    verified_email,
    orders_count,
    total_spent,
    currency,
    state,
    country_code,
    city,
    tags,
    note,
    airbyte_record_id,
    airbyte_emitted_at,
    tenant_id
from customers_with_tenant
where tenant_id is not null
