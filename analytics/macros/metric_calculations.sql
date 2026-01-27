{% macro calculate_cpm(spend, impressions) %}
    {#
    Calculates Cost Per Mille (cost per 1,000 impressions).

    Formula: (spend / impressions) * 1000

    Args:
        spend: Total spend amount
        impressions: Total impression count

    Returns:
        CPM value, or null if impressions is 0 or null
    #}

    case
        when {{ impressions }} is null or {{ impressions }} = 0 then null
        else round(({{ spend }}::numeric / {{ impressions }}::numeric) * 1000, 2)
    end
{% endmacro %}


{% macro calculate_cpc(spend, clicks) %}
    {#
    Calculates Cost Per Click.

    Formula: spend / clicks

    Args:
        spend: Total spend amount
        clicks: Total click count

    Returns:
        CPC value, or null if clicks is 0 or null
    #}

    case
        when {{ clicks }} is null or {{ clicks }} = 0 then null
        else round({{ spend }}::numeric / {{ clicks }}::numeric, 2)
    end
{% endmacro %}


{% macro calculate_ctr(clicks, impressions) %}
    {#
    Calculates Click-Through Rate as a percentage.

    Formula: (clicks / impressions) * 100

    Args:
        clicks: Total click count
        impressions: Total impression count

    Returns:
        CTR as percentage (e.g., 2.5 for 2.5%), or null if impressions is 0
    #}

    case
        when {{ impressions }} is null or {{ impressions }} = 0 then null
        else round(({{ clicks }}::numeric / {{ impressions }}::numeric) * 100, 4)
    end
{% endmacro %}


{% macro calculate_cpa(spend, conversions) %}
    {#
    Calculates Cost Per Acquisition/Conversion.

    Formula: spend / conversions

    Args:
        spend: Total spend amount
        conversions: Total conversion count

    Returns:
        CPA value, or null if conversions is 0 or null
    #}

    case
        when {{ conversions }} is null or {{ conversions }} = 0 then null
        else round({{ spend }}::numeric / {{ conversions }}::numeric, 2)
    end
{% endmacro %}


{% macro calculate_roas(conversion_value, spend) %}
    {#
    Calculates Return On Ad Spend.

    Formula: conversion_value / spend

    This is the platform-reported ROAS, not blended ROAS.

    Args:
        conversion_value: Total value of conversions (revenue from ads)
        spend: Total spend amount

    Returns:
        ROAS ratio (e.g., 3.5 means $3.50 revenue per $1 spent), or null if spend is 0
    #}

    case
        when {{ spend }} is null or {{ spend }} = 0 then null
        else round({{ conversion_value }}::numeric / {{ spend }}::numeric, 4)
    end
{% endmacro %}


{% macro calculate_aov(revenue, orders) %}
    {#
    Calculates Average Order Value.

    Formula: revenue / orders

    Args:
        revenue: Total revenue amount
        orders: Total order count

    Returns:
        AOV value, or null if orders is 0 or null
    #}

    case
        when {{ orders }} is null or {{ orders }} = 0 then null
        else round({{ revenue }}::numeric / {{ orders }}::numeric, 2)
    end
{% endmacro %}


{% macro calculate_conversion_rate(conversions, clicks) %}
    {#
    Calculates Conversion Rate as a percentage.

    Formula: (conversions / clicks) * 100

    Args:
        conversions: Total conversion count
        clicks: Total click count

    Returns:
        Conversion rate as percentage, or null if clicks is 0
    #}

    case
        when {{ clicks }} is null or {{ clicks }} = 0 then null
        else round(({{ conversions }}::numeric / {{ clicks }}::numeric) * 100, 4)
    end
{% endmacro %}


{% macro safe_divide(numerator, denominator, default_value=0) %}
    {#
    Performs safe division with null/zero handling.

    Args:
        numerator: The dividend
        denominator: The divisor
        default_value: Value to return if division is not possible (default: 0)

    Returns:
        Result of division, or default_value if denominator is 0 or null
    #}

    case
        when {{ denominator }} is null or {{ denominator }} = 0 then {{ default_value }}
        else {{ numerator }}::numeric / {{ denominator }}::numeric
    end
{% endmacro %}


{% macro normalize_currency_to_dollars(amount_cents) %}
    {#
    Converts amount from cents to dollars.

    Args:
        amount_cents: Amount in cents (integer)

    Returns:
        Amount in dollars (numeric with 2 decimal places)
    #}

    round(coalesce({{ amount_cents }}, 0)::numeric / 100, 2)
{% endmacro %}


{% macro normalize_micros_to_dollars(amount_micros) %}
    {#
    Converts amount from micros to dollars (Google Ads format).

    Google Ads API returns monetary values in micros (1/1,000,000 of currency unit).

    Args:
        amount_micros: Amount in micros (integer)

    Returns:
        Amount in dollars (numeric with 2 decimal places)
    #}

    round(coalesce({{ amount_micros }}, 0)::numeric / 1000000, 2)
{% endmacro %}
