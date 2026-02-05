{#
    Test: Schema Drift Guard

    Singular dbt test that validates ALL governed staging models have only
    approved columns. Fails if any model contains a column not present in
    its source allowlist under governance/approved_columns_*.yml.

    When this test fails, the output will show:
      - model_name:        which model has the unapproved column
      - unapproved_column: the column name that is not in the allowlist
      - allowlist_file:    which YAML file to update
      - error_message:     human-readable instruction

    To fix a failure:
      1. Open the allowlist file shown in allowlist_file
      2. Add the column name under the correct model key
      3. Commit and open a PR for review
      4. Re-run: dbt test -s test_schema_drift_guard
#}

-- Shopify models
{{ assert_columns_approved('stg_shopify_orders', 'shopify') }}
union all
{{ assert_columns_approved('stg_shopify_customers', 'shopify') }}

union all
-- Facebook / Meta Ads
{{ assert_columns_approved('stg_meta_ads', 'facebook') }}

union all
-- Google Ads
{{ assert_columns_approved('stg_google_ads', 'google') }}

union all
-- TikTok Ads
{{ assert_columns_approved('stg_tiktok_ads', 'tiktok') }}

union all
-- Email: Klaviyo Events
{{ assert_columns_approved('stg_klaviyo_events', 'email') }}
union all
-- Email: Klaviyo Campaigns
{{ assert_columns_approved('stg_klaviyo_campaigns', 'email') }}
union all
-- Email: Shopify Email Events
{{ assert_columns_approved('stg_shopify_email_events', 'email') }}
