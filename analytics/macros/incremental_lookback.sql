{% macro get_lookback_days(source_name) %}
    {#
    Gets the lookback days for a source from vars.

    Lookback days are used in incremental models to reprocess
    recent data that may have been updated (late-arriving conversions,
    attribution updates, etc.).

    Args:
        source_name: Name of the source (meta_ads, google_ads, etc.)

    Returns:
        Number of lookback days for the source
    #}

    {% set lookback_config = var('lookback_days', {}) %}
    {% set default_lookback = var('default_lookback_days', 3) %}

    {{ lookback_config.get(source_name, default_lookback) }}
{% endmacro %}


{% macro incremental_filter(date_column, source_name) %}
    {#
    Generates the incremental filter clause for a staging model.

    This macro handles:
    - Full refresh: No filter applied
    - Incremental: Filters to max(date) - lookback_days from target

    Args:
        date_column: The date column to filter on
        source_name: Name of the source for lookback config

    Returns:
        WHERE clause for incremental filtering
    #}

    {% if is_incremental() %}
        {% set lookback = get_lookback_days(source_name) %}
        where {{ date_column }} >= (
            select coalesce(
                max({{ date_column }}) - interval '{{ lookback }} days',
                '1970-01-01'::date
            )
            from {{ this }}
        )
    {% endif %}
{% endmacro %}


{% macro incremental_filter_timestamp(timestamp_column, source_name) %}
    {#
    Generates the incremental filter clause using a timestamp column.

    Similar to incremental_filter but for timestamp-based filtering.

    Args:
        timestamp_column: The timestamp column to filter on
        source_name: Name of the source for lookback config

    Returns:
        WHERE clause for incremental filtering
    #}

    {% if is_incremental() %}
        {% set lookback = get_lookback_days(source_name) %}
        where {{ timestamp_column }} >= (
            select coalesce(
                max({{ timestamp_column }}) - interval '{{ lookback }} days',
                '1970-01-01'::timestamp
            )
            from {{ this }}
        )
    {% endif %}
{% endmacro %}


{% macro get_freshness_threshold(source_name, level) %}
    {#
    Gets the freshness threshold for a source from vars.

    Args:
        source_name: Name of the source
        level: 'warn' or 'error'

    Returns:
        Freshness threshold in minutes
    #}

    {% set freshness_config = var('freshness_thresholds', {}) %}
    {% set source_thresholds = freshness_config.get(source_name, {'warn': 1440, 'error': 5760}) %}

    {{ source_thresholds.get(level, 1440) }}
{% endmacro %}
