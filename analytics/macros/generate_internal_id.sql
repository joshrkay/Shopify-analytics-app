{% macro generate_internal_id(tenant_id, source, platform_id) %}
    {#
    Generates a deterministic internal ID for cross-platform entity normalization.

    Uses MD5 hash of concatenated inputs to create a stable, reproducible ID.
    This enables consistent joins across different source systems.

    Args:
        tenant_id: The tenant identifier (required for multi-tenant isolation)
        source: The data source identifier (e.g., 'meta_ads', 'google_ads')
        platform_id: The platform-specific entity ID (e.g., campaign_id, account_id)

    Returns:
        32-character hexadecimal MD5 hash string

    Formula:
        md5(tenant_id || '|' || source || '|' || platform_id)

    The pipe delimiter prevents collision between:
        - tenant_id='abc', source='def', platform_id='123'
        - tenant_id='ab', source='cdef', platform_id='123'

    See docs/ID_NORMALIZATION.md for detailed documentation.
    #}

    md5(
        coalesce(cast({{ tenant_id }} as varchar), '')
        || '|'
        || coalesce(cast({{ source }} as varchar), '')
        || '|'
        || coalesce(cast({{ platform_id }} as varchar), '')
    )
{% endmacro %}


{% macro generate_internal_account_id(tenant_id, source, platform_account_id) %}
    {#
    Generates a deterministic internal ID for ad accounts.

    Wrapper around generate_internal_id with semantic naming for accounts.

    Args:
        tenant_id: The tenant identifier
        source: The data source identifier
        platform_account_id: The platform-specific account ID

    Returns:
        32-character hexadecimal MD5 hash string prefixed with 'acc_'
    #}

    'acc_' || {{ generate_internal_id(tenant_id, source, platform_account_id) }}
{% endmacro %}


{% macro generate_internal_campaign_id(tenant_id, source, platform_campaign_id) %}
    {#
    Generates a deterministic internal ID for campaigns.

    Wrapper around generate_internal_id with semantic naming for campaigns.

    Args:
        tenant_id: The tenant identifier
        source: The data source identifier
        platform_campaign_id: The platform-specific campaign ID

    Returns:
        32-character hexadecimal MD5 hash string prefixed with 'cmp_'
    #}

    'cmp_' || {{ generate_internal_id(tenant_id, source, platform_campaign_id) }}
{% endmacro %}


{% macro generate_internal_adgroup_id(tenant_id, source, platform_adgroup_id) %}
    {#
    Generates a deterministic internal ID for ad groups/ad sets.

    Args:
        tenant_id: The tenant identifier
        source: The data source identifier
        platform_adgroup_id: The platform-specific ad group/ad set ID

    Returns:
        32-character hexadecimal MD5 hash string prefixed with 'adg_'
    #}

    'adg_' || {{ generate_internal_id(tenant_id, source, platform_adgroup_id) }}
{% endmacro %}


{% macro generate_internal_ad_id(tenant_id, source, platform_ad_id) %}
    {#
    Generates a deterministic internal ID for individual ads.

    Args:
        tenant_id: The tenant identifier
        source: The data source identifier
        platform_ad_id: The platform-specific ad ID

    Returns:
        32-character hexadecimal MD5 hash string prefixed with 'ad_'
    #}

    'ad_' || {{ generate_internal_id(tenant_id, source, platform_ad_id) }}
{% endmacro %}


{% macro generate_composite_key(tenant_id, fields) %}
    {#
    Generates a deterministic composite key from multiple fields.

    Useful for creating unique identifiers for fact table rows that span
    multiple dimensions.

    Args:
        tenant_id: The tenant identifier (always included first)
        fields: List of additional field names to include

    Returns:
        32-character hexadecimal MD5 hash string

    Example:
        {{ generate_composite_key('tenant_id', ['report_date', 'campaign_id', 'source']) }}
    #}

    md5(
        coalesce(cast({{ tenant_id }} as varchar), '')
        {% for field in fields %}
        || '|' || coalesce(cast({{ field }} as varchar), '')
        {% endfor %}
    )
{% endmacro %}
