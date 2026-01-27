{{
    config(
        materialized='incremental',
        unique_key='order_surrogate_key',
        schema='staging',
        incremental_strategy='merge'
    )
}}

{#
    Staging model for Shopify orders.

    This model normalizes raw Shopify order data and:
    - Removes all PII (no names, emails, addresses, phone numbers)
    - Adds tenant isolation
    - Normalizes IDs and timestamps
    - Adds channel taxonomy fields
    - Supports incremental processing with lookback window

    Output contract:
    - tenant_id
    - report_date
    - platform_channel / canonical_channel
    - platform_account_id / internal_account_id
    - Revenue and order metrics
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

orders_extracted as (
    select
        raw.airbyte_record_id,
        raw.airbyte_emitted_at,
        -- Order identifiers
        raw.order_data->>'id' as order_id_raw,
        raw.order_data->>'name' as order_name,
        raw.order_data->>'order_number' as order_number_raw,
        -- Timestamps
        raw.order_data->>'created_at' as created_at_raw,
        raw.order_data->>'updated_at' as updated_at_raw,
        raw.order_data->>'cancelled_at' as cancelled_at_raw,
        raw.order_data->>'closed_at' as closed_at_raw,
        raw.order_data->>'processed_at' as processed_at_raw,
        -- Status fields
        raw.order_data->>'financial_status' as financial_status,
        raw.order_data->>'fulfillment_status' as fulfillment_status,
        -- Financial data
        raw.order_data->>'total_price' as total_price_raw,
        raw.order_data->>'subtotal_price' as subtotal_price_raw,
        raw.order_data->>'total_tax' as total_tax_raw,
        raw.order_data->>'total_discounts' as total_discounts_raw,
        raw.order_data->>'total_shipping_price_set' as total_shipping_raw,
        raw.order_data->>'currency' as currency_code,
        -- Customer reference (ID only - no PII)
        raw.order_data->'customer'->>'id' as customer_id_raw,
        -- Line items for units calculation
        raw.order_data->'line_items' as line_items_json,
        -- Refunds data
        raw.order_data->'refunds' as refunds_json,
        -- Channel/source info
        raw.order_data->>'source_name' as source_name,
        raw.order_data->>'landing_site' as landing_site,
        raw.order_data->>'referring_site' as referring_site,
        raw.order_data->>'app_id' as app_id,
        -- Tags (for filtering, no PII)
        raw.order_data->>'tags' as tags_raw,
        -- Shop identifier
        coalesce(
            raw.order_data->>'shop_id',
            raw.order_data->>'admin_graphql_api_id'
        ) as shop_id_raw
    from raw_orders raw
),

orders_normalized as (
    select
        -- =====================================================================
        -- Primary identifiers
        -- =====================================================================
        case
            when order_id_raw is null or trim(order_id_raw) = '' then null
            when order_id_raw like 'gid://shopify/Order/%'
                then replace(order_id_raw, 'gid://shopify/Order/', '')
            else trim(order_id_raw)
        end as order_id,

        order_name,

        case
            when order_number_raw is null or trim(order_number_raw) = '' then null
            when order_number_raw ~ '^[0-9]+$' then order_number_raw::bigint
            else null
        end as order_number,

        -- =====================================================================
        -- Timestamps (normalized to UTC)
        -- =====================================================================
        case
            when created_at_raw is null or trim(created_at_raw) = '' then null
            when created_at_raw ~ '^\d{4}-\d{2}-\d{2}'
                then (created_at_raw::timestamp with time zone) at time zone 'UTC'
            else null
        end as created_at,

        -- Report date grain (date only from created_at)
        case
            when created_at_raw is null or trim(created_at_raw) = '' then null
            when created_at_raw ~ '^\d{4}-\d{2}-\d{2}'
                then (created_at_raw::timestamp with time zone)::date
            else null
        end as report_date,

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

        -- =====================================================================
        -- Financial metrics (normalized to numeric)
        -- =====================================================================
        case
            when total_price_raw is null or trim(total_price_raw) = '' then 0.0
            when trim(total_price_raw) ~ '^-?[0-9]+\.?[0-9]*([eE][+-]?[0-9]+)?$'
                then least(greatest(trim(total_price_raw)::numeric, 0), 999999999.99)
            else 0.0
        end as revenue_gross,

        case
            when subtotal_price_raw is null or trim(subtotal_price_raw) = '' then 0.0
            when trim(subtotal_price_raw) ~ '^-?[0-9]+\.?[0-9]*([eE][+-]?[0-9]+)?$'
                then least(greatest(trim(subtotal_price_raw)::numeric, 0), 999999999.99)
            else 0.0
        end as subtotal_price,

        case
            when total_tax_raw is null or trim(total_tax_raw) = '' then 0.0
            when trim(total_tax_raw) ~ '^-?[0-9]+\.?[0-9]*([eE][+-]?[0-9]+)?$'
                then least(greatest(trim(total_tax_raw)::numeric, 0), 999999999.99)
            else 0.0
        end as total_tax,

        case
            when total_discounts_raw is null or trim(total_discounts_raw) = '' then 0.0
            when trim(total_discounts_raw) ~ '^-?[0-9]+\.?[0-9]*([eE][+-]?[0-9]+)?$'
                then least(greatest(trim(total_discounts_raw)::numeric, 0), 999999999.99)
            else 0.0
        end as total_discounts,

        -- =====================================================================
        -- Currency
        -- =====================================================================
        case
            when currency_code is null or trim(currency_code) = '' then 'USD'
            when upper(trim(currency_code)) ~ '^[A-Z]{3}$'
                then upper(trim(currency_code))
            else 'USD'
        end as currency,

        -- =====================================================================
        -- Status fields
        -- =====================================================================
        coalesce(lower(trim(financial_status)), 'unknown') as financial_status,
        coalesce(lower(trim(fulfillment_status)), 'unfulfilled') as fulfillment_status,

        -- Is this a valid/countable order?
        case
            when lower(trim(financial_status)) in ('paid', 'partially_paid', 'authorized', 'partially_refunded')
            then true
            else false
        end as is_valid_order,

        -- =====================================================================
        -- Units sold (count line items)
        -- =====================================================================
        case
            when line_items_json is null then 0
            when line_items_json::text = '[]' then 0
            else coalesce(
                (select sum((item->>'quantity')::integer)
                 from jsonb_array_elements(line_items_json) as item),
                0
            )
        end as units_sold,

        -- =====================================================================
        -- Refund metrics
        -- =====================================================================
        case
            when refunds_json is null then 0
            when refunds_json::text = '[]' then 0
            else jsonb_array_length(refunds_json)
        end as refunds_count,

        -- =====================================================================
        -- Channel fields
        -- =====================================================================
        coalesce(lower(trim(source_name)), 'web') as platform_channel,

        -- Customer reference (ID only)
        case
            when customer_id_raw is null or trim(customer_id_raw) = '' then null
            when customer_id_raw like 'gid://shopify/Customer/%'
                then replace(customer_id_raw, 'gid://shopify/Customer/', '')
            else trim(customer_id_raw)
        end as customer_id,

        -- =====================================================================
        -- Account/Shop identifier
        -- =====================================================================
        coalesce(trim(shop_id_raw), 'unknown') as platform_account_id,

        -- =====================================================================
        -- Tags (no PII content)
        -- =====================================================================
        tags_raw as tags,

        -- =====================================================================
        -- Metadata
        -- =====================================================================
        airbyte_record_id,
        airbyte_emitted_at

    from orders_extracted
),

-- Join to tenant mapping to get tenant_id
orders_with_tenant as (
    select
        ord.*,
        coalesce(
            (select tenant_id
             from {{ ref('_tenant_airbyte_connections') }}
             where source_type = 'shopify'
               and platform_account_id = ord.platform_account_id
               and status = 'active'
               and is_enabled = true
             limit 1),
            null
        ) as tenant_id
    from orders_normalized ord
),

-- Add internal IDs and canonical channel
final as (
    select
        -- =====================================================================
        -- Surrogate key for incremental merge
        -- =====================================================================
        md5(
            coalesce(tenant_id, '') || '|' ||
            coalesce(order_id, '') || '|' ||
            coalesce(platform_account_id, '')
        ) as order_surrogate_key,

        -- =====================================================================
        -- Core identity fields
        -- =====================================================================
        tenant_id,
        order_id,
        order_name,
        order_number,

        -- =====================================================================
        -- Date grain
        -- =====================================================================
        report_date,

        -- =====================================================================
        -- Source identification
        -- =====================================================================
        'shopify' as source,

        -- =====================================================================
        -- Channel taxonomy
        -- =====================================================================
        platform_channel,
        {{ map_canonical_channel("'shopify'", 'platform_channel') }} as canonical_channel,

        -- =====================================================================
        -- Account/Shop identity
        -- =====================================================================
        platform_account_id,
        {{ generate_internal_account_id('tenant_id', "'shopify'", 'platform_account_id') }} as internal_account_id,

        -- =====================================================================
        -- Timestamps
        -- =====================================================================
        created_at,
        updated_at,
        cancelled_at,
        closed_at,

        -- =====================================================================
        -- Financial metrics
        -- =====================================================================
        revenue_gross,
        subtotal_price,
        total_tax,
        total_discounts,
        -- Net revenue = gross - tax - discounts (simplified; refunds handled separately)
        greatest(revenue_gross - total_discounts, 0) as revenue_net,
        currency,

        -- =====================================================================
        -- Order metrics
        -- =====================================================================
        case when is_valid_order then 1 else 0 end as orders,
        units_sold,
        refunds_count,

        -- =====================================================================
        -- Status fields
        -- =====================================================================
        financial_status,
        fulfillment_status,
        is_valid_order,

        -- =====================================================================
        -- Customer reference
        -- =====================================================================
        customer_id,

        -- =====================================================================
        -- Additional fields
        -- =====================================================================
        tags,

        -- =====================================================================
        -- Metadata
        -- =====================================================================
        airbyte_record_id,
        airbyte_emitted_at,
        current_timestamp as dbt_loaded_at

    from orders_with_tenant
    where tenant_id is not null
        and order_id is not null
        and trim(order_id) != ''
        and report_date is not null
)

select * from final
