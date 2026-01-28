{{
    config(
        materialized='incremental',
        schema='staging',
        unique_key=['tenant_id', 'date', 'subscription_id'],
        incremental_strategy='delete+insert'
    )
}}

{#
    Staging model for Recharge subscription data with normalized fields and tenant isolation.

    Recharge provides subscription/recurring revenue data.
    This model normalizes subscription events and charges.

    Recharge field mappings:
    - id -> subscription_id
    - customer_id -> customer_id
    - created_at -> created_at
    - status -> subscription_status
    - price -> subscription_price
    - charge_interval_unit_type + charge_interval_frequency -> billing_interval
#}

with raw_recharge as (
    select
        _airbyte_ab_id as airbyte_record_id,
        _airbyte_emitted_at as airbyte_emitted_at,
        _airbyte_data as subscription_data
    from {{ source('airbyte_raw', '_airbyte_raw_recharge') }}
    {% if is_incremental() %}
    where _airbyte_emitted_at >= current_timestamp - interval '{{ get_lookback_days("recharge") }} days'
    {% endif %}
),

recharge_extracted as (
    select
        raw.airbyte_record_id,
        raw.airbyte_emitted_at,
        raw.subscription_data->>'id' as subscription_id_raw,
        raw.subscription_data->>'customer_id' as customer_id_raw,
        raw.subscription_data->>'external_product_id' as product_id,
        raw.subscription_data->>'external_variant_id' as variant_id,
        coalesce(raw.subscription_data->>'created_at', raw.subscription_data->>'date') as created_at_raw,
        raw.subscription_data->>'updated_at' as updated_at_raw,
        raw.subscription_data->>'cancelled_at' as cancelled_at_raw,
        raw.subscription_data->>'next_charge_scheduled_at' as next_charge_at_raw,
        raw.subscription_data->>'status' as subscription_status,
        raw.subscription_data->>'price' as price_raw,
        raw.subscription_data->>'quantity' as quantity_raw,
        raw.subscription_data->>'charge_interval_unit_type' as charge_interval_unit,
        raw.subscription_data->>'charge_interval_frequency' as charge_interval_frequency,
        raw.subscription_data->>'order_interval_unit' as order_interval_unit,
        raw.subscription_data->>'order_interval_frequency' as order_interval_frequency,
        raw.subscription_data->>'product_title' as product_title,
        raw.subscription_data->>'variant_title' as variant_title,
        raw.subscription_data->>'sku' as sku,
        coalesce(raw.subscription_data->>'presentment_currency', 'USD') as currency_code
    from raw_recharge raw
),

recharge_normalized as (
    select
        case when subscription_id_raw is null or trim(subscription_id_raw) = '' then null else trim(subscription_id_raw) end as subscription_id,
        case when customer_id_raw is null or trim(customer_id_raw) = '' then null else trim(customer_id_raw) end as customer_id,
        product_id,
        variant_id,
        case when created_at_raw is null or trim(created_at_raw) = '' then null
             when created_at_raw ~ '^\d{4}-\d{2}-\d{2}' then (created_at_raw::timestamp with time zone) at time zone 'UTC'
             else null end as created_at,
        case when updated_at_raw is null or trim(updated_at_raw) = '' then null
             when updated_at_raw ~ '^\d{4}-\d{2}-\d{2}' then (updated_at_raw::timestamp with time zone) at time zone 'UTC'
             else null end as updated_at,
        case when cancelled_at_raw is null or trim(cancelled_at_raw) = '' then null
             when cancelled_at_raw ~ '^\d{4}-\d{2}-\d{2}' then (cancelled_at_raw::timestamp with time zone) at time zone 'UTC'
             else null end as cancelled_at,
        case when next_charge_at_raw is null or trim(next_charge_at_raw) = '' then null
             when next_charge_at_raw ~ '^\d{4}-\d{2}-\d{2}' then (next_charge_at_raw::timestamp with time zone) at time zone 'UTC'
             else null end as next_charge_at,
        coalesce(subscription_status, 'unknown') as subscription_status,
        case when price_raw is null or trim(price_raw) = '' then 0.0 when trim(price_raw) ~ '^[0-9]+\.?[0-9]*$' then trim(price_raw)::numeric else 0.0 end as subscription_price,
        case when quantity_raw is null or trim(quantity_raw) = '' then 1 when trim(quantity_raw) ~ '^[0-9]+$' then trim(quantity_raw)::integer else 1 end as quantity,
        coalesce(charge_interval_unit, 'month') as charge_interval_unit,
        case when charge_interval_frequency is null or trim(charge_interval_frequency) = '' then 1 when trim(charge_interval_frequency) ~ '^[0-9]+$' then trim(charge_interval_frequency)::integer else 1 end as charge_interval_frequency,
        concat(coalesce(charge_interval_frequency, '1'), ' ', coalesce(charge_interval_unit, 'month')) as billing_interval,
        product_title,
        variant_title,
        sku,
        case when currency_code is null or trim(currency_code) = '' then 'USD' when upper(trim(currency_code)) ~ '^[A-Z]{3}$' then upper(trim(currency_code)) else 'USD' end as currency,
        'recharge' as source,
        'recharge' as platform,
        'direct' as platform_channel,  -- Subscription revenue is typically direct
        airbyte_record_id, airbyte_emitted_at
    from recharge_extracted
),

recharge_with_tenant as (
    select subs.*,
        coalesce((select tenant_id from {{ ref('_tenant_airbyte_connections') }} where source_type = 'source-recharge' and status = 'active' and is_enabled = true limit 1), null) as tenant_id
    from recharge_normalized subs
),

recharge_final as (
    select
        tenant_id,
        created_at::date as date,
        created_at::date as report_date,
        source,
        subscription_id,
        customer_id,
        product_id,
        variant_id,
        created_at,
        updated_at,
        cancelled_at,
        next_charge_at,
        subscription_status,
        -- Determine if this is a new, active, cancelled, or churned subscription
        case
            when cancelled_at is not null then 'cancelled'
            when subscription_status = 'active' then 'active'
            when subscription_status = 'cancelled' then 'cancelled'
            else subscription_status
        end as status_category,
        subscription_price,
        quantity,
        subscription_price * quantity as total_price,
        billing_interval,
        charge_interval_unit,
        charge_interval_frequency,
        product_title,
        variant_title,
        sku,
        currency,
        platform_channel,
        {{ map_canonical_channel("'recharge'", "'direct'") }} as canonical_channel,
        -- For compatibility with ad staging models (subscriptions don't have ad metrics)
        0.0 as spend,
        0 as impressions,
        0 as clicks,
        case when subscription_status = 'active' and cancelled_at is null then 1 else 0 end as conversions,
        subscription_price * quantity as conversion_value,
        platform,
        airbyte_record_id,
        airbyte_emitted_at
    from recharge_with_tenant
)

select * from recharge_final
where tenant_id is not null and subscription_id is not null and date is not null
{% if is_incremental() %} and date >= current_date - {{ get_lookback_days('recharge') }} {% endif %}
