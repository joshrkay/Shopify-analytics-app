{{
    config(
        materialized='view',
        schema='staging'
    )
}}

{#
    Staging model for Shopify orders with strict typing, standardization, and dedup.

    Migrated from Airbyte v1 JSONB (_airbyte_data blob) to v2 typed columns.
    Source: airbyte_raw.orders (v2)

    v1 → v2 metadata column mapping:
      _airbyte_ab_id       → _airbyte_raw_id
      _airbyte_emitted_at  → _airbyte_extracted_at

    Output contract is unchanged — same column names and types as the v1 version.
    All downstream models (canonical, attribution, marts) continue to work without changes.

    SECURITY: Tenant isolation enforced via inner join on shop_domain.
#}

with raw_orders as (
    select
        _airbyte_raw_id       as airbyte_record_id,
        _airbyte_extracted_at as airbyte_emitted_at,
        -- v2: id is bigint (no gid:// prefix — plain numeric Shopify ID)
        id::text              as order_id_raw,
        name                  as order_name,
        order_number,                               -- bigint
        email                 as customer_email,
        created_at,                                 -- timestamp with time zone
        updated_at,
        cancelled_at,
        closed_at,
        financial_status,
        fulfillment_status,
        total_price,                                -- numeric
        subtotal_price,
        total_tax,
        -- total_shipping_price_set is still JSONB in v2
        total_shipping_price_set->'shop_money'->>'amount' as total_shipping_price_raw,
        currency,
        customer,                                   -- jsonb
        tags,
        note,
        refunds,                                    -- jsonb
        shop_url
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

orders_normalized as (
    select
        airbyte_record_id,
        airbyte_emitted_at,

        -- order_id: v2 id is a plain bigint — no gid:// prefix to strip
        case
            when order_id_raw is null or trim(order_id_raw) = '' then null
            else trim(order_id_raw)
        end as order_id,

        order_name,

        -- order_number: already bigint in v2, just bounds-check
        case
            when order_number is null then null
            when order_number between 0 and 2147483647 then order_number::integer
            else null
        end as order_number,

        customer_email,

        -- customer_id: extract from jsonb customer field (still jsonb in v2)
        case
            when customer is null then null
            else (customer->>'id')
        end as customer_id_raw,

        -- Timestamps: already timestamp with time zone in v2 — normalize to UTC
        (created_at at time zone 'UTC') as created_at,
        (updated_at at time zone 'UTC') as updated_at,
        (cancelled_at at time zone 'UTC') as cancelled_at,
        (closed_at at time zone 'UTC') as closed_at,

        -- Financial: already numeric in v2 — apply bounds checking only
        case
            when total_price is null then 0.0
            else least(greatest(total_price, -999999999.99), 999999999.99)
        end as total_price,

        case
            when subtotal_price is null then 0.0
            else least(greatest(subtotal_price, -999999999.99), 999999999.99)
        end as subtotal_price,

        case
            when total_tax is null then 0.0
            else least(greatest(total_tax, -999999999.99), 999999999.99)
        end as total_tax,

        -- Shipping: extracted from JSONB (still a nested price_set object in v2)
        case
            when total_shipping_price_raw is null or trim(total_shipping_price_raw) = '' then 0.0
            when trim(total_shipping_price_raw) ~ '^-?[0-9]+\.?[0-9]*([eE][+-]?[0-9]+)?$'
                then least(greatest(trim(total_shipping_price_raw)::numeric, -999999999.99), 999999999.99)
            else 0.0
        end as total_shipping_price,

        -- Currency: already varchar in v2 — standardize to uppercase
        case
            when currency is null or trim(currency) = '' then 'USD'
            when upper(trim(currency)) ~ '^[A-Z]{3}$'
                then upper(trim(currency))
            else 'USD'
        end as currency,

        coalesce(financial_status, 'unknown') as financial_status,
        coalesce(fulfillment_status, 'unfulfilled') as fulfillment_status,

        tags,
        note,
        refunds as refunds_json,

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

    from raw_orders
),

orders_with_tenant as (
    select
        ord.*,
        tm.tenant_id
    from orders_normalized ord
    inner join tenant_mapping tm
        on ord.shop_domain = tm.shop_domain
),

-- Dedup: keep latest record per (tenant_id, order_id)
orders_deduped as (
    select
        *,
        row_number() over (
            partition by tenant_id, order_id
            order by airbyte_emitted_at desc
        ) as _row_num
    from orders_with_tenant
    where order_id is not null
        and trim(order_id) != ''
)

select
    -- Surrogate key: md5(tenant_id || source_system || source_primary_key)
    md5(tenant_id || '|' || 'shopify' || '|' || order_id) as record_sk,

    -- Source tracking
    'shopify' as source_system,
    order_id as source_primary_key,

    -- Tenant isolation
    tenant_id,

    -- Order identifiers
    order_id,
    order_name,
    order_number,
    created_at::date as report_date,

    -- Customer fields
    customer_email,
    customer_id_raw,

    -- Timestamps (all UTC)
    created_at,
    updated_at,
    cancelled_at,
    closed_at,

    -- Financial fields (strict numeric types, no business metric calculations)
    total_price,
    subtotal_price,
    total_tax,
    total_shipping_price,
    currency,

    -- Status fields
    financial_status,
    fulfillment_status,

    -- Additional fields
    tags,
    note,
    refunds_json,

    -- Metadata
    airbyte_record_id,
    airbyte_emitted_at

from orders_deduped
where _row_num = 1
