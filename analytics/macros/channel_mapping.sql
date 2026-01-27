{% macro map_canonical_channel(source, platform_channel) %}
    {#
    Maps platform-specific channel values to canonical channel taxonomy.

    Args:
        source: The data source (meta_ads, google_ads, tiktok_ads, etc.)
        platform_channel: The platform-specific channel value

    Returns:
        Canonical channel value from the standard taxonomy:
        - paid_social
        - paid_search
        - display
        - video
        - shopping
        - email
        - organic_social
        - organic_search
        - direct
        - referral
        - affiliate
        - sms
        - push
        - marketplace
        - other

    See docs/CHANNEL_TAXONOMY.md for detailed mapping rules.
    #}

    case
        -- =====================================================================
        -- Meta Ads (Facebook/Instagram)
        -- =====================================================================
        when {{ source }} = 'meta_ads' then
            case
                when lower({{ platform_channel }}) in (
                    'facebook_feed', 'instagram_feed', 'facebook_stories',
                    'instagram_stories', 'facebook_reels', 'instagram_reels',
                    'messenger_inbox', 'audience_network', 'feed', 'story', 'reels'
                ) then 'paid_social'
                when lower({{ platform_channel }}) in (
                    'facebook_marketplace', 'marketplace'
                ) then 'marketplace'
                when lower({{ platform_channel }}) in (
                    'video', 'in_stream_video', 'video_feeds'
                ) then 'video'
                when lower({{ platform_channel }}) in (
                    'audience_network_classic', 'display', 'banner'
                ) then 'display'
                else 'paid_social'
            end

        -- =====================================================================
        -- Google Ads
        -- =====================================================================
        when {{ source }} = 'google_ads' then
            case
                when lower({{ platform_channel }}) in (
                    'search', 'search_network', 'google_search'
                ) then 'paid_search'
                when lower({{ platform_channel }}) in (
                    'display', 'display_network', 'google_display', 'gdn'
                ) then 'display'
                when lower({{ platform_channel }}) in (
                    'video', 'youtube', 'youtube_video'
                ) then 'video'
                when lower({{ platform_channel }}) in (
                    'shopping', 'google_shopping', 'pla', 'product_listing'
                ) then 'shopping'
                when lower({{ platform_channel }}) in (
                    'discovery', 'demand_gen', 'discover'
                ) then 'paid_social'
                when lower({{ platform_channel }}) in (
                    'app', 'universal_app', 'app_campaign'
                ) then 'display'
                when lower({{ platform_channel }}) in (
                    'performance_max', 'pmax'
                ) then 'paid_search'  -- Primary driver is search for most pmax
                else 'paid_search'
            end

        -- =====================================================================
        -- TikTok Ads
        -- =====================================================================
        when {{ source }} = 'tiktok_ads' then
            case
                when lower({{ platform_channel }}) in (
                    'tiktok_feed', 'in_feed', 'for_you', 'fyp'
                ) then 'paid_social'
                when lower({{ platform_channel }}) in (
                    'spark_ads', 'branded_content'
                ) then 'paid_social'
                when lower({{ platform_channel }}) in (
                    'topview', 'brand_takeover'
                ) then 'video'
                when lower({{ platform_channel }}) in (
                    'pangle', 'audience_network'
                ) then 'display'
                else 'paid_social'
            end

        -- =====================================================================
        -- Pinterest Ads
        -- =====================================================================
        when {{ source }} = 'pinterest_ads' then
            case
                when lower({{ platform_channel }}) in (
                    'browse', 'home_feed', 'pinterest_feed'
                ) then 'paid_social'
                when lower({{ platform_channel }}) in (
                    'search', 'pinterest_search'
                ) then 'paid_search'
                when lower({{ platform_channel }}) in (
                    'shopping', 'catalog', 'product'
                ) then 'shopping'
                when lower({{ platform_channel }}) in (
                    'video', 'video_pins'
                ) then 'video'
                else 'paid_social'
            end

        -- =====================================================================
        -- Snapchat Ads
        -- =====================================================================
        when {{ source }} = 'snap_ads' then
            case
                when lower({{ platform_channel }}) in (
                    'snap_ads', 'story_ads', 'between_stories'
                ) then 'paid_social'
                when lower({{ platform_channel }}) in (
                    'spotlight', 'spotlight_ads'
                ) then 'video'
                when lower({{ platform_channel }}) in (
                    'discover', 'discover_ads'
                ) then 'display'
                when lower({{ platform_channel }}) in (
                    'collection', 'dynamic_ads', 'catalog'
                ) then 'shopping'
                else 'paid_social'
            end

        -- =====================================================================
        -- Amazon Ads
        -- =====================================================================
        when {{ source }} = 'amazon_ads' then
            case
                when lower({{ platform_channel }}) in (
                    'sponsored_products', 'sp'
                ) then 'shopping'
                when lower({{ platform_channel }}) in (
                    'sponsored_brands', 'sb', 'headline_search'
                ) then 'paid_search'
                when lower({{ platform_channel }}) in (
                    'sponsored_display', 'sd', 'product_display'
                ) then 'display'
                when lower({{ platform_channel }}) in (
                    'dsp', 'demand_side_platform'
                ) then 'display'
                when lower({{ platform_channel }}) in (
                    'video', 'ott', 'streaming_tv'
                ) then 'video'
                else 'marketplace'
            end

        -- =====================================================================
        -- Klaviyo (Email/SMS)
        -- =====================================================================
        when {{ source }} = 'klaviyo' then
            case
                when lower({{ platform_channel }}) in (
                    'email', 'campaign', 'flow', 'automation'
                ) then 'email'
                when lower({{ platform_channel }}) in (
                    'sms', 'text', 'mms'
                ) then 'sms'
                when lower({{ platform_channel }}) in (
                    'push', 'push_notification', 'mobile_push'
                ) then 'push'
                else 'email'
            end

        -- =====================================================================
        -- Google Analytics 4
        -- =====================================================================
        when {{ source }} = 'ga4' then
            case
                when lower({{ platform_channel }}) in (
                    'organic search', 'organic_search'
                ) then 'organic_search'
                when lower({{ platform_channel }}) in (
                    'paid search', 'paid_search', 'cpc'
                ) then 'paid_search'
                when lower({{ platform_channel }}) in (
                    'organic social', 'organic_social'
                ) then 'organic_social'
                when lower({{ platform_channel }}) in (
                    'paid social', 'paid_social', 'paidsocial'
                ) then 'paid_social'
                when lower({{ platform_channel }}) in (
                    'email', 'e-mail'
                ) then 'email'
                when lower({{ platform_channel }}) in (
                    'display', 'banner'
                ) then 'display'
                when lower({{ platform_channel }}) in (
                    'video', 'youtube'
                ) then 'video'
                when lower({{ platform_channel }}) in (
                    'referral', 'ref'
                ) then 'referral'
                when lower({{ platform_channel }}) in (
                    'direct', '(direct)', '(none)'
                ) then 'direct'
                when lower({{ platform_channel }}) in (
                    'affiliate', 'affiliates'
                ) then 'affiliate'
                else 'other'
            end

        -- =====================================================================
        -- Recharge (Subscriptions)
        -- =====================================================================
        when {{ source }} = 'recharge' then 'direct'

        -- =====================================================================
        -- Shopify (Commerce)
        -- =====================================================================
        when {{ source }} = 'shopify' then
            case
                when lower({{ platform_channel }}) in (
                    'online_store', 'web', 'storefront'
                ) then 'direct'
                when lower({{ platform_channel }}) in (
                    'pos', 'point_of_sale', 'retail'
                ) then 'direct'
                when lower({{ platform_channel }}) in (
                    'draft_orders', 'draft'
                ) then 'direct'
                when lower({{ platform_channel }}) in (
                    'shopify_inbox', 'inbox', 'chat'
                ) then 'direct'
                else 'direct'
            end

        -- =====================================================================
        -- Default fallback
        -- =====================================================================
        else 'other'
    end
{% endmacro %}


{% macro get_platform_channel(source, raw_channel_field) %}
    {#
    Extracts and normalizes platform-specific channel from raw data.
    This preserves the original platform terminology for analysis.

    Args:
        source: The data source identifier
        raw_channel_field: The raw channel value from the source

    Returns:
        Normalized platform channel string (lowercase, trimmed)
    #}

    case
        when {{ raw_channel_field }} is null or trim({{ raw_channel_field }}) = '' then
            {{ source }} || '_default'
        else
            lower(trim({{ raw_channel_field }}))
    end
{% endmacro %}
