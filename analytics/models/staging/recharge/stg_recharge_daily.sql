{{
    config(
        materialized='incremental',
        schema='staging',
        unique_key=['tenant_id', 'report_date'],
        incremental_strategy='delete+insert'
    )
}}

{#
    Staging model for Recharge subscription metrics aggregated daily.

    Tracks subscription commerce:
    - New subscriptions
    - Churned subscriptions
    - Subscription revenue (recurring charges)

    Required contract fields:
    - tenant_id, report_date, source, platform_channel, canonical_channel
    - Subscription metrics

    PII Policy: No PII fields exposed. IDs and aggregate metrics only.
#}

with raw_recharge_subscriptions as (
    select
        _airbyte_ab_id as airbyte_record_id,
        _airbyte_emitted_at as airbyte_emitted_at,
        _airbyte_data as subscription_data
    from {{ source('airbyte_raw', '_airbyte_raw_recharge_subscriptions') }}
),

raw_recharge_charges as (
    select
        _airbyte_ab_id as airbyte_record_id,
        _airbyte_emitted_at as airbyte_emitted_at,
        _airbyte_data as charge_data
    from {{ source('airbyte_raw', '_airbyte_raw_recharge_charges') }}
),

-- Extract subscription data
subscriptions_extracted as (
    select
        raw.airbyte_record_id,
        raw.airbyte_emitted_at,
        raw.subscription_data->>'id' as subscription_id_raw,
        raw.subscription_data->>'status' as status,
        raw.subscription_data->>'created_at' as created_at_raw,
        raw.subscription_data->>'cancelled_at' as cancelled_at_raw,
        raw.subscription_data->>'price' as price_raw,
        raw.subscription_data->>'quantity' as quantity_raw,
        raw.subscription_data->>'product_title' as product_title,
        -- No PII: customer_id only
        raw.subscription_data->>'customer_id' as customer_id
    from raw_recharge_subscriptions raw
),

-- Extract charge data
charges_extracted as (
    select
        raw.airbyte_record_id,
        raw.airbyte_emitted_at,
        raw.charge_data->>'id' as charge_id_raw,
        raw.charge_data->>'status' as status,
        raw.charge_data->>'processed_at' as processed_at_raw,
        raw.charge_data->>'total_price' as total_price_raw,
        raw.charge_data->>'subtotal_price' as subtotal_price_raw,
        raw.charge_data->>'total_tax' as total_tax_raw,
        raw.charge_data->>'total_discounts' as total_discounts_raw,
        raw.charge_data->>'currency' as currency_code,
        -- No PII: customer_id only
        raw.charge_data->>'customer_id' as customer_id
    from raw_recharge_charges raw
),

-- Normalize subscriptions
subscriptions_normalized as (
    select
        case
            when subscription_id_raw is null or trim(subscription_id_raw) = '' then null
            else trim(subscription_id_raw)
        end as subscription_id,

        status,

        case
            when created_at_raw is null or trim(created_at_raw) = '' then null
            when created_at_raw ~ '^\d{4}-\d{2}-\d{2}'
                then (created_at_raw::timestamp with time zone)::date
            else null
        end as created_date,

        case
            when cancelled_at_raw is null or trim(cancelled_at_raw) = '' then null
            when cancelled_at_raw ~ '^\d{4}-\d{2}-\d{2}'
                then (cancelled_at_raw::timestamp with time zone)::date
            else null
        end as cancelled_date,

        case
            when price_raw is null or trim(price_raw) = '' then 0.0
            when trim(price_raw) ~ '^-?[0-9]+\.?[0-9]*$'
                then greatest(trim(price_raw)::numeric, 0)
            else 0.0
        end as price,

        case
            when quantity_raw is null or trim(quantity_raw) = '' then 1
            when trim(quantity_raw) ~ '^[0-9]+$'
                then trim(quantity_raw)::integer
            else 1
        end as quantity,

        customer_id,
        airbyte_emitted_at

    from subscriptions_extracted
),

-- Normalize charges
charges_normalized as (
    select
        case
            when charge_id_raw is null or trim(charge_id_raw) = '' then null
            else trim(charge_id_raw)
        end as charge_id,

        status,

        case
            when processed_at_raw is null or trim(processed_at_raw) = '' then null
            when processed_at_raw ~ '^\d{4}-\d{2}-\d{2}'
                then (processed_at_raw::timestamp with time zone)::date
            else null
        end as processed_date,

        case
            when total_price_raw is null or trim(total_price_raw) = '' then 0.0
            when trim(total_price_raw) ~ '^-?[0-9]+\.?[0-9]*$'
                then greatest(trim(total_price_raw)::numeric, 0)
            else 0.0
        end as total_price,

        case
            when subtotal_price_raw is null or trim(subtotal_price_raw) = '' then 0.0
            when trim(subtotal_price_raw) ~ '^-?[0-9]+\.?[0-9]*$'
                then greatest(trim(subtotal_price_raw)::numeric, 0)
            else 0.0
        end as subtotal_price,

        case
            when total_tax_raw is null or trim(total_tax_raw) = '' then 0.0
            when trim(total_tax_raw) ~ '^-?[0-9]+\.?[0-9]*$'
                then greatest(trim(total_tax_raw)::numeric, 0)
            else 0.0
        end as total_tax,

        case
            when total_discounts_raw is null or trim(total_discounts_raw) = '' then 0.0
            when trim(total_discounts_raw) ~ '^-?[0-9]+\.?[0-9]*$'
                then greatest(trim(total_discounts_raw)::numeric, 0)
            else 0.0
        end as total_discounts,

        case
            when currency_code is null or trim(currency_code) = '' then 'USD'
            when upper(trim(currency_code)) ~ '^[A-Z]{3}$'
                then upper(trim(currency_code))
            else 'USD'
        end as currency,

        customer_id,
        airbyte_emitted_at

    from charges_extracted
),

-- Aggregate subscriptions by day
subscription_daily as (
    select
        created_date as report_date,
        count(*) as new_subscriptions,
        count(distinct customer_id) as new_subscribers,
        sum(price * quantity) as new_subscription_mrr
    from subscriptions_normalized
    where created_date is not null
    group by created_date
),

-- Aggregate churned subscriptions by day
churn_daily as (
    select
        cancelled_date as report_date,
        count(*) as churned_subscriptions,
        count(distinct customer_id) as churned_subscribers,
        sum(price * quantity) as churned_mrr
    from subscriptions_normalized
    where cancelled_date is not null
    group by cancelled_date
),

-- Aggregate charges by day
charges_daily as (
    select
        processed_date as report_date,
        count(*) as successful_charges,
        count(distinct customer_id) as charged_customers,
        sum(total_price) as revenue_gross,
        sum(subtotal_price) as revenue_subtotal,
        sum(total_tax) as revenue_tax,
        sum(total_discounts) as revenue_discounts,
        sum(total_price) - sum(total_discounts) as revenue_net,
        max(currency) as currency,
        max(airbyte_emitted_at) as airbyte_emitted_at
    from charges_normalized
    where processed_date is not null
        and status = 'SUCCESS'
    group by processed_date
),

-- Combine all daily metrics
recharge_daily_combined as (
    select
        coalesce(c.report_date, s.report_date, ch.report_date) as report_date,
        coalesce(s.new_subscriptions, 0) as new_subscriptions,
        coalesce(s.new_subscribers, 0) as new_subscribers,
        coalesce(s.new_subscription_mrr, 0) as new_subscription_mrr,
        coalesce(ch.churned_subscriptions, 0) as churned_subscriptions,
        coalesce(ch.churned_subscribers, 0) as churned_subscribers,
        coalesce(ch.churned_mrr, 0) as churned_mrr,
        coalesce(c.successful_charges, 0) as orders,
        coalesce(c.charged_customers, 0) as unique_customers,
        coalesce(c.revenue_gross, 0) as revenue_gross,
        coalesce(c.revenue_net, 0) as revenue_net,
        coalesce(c.revenue_tax, 0) as revenue_tax,
        coalesce(c.revenue_discounts, 0) as revenue_discounts,
        coalesce(c.currency, 'USD') as currency,
        coalesce(c.airbyte_emitted_at, current_timestamp) as airbyte_emitted_at,
        'recharge' as source,
        'subscription' as platform_channel
    from charges_daily c
    full outer join subscription_daily s on c.report_date = s.report_date
    full outer join churn_daily ch on coalesce(c.report_date, s.report_date) = ch.report_date
    where coalesce(c.report_date, s.report_date, ch.report_date) is not null
),

-- Join to tenant mapping
recharge_with_tenant as (
    select
        r.*,
        coalesce(
            (select tenant_id
             from {{ ref('_tenant_airbyte_connections') }}
             where source_type = 'source-recharge'
               and status = 'active'
               and is_enabled = true
             limit 1),
            null
        ) as tenant_id
    from recharge_daily_combined r
)

select
    -- Primary identifiers
    tenant_id,
    report_date,
    source,

    -- Channel taxonomy
    platform_channel,
    {{ map_canonical_channel("'recharge'", 'platform_channel') }} as canonical_channel,

    -- Subscription metrics
    new_subscriptions,
    new_subscribers,
    new_subscription_mrr,
    churned_subscriptions,
    churned_subscribers,
    churned_mrr,
    new_subscriptions - churned_subscriptions as net_subscriptions,
    new_subscription_mrr - churned_mrr as net_mrr_change,

    -- Order/revenue metrics
    orders,
    unique_customers,
    revenue_gross,
    revenue_net,
    revenue_tax,
    revenue_discounts,
    currency,

    -- Derived metrics
    case when orders > 0 then revenue_gross / orders else 0 end as aov,

    -- Metadata
    airbyte_emitted_at

from recharge_with_tenant
where tenant_id is not null

{{ incremental_filter('report_date', 'recharge') }}
