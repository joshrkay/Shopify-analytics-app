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
    from {{ source('raw_shopify', 'customers') }}
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

customers_extracted as (
    select
        raw.airbyte_record_id,
        raw.airbyte_emitted_at,
        -- Extract shop_url for tenant mapping (Airbyte includes this in customer data)
        raw.customer_data->>'shop_url' as shop_url,
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
        -- Edge case: Handle null, empty, and various GID formats
        case
            when customer_id_raw is null or trim(customer_id_raw) = '' then null
            when customer_id_raw like 'gid://shopify/Customer/%' 
                then replace(customer_id_raw, 'gid://shopify/Customer/', '')
            when customer_id_raw like 'gid://shopify/Customer%' 
                then regexp_replace(customer_id_raw, '^gid://shopify/Customer/?', '', 'g')
            else trim(customer_id_raw)
        end as customer_id,
        
        -- Customer information
        email,
        first_name,
        last_name,
        phone,
        coalesce(first_name || ' ' || last_name, first_name, last_name, email) as full_name,
        
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
        
        -- Boolean fields: convert to boolean
        -- Edge case: Handle case variations, numeric booleans, whitespace
        case
            when accepts_marketing_raw is null then null
            when lower(trim(coalesce(accepts_marketing_raw, ''))) in ('true', '1', 'yes', 'y', 't') then true
            when lower(trim(coalesce(accepts_marketing_raw, ''))) in ('false', '0', 'no', 'n', 'f', '') then false
            else null
        end as accepts_marketing,
        
        case
            when verified_email_raw is null then null
            when lower(trim(coalesce(verified_email_raw, ''))) in ('true', '1', 'yes', 'y', 't') then true
            when lower(trim(coalesce(verified_email_raw, ''))) in ('false', '0', 'no', 'n', 'f', '') then false
            else null
        end as verified_email,
        
        -- Numeric fields: convert to numeric, handle nulls and invalid values
        -- Edge case: Validate format, handle negative values, bounds checking
        case
            when orders_count_raw is null or trim(orders_count_raw) = '' then 0
            when trim(orders_count_raw) ~ '^-?[0-9]+$' 
                then least(greatest(trim(orders_count_raw)::integer, 0), 2147483647)
            else 0
        end as orders_count,
        
        case
            when total_spent_raw is null or trim(total_spent_raw) = '' then 0.0
            when trim(total_spent_raw) ~ '^-?[0-9]+\.?[0-9]*([eE][+-]?[0-9]+)?$' 
                then least(greatest(trim(total_spent_raw)::numeric, -999999999.99), 999999999.99)
            else 0.0
        end as total_spent,
        
        -- Currency: standardize to uppercase, validate format
        -- Edge case: Handle null, empty, invalid currency codes
        case
            when currency_code is null or trim(currency_code) = '' then 'USD'
            when upper(trim(currency_code)) ~ '^[A-Z]{3}$' 
                then upper(trim(currency_code))
            else 'USD'
        end as currency,
        
        -- Additional fields
        state,
        tags_raw as tags,
        note,
        
        -- Address information (extracted from JSON)
        -- Edge case: Validate JSON before extraction to prevent casting errors
        case
            when default_address_json is null or trim(default_address_json) = '' then null
            when default_address_json::text ~ '^\s*\{' 
                then (default_address_json::json->>'country')
            else null
        end as country_code,
        
        case
            when default_address_json is null or trim(default_address_json) = '' then null
            when default_address_json::text ~ '^\s*\{' 
                then (default_address_json::json->>'city')
            else null
        end as city,
        
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

    from customers_extracted
),

-- Join to tenant mapping on shop_domain for proper multi-tenant isolation
-- Each customer is mapped to its tenant via the shop_url field from Airbyte
customers_with_tenant as (
    select
        cust.customer_id,
        cust.email,
        cust.first_name,
        cust.last_name,
        cust.full_name,
        cust.phone,
        cust.created_at,
        cust.updated_at,
        cust.accepts_marketing,
        cust.verified_email,
        cust.orders_count,
        cust.total_spent,
        cust.currency,
        cust.state,
        cust.country_code,
        cust.city,
        cust.tags,
        cust.note,
        cust.airbyte_record_id,
        cust.airbyte_emitted_at,
        tm.tenant_id
    from customers_normalized cust
    inner join tenant_mapping tm
        on cust.shop_domain = tm.shop_domain
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
where customer_id is not null
    and trim(customer_id) != ''
    and email is not null
    and trim(email) != ''
