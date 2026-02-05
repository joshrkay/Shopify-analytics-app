{#
    Macro: assert_columns_approved

    Validates that every column in a staging/canonical model is present in the
    governance allowlist for its source. Returns a SQL query that produces one
    row per unapproved column. A dbt test calling this macro will FAIL if any
    rows are returned.

    Arguments:
        model_name  (string) - The dbt model name, e.g. 'stg_shopify_orders'
        source_name (string) - The allowlist source key, e.g. 'shopify'
                               (used in error messages only)

    Usage in a test:
        {{ assert_columns_approved('stg_shopify_orders', 'shopify') }}

    How it works:
        1. Calls get_approved_columns() to retrieve the compile-time allowlist.
        2. Extracts the list of approved column names for the given model.
        3. Queries information_schema to find actual columns in the relation.
        4. Returns rows for any column present in the relation but absent from
           the allowlist (i.e. unapproved columns).
#}

{% macro assert_columns_approved(model_name, source_name) %}

{#-- Load the allowlist from the compiled macro --#}
{%- set all_approved = get_approved_columns() -%}
{%- set approved_columns = all_approved.get(model_name, []) -%}

{#-- Build a set of lowercase approved column names for comparison --#}
{%- set approved_set = [] -%}
{%- for col in approved_columns -%}
    {%- do approved_set.append(col | lower) -%}
{%- endfor -%}

{#-- Reference file path for error messages --#}
{%- set allowlist_path = 'governance/approved_columns_' ~ source_name ~ '.yml' -%}

{#-- Get the relation for the model --#}
{%- set model_relation = ref(model_name) -%}

{#--
    Query: select every column from the model's relation that is NOT in
    the approved set. If this returns rows, the test fails.
--#}
with model_columns as (
    select
        lower(column_name) as column_name
    from information_schema.columns
    where table_schema = '{{ model_relation.schema }}'
      and table_name   = '{{ model_relation.identifier }}'
)

select
    '{{ model_name }}' as model_name,
    column_name as unapproved_column,
    '{{ allowlist_path }}' as allowlist_file,
    'SCHEMA DRIFT DETECTED: Column "' || column_name || '" in model "{{ model_name }}" is not in the approved allowlist ({{ allowlist_path }}). Add it to the allowlist and open a PR for approval.' as error_message
from model_columns
where column_name not in (
    {%- for col in approved_set -%}
        '{{ col }}'{{ ',' if not loop.last }}
    {%- endfor -%}
)

{% endmacro %}
