{% macro get_tenant_id(connection_id_expr) %}
    {#
    Macro to get tenant_id from Airbyte connection_id.
    
    This macro looks up the tenant_id from tenant_airbyte_connections
    based on the connection_id. The connection_id should be explicitly
    provided or extracted from your Airbyte setup.
    
    SECURITY: Do NOT use this macro without providing a proper connection_id_expr.
    Using a subquery that selects with `limit 1` causes cross-tenant data leakage
    when multiple connections exist for the same source_type.
    
    Args:
        connection_id_expr: Expression that evaluates to the Airbyte connection_id
                           This should come from schema name, table metadata, or
                           a join key - never from a limit 1 query.
        
    Returns:
        tenant_id for the given connection_id
        
    Example usage:
        {{ get_tenant_id("'my-connection-id'") }}
        {{ get_tenant_id("ord.connection_identifier") }}
    #}
    
    (
        select tenant_id
        from {{ ref('_tenant_airbyte_connections') }}
        where airbyte_connection_id = {{ connection_id_expr }}
          and status = 'active'
          and is_enabled = true
        limit 1
    )
{% endmacro %}
