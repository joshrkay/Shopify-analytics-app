{% macro get_tenant_id(connection_id_expr) %}
    {#
    Macro to get tenant_id from Airbyte connection_id.
    
    This macro looks up the tenant_id from tenant_airbyte_connections
    based on the connection_id. The connection_id can come from:
    - Schema name (if Airbyte uses connection-specific schemas)
    - Table metadata
    - A mapping table
    
    Args:
        connection_id_expr: Expression that evaluates to the Airbyte connection_id
        
    Returns:
        tenant_id for the given connection_id
    #}
    
    (
        select tenant_id
        from {{ ref('_tenant_airbyte_connections') }}
        where airbyte_connection_id = {{ connection_id_expr }}
        limit 1
    )
{% endmacro %}
