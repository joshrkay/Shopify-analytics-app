{% macro generate_schema_name(custom_schema_name, node) -%}

    {#-
        Override dbt's default schema naming to deploy models directly to the
        custom schema, without prepending the target schema as a prefix.

        Default dbt behavior: <target_schema>_<custom_schema>  (e.g. public_analytics)
        This macro:           <custom_schema>                   (e.g. analytics)

        This matches the production setup where backend routes query:
            analytics.orders
            analytics.marketing_spend
            marts.mart_marketing_metrics
            staging.stg_shopify_orders
            ...etc.

        If no custom schema is set on a model, falls back to the profile's
        target schema (consistent with dbt's default for that case).
    -#}

    {%- set default_schema = target.schema -%}
    {%- if custom_schema_name is none -%}
        {{ default_schema }}
    {%- else -%}
        {{ custom_schema_name | trim }}
    {%- endif -%}

{%- endmacro %}
