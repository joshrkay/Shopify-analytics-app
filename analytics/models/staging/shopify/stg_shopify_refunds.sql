{{
    config(
        materialized='view',
        schema='staging'
    )
}}

{#
    Staging model for Shopify refunds extracted from order data.

    Shopify stores refunds as a JSON array within each order record.
    This model unnests that array to provide individual refund records
    with proper amounts, dates, and line item details.

    This enables:
    - Accurate refund amounts (vs. estimating from financial_status)
    - Proper refund dates (vs. using cancelled_at)
    - Line-item level refund tracking
    - Multiple refunds per order support

    Output columns:
    - tenant_id: Tenant identifier for data isolation
    - report_date: Refund date (for staging contract consistency)
    - refund_id: Unique refund identifier
    - order_id: Parent order identifier
    - refund_amount: Total refund amount (positive value)
    - refund_reason: Reason for refund (if provided)
    - created_at: Refund creation timestamp
    - processed_at: Refund processing timestamp
#}

with orders_with_refunds as (
    select
        tenant_id,
        order_id,
        refunds_json,
        currency,
        airbyte_record_id,
        airbyte_emitted_at
    from {{ ref('stg_shopify_orders') }}
    where refunds_json is not null
      and refunds_json::text != '[]'
      and refunds_json::text != 'null'
),

-- Unnest the refunds JSON array
refunds_unnested as (
    select
        o.tenant_id,
        o.order_id,
        o.currency,
        o.airbyte_record_id,
        o.airbyte_emitted_at,
        refund_element.value as refund_data
    from orders_with_refunds o,
    lateral jsonb_array_elements(o.refunds_json::jsonb) as refund_element(value)
),

refunds_extracted as (
    select
        tenant_id,
        order_id,
        currency,
        airbyte_record_id,
        airbyte_emitted_at,

        -- Refund identifiers
        refund_data->>'id' as refund_id_raw,
        refund_data->>'admin_graphql_api_id' as refund_gid,

        -- Timestamps
        refund_data->>'created_at' as created_at_raw,
        refund_data->>'processed_at' as processed_at_raw,

        -- Refund details
        refund_data->>'note' as refund_note,
        refund_data->>'restock' as restock_raw,

        -- User who processed refund
        refund_data->>'user_id' as user_id,

        -- Refund line items (for calculating actual refund amount)
        refund_data->'refund_line_items' as refund_line_items_json,

        -- Order adjustments (shipping refunds, etc.)
        refund_data->'order_adjustments' as order_adjustments_json,

        -- Transactions (actual money movement)
        refund_data->'transactions' as transactions_json

    from refunds_unnested
),

refunds_normalized as (
    select
        tenant_id,
        order_id,
        currency,
        airbyte_record_id,
        airbyte_emitted_at,

        -- Refund ID: normalize (remove gid:// prefix if present)
        case
            when refund_id_raw is null or trim(refund_id_raw) = '' then null
            when refund_id_raw like 'gid://shopify/Refund/%'
                then replace(refund_id_raw, 'gid://shopify/Refund/', '')
            else trim(refund_id_raw)
        end as refund_id,

        -- Timestamps: normalize to UTC
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

        -- Refund note/reason
        refund_note as refund_reason,

        -- Restock flag
        case
            when lower(restock_raw) in ('true', '1', 'yes', 'y', 't') then true
            when lower(restock_raw) in ('false', '0', 'no', 'n', 'f') then false
            else null
        end as is_restock,

        -- Calculate refund amount from refund_line_items
        -- Each line item has: subtotal (item cost), total_tax
        coalesce(
            (
                select sum(
                    coalesce((item->>'subtotal')::numeric, 0) +
                    coalesce((item->>'total_tax')::numeric, 0)
                )
                from jsonb_array_elements(refund_line_items_json) as item
            ),
            0.0
        ) as line_items_refund_amount,

        -- Calculate order adjustments (shipping refunds, restocking fees, etc.)
        coalesce(
            (
                select sum(coalesce((adj->>'amount')::numeric, 0))
                from jsonb_array_elements(order_adjustments_json) as adj
            ),
            0.0
        ) as adjustments_amount,

        -- Calculate actual refund from transactions (most accurate)
        coalesce(
            (
                select sum(coalesce((txn->>'amount')::numeric, 0))
                from jsonb_array_elements(transactions_json) as txn
                where txn->>'kind' = 'refund'
                  and txn->>'status' = 'success'
            ),
            0.0
        ) as transaction_refund_amount,

        -- Count of line items refunded
        coalesce(jsonb_array_length(refund_line_items_json), 0) as refund_line_items_count,

        -- Raw JSON for debugging
        refund_line_items_json,
        order_adjustments_json,
        transactions_json

    from refunds_extracted
),

refunds_final as (
    select
        tenant_id,

        -- Date fields
        coalesce(processed_at, created_at)::date as report_date,

        -- Identifiers
        refund_id,
        order_id,

        -- Timestamps
        created_at,
        processed_at,

        -- Refund amount: prefer transaction amount, fall back to line items + adjustments
        case
            when transaction_refund_amount > 0 then transaction_refund_amount
            else line_items_refund_amount + adjustments_amount
        end as refund_amount,

        -- Component amounts for transparency
        line_items_refund_amount,
        adjustments_amount as shipping_refund_amount,
        transaction_refund_amount,

        -- Details
        refund_reason,
        is_restock,
        refund_line_items_count,
        currency,

        -- Metadata
        airbyte_record_id,
        airbyte_emitted_at

    from refunds_normalized
)

select
    tenant_id,
    report_date,
    refund_id,
    order_id,
    created_at,
    processed_at,
    refund_amount,
    line_items_refund_amount,
    shipping_refund_amount,
    transaction_refund_amount,
    refund_reason,
    is_restock,
    refund_line_items_count,
    currency,
    airbyte_record_id,
    airbyte_emitted_at
from refunds_final
where tenant_id is not null
    and refund_id is not null
    and trim(refund_id) != ''
    and report_date is not null
