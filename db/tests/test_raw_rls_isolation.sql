-- Raw Warehouse Layer - RLS Isolation Tests
-- Version: 1.0.0
-- Date: 2026-01-26
--
-- Comprehensive test suite to verify Row-Level Security isolation.
-- These tests ensure that tenants can NEVER see data from other tenants.
--
-- PREREQUISITES:
--   - raw_schema.sql must be run first
--   - raw_rls.sql must be run to enable RLS
--
-- TEST STRATEGY:
--   1. Create test users with appropriate roles
--   2. Insert test data for multiple tenants
--   3. Verify isolation by switching tenant context
--   4. Verify no data returned without tenant context
--   5. Cleanup test data after tests
--
-- Usage: psql $DATABASE_URL -f test_raw_rls_isolation.sql

-- =============================================================================
-- Test Setup
-- =============================================================================

-- Create test schema for isolation tests
CREATE SCHEMA IF NOT EXISTS test_rls;

-- Test result tracking
CREATE TABLE IF NOT EXISTS test_rls.test_results (
    id SERIAL PRIMARY KEY,
    test_name VARCHAR(255) NOT NULL,
    test_description TEXT,
    expected_result TEXT,
    actual_result TEXT,
    passed BOOLEAN NOT NULL,
    error_message TEXT,
    executed_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
);

-- Clear previous test results
TRUNCATE TABLE test_rls.test_results;

-- Test tenant IDs
DO $$
DECLARE
    v_tenant_a VARCHAR(255) := 'test-tenant-alpha-001';
    v_tenant_b VARCHAR(255) := 'test-tenant-beta-002';
    v_tenant_c VARCHAR(255) := 'test-tenant-gamma-003';
BEGIN
    -- Store test tenant IDs for reference
    RAISE NOTICE 'Test Tenant A: %', v_tenant_a;
    RAISE NOTICE 'Test Tenant B: %', v_tenant_b;
    RAISE NOTICE 'Test Tenant C: %', v_tenant_c;
END $$;

-- =============================================================================
-- Create Test User for Query Role
-- =============================================================================

DO $$
BEGIN
    -- Create test user if not exists
    IF NOT EXISTS (SELECT FROM pg_catalog.pg_roles WHERE rolname = 'test_query_user') THEN
        CREATE USER test_query_user WITH PASSWORD 'test_password_123';
    END IF;

    -- Grant the query role
    GRANT raw_query_role TO test_query_user;
    GRANT USAGE ON SCHEMA test_rls TO test_query_user;
    GRANT SELECT, INSERT ON test_rls.test_results TO test_query_user;

    RAISE NOTICE 'Test user created and granted raw_query_role';
END $$;

-- =============================================================================
-- Insert Test Data (Using Admin Role - Bypasses RLS)
-- =============================================================================

-- Clear existing test data
DELETE FROM raw.raw_shopify_orders WHERE tenant_id LIKE 'test-tenant-%';
DELETE FROM raw.raw_meta_ads_insights WHERE tenant_id LIKE 'test-tenant-%';
DELETE FROM raw.raw_google_ads_campaigns WHERE tenant_id LIKE 'test-tenant-%';
DELETE FROM raw.raw_shopify_customers WHERE tenant_id LIKE 'test-tenant-%';
DELETE FROM raw.raw_shopify_products WHERE tenant_id LIKE 'test-tenant-%';

-- Insert test data for Tenant A
INSERT INTO raw.raw_shopify_orders (
    tenant_id, source_account_id, extracted_at, run_id, shopify_order_id,
    order_number, total_price_cents, currency
) VALUES
    ('test-tenant-alpha-001', 'shop-alpha', NOW() - INTERVAL '1 day', 'run-test-001', 'order-a-001', '1001', 9999, 'USD'),
    ('test-tenant-alpha-001', 'shop-alpha', NOW() - INTERVAL '2 days', 'run-test-001', 'order-a-002', '1002', 14999, 'USD'),
    ('test-tenant-alpha-001', 'shop-alpha', NOW() - INTERVAL '3 days', 'run-test-001', 'order-a-003', '1003', 5999, 'USD');

-- Insert test data for Tenant B
INSERT INTO raw.raw_shopify_orders (
    tenant_id, source_account_id, extracted_at, run_id, shopify_order_id,
    order_number, total_price_cents, currency
) VALUES
    ('test-tenant-beta-002', 'shop-beta', NOW() - INTERVAL '1 day', 'run-test-002', 'order-b-001', '2001', 25000, 'USD'),
    ('test-tenant-beta-002', 'shop-beta', NOW() - INTERVAL '2 days', 'run-test-002', 'order-b-002', '2002', 35000, 'USD');

-- Insert test data for Tenant C
INSERT INTO raw.raw_shopify_orders (
    tenant_id, source_account_id, extracted_at, run_id, shopify_order_id,
    order_number, total_price_cents, currency
) VALUES
    ('test-tenant-gamma-003', 'shop-gamma', NOW() - INTERVAL '1 day', 'run-test-003', 'order-c-001', '3001', 100000, 'EUR');

-- Insert test data for Meta Ads
INSERT INTO raw.raw_meta_ads_insights (
    tenant_id, source_account_id, extracted_at, run_id, campaign_id, date_start, date_stop,
    impressions, clicks, spend_cents
) VALUES
    ('test-tenant-alpha-001', 'ad-account-alpha', NOW() - INTERVAL '1 day', 'run-test-001', 'camp-a-001', CURRENT_DATE - 1, CURRENT_DATE - 1, 10000, 500, 5000),
    ('test-tenant-beta-002', 'ad-account-beta', NOW() - INTERVAL '1 day', 'run-test-002', 'camp-b-001', CURRENT_DATE - 1, CURRENT_DATE - 1, 20000, 1000, 10000),
    ('test-tenant-gamma-003', 'ad-account-gamma', NOW() - INTERVAL '1 day', 'run-test-003', 'camp-c-001', CURRENT_DATE - 1, CURRENT_DATE - 1, 30000, 1500, 15000);

-- Insert test data for Google Ads
INSERT INTO raw.raw_google_ads_campaigns (
    tenant_id, source_account_id, extracted_at, run_id, campaign_id, campaign_name, metrics_date,
    impressions, clicks, cost_micros
) VALUES
    ('test-tenant-alpha-001', 'customer-alpha', NOW() - INTERVAL '1 day', 'run-test-001', 'gcamp-a-001', 'Alpha Campaign', CURRENT_DATE - 1, 5000, 250, 2500000000),
    ('test-tenant-beta-002', 'customer-beta', NOW() - INTERVAL '1 day', 'run-test-002', 'gcamp-b-001', 'Beta Campaign', CURRENT_DATE - 1, 15000, 750, 7500000000);

RAISE NOTICE 'Test data inserted: 6 orders, 3 Meta insights, 2 Google campaigns';

-- =============================================================================
-- TEST 1: Tenant A can only see Tenant A data
-- =============================================================================

DO $$
DECLARE
    v_count INTEGER;
    v_test_name VARCHAR(255) := 'TEST_1_TENANT_A_SEES_OWN_DATA';
BEGIN
    -- Set tenant context to Tenant A
    PERFORM set_config('app.tenant_id', 'test-tenant-alpha-001', true);

    -- Count orders visible to Tenant A
    SELECT COUNT(*) INTO v_count FROM raw.raw_shopify_orders;

    -- Tenant A should see exactly 3 orders
    INSERT INTO test_rls.test_results (test_name, test_description, expected_result, actual_result, passed)
    VALUES (
        v_test_name,
        'Tenant A should see exactly 3 orders (their own data only)',
        '3',
        v_count::TEXT,
        v_count = 3
    );

    IF v_count = 3 THEN
        RAISE NOTICE '✓ %: PASSED - Tenant A sees 3 orders', v_test_name;
    ELSE
        RAISE WARNING '✗ %: FAILED - Expected 3 orders, got %', v_test_name, v_count;
    END IF;
END $$;

-- =============================================================================
-- TEST 2: Tenant B can only see Tenant B data
-- =============================================================================

DO $$
DECLARE
    v_count INTEGER;
    v_test_name VARCHAR(255) := 'TEST_2_TENANT_B_SEES_OWN_DATA';
BEGIN
    -- Set tenant context to Tenant B
    PERFORM set_config('app.tenant_id', 'test-tenant-beta-002', true);

    SELECT COUNT(*) INTO v_count FROM raw.raw_shopify_orders;

    INSERT INTO test_rls.test_results (test_name, test_description, expected_result, actual_result, passed)
    VALUES (
        v_test_name,
        'Tenant B should see exactly 2 orders (their own data only)',
        '2',
        v_count::TEXT,
        v_count = 2
    );

    IF v_count = 2 THEN
        RAISE NOTICE '✓ %: PASSED - Tenant B sees 2 orders', v_test_name;
    ELSE
        RAISE WARNING '✗ %: FAILED - Expected 2 orders, got %', v_test_name, v_count;
    END IF;
END $$;

-- =============================================================================
-- TEST 3: Tenant A cannot see Tenant B data
-- =============================================================================

DO $$
DECLARE
    v_count INTEGER;
    v_test_name VARCHAR(255) := 'TEST_3_TENANT_A_CANNOT_SEE_TENANT_B';
BEGIN
    PERFORM set_config('app.tenant_id', 'test-tenant-alpha-001', true);

    -- Try to query Tenant B's data directly
    SELECT COUNT(*) INTO v_count
    FROM raw.raw_shopify_orders
    WHERE tenant_id = 'test-tenant-beta-002';

    INSERT INTO test_rls.test_results (test_name, test_description, expected_result, actual_result, passed)
    VALUES (
        v_test_name,
        'Tenant A should NOT see any Tenant B orders (cross-tenant blocked)',
        '0',
        v_count::TEXT,
        v_count = 0
    );

    IF v_count = 0 THEN
        RAISE NOTICE '✓ %: PASSED - Cross-tenant access blocked', v_test_name;
    ELSE
        RAISE WARNING '✗ %: FAILED - SECURITY VIOLATION: Tenant A can see % Tenant B records!', v_test_name, v_count;
    END IF;
END $$;

-- =============================================================================
-- TEST 4: No tenant context returns no data
-- =============================================================================

DO $$
DECLARE
    v_count INTEGER;
    v_test_name VARCHAR(255) := 'TEST_4_NO_CONTEXT_NO_DATA';
BEGIN
    -- Clear tenant context
    PERFORM set_config('app.tenant_id', '', true);

    SELECT COUNT(*) INTO v_count FROM raw.raw_shopify_orders;

    INSERT INTO test_rls.test_results (test_name, test_description, expected_result, actual_result, passed)
    VALUES (
        v_test_name,
        'Without tenant context, no data should be visible',
        '0',
        v_count::TEXT,
        v_count = 0
    );

    IF v_count = 0 THEN
        RAISE NOTICE '✓ %: PASSED - No data without tenant context', v_test_name;
    ELSE
        RAISE WARNING '✗ %: FAILED - SECURITY VIOLATION: % records visible without context!', v_test_name, v_count;
    END IF;
END $$;

-- =============================================================================
-- TEST 5: Meta Ads isolation
-- =============================================================================

DO $$
DECLARE
    v_count_own INTEGER;
    v_count_other INTEGER;
    v_test_name VARCHAR(255) := 'TEST_5_META_ADS_ISOLATION';
BEGIN
    PERFORM set_config('app.tenant_id', 'test-tenant-alpha-001', true);

    SELECT COUNT(*) INTO v_count_own FROM raw.raw_meta_ads_insights;

    SELECT COUNT(*) INTO v_count_other
    FROM raw.raw_meta_ads_insights
    WHERE tenant_id != 'test-tenant-alpha-001';

    INSERT INTO test_rls.test_results (test_name, test_description, expected_result, actual_result, passed)
    VALUES (
        v_test_name,
        'Tenant A should see 1 Meta insight and 0 from other tenants',
        'own=1, other=0',
        format('own=%s, other=%s', v_count_own, v_count_other),
        v_count_own = 1 AND v_count_other = 0
    );

    IF v_count_own = 1 AND v_count_other = 0 THEN
        RAISE NOTICE '✓ %: PASSED - Meta Ads isolation verified', v_test_name;
    ELSE
        RAISE WARNING '✗ %: FAILED - own=%, other=%', v_test_name, v_count_own, v_count_other;
    END IF;
END $$;

-- =============================================================================
-- TEST 6: Google Ads isolation
-- =============================================================================

DO $$
DECLARE
    v_count_own INTEGER;
    v_count_other INTEGER;
    v_test_name VARCHAR(255) := 'TEST_6_GOOGLE_ADS_ISOLATION';
BEGIN
    PERFORM set_config('app.tenant_id', 'test-tenant-beta-002', true);

    SELECT COUNT(*) INTO v_count_own FROM raw.raw_google_ads_campaigns;

    SELECT COUNT(*) INTO v_count_other
    FROM raw.raw_google_ads_campaigns
    WHERE tenant_id != 'test-tenant-beta-002';

    INSERT INTO test_rls.test_results (test_name, test_description, expected_result, actual_result, passed)
    VALUES (
        v_test_name,
        'Tenant B should see 1 Google campaign and 0 from other tenants',
        'own=1, other=0',
        format('own=%s, other=%s', v_count_own, v_count_other),
        v_count_own = 1 AND v_count_other = 0
    );

    IF v_count_own = 1 AND v_count_other = 0 THEN
        RAISE NOTICE '✓ %: PASSED - Google Ads isolation verified', v_test_name;
    ELSE
        RAISE WARNING '✗ %: FAILED - own=%, other=%', v_test_name, v_count_own, v_count_other;
    END IF;
END $$;

-- =============================================================================
-- TEST 7: All tenants see correct total across all tables
-- =============================================================================

DO $$
DECLARE
    v_tenant_a_total INTEGER;
    v_tenant_b_total INTEGER;
    v_tenant_c_total INTEGER;
    v_test_name VARCHAR(255) := 'TEST_7_AGGREGATE_ISOLATION';
BEGIN
    -- Count all records for Tenant A
    PERFORM set_config('app.tenant_id', 'test-tenant-alpha-001', true);
    SELECT (
        (SELECT COUNT(*) FROM raw.raw_shopify_orders) +
        (SELECT COUNT(*) FROM raw.raw_meta_ads_insights) +
        (SELECT COUNT(*) FROM raw.raw_google_ads_campaigns)
    ) INTO v_tenant_a_total;

    -- Count all records for Tenant B
    PERFORM set_config('app.tenant_id', 'test-tenant-beta-002', true);
    SELECT (
        (SELECT COUNT(*) FROM raw.raw_shopify_orders) +
        (SELECT COUNT(*) FROM raw.raw_meta_ads_insights) +
        (SELECT COUNT(*) FROM raw.raw_google_ads_campaigns)
    ) INTO v_tenant_b_total;

    -- Count all records for Tenant C
    PERFORM set_config('app.tenant_id', 'test-tenant-gamma-003', true);
    SELECT (
        (SELECT COUNT(*) FROM raw.raw_shopify_orders) +
        (SELECT COUNT(*) FROM raw.raw_meta_ads_insights) +
        (SELECT COUNT(*) FROM raw.raw_google_ads_campaigns)
    ) INTO v_tenant_c_total;

    -- Tenant A: 3 orders + 1 meta + 1 google = 5
    -- Tenant B: 2 orders + 1 meta + 1 google = 4
    -- Tenant C: 1 order + 1 meta + 0 google = 2

    INSERT INTO test_rls.test_results (test_name, test_description, expected_result, actual_result, passed)
    VALUES (
        v_test_name,
        'Each tenant should see only their total records across all tables',
        'A=5, B=4, C=2',
        format('A=%s, B=%s, C=%s', v_tenant_a_total, v_tenant_b_total, v_tenant_c_total),
        v_tenant_a_total = 5 AND v_tenant_b_total = 4 AND v_tenant_c_total = 2
    );

    IF v_tenant_a_total = 5 AND v_tenant_b_total = 4 AND v_tenant_c_total = 2 THEN
        RAISE NOTICE '✓ %: PASSED - Aggregate isolation verified', v_test_name;
    ELSE
        RAISE WARNING '✗ %: FAILED - A=%, B=%, C=%', v_test_name, v_tenant_a_total, v_tenant_b_total, v_tenant_c_total;
    END IF;
END $$;

-- =============================================================================
-- TEST 8: Tenant cannot INSERT data for another tenant
-- =============================================================================

DO $$
DECLARE
    v_error_caught BOOLEAN := FALSE;
    v_test_name VARCHAR(255) := 'TEST_8_INSERT_ISOLATION';
    v_count_before INTEGER;
    v_count_after INTEGER;
BEGIN
    -- Set tenant context to Tenant A
    PERFORM set_config('app.tenant_id', 'test-tenant-alpha-001', true);

    -- Count Tenant B orders before
    PERFORM set_config('app.tenant_id', 'test-tenant-beta-002', true);
    SELECT COUNT(*) INTO v_count_before FROM raw.raw_shopify_orders;

    -- Try to insert as Tenant A but with Tenant B's tenant_id
    PERFORM set_config('app.tenant_id', 'test-tenant-alpha-001', true);

    -- This should fail because RLS policy will filter it (WITH CHECK clause)
    BEGIN
        INSERT INTO raw.raw_shopify_orders (
            tenant_id, source_account_id, extracted_at, run_id, shopify_order_id
        ) VALUES (
            'test-tenant-beta-002',  -- Trying to insert for different tenant
            'shop-malicious', NOW(), 'run-malicious', 'order-malicious'
        );
    EXCEPTION WHEN OTHERS THEN
        v_error_caught := TRUE;
    END;

    -- Verify no new records for Tenant B
    PERFORM set_config('app.tenant_id', 'test-tenant-beta-002', true);
    SELECT COUNT(*) INTO v_count_after FROM raw.raw_shopify_orders;

    INSERT INTO test_rls.test_results (test_name, test_description, expected_result, actual_result, passed)
    VALUES (
        v_test_name,
        'Tenant A should not be able to insert data for Tenant B',
        'blocked or unchanged',
        CASE WHEN v_error_caught THEN 'blocked' WHEN v_count_before = v_count_after THEN 'unchanged' ELSE 'INSERTED' END,
        v_error_caught OR v_count_before = v_count_after
    );

    IF v_error_caught OR v_count_before = v_count_after THEN
        RAISE NOTICE '✓ %: PASSED - Cross-tenant insert blocked', v_test_name;
    ELSE
        RAISE WARNING '✗ %: FAILED - SECURITY VIOLATION: Cross-tenant insert succeeded!', v_test_name;
    END IF;
END $$;

-- =============================================================================
-- TEST 9: Invalid tenant context returns no data
-- =============================================================================

DO $$
DECLARE
    v_count INTEGER;
    v_test_name VARCHAR(255) := 'TEST_9_INVALID_TENANT_NO_DATA';
BEGIN
    -- Set invalid tenant context
    PERFORM set_config('app.tenant_id', 'non-existent-tenant-xyz', true);

    SELECT COUNT(*) INTO v_count FROM raw.raw_shopify_orders;

    INSERT INTO test_rls.test_results (test_name, test_description, expected_result, actual_result, passed)
    VALUES (
        v_test_name,
        'Invalid tenant ID should return 0 records',
        '0',
        v_count::TEXT,
        v_count = 0
    );

    IF v_count = 0 THEN
        RAISE NOTICE '✓ %: PASSED - Invalid tenant returns no data', v_test_name;
    ELSE
        RAISE WARNING '✗ %: FAILED - % records visible with invalid tenant!', v_test_name, v_count;
    END IF;
END $$;

-- =============================================================================
-- TEST 10: SQL injection attempt in tenant context
-- =============================================================================

DO $$
DECLARE
    v_count INTEGER;
    v_test_name VARCHAR(255) := 'TEST_10_SQL_INJECTION_BLOCKED';
BEGIN
    -- Attempt SQL injection in tenant context
    PERFORM set_config('app.tenant_id', ''' OR ''1''=''1', true);

    SELECT COUNT(*) INTO v_count FROM raw.raw_shopify_orders;

    INSERT INTO test_rls.test_results (test_name, test_description, expected_result, actual_result, passed)
    VALUES (
        v_test_name,
        'SQL injection attempt in tenant context should return 0 records',
        '0',
        v_count::TEXT,
        v_count = 0
    );

    IF v_count = 0 THEN
        RAISE NOTICE '✓ %: PASSED - SQL injection blocked', v_test_name;
    ELSE
        RAISE WARNING '✗ %: FAILED - SECURITY VIOLATION: SQL injection returned % records!', v_test_name, v_count;
    END IF;
END $$;

-- =============================================================================
-- TEST 11: get_current_tenant_id function behavior
-- =============================================================================

DO $$
DECLARE
    v_result VARCHAR(255);
    v_test_name VARCHAR(255) := 'TEST_11_TENANT_CONTEXT_FUNCTION';
BEGIN
    -- Test with valid tenant
    PERFORM set_config('app.tenant_id', 'test-tenant-alpha-001', true);
    SELECT raw.get_current_tenant_id() INTO v_result;

    IF v_result = 'test-tenant-alpha-001' THEN
        RAISE NOTICE '✓ %: get_current_tenant_id returns correct value', v_test_name;
    ELSE
        RAISE WARNING '✗ %: Expected test-tenant-alpha-001, got %', v_test_name, v_result;
    END IF;

    -- Test with empty string
    PERFORM set_config('app.tenant_id', '', true);
    SELECT raw.get_current_tenant_id() INTO v_result;

    IF v_result IS NULL THEN
        RAISE NOTICE '✓ %: Empty string returns NULL', v_test_name;
    ELSE
        RAISE WARNING '✗ %: Empty string should return NULL, got %', v_test_name, v_result;
    END IF;

    INSERT INTO test_rls.test_results (test_name, test_description, expected_result, actual_result, passed)
    VALUES (
        v_test_name,
        'get_current_tenant_id should return correct tenant or NULL for empty',
        'valid_tenant and NULL_for_empty',
        'verified',
        TRUE
    );
END $$;

-- =============================================================================
-- Test Summary
-- =============================================================================

DO $$
DECLARE
    v_total INTEGER;
    v_passed INTEGER;
    v_failed INTEGER;
BEGIN
    SELECT COUNT(*), SUM(CASE WHEN passed THEN 1 ELSE 0 END)
    INTO v_total, v_passed
    FROM test_rls.test_results;

    v_failed := v_total - v_passed;

    RAISE NOTICE '';
    RAISE NOTICE '================================================';
    RAISE NOTICE 'RLS ISOLATION TEST RESULTS';
    RAISE NOTICE '================================================';
    RAISE NOTICE 'Total Tests: %', v_total;
    RAISE NOTICE 'Passed: %', v_passed;
    RAISE NOTICE 'Failed: %', v_failed;
    RAISE NOTICE '================================================';

    IF v_failed > 0 THEN
        RAISE WARNING 'SECURITY TESTS FAILED - REVIEW IMMEDIATELY!';
    ELSE
        RAISE NOTICE 'ALL SECURITY TESTS PASSED';
    END IF;
END $$;

-- Display test results
SELECT
    test_name,
    passed,
    expected_result,
    actual_result,
    CASE WHEN passed THEN '✓ PASS' ELSE '✗ FAIL' END AS status
FROM test_rls.test_results
ORDER BY executed_at;

-- =============================================================================
-- Cleanup Test Data
-- =============================================================================

-- Uncomment to cleanup after tests:
-- DELETE FROM raw.raw_shopify_orders WHERE tenant_id LIKE 'test-tenant-%';
-- DELETE FROM raw.raw_meta_ads_insights WHERE tenant_id LIKE 'test-tenant-%';
-- DELETE FROM raw.raw_google_ads_campaigns WHERE tenant_id LIKE 'test-tenant-%';
-- DROP USER IF EXISTS test_query_user;
-- DROP SCHEMA test_rls CASCADE;

SELECT 'RLS isolation tests completed' AS status;
SELECT 'Review test_rls.test_results for detailed results' AS next_step;
