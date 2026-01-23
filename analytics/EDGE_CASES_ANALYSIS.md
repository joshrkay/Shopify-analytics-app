# Edge Cases Analysis - Story 4.2 Staging Models

## Critical Issues Found

### 1. Type Conversion Failures
- **Issue**: Direct casting (`::integer`, `::numeric`) will fail on invalid values
- **Impact**: Query will crash on malformed data
- **Fix**: Add try-catch logic or validate before casting

### 2. Null Primary Keys
- **Issue**: `order_id_raw` or `customer_id_raw` could be null
- **Impact**: Violates primary key constraint, data loss
- **Fix**: Filter out null IDs or generate fallback IDs

### 3. Invalid JSON Extraction
- **Issue**: `customer_json::json` will fail if string is not valid JSON
- **Impact**: Query crashes on malformed JSON
- **Fix**: Validate JSON before casting

### 4. Tenant Isolation Vulnerability
- **Issue**: `limit 1` assigns all orders to first tenant if multiple connections exist
- **Impact**: **CRITICAL SECURITY BUG** - Cross-tenant data leakage
- **Fix**: Must properly map each record to its specific tenant

### 5. Timestamp Parsing Errors
- **Issue**: Invalid timestamp formats will cause casting errors
- **Impact**: Query fails on bad dates
- **Fix**: Add error handling for timestamp parsing

### 6. Empty String vs Null
- **Issue**: Whitespace-only strings not handled
- **Impact**: Invalid data passes through
- **Fix**: Trim whitespace before validation

### 7. Currency Code Validation
- **Issue**: No validation of currency codes
- **Impact**: Invalid currencies in data
- **Fix**: Add accepted values check

### 8. Numeric Conversion Edge Cases
- **Issue**: Scientific notation, negative values, very large numbers
- **Impact**: Data corruption or overflow
- **Fix**: Add bounds checking

### 9. GID Normalization Edge Cases
- **Issue**: Unexpected GID formats not handled
- **Impact**: IDs not normalized correctly
- **Fix**: More robust GID parsing

### 10. Boolean Conversion Edge Cases
- **Issue**: Case sensitivity, numeric booleans (0/1)
- **Impact**: Incorrect boolean values
- **Fix**: More comprehensive conversion logic
