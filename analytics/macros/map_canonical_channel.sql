{% macro map_canonical_channel(source, platform_channel) %}
    {#
    Maps platform-specific channel values to canonical channel taxonomy.

    Canonical channels:
    - paid_social: Meta Ads, TikTok Ads, Pinterest Ads, Snap Ads (paid campaigns)
    - paid_search: Google Ads Search, Amazon Sponsored Products
    - organic_social: Organic social media traffic
    - organic_search: SEO traffic
    - email: Klaviyo, email campaigns
    - sms: SMS marketing (Klaviyo SMS, Postscript, Attentive)
    - affiliate: Affiliate referrals
    - referral: Non-affiliate referrals
    - direct: Direct traffic
    - display: Display ads, GDN
    - video: YouTube ads, video campaigns
    - shopping: Google Shopping, Meta Shopping
    - other: Unclassified channels

    Args:
        source: The data source (meta_ads, google_ads, tiktok_ads, etc.)
        platform_channel: The platform-specific channel value

    Returns:
        Canonical channel value
    #}

    case
        -- Meta Ads channel mapping
        when {{ source }} = 'meta_ads' then
            case
                when lower({{ platform_channel }}) like '%shopping%'
                    or lower({{ platform_channel }}) like '%catalog%'
                    or lower({{ platform_channel }}) like '%product%' then 'shopping'
                when lower({{ platform_channel }}) like '%video%'
                    or lower({{ platform_channel }}) like '%reels%'
                    or lower({{ platform_channel }}) like '%stories%' then 'video'
                else 'paid_social'
            end

        -- Google Ads channel mapping
        when {{ source }} = 'google_ads' then
            case
                when lower({{ platform_channel }}) in ('search', 'search network', 'search_network') then 'paid_search'
                when lower({{ platform_channel }}) in ('shopping', 'google shopping', 'shopping_campaign') then 'shopping'
                when lower({{ platform_channel }}) in ('display', 'display network', 'display_network', 'gdn') then 'display'
                when lower({{ platform_channel }}) in ('video', 'youtube', 'youtube_video') then 'video'
                when lower({{ platform_channel }}) in ('discovery', 'demand gen', 'demand_gen') then 'display'
                when lower({{ platform_channel }}) in ('performance max', 'pmax', 'performance_max') then 'paid_search'
                else 'paid_search'
            end

        -- TikTok Ads channel mapping
        when {{ source }} = 'tiktok_ads' then
            case
                when lower({{ platform_channel }}) like '%shopping%'
                    or lower({{ platform_channel }}) like '%catalog%' then 'shopping'
                else 'paid_social'
            end

        -- Pinterest Ads channel mapping
        when {{ source }} = 'pinterest_ads' then
            case
                when lower({{ platform_channel }}) like '%shopping%'
                    or lower({{ platform_channel }}) like '%catalog%' then 'shopping'
                else 'paid_social'
            end

        -- Snap Ads channel mapping
        when {{ source }} = 'snap_ads' then 'paid_social'

        -- Amazon Ads channel mapping
        when {{ source }} = 'amazon_ads' then
            case
                when lower({{ platform_channel }}) in ('sponsored_products', 'sp') then 'paid_search'
                when lower({{ platform_channel }}) in ('sponsored_brands', 'sb') then 'paid_search'
                when lower({{ platform_channel }}) in ('sponsored_display', 'sd') then 'display'
                when lower({{ platform_channel }}) in ('dsp') then 'display'
                else 'paid_search'
            end

        -- Klaviyo channel mapping
        when {{ source }} = 'klaviyo' then
            case
                when lower({{ platform_channel }}) like '%sms%' then 'sms'
                else 'email'
            end

        -- GA4 channel mapping (uses Google's default channel grouping)
        when {{ source }} = 'ga4' then
            case
                when lower({{ platform_channel }}) in ('organic search', 'organic_search') then 'organic_search'
                when lower({{ platform_channel }}) in ('organic social', 'organic_social') then 'organic_social'
                when lower({{ platform_channel }}) in ('paid search', 'paid_search') then 'paid_search'
                when lower({{ platform_channel }}) in ('paid social', 'paid_social') then 'paid_social'
                when lower({{ platform_channel }}) in ('email') then 'email'
                when lower({{ platform_channel }}) in ('sms') then 'sms'
                when lower({{ platform_channel }}) in ('affiliate', 'affiliates') then 'affiliate'
                when lower({{ platform_channel }}) in ('referral') then 'referral'
                when lower({{ platform_channel }}) in ('direct') then 'direct'
                when lower({{ platform_channel }}) in ('display') then 'display'
                when lower({{ platform_channel }}) in ('video') then 'video'
                else 'other'
            end

        -- Recharge channel mapping (subscriptions = direct store)
        when {{ source }} = 'recharge' then 'direct'

        -- Shopify orders - use UTM-derived channel or default
        when {{ source }} = 'shopify' then
            case
                when lower({{ platform_channel }}) like '%facebook%'
                    or lower({{ platform_channel }}) like '%instagram%'
                    or lower({{ platform_channel }}) like '%meta%' then 'paid_social'
                when lower({{ platform_channel }}) like '%google%'
                    or lower({{ platform_channel }}) like '%gclid%' then 'paid_search'
                when lower({{ platform_channel }}) like '%tiktok%' then 'paid_social'
                when lower({{ platform_channel }}) like '%email%'
                    or lower({{ platform_channel }}) like '%klaviyo%' then 'email'
                when lower({{ platform_channel }}) like '%sms%' then 'sms'
                when {{ platform_channel }} is null or {{ platform_channel }} = '' then 'direct'
                else 'other'
            end

        else 'other'
    end
{% endmacro %}


{% macro get_platform_channel(source, raw_data) %}
    {#
    Extracts the platform-specific channel from raw data.
    Each source has different field names for channel/campaign type.

    Args:
        source: The data source
        raw_data: The raw JSON data object

    Returns:
        Platform-specific channel value
    #}

    case
        when {{ source }} = 'meta_ads' then coalesce({{ raw_data }}->>'objective', 'unknown')
        when {{ source }} = 'google_ads' then coalesce({{ raw_data }}->>'campaign_type', {{ raw_data }}->>'network', 'search')
        when {{ source }} = 'tiktok_ads' then coalesce({{ raw_data }}->>'objective_type', 'traffic')
        when {{ source }} = 'pinterest_ads' then coalesce({{ raw_data }}->>'objective_type', 'awareness')
        when {{ source }} = 'snap_ads' then coalesce({{ raw_data }}->>'objective', 'awareness')
        when {{ source }} = 'amazon_ads' then coalesce({{ raw_data }}->>'campaign_type', 'sponsored_products')
        when {{ source }} = 'klaviyo' then coalesce({{ raw_data }}->>'message_type', 'email')
        when {{ source }} = 'ga4' then coalesce({{ raw_data }}->>'default_channel_grouping', {{ raw_data }}->>'session_default_channel_grouping', 'direct')
        when {{ source }} = 'recharge' then 'subscription'
        when {{ source }} = 'shopify' then coalesce({{ raw_data }}->>'source_name', {{ raw_data }}->>'landing_site', '')
        else 'unknown'
    end
{% endmacro %}
