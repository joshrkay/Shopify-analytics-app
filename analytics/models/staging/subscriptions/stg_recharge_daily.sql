{{
    config(
        materialized='incremental',
        unique_key='row_surrogate_key',
        schema='staging',
        incremental_strategy='merge'
    )
}}

{#
    Staging model for ReCharge subscription data aggregated to daily grain.

    ReCharge powers subscription commerce for Shopify stores.
    This model aggregates subscription events (charges, cancellations)
    to daily metrics for revenue analysis.

    No PII - only subscription IDs and financial metrics.
#}

with raw_recharge_charges as (
    select
        _airbyte_ab_id as airbyte_record_id,
        _airbyte_emitted_at as airbyte_emitted_at,
        _airbyte_data as charge_data
    from {{ source('raw_sources', 'raw_recharge_subscriptions') }}
    {% if is_incremental() %}
    where {{ incremental_timestamp_filter('_airbyte_emitted_at', 'recharge') }}
    {% endif %}
),

recharge_extracted as (
    select
        raw.airbyte_record_id,
        raw.airbyte_emitted_at,
        -- Store/Shop identifier
        raw.charge_data->>'shop_id' as shop_id_raw,
        -- Subscription identifiers (no PII)
        raw.charge_data->>'subscription_id' as subscription_id_raw,
        raw.charge_data->>'charge_id' as charge_id_raw,
        -- Charge details
        raw.charge_data->>'status' as charge_status,
        raw.charge_data->>'type' as charge_type,
        raw.charge_data->>'processed_at' as processed_at_raw,
        raw.charge_data->>'scheduled_at' as scheduled_at_raw,
        -- Financial data
        raw.charge_data->>'total_price' as total_price_raw,
        raw.charge_data->>'subtotal_price' as subtotal_price_raw,
        raw.charge_data->>'tax_lines' as tax_lines_raw,
        raw.charge_data->>'total_tax' as total_tax_raw,
        raw.charge_data->>'total_discounts' as total_discounts_raw,
        raw.charge_data->>'currency' as currency_code,
        -- Subscription metadata
        raw.charge_data->>'order_interval_unit' as interval_unit,
        raw.charge_data->>'order_interval_frequency' as interval_frequency
    from raw_recharge_charges raw
),

-- Aggregate to daily shop level
recharge_daily_aggregated as (
    select
        -- Shop ID as account
        case
            when shop_id_raw is null or trim(shop_id_raw) = '' then null
            else trim(shop_id_raw)
        end as platform_account_id,

        -- Report date from processed_at
        case
            when processed_at_raw is null or trim(processed_at_raw) = '' then null
            when processed_at_raw ~ '^\d{4}-\d{2}-\d{2}'
                then (processed_at_raw::timestamp with time zone)::date
            else null
        end as report_date,

        -- Count of successful charges
        count(*) filter (where lower(charge_status) in ('success', 'paid')) as successful_charges,

        -- Count of failed charges
        count(*) filter (where lower(charge_status) in ('error', 'failed', 'refunded')) as failed_charges,

        -- Count of new subscriptions (first charge)
        count(*) filter (where lower(charge_type) = 'checkout') as new_subscriptions,

        -- Gross revenue
        sum(
            case
                when lower(charge_status) in ('success', 'paid')
                    and total_price_raw is not null
                    and trim(total_price_raw) ~ '^-?[0-9]+\.?[0-9]*$'
                then greatest(trim(total_price_raw)::numeric, 0)
                else 0
            end
        ) as revenue_gross,

        -- Tax
        sum(
            case
                when lower(charge_status) in ('success', 'paid')
                    and total_tax_raw is not null
                    and trim(total_tax_raw) ~ '^-?[0-9]+\.?[0-9]*$'
                then greatest(trim(total_tax_raw)::numeric, 0)
                else 0
            end
        ) as total_tax,

        -- Discounts
        sum(
            case
                when lower(charge_status) in ('success', 'paid')
                    and total_discounts_raw is not null
                    and trim(total_discounts_raw) ~ '^-?[0-9]+\.?[0-9]*$'
                then greatest(trim(total_discounts_raw)::numeric, 0)
                else 0
            end
        ) as total_discounts,

        -- Currency
        mode() within group (order by upper(coalesce(currency_code, 'USD'))) as currency,

        -- Metadata
        max(airbyte_emitted_at) as airbyte_emitted_at

    from recharge_extracted
    where report_date is not null
    group by 1, 2
),

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
    from recharge_daily_aggregated r
),

final as (
    select
        md5(
            coalesce(tenant_id, '') || '|' ||
            coalesce(report_date::text, '') || '|' ||
            coalesce(platform_account_id, '')
        ) as row_surrogate_key,

        tenant_id,
        report_date,
        'recharge' as source,

        -- Subscription revenue is direct/organic
        'subscription' as platform_channel,
        {{ map_canonical_channel("'recharge'", "'subscription'") }} as canonical_channel,

        platform_account_id,
        {{ generate_internal_account_id('tenant_id', "'recharge'", 'platform_account_id') }} as internal_account_id,

        -- ReCharge doesn't have campaigns
        null::text as platform_campaign_id,
        null::text as internal_campaign_id,
        null::text as platform_adgroup_id,
        null::text as internal_adgroup_id,
        null::text as platform_ad_id,
        null::text as internal_ad_id,

        null::text as campaign_name,
        null::text as adgroup_name,
        null::text as ad_name,
        null::text as objective,

        -- No marketing spend for subscriptions
        0.0::numeric as spend,
        successful_charges::bigint as impressions,  -- Charges as proxy
        successful_charges::bigint as clicks,
        0::bigint as reach,
        successful_charges::numeric as conversions,
        revenue_gross as conversion_value,
        currency,

        -- No cost-based metrics
        null::numeric as cpm,
        null::numeric as cpc,
        null::numeric as ctr,
        null::numeric as cpa,
        null::numeric as roas_platform,

        -- Subscription-specific metrics
        successful_charges,
        failed_charges,
        new_subscriptions,
        revenue_gross,
        greatest(revenue_gross - total_discounts, 0) as revenue_net,
        total_tax,
        total_discounts,

        null::text as airbyte_record_id,
        airbyte_emitted_at,
        current_timestamp as dbt_loaded_at

    from recharge_with_tenant
    where tenant_id is not null
        and platform_account_id is not null
        and report_date is not null
)

select * from final
