{% macro setup_test_data() %}
  {% set setup_sql %}
    -- Create test schema
    CREATE SCHEMA IF NOT EXISTS test_airbyte;
    
    -- Create test tables (simplified - full data in test_data_setup.sql)
    CREATE TABLE IF NOT EXISTS test_airbyte._airbyte_raw_shopify_orders (
        _airbyte_ab_id VARCHAR(255) PRIMARY KEY,
        _airbyte_emitted_at TIMESTAMP WITH TIME ZONE NOT NULL,
        _airbyte_data JSONB NOT NULL
    );
    
    CREATE TABLE IF NOT EXISTS test_airbyte._airbyte_raw_shopify_customers (
        _airbyte_ab_id VARCHAR(255) PRIMARY KEY,
        _airbyte_emitted_at TIMESTAMP WITH TIME ZONE NOT NULL,
        _airbyte_data JSONB NOT NULL
    );
    
    CREATE TABLE IF NOT EXISTS test_airbyte._airbyte_raw_meta_ads (
        _airbyte_ab_id VARCHAR(255) PRIMARY KEY,
        _airbyte_emitted_at TIMESTAMP WITH TIME ZONE NOT NULL,
        _airbyte_data JSONB NOT NULL
    );
    
    CREATE TABLE IF NOT EXISTS test_airbyte._airbyte_raw_google_ads (
        _airbyte_ab_id VARCHAR(255) PRIMARY KEY,
        _airbyte_emitted_at TIMESTAMP WITH TIME ZONE NOT NULL,
        _airbyte_data JSONB NOT NULL
    );
    
    CREATE TABLE IF NOT EXISTS test_airbyte.tenant_airbyte_connections (
        id VARCHAR(255) PRIMARY KEY,
        tenant_id VARCHAR(255) NOT NULL,
        airbyte_connection_id VARCHAR(255) NOT NULL,
        source_type VARCHAR(100),
        platform_account_id VARCHAR(255),
        status VARCHAR(50),
        is_enabled BOOLEAN,
        created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
        updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
    );
    
    -- Insert test tenant connections
    INSERT INTO test_airbyte.tenant_airbyte_connections VALUES
    ('conn-1', 'tenant-test-123', 'airbyte-conn-shopify-1', 'shopify', 'test-shop-12345', 'active', true, NOW(), NOW()),
    ('conn-2', 'tenant-test-123', 'airbyte-conn-meta-1', 'source-facebook-marketing', 'act_123456', 'active', true, NOW(), NOW()),
    ('conn-3', 'tenant-test-123', 'airbyte-conn-google-1', 'source-google-ads', '1234567890', 'active', true, NOW(), NOW())
    ON CONFLICT (id) DO NOTHING;
  {% endset %}
  
  {% do run_query(setup_sql) %}
  {{ return('Test data schema and tables created') }}
{% endmacro %}
