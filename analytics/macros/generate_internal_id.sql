{% macro generate_internal_id(tenant_id, source, platform_id) %}
    {#
    Generates a deterministic internal ID from tenant_id + source + platform_id.

    Uses MD5 hash to create a stable, deterministic identifier that:
    - Is unique across tenants (includes tenant_id)
    - Is unique across sources (includes source)
    - Maps 1:1 to platform IDs (includes platform_id)
    - Is stable across runs (deterministic hash)

    Format: md5(tenant_id || '|' || source || '|' || platform_id)

    Args:
        tenant_id: The tenant identifier
        source: The data source (meta_ads, google_ads, etc.)
        platform_id: The platform-specific ID (account_id, campaign_id, etc.)

    Returns:
        32-character hexadecimal MD5 hash
    #}

    md5({{ tenant_id }}::text || '|' || {{ source }}::text || '|' || {{ platform_id }}::text)
{% endmacro %}


{% macro generate_internal_account_id(tenant_id, source, platform_account_id) %}
    {#
    Generates an internal account ID for dim_ad_accounts.

    Wrapper around generate_internal_id for account-specific use.

    Args:
        tenant_id: The tenant identifier
        source: The data source
        platform_account_id: The platform-specific account ID

    Returns:
        Internal account ID (MD5 hash)
    #}

    {{ generate_internal_id(tenant_id, source, platform_account_id) }}
{% endmacro %}


{% macro generate_internal_campaign_id(tenant_id, source, platform_campaign_id) %}
    {#
    Generates an internal campaign ID for dim_campaigns.

    Wrapper around generate_internal_id for campaign-specific use.

    Args:
        tenant_id: The tenant identifier
        source: The data source
        platform_campaign_id: The platform-specific campaign ID

    Returns:
        Internal campaign ID (MD5 hash)
    #}

    {{ generate_internal_id(tenant_id, source, platform_campaign_id) }}
{% endmacro %}


{% macro generate_composite_key(parts) %}
    {#
    Generates a composite key from multiple parts.

    Useful for creating unique row identifiers from multiple columns.

    Args:
        parts: List of column expressions to combine

    Returns:
        MD5 hash of concatenated parts
    #}

    md5(
        {% for part in parts %}
            coalesce({{ part }}::text, '')
            {% if not loop.last %} || '|' || {% endif %}
        {% endfor %}
    )
{% endmacro %}
