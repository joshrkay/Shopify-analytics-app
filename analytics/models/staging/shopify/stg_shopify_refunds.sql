{{
    config(
        materialized='incremental',
        schema='staging',
        unique_key='refund_id',
        incremental_strategy='delete+insert'
    )
}}

{#
    Staging model for Shopify refunds.

    PII Policy: No PII fields (names, emails, phones, addresses) are exposed.
    Only IDs and metrics are included.

    Required contract fields:
    - tenant_id
    - report_date (date grain)
    - refund_id (primary key)
    - order_id (foreign key to stg_shopify_orders)
#}

with raw_refunds as (
    select
        _airbyte_ab_id as airbyte_record_id,
        _airbyte_emitted_at as airbyte_emitted_at,
        _airbyte_data as refund_data
    from {{ source('airbyte_raw', '_airbyte_raw_shopify_refunds') }}
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

refunds_extracted as (
    select
        raw.airbyte_record_id,
        raw.airbyte_emitted_at,
        raw.refund_data->>'id' as refund_id_raw,
        raw.refund_data->>'order_id' as order_id_raw,
        raw.refund_data->>'created_at' as created_at_raw,
        raw.refund_data->>'processed_at' as processed_at_raw,
        -- PII EXCLUDED: note field may contain customer info
        -- Extract refund line items for amount calculation
        raw.refund_data->'refund_line_items' as refund_line_items_json,
        raw.refund_data->'transactions' as transactions_json,
        -- Order adjustments for shipping refunds
        raw.refund_data->'order_adjustments' as order_adjustments_json
    from raw_refunds raw
),

refunds_normalized as (
    select
        -- Primary key: normalize refund ID
        case
            when refund_id_raw is null or trim(refund_id_raw) = '' then null
            when refund_id_raw like 'gid://shopify/Refund/%'
                then replace(refund_id_raw, 'gid://shopify/Refund/', '')
            else trim(refund_id_raw)
        end as refund_id,

        -- Order ID (foreign key)
        case
            when order_id_raw is null or trim(order_id_raw) = '' then null
            when order_id_raw like 'gid://shopify/Order/%'
                then replace(order_id_raw, 'gid://shopify/Order/', '')
            else trim(order_id_raw)
        end as order_id,

        -- Timestamps
        case
            when created_at_raw is null or trim(created_at_raw) = '' then null
            when created_at_raw ~ '^\d{4}-\d{2}-\d{2}'
                then (created_at_raw::timestamp with time zone) at time zone 'UTC'
            else null
        end as created_at,

        case
            when processed_at_raw is null or trim(processed_at_raw) = '' then null
            when processed_at_raw ~ '^\d{4}-\d{2}-\d{2}'
                then (processed_at_raw::timestamp with time zone) at time zone 'UTC'
            else null
        end as processed_at,

        -- Calculate refund amount from transactions
        coalesce(
            (
                select sum(
                    case
                        when (t->>'amount') ~ '^-?[0-9]+\.?[0-9]*$'
                        then (t->>'amount')::numeric
                        else 0
                    end
                )
                from jsonb_array_elements(coalesce(transactions_json, '[]'::jsonb)) as t
                where t->>'kind' = 'refund'
            ),
            0
        ) as refund_amount,

        -- Count of refunded line items
        coalesce(jsonb_array_length(refund_line_items_json), 0) as refunded_items_count,

        -- Shipping refund amount from order adjustments
        coalesce(
            (
                select sum(
                    case
                        when (a->>'amount') ~ '^-?[0-9]+\.?[0-9]*$'
                        then abs((a->>'amount')::numeric)
                        else 0
                    end
                )
                from jsonb_array_elements(coalesce(order_adjustments_json, '[]'::jsonb)) as a
                where a->>'kind' = 'shipping_refund'
            ),
            0
        ) as shipping_refund_amount,

        -- Metadata
        airbyte_record_id,
        airbyte_emitted_at

    from refunds_extracted
),

-- Join to tenant mapping
refunds_with_tenant as (
    select
        ref.*,
        coalesce(
            (select tenant_id
             from {{ ref('_tenant_airbyte_connections') }}
             where source_type = 'shopify'
               and status = 'active'
               and is_enabled = true
             limit 1),
            null
        ) as tenant_id
    from refunds_normalized ref
)

select
    -- Primary keys
    refund_id,
    tenant_id,

    -- Date grain (required contract field)
    coalesce(processed_at, created_at)::date as report_date,

    -- Foreign key
    order_id,

    -- Timestamps
    created_at,
    processed_at,

    -- Refund metrics
    refund_amount,
    shipping_refund_amount,
    refund_amount + shipping_refund_amount as total_refund_amount,
    refunded_items_count,

    -- Metadata
    airbyte_record_id,
    airbyte_emitted_at

from refunds_with_tenant
where tenant_id is not null
    and refund_id is not null
    and trim(refund_id) != ''

{{ incremental_filter_timestamp('airbyte_emitted_at', 'shopify_refunds') }}
