# E2E Visual API Testing Suite

This directory contains end-to-end visual tests for verifying real API integrations
with Shopify, Meta Ads, and Google Ads.

## Purpose

These tests are designed for:
- **Manual verification** of API connections with real credentials
- **Visual inspection** of API response data via HTML reports
- **Integration validation** before deployments
- **Debugging** connectivity issues with external platforms

## Setup

### 1. Create Environment File

Copy the example environment file and fill in your credentials:

```bash
cp .env.visual.example .env.visual
```

### 2. Required Environment Variables

```bash
# Shopify API Credentials
SHOPIFY_SHOP_DOMAIN=your-store.myshopify.com
SHOPIFY_ACCESS_TOKEN=shpat_xxxxx
SHOPIFY_API_KEY=your_api_key
SHOPIFY_API_SECRET=your_api_secret

# Meta (Facebook) Ads API Credentials
META_APP_ID=your_app_id
META_APP_SECRET=your_app_secret
META_ACCESS_TOKEN=your_access_token
META_AD_ACCOUNT_ID=act_xxxxx

# Google Ads API Credentials
GOOGLE_CLIENT_ID=your_client_id
GOOGLE_CLIENT_SECRET=your_client_secret
GOOGLE_REFRESH_TOKEN=your_refresh_token
GOOGLE_DEVELOPER_TOKEN=your_developer_token
GOOGLE_CUSTOMER_ID=1234567890
```

## Running Tests

### Full Test Suite (All Platforms)

```bash
python -m src.tests.e2e.visual.run_visual_tests --all
```

### Individual Platform Tests

```bash
# Shopify only
python -m src.tests.e2e.visual.run_visual_tests --shopify

# Meta Ads only
python -m src.tests.e2e.visual.run_visual_tests --meta

# Google Ads only
python -m src.tests.e2e.visual.run_visual_tests --google
```

### Dry Run (No API Calls)

```bash
python -m src.tests.e2e.visual.run_visual_tests --dry-run
```

### Generate HTML Report Only

```bash
python -m src.tests.e2e.visual.run_visual_tests --all --output-dir ./reports
```

## Output

After running tests, an HTML report is generated at:
- `./reports/visual_test_report_YYYYMMDD_HHMMSS.html`

The report includes:
- Connection status for each API
- Sample data fetched from each platform
- Detailed error messages (if any)
- Response times and performance metrics

## Security Notes

- **NEVER commit `.env.visual` to git** - it contains sensitive credentials
- Use test/sandbox accounts when possible
- Meta and Google provide sandbox environments for testing
- Rotate credentials after testing in production

## Test Coverage

### Shopify API Tests
- Store information retrieval
- Products listing
- Orders listing
- Customers listing
- GraphQL Admin API queries

### Meta Ads API Tests
- Ad Account info
- Campaigns listing
- Ad Sets listing
- Ads listing
- Insights/metrics retrieval

### Google Ads API Tests
- Customer info
- Campaigns listing
- Ad Groups listing
- Ads listing
- Performance metrics retrieval
