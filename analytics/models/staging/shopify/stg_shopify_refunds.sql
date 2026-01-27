{{
    config(
        materialized='incremental',
        unique_key='refund_surrogate_key',
        schema='staging',
        incremental_strategy='merge'
    )
}}

{#
    Staging model for Shopify refunds.

    This model extracts refund data from orders and normalizes it into a
    dedicated refunds table for accurate revenue_net calculations.

    Output contract:
    - tenant_id
    - report_date (refund date)
    - order_id (link to original order)
    - refund_id
    - Refund amount metrics
#}

with raw_orders as (
    select
        _airbyte_ab_id as airbyte_record_id,
        _airbyte_emitted_at as airbyte_emitted_at,
        _airbyte_data as order_data
    from {{ source('airbyte_raw', '_airbyte_raw_shopify_orders') }}
    {% if is_incremental() %}
    where {{ incremental_timestamp_filter('_airbyte_emitted_at', 'shopify') }}
    {% endif %}
),

orders_with_refunds as (
    select
        raw.airbyte_record_id,
        raw.airbyte_emitted_at,
        raw.order_data->>'id' as order_id_raw,
        raw.order_data->>'currency' as currency_code,
        coalesce(
            raw.order_data->>'shop_id',
            raw.order_data->>'admin_graphql_api_id'
        ) as shop_id_raw,
        raw.order_data->'refunds' as refunds_json
    from raw_orders raw
    where raw.order_data->'refunds' is not null
        and jsonb_array_length(raw.order_data->'refunds') > 0
),

refunds_unnested as (
    select
        o.airbyte_record_id,
        o.airbyte_emitted_at,
        o.order_id_raw,
        o.currency_code,
        o.shop_id_raw,
        refund.value as refund_data
    from orders_with_refunds o,
    lateral jsonb_array_elements(o.refunds_json) as refund(value)
),

refunds_extracted as (
    select
        airbyte_record_id,
        airbyte_emitted_at,
        -- Order ID normalization
        case
            when order_id_raw is null or trim(order_id_raw) = '' then null
            when order_id_raw like 'gid://shopify/Order/%'
                then replace(order_id_raw, 'gid://shopify/Order/', '')
            else trim(order_id_raw)
        end as order_id,
        -- Refund identifiers
        refund_data->>'id' as refund_id_raw,
        refund_data->>'created_at' as refund_created_at_raw,
        refund_data->>'processed_at' as refund_processed_at_raw,
        -- Refund line items for amount calculation
        refund_data->'refund_line_items' as refund_line_items_json,
        refund_data->'transactions' as transactions_json,
        -- Currency
        currency_code,
        -- Shop ID
        shop_id_raw
    from refunds_unnested
),

refunds_normalized as (
    select
        -- Refund ID
        case
            when refund_id_raw is null or trim(refund_id_raw) = '' then null
            when refund_id_raw like 'gid://shopify/Refund/%'
                then replace(refund_id_raw, 'gid://shopify/Refund/', '')
            else trim(refund_id_raw)
        end as refund_id,

        order_id,

        -- Refund timestamp
        case
            when refund_created_at_raw is null or trim(refund_created_at_raw) = '' then null
            when refund_created_at_raw ~ '^\d{4}-\d{2}-\d{2}'
                then (refund_created_at_raw::timestamp with time zone) at time zone 'UTC'
            else null
        end as refund_created_at,

        -- Report date (date grain)
        case
            when refund_created_at_raw is null or trim(refund_created_at_raw) = '' then null
            when refund_created_at_raw ~ '^\d{4}-\d{2}-\d{2}'
                then (refund_created_at_raw::timestamp with time zone)::date
            else null
        end as report_date,

        -- Calculate refund amount from transactions
        coalesce(
            (select sum(
                case
                    when (txn->>'amount') ~ '^-?[0-9]+\.?[0-9]*$'
                    then abs((txn->>'amount')::numeric)
                    else 0
                end
            )
            from jsonb_array_elements(transactions_json) as txn
            where txn->>'kind' = 'refund'
            ),
            0
        ) as refund_amount,

        -- Count refund line items for units
        case
            when refund_line_items_json is null then 0
            else coalesce(
                (select sum((item->>'quantity')::integer)
                 from jsonb_array_elements(refund_line_items_json) as item),
                0
            )
        end as refund_units,

        -- Currency normalization
        case
            when currency_code is null or trim(currency_code) = '' then 'USD'
            when upper(trim(currency_code)) ~ '^[A-Z]{3}$'
                then upper(trim(currency_code))
            else 'USD'
        end as currency,

        -- Account ID
        coalesce(trim(shop_id_raw), 'unknown') as platform_account_id,

        -- Metadata
        airbyte_record_id,
        airbyte_emitted_at

    from refunds_extracted
    where refund_id_raw is not null
),

-- Join to tenant mapping
refunds_with_tenant as (
    select
        r.*,
        coalesce(
            (select tenant_id
             from {{ ref('_tenant_airbyte_connections') }}
             where source_type = 'shopify'
               and platform_account_id = r.platform_account_id
               and status = 'active'
               and is_enabled = true
             limit 1),
            null
        ) as tenant_id
    from refunds_normalized r
),

final as (
    select
        -- Surrogate key
        md5(
            coalesce(tenant_id, '') || '|' ||
            coalesce(refund_id, '') || '|' ||
            coalesce(order_id, '')
        ) as refund_surrogate_key,

        -- Identity
        tenant_id,
        refund_id,
        order_id,

        -- Date grain
        report_date,

        -- Source
        'shopify' as source,

        -- Account identity
        platform_account_id,
        {{ generate_internal_account_id('tenant_id', "'shopify'", 'platform_account_id') }} as internal_account_id,

        -- Timestamps
        refund_created_at,

        -- Refund metrics
        refund_amount,
        refund_units,
        currency,

        -- Metadata
        airbyte_record_id,
        airbyte_emitted_at,
        current_timestamp as dbt_loaded_at

    from refunds_with_tenant
    where tenant_id is not null
        and refund_id is not null
        and order_id is not null
        and report_date is not null
)

select * from final
