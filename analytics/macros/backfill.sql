{#
  Macro: backfill_date_range
  
  Generates SQL WHERE clause filters for date-range and tenant-scoped backfills.
  
  Usage:
    SELECT * FROM {{ ref('staging_model') }}
    WHERE 1=1
      {{ backfill_date_range(var('backfill_start_date'), var('backfill_end_date'), var('tenant_id')) }}
  
  Parameters:
    - start_date: Optional date string (YYYY-MM-DD) or datetime
    - end_date: Optional date string (YYYY-MM-DD) or datetime
    - tenant_id: Optional tenant identifier string
  
  Returns:
    SQL WHERE clause conditions for date range and tenant filtering
#}

{% macro backfill_date_range(start_date, end_date, tenant_id=none) %}
  {%- set conditions = [] -%}
  
  {# Date range filtering #}
  {%- if start_date is not none and start_date != '' -%}
    {%- set _ = conditions.append("created_at >= " ~ dbt.string_literal(start_date) ~ "::timestamp") -%}
  {%- endif -%}
  
  {%- if end_date is not none and end_date != '' -%}
    {%- set _ = conditions.append("created_at <= " ~ dbt.string_literal(end_date) ~ "::timestamp") -%}
  {%- endif -%}
  
  {# Tenant filtering #}
  {%- if tenant_id is not none and tenant_id != '' -%}
    {%- set _ = conditions.append("tenant_id = " ~ dbt.string_literal(tenant_id)) -%}
  {%- endif -%}
  
  {# Return combined conditions #}
  {%- if conditions|length > 0 -%}
    {%- for condition in conditions -%}
      AND {{ condition }}
    {%- endfor -%}
  {%- endif -%}
{% endmacro %}
