{{
    config(
        materialized='view',
        schema='staging'
    )
}}

{#
    Staging model for Shopify customers with normalized fields and tenant isolation.

    Migrated from Airbyte v1 JSONB (_airbyte_data blob) to v2 typed columns.
    Source: airbyte_raw.customers (v2)

    v1 → v2 metadata column mapping:
      _airbyte_ab_id       → _airbyte_raw_id
      _airbyte_emitted_at  → _airbyte_extracted_at

    Key simplifications in v2:
      - accepts_marketing, verified_email: already boolean (no string parsing needed)
      - created_at, updated_at: already timestamp with time zone
      - orders_count: already bigint
      - total_spent: already numeric
      - default_address: already jsonb

    Output contract is unchanged — same column names and types as the v1 version.

    SECURITY: Tenant isolation enforced via inner join on shop_domain.
#}

with raw_customers as (
    select
        _airbyte_raw_id       as airbyte_record_id,
        _airbyte_extracted_at as airbyte_emitted_at,
        -- v2: id is bigint (plain numeric Shopify ID)
        id::text              as customer_id_raw,
        email,
        first_name,
        last_name,
        phone,
        state,
        currency              as currency_code,
        tags,
        note,
        created_at,                     -- timestamp with time zone
        updated_at,
        accepts_marketing,              -- boolean in v2
        verified_email,                 -- boolean in v2
        orders_count,                   -- bigint in v2
        total_spent,                    -- numeric in v2
        default_address,                -- jsonb in v2
        shop_url
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

customers_normalized as (
    select
        airbyte_record_id,
        airbyte_emitted_at,

        -- customer_id: v2 id is bigint — no gid:// prefix to strip
        case
            when customer_id_raw is null or trim(customer_id_raw) = '' then null
            else trim(customer_id_raw)
        end as customer_id,

        -- Customer information
        email,
        first_name,
        last_name,
        phone,
        coalesce(first_name || ' ' || last_name, first_name, last_name, email) as full_name,

        -- Timestamps: already timestamp with time zone in v2 — normalize to UTC
        (created_at at time zone 'UTC') as created_at,
        (updated_at at time zone 'UTC') as updated_at,

        -- Booleans: already boolean in v2 — no string parsing needed
        accepts_marketing,
        verified_email,

        -- Numeric fields: already typed in v2 — apply bounds checking only
        case
            when orders_count is null then 0
            else least(greatest(orders_count::integer, 0), 2147483647)
        end as orders_count,

        case
            when total_spent is null then 0.0
            else least(greatest(total_spent, -999999999.99), 999999999.99)
        end as total_spent,

        -- Currency: standardize to uppercase
        case
            when currency_code is null or trim(currency_code) = '' then 'USD'
            when upper(trim(currency_code)) ~ '^[A-Z]{3}$'
                then upper(trim(currency_code))
            else 'USD'
        end as currency,

        state,
        tags,
        note,

        -- Address extraction: default_address is already jsonb in v2
        case
            when default_address is null then null
            else (default_address->>'country_code')
        end as country_code,

        case
            when default_address is null then null
            else (default_address->>'city')
        end as city,

        -- Normalized shop_domain for tenant mapping
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

    from raw_customers
),

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
