{% macro extract_connection_identifier() %}
    {#
    Macro to extract Airbyte connection identifier from the current schema.
    
    This macro supports multiple schema naming patterns:
    - airbyte_raw_<connection_id> -> extracts connection_id
    - <connection_id>_raw -> extracts connection_id
    - <tenant>_<connection_id>_raw -> extracts connection_id
    - custom patterns -> returns full schema name
    
    Returns:
        SQL CASE expression that evaluates to the connection identifier string
    
    Example usage:
        {{ extract_connection_identifier() }} as connection_identifier
    #}
    
    case
        -- Pattern: airbyte_raw_<connection_id>
        when current_schema() ~ '^airbyte_raw_[a-zA-Z0-9-]+$'
            then regexp_replace(current_schema(), '^airbyte_raw_', '')
        
        -- Pattern: <connection_id>_raw
        when current_schema() ~ '^[a-zA-Z0-9-]+_raw$'
            then regexp_replace(current_schema(), '_raw$', '')
        
        -- Pattern: <prefix>_<connection_id>_raw (tenant-prefixed)
        -- Extract everything between first underscore and _raw suffix
        when current_schema() ~ '^[a-zA-Z0-9-]+_[a-zA-Z0-9-]+_raw$'
            then regexp_replace(current_schema(), '^[^_]+_|_raw$', '', 'g')
        
        -- Fallback: use full schema name as identifier
        else current_schema()
    end
{% endmacro %}
