{{
    config(
        materialized='incremental',
        schema='staging',
        unique_key='record_sk',
        incremental_strategy='delete+insert'
    )
}}

{#
    Staging model for Meta Ads (Facebook/Instagram) with strict typing and standardization.

    Migrated from Airbyte v1 JSONB (_airbyte_data blob) to v2 typed columns.
    Source: airbyte_google_ads.ads_insights (v2)
    Note: The Airbyte destination is configured to write to the 'airbyte_google_ads' schema
    despite this being a Facebook Marketing connection. The schema name reflects how Airbyte
    Cloud named the destination; sources.yml has been updated to match.

    v1 → v2 key changes:
      - _airbyte_ab_id       → _airbyte_raw_id
      - _airbyte_emitted_at  → _airbyte_extracted_at
      - _airbyte_data->>'...' → direct typed columns
      - account_id: varchar (may still carry 'act_' prefix — stripped for tenant join)
      - date_start/date_stop: now date type (not text)
      - spend, impressions, clicks: already typed (numeric/bigint)
      - conversions: now JSONB array of {action_type, value} objects (not a scalar)
      - action_values: JSONB array of {action_type, value} for revenue
      - currency: now 'account_currency' column (not 'currency')

    Output contract is unchanged — same column names and types as the v1 version.

    SECURITY: Tenant isolation enforced via _tenant_airbyte_connections.
#}

with raw_meta_ads as (
    select
        _airbyte_raw_id       as airbyte_record_id,
        _airbyte_extracted_at as airbyte_emitted_at,
        -- v2 typed columns — no JSONB extraction needed
        account_id            as account_id_raw,
        campaign_id,
        adset_id,
        ad_id,
        date_start,                 -- date type in v2
        date_stop,                  -- date type in v2
        spend,                      -- numeric
        impressions,                -- bigint
        clicks,                     -- bigint
        conversions,                -- jsonb array: [{action_type, value}, ...]
        action_values,              -- jsonb array: [{action_type, value}, ...] for revenue
        account_currency            as currency_code,
        campaign_name,
        adset_name,
        ad_name,
        objective,
        reach,                      -- bigint
        frequency,                  -- numeric
        -- platform_channel: v2 doesn't have 'placement'; use objective as fallback
        coalesce(objective, 'feed') as platform_channel_raw
    from {{ source('raw_facebook_ads', 'ad_insights') }}
    {% if is_incremental() %}
    where _airbyte_extracted_at >= current_timestamp - interval '{{ get_lookback_days("meta_ads") }} days'
    {% endif %}
),

meta_ads_normalized as (
    select
        -- Strip 'act_' prefix if present (v1 data had it; v2 may vary)
        case
            when account_id_raw is null or trim(account_id_raw) = '' then null
            else regexp_replace(trim(account_id_raw), '^act_', '')
        end as ad_account_id,

        campaign_id,
        adset_id,
        ad_id,

        -- Dates: already date type in v2 — no parsing needed
        date_start as date,
        date_stop,

        -- Spend: already numeric in v2 — apply bounds checking only
        case
            when spend is null then 0.0
            else least(greatest(spend, -999999999.99), 999999999.99)
        end as spend,

        -- Impressions: already bigint in v2
        case
            when impressions is null then 0
            else least(greatest(impressions::integer, 0), 2147483647)
        end as impressions,

        -- Clicks: already bigint in v2
        case
            when clicks is null then 0
            else least(greatest(clicks::integer, 0), 2147483647)
        end as clicks,

        -- Conversions: v2 stores as JSONB array [{action_type, value}, ...]
        -- Sum 'purchase' action type for ecommerce conversion count
        coalesce(
            (
                select sum((elem->>'value')::numeric)
                from jsonb_array_elements(conversions) as elem
                where elem->>'action_type' = 'purchase'
            ),
            0.0
        ) as conversions,

        -- Conversion value: extract from action_values JSONB array
        -- Sum 'purchase' action type for ecommerce revenue
        coalesce(
            (
                select sum((elem->>'value')::numeric)
                from jsonb_array_elements(action_values) as elem
                where elem->>'action_type' = 'purchase'
            ),
            0.0
        ) as conversion_value,

        -- Currency: from account_currency column in v2 (was nested in JSONB in v1)
        case
            when currency_code is null or trim(currency_code) = '' then 'USD'
            when upper(trim(currency_code)) ~ '^[A-Z]{3}$'
                then upper(trim(currency_code))
            else 'USD'
        end as currency,

        -- Additional fields
        campaign_name,
        adset_name,
        ad_name,
        objective,

        -- Platform channel
        coalesce(platform_channel_raw, 'feed') as platform_channel,

        -- Reach: already bigint in v2
        case
            when reach is null then null
            else least(greatest(reach::integer, 0), 2147483647)
        end as reach,

        -- Frequency: already numeric in v2
        case
            when frequency is null then null
            else least(greatest(frequency, 0.0), 100.0)
        end as frequency,

        'meta_ads' as platform,
        'meta_ads' as source,

        airbyte_record_id,
        airbyte_emitted_at

    from raw_meta_ads
),

-- Tenant mapping: join on ad_account_id for multi-tenant isolation
meta_tenant_mapping as (
    select
        tenant_id,
        config_account_id as mapped_account_id
    from {{ ref('_tenant_airbyte_connections') }}
    where source_type = 'source-facebook-marketing'
        and config_account_id is not null
        and config_account_id != ''
),

meta_ads_with_tenant as (
    select
        ads.*,
        tm.tenant_id
    from meta_ads_normalized ads
    inner join meta_tenant_mapping tm
        on ads.ad_account_id = tm.mapped_account_id
),

-- Add internal IDs, canonical channel, and dedup
meta_ads_enriched as (
    select
        tenant_id,
        date,
        date as report_date,
        date_stop,
        source,
        ad_account_id,
        campaign_id,
        adset_id,
        ad_id,

        -- Internal IDs (Option B ID normalization)
        {{ generate_internal_id('tenant_id', 'source', 'ad_account_id') }} as internal_account_id,
        {{ generate_internal_id('tenant_id', 'source', 'campaign_id') }} as internal_campaign_id,

        -- Channel taxonomy
        platform_channel,
        {{ map_canonical_channel('source', 'platform_channel') }} as canonical_channel,

        -- Core metrics only (no derived business metrics)
        spend,
        impressions,
        clicks,
        conversions,
        conversion_value,
        currency,

        -- Additional fields
        campaign_name,
        adset_name,
        ad_name,
        objective,
        reach,
        frequency,

        platform,
        airbyte_record_id,
        airbyte_emitted_at,

        -- Dedup: keep latest record per natural key
        row_number() over (
            partition by tenant_id, ad_account_id, campaign_id, adset_id, ad_id, date
            order by airbyte_emitted_at desc
        ) as _row_num

    from meta_ads_with_tenant
    where tenant_id is not null
        and ad_account_id is not null
        and trim(ad_account_id) != ''
        and campaign_id is not null
        and trim(campaign_id) != ''
        and date is not null
)

select
    -- Surrogate key: md5(tenant_id || source_system || source_primary_key)
    md5(concat(
        tenant_id, '|', 'meta_ads', '|',
        ad_account_id, '|', campaign_id, '|',
        coalesce(adset_id, ''), '|', coalesce(ad_id, ''), '|',
        date::text
    )) as record_sk,

    -- Source tracking
    'meta_ads' as source_system,
    concat(
        ad_account_id, '|', campaign_id, '|',
        coalesce(adset_id, ''), '|', coalesce(ad_id, ''), '|',
        date::text
    ) as source_primary_key,

    -- All staging columns
    tenant_id,
    report_date,
    date,
    date_stop,
    source,
    ad_account_id,
    campaign_id,
    adset_id,
    ad_id,
    internal_account_id,
    internal_campaign_id,
    platform_channel,
    canonical_channel,
    spend,
    impressions,
    clicks,
    conversions,
    conversion_value,
    currency,
    campaign_name,
    adset_name,
    ad_name,
    objective,
    reach,
    frequency,
    platform,
    airbyte_record_id,
    airbyte_emitted_at

from meta_ads_enriched
where _row_num = 1
    {% if is_incremental() %}
    and date >= current_date - {{ get_lookback_days('meta_ads') }}
    {% endif %}
