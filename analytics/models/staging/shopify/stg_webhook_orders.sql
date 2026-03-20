{{
    config(
        materialized='view',
        schema='staging'
    )
}}

{#
    Staging model for webhook-delivered Shopify orders.

    Normalizes webhook_order_events into the same shape as stg_shopify_orders
    so downstream models (canonical, attribution) can UNION both sources.

    Deduplicates by (tenant_id, order_id) keeping the latest webhook event.
    Returns empty result if source table doesn't exist yet (CI safety).

    SECURITY: Tenant isolation enforced via tenant_id (set at webhook ingestion time).
#}

-- Check if source table exists; if not, return empty result set
{% if not source_exists('platform', 'webhook_order_events') %}

select
    cast(null as text) as record_sk,
    cast(null as text) as source_system,
    cast(null as text) as source_primary_key,
    cast(null as text) as tenant_id,
    cast(null as text) as order_id,
    cast(null as text) as order_name,
    cast(null as integer) as order_number,
    cast(null as date) as report_date,
    cast(null as text) as customer_email,
    cast(null as text) as customer_id_raw,
    cast(null as timestamp with time zone) as created_at,
    cast(null as timestamp with time zone) as updated_at,
    cast(null as timestamp with time zone) as cancelled_at,
    cast(null as timestamp with time zone) as closed_at,
    cast(null as numeric) as total_price,
    cast(null as numeric) as subtotal_price,
    cast(null as numeric) as total_tax,
    cast(null as numeric) as total_shipping_price,
    cast(null as text) as currency,
    cast(null as text) as financial_status,
    cast(null as text) as fulfillment_status,
    cast(null as text) as tags,
    cast(null as text) as note,
    cast(null as jsonb) as refunds_json,
    cast(null as text) as utm_source,
    cast(null as text) as utm_medium,
    cast(null as text) as utm_campaign,
    cast(null as text) as utm_term,
    cast(null as text) as utm_content,
    cast(null as text) as airbyte_record_id,
    cast(null as timestamp with time zone) as airbyte_emitted_at
where 1=0

{% else %}

with webhook_orders as (
    select
        id as webhook_event_id,
        tenant_id,
        shop_domain,
        shopify_order_id,
        order_name,
        order_number,
        total_price,
        subtotal_price,
        currency,
        financial_status,
        fulfillment_status,
        utm_source,
        utm_medium,
        utm_campaign,
        utm_term,
        utm_content,
        order_created_at,
        received_at,
        event_type,
        raw_payload,
        created_at
    from {{ source('platform', 'webhook_order_events') }}
    where tenant_id is not null
),

-- Dedup: keep latest webhook event per (tenant_id, order_id)
orders_deduped as (
    select
        *,
        row_number() over (
            partition by tenant_id, shopify_order_id
            order by received_at desc
        ) as _row_num
    from webhook_orders
    where shopify_order_id is not null
        and trim(shopify_order_id) != ''
)

select
    -- Surrogate key matching stg_shopify_orders pattern
    md5(tenant_id || '|' || 'shopify_webhook' || '|' || shopify_order_id) as record_sk,

    -- Source tracking
    'shopify_webhook' as source_system,
    shopify_order_id as source_primary_key,

    -- Tenant isolation
    tenant_id,

    -- Order identifiers
    shopify_order_id as order_id,
    order_name,
    case
        when order_number is null or trim(order_number) = '' then null
        when order_number ~ '^[0-9]+$' then order_number::integer
        else null
    end as order_number,
    order_created_at::date as report_date,

    -- Customer fields (not available in webhook payload without extraction)
    raw_payload->>'email' as customer_email,
    raw_payload->'customer'->>'id' as customer_id_raw,

    -- Timestamps
    order_created_at as created_at,
    received_at as updated_at,
    case
        when raw_payload->>'cancelled_at' is not null
            and raw_payload->>'cancelled_at' != ''
        then (raw_payload->>'cancelled_at')::timestamp with time zone
        else null
    end as cancelled_at,
    case
        when raw_payload->>'closed_at' is not null
            and raw_payload->>'closed_at' != ''
        then (raw_payload->>'closed_at')::timestamp with time zone
        else null
    end as closed_at,

    -- Financial fields
    coalesce(total_price, 0.0) as total_price,
    coalesce(subtotal_price, 0.0) as subtotal_price,
    coalesce((raw_payload->>'total_tax')::numeric, 0.0) as total_tax,
    coalesce(
        (raw_payload->'total_shipping_price_set'->'shop_money'->>'amount')::numeric,
        0.0
    ) as total_shipping_price,
    coalesce(upper(trim(currency)), 'USD') as currency,

    -- Status fields
    coalesce(financial_status, 'unknown') as financial_status,
    coalesce(fulfillment_status, 'unfulfilled') as fulfillment_status,

    -- Additional fields
    raw_payload->>'tags' as tags,
    raw_payload->>'note' as note,
    raw_payload->'refunds' as refunds_json,

    -- UTM attribution (pre-extracted from note_attributes)
    utm_source,
    utm_medium,
    utm_campaign,
    utm_term,
    utm_content,

    -- Metadata
    webhook_event_id as airbyte_record_id,
    received_at as airbyte_emitted_at

from orders_deduped
where _row_num = 1

{% endif %}
