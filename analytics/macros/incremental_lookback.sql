{% macro get_lookback_days(source_name) %}
    {#
    Returns the lookback window (in days) for a given source.

    Lookback windows handle:
    - Late-arriving data (conversions reported after the fact)
    - Attribution window delays (7-day click attribution, etc.)
    - API reporting delays

    Priority:
    1. Source-specific value from vars.lookback_days.{source_name}
    2. Default value from vars.default_lookback_days
    3. Hardcoded fallback of 3 days

    Args:
        source_name: The source identifier (e.g., 'meta_ads', 'google_ads')

    Returns:
        Integer number of days to look back
    #}

    {% set source_lookback = var('lookback_days', {}).get(source_name, none) %}
    {% set default_lookback = var('default_lookback_days', 3) %}

    {{ source_lookback if source_lookback is not none else default_lookback }}
{% endmacro %}


{% macro incremental_date_filter(date_column, source_name, include_buffer=true) %}
    {#
    Generates an incremental date filter clause for staging models.

    This macro creates the WHERE clause condition for incremental processing
    with configurable lookback windows per source.

    Args:
        date_column: The column containing the date to filter on
        source_name: The source identifier for lookback config
        include_buffer: If true, applies lookback buffer; if false, uses exact max date

    Returns:
        SQL WHERE clause fragment for incremental filtering

    Example usage in a model:
        {% if is_incremental() %}
        where {{ incremental_date_filter('report_date', 'meta_ads') }}
        {% endif %}
    #}

    {% set lookback = get_lookback_days(source_name) %}

    {% if include_buffer %}
        {{ date_column }} >= (
            select coalesce(max({{ date_column }}), '1970-01-01'::date) - interval '{{ lookback }} days'
            from {{ this }}
        )
    {% else %}
        {{ date_column }} >= (
            select coalesce(max({{ date_column }}), '1970-01-01'::date)
            from {{ this }}
        )
    {% endif %}
{% endmacro %}


{% macro incremental_timestamp_filter(timestamp_column, source_name, include_buffer=true) %}
    {#
    Generates an incremental timestamp filter clause for staging models.

    Similar to incremental_date_filter but works with timestamp columns.
    Useful for sources that report by timestamp rather than date.

    Args:
        timestamp_column: The column containing the timestamp to filter on
        source_name: The source identifier for lookback config
        include_buffer: If true, applies lookback buffer; if false, uses exact max timestamp

    Returns:
        SQL WHERE clause fragment for incremental filtering
    #}

    {% set lookback = get_lookback_days(source_name) %}

    {% if include_buffer %}
        {{ timestamp_column }} >= (
            select coalesce(max({{ timestamp_column }}), '1970-01-01'::timestamp) - interval '{{ lookback }} days'
            from {{ this }}
        )
    {% else %}
        {{ timestamp_column }} >= (
            select coalesce(max({{ timestamp_column }}), '1970-01-01'::timestamp)
            from {{ this }}
        )
    {% endif %}
{% endmacro %}


{% macro get_incremental_strategy_config(source_name) %}
    {#
    Returns the incremental strategy configuration for a source.

    This is used to configure the model's incremental behavior.

    Returns a dict with:
        - strategy: The incremental strategy type
        - unique_key: The unique key for merge operations
        - lookback_days: The lookback window for this source
    #}

    {% set lookback = get_lookback_days(source_name) %}

    {%- set config = {
        'strategy': 'merge',
        'unique_key': ['tenant_id', 'report_date', 'platform_account_id', 'platform_campaign_id'],
        'lookback_days': lookback
    } -%}

    {{ return(config) }}
{% endmacro %}


{% macro apply_incremental_merge_key(tenant_id, report_date, account_id, campaign_id, ad_id=none) %}
    {#
    Generates a composite merge key for incremental models.

    This ensures proper deduplication during incremental runs.

    Args:
        tenant_id: Tenant identifier
        report_date: The date grain
        account_id: The account identifier
        campaign_id: The campaign identifier
        ad_id: Optional ad-level identifier for ad-level granularity

    Returns:
        MD5 hash of concatenated identifiers
    #}

    md5(
        coalesce(cast({{ tenant_id }} as varchar), '')
        || '|' || coalesce(cast({{ report_date }} as varchar), '')
        || '|' || coalesce(cast({{ account_id }} as varchar), '')
        || '|' || coalesce(cast({{ campaign_id }} as varchar), '')
        {% if ad_id %}
        || '|' || coalesce(cast({{ ad_id }} as varchar), '')
        {% endif %}
    )
{% endmacro %}
