# Shopify Analytics App - Implementation Plan
## Stories 4.5 - 4.9: Metrics, Attribution & Data Quality

---

## 📋 Executive Summary

This plan covers five critical data infrastructure stories:
- **4.5**: Core Business Metrics (Revenue, AOV, ROAS, CAC)
- **4.6**: Attribution Baseline (Last-click v1)
- **4.7**: Data Quality & Freshness Tests
- **4.8**: Backfills & Reprocessing
- **4.9**: CI & Regression Integration

**Estimated Timeline**: 3-4 weeks
**Complexity**: High - requires cross-functional coordination
**Dependencies**: Fact tables must exist before metric SQL can be written

---

## 🎯 Execution Order & Dependencies

### Phase 1: Foundations (Week 1)
**Stories 4.5 & 4.6** - These can be worked in parallel
- Story 4.5 establishes business metrics
- Story 4.6 establishes attribution logic
- Both are prerequisites for quality tests

### Phase 2: Protection Layer (Week 2)
**Story 4.7** - Requires metrics from 4.5 and 4.6
- Build quality checks on top of defined metrics
- Establishes baseline for "good data"

### Phase 3: Operations (Week 2-3)
**Story 4.8** - Requires all models to be stable
- Safe reprocessing depends on quality tests from 4.7

### Phase 4: Automation (Week 3-4)
**Story 4.9** - Final integration layer
- Enforces all previous policies automatically

---

## 📖 STORY 4.5 – Core Business Metrics

### 🧠 Human Decisions Required (BLOCKING)

#### 1. Metric Ownership
**Questions to answer:**
- Who is the single owner for each metric (Revenue, AOV, ROAS, CAC)?
- What is the approval process for metric changes?
  - Single approver vs. committee?
  - Async Slack approval vs. formal meeting?
  - Do changes require data/engineering + business signoff?

**Recommendation**:
- Owner: Head of Analytics or Product Manager
- Process: PR review required + Slack approval in #analytics channel for changes affecting historical data

---

#### 2. Revenue Definition
**Questions to answer:**
- Does Revenue include taxes? (Yes/No)
- Does Revenue include shipping? (Yes/No)
- How are refunds handled?
  - Subtract from original order date?
  - Record as separate negative transaction on refund date?
  - Net revenue only (refunds already subtracted)?
- How are partial refunds handled?
- Are discounts subtracted before or after revenue is recorded?
  - Gross revenue (before discounts)?
  - Net revenue (after discounts)?
- Do we include pending/unfulfilled orders?

**Recommendation**:
```
Revenue = Gross merchandise value
        - Refunds (allocated to original order date)
        - Discounts
        + Shipping fees
        + Taxes (if market requires)

Only include: completed orders (paid status)
Exclude: cancelled, pending, draft orders
```

---

#### 3. AOV (Average Order Value) Definition
**Questions to answer:**
- Is AOV calculated as:
  - `Total Revenue / Number of Orders`?
  - `Total Revenue / Number of Customers`?
- Do we use the same revenue definition as above?
- Do we exclude outliers (e.g., orders > $10,000)?
- Is this per-customer first order AOV or all orders?

**Recommendation**:
```
AOV = Total Revenue / Total Orders
Where Revenue follows definition above
No outlier exclusion (report median separately if needed)
```

---

#### 4. ROAS (Return on Ad Spend) Definition
**Questions to answer:**
- Numerator: What revenue counts?
  - Only attributed sales?
  - All sales in attribution window?
  - Gross or net revenue?
- Denominator: What spend counts?
  - Only paid media (Meta, Google)?
  - Include organic spend (content, SEO)?
  - Include agency fees?
- Attribution window: 7-day? 28-day? Click only or view-through?
- How do we handle ROAS when spend = 0?

**Recommendation**:
```
ROAS = Attributed Revenue / Paid Media Spend
Where:
  - Attributed Revenue = last-click attributed orders (Story 4.6)
  - Paid Media Spend = Meta Ads + Google Ads (actual spend from platform APIs)
  - Attribution window = 7-day click
  - If spend = 0, ROAS = NULL (not infinity or 0)
```

---

#### 5. CAC (Customer Acquisition Cost) Definition
**Questions to answer:**
- Is this:
  - First-order CAC: `Spend / New Customers`?
  - Blended CAC: `Spend / All Customers`?
- Do we include only paid channel spend or all marketing spend?
- How do we define "new customer"?
  - First order ever?
  - First order in time period?
- Do we include customers with $0 orders?

**Recommendation**:
```
CAC = Total Paid Media Spend / New Customers Acquired
Where:
  - New Customer = first order ever (email or customer_id based)
  - Paid Media Spend = Meta + Google (same as ROAS denominator)
  - Exclude customers with cancelled/refunded first orders
```

---

#### 6. Discrepancy Policy
**Questions to answer:**
- When Shopify revenue ≠ Meta reported revenue ≠ Google reported revenue:
  - Which is the "source of truth"?
  - Do we show all three?
  - Do we explain the variance?
- What language do we use?
  - "Shopify is more accurate because..."?
  - "These platforms use different attribution..."?
  - "Expect 10-20% variance due to..."?

**Recommendation**:
```
Source of Truth Hierarchy:
1. Shopify = financial truth (actual money received)
2. Meta/Google = marketing attribution (directional guidance)

User Communication:
"Shopify shows actual revenue received. Meta and Google show
revenue they attribute to their platforms using their own
tracking. Differences are normal due to:
  - Different attribution windows
  - Cross-device limitations
  - Ad blocker impacts

Use Shopify for financial reporting and Meta/Google for
marketing optimization."
```

---

#### 7. Metric Stability Rules
**Questions to answer:**
- Can metrics change retroactively?
  - Never?
  - Only for bug fixes?
  - Only with approval?
- If changes happen, how are they communicated?
  - Email to all users?
  - Banner in app?
  - Changelog only?
- Do we version metrics (v1, v2)?
- Do we show "last updated" timestamps?

**Recommendation**:
```
Metric Change Policy:
- Bug fixes: Can update retroactively (with changelog entry)
- Definition changes: Create new metric version (Revenue_v2)
- Data corrections: Allowed with approval + user notification

Communication:
- All changes logged in CHANGELOG.md
- Breaking changes: in-app banner for 7 days
- Non-breaking: changelog only
```

---

### 🤖 AI-Executable Tasks

Once human decisions above are finalized:

1. **Create dbt metric models** (`models/marts/metrics/`)
   - `fct_revenue.sql`
   - `fct_aov.sql`
   - `fct_roas.sql`
   - `fct_cac.sql`

2. **Create metric documentation**
   - `models/marts/metrics/schema.yml`
   - Document each metric with plain-English definition
   - Include calculation logic, exclusions, edge cases

3. **Write dbt tests**
   - Revenue is never negative (warn only - refunds may cause this)
   - AOV is > $0
   - ROAS is NULL or >= 0
   - CAC is NULL or > 0
   - All metrics have no unexpected NULLs

4. **Create seed file for test data**
   - `seeds/test_orders.csv` with edge cases:
     - Refunded order
     - Partially refunded order
     - Order with $0 discount
     - Order with 100% discount
     - Multi-item order
     - Single-item order

---

### ✅ Human Validation Checklist

- [ ] Run metrics against production data sample
- [ ] Compare calculated Revenue to Shopify admin's reported revenue
- [ ] Check AOV "feels right" (compare to historical GA data)
- [ ] Validate ROAS against Meta Ads Manager
- [ ] Test edge cases:
  - [ ] Order placed yesterday, refunded today
  - [ ] Order spanning month boundary
  - [ ] Order with partial refund
  - [ ] Multiple orders from same customer (CAC should only count once)
- [ ] Review metric definitions with merchant stakeholders
- [ ] Confirm timezone handling (UTC vs. store timezone)

---

## 🎯 STORY 4.6 – Attribution Baseline (v1)

### 🧠 Human Decisions Required (BLOCKING)

#### 1. Attribution Philosophy
**Questions to answer:**
- Why are we starting with last-click?
  - Simplicity?
  - Industry standard?
  - Data availability?
- What's the future roadmap?
  - First-click next?
  - Multi-touch later?
  - Data-driven attribution eventually?
- How do we communicate limitations to users?

**Recommendation**:
```
Philosophy: "Start simple, evolve with data"

Last-click chosen because:
1. Simplest to explain and debug
2. Matches platform defaults (Meta/Google)
3. Sufficient for early-stage brands
4. Deterministic (reproducible results)

Future evolution:
- Phase 2: Add first-click view
- Phase 3: Add linear multi-touch
- Phase 4: Explore ML-based attribution (if scale justifies)

User communication:
"We use last-click attribution, meaning the most recent ad
click before purchase gets credit. This matches how Meta and
Google report by default."
```

---

#### 2. UTM Trust Rules
**Questions to answer:**
- Which UTM parameters are required?
  - utm_source only?
  - utm_source + utm_medium?
  - All five (source, medium, campaign, term, content)?
- What happens when UTMs are missing?
  - Attribute to "Direct"?
  - Attribute to "Unknown"?
  - Try to infer from referrer?
- Do we trust all UTMs or validate against known campaigns?
- How do we handle malformed UTMs (spaces, special characters)?

**Recommendation**:
```
Required UTMs:
- utm_source (mandatory)
- utm_medium (mandatory)
- utm_campaign (optional but recommended)

Fallback logic:
1. If utm_source + utm_medium exist: use them
2. Else if referrer exists: parse domain
   - google.com → source: google, medium: organic
   - facebook.com → source: facebook, medium: social
3. Else: source: direct, medium: none

Validation:
- Allow all UTM values (no whitelist)
- Normalize to lowercase
- Trim whitespace
- Log malformed UTMs for review (don't fail)
```

---

#### 3. Edge Cases
**Questions to answer:**

**Multi-touch journeys:**
- Customer clicks Meta ad Monday, Google ad Wednesday, purchases Thursday
  - Which gets credit? (Last click = Google)
  - Do we show the journey somewhere?

**Cross-device behavior:**
- Customer clicks ad on mobile, purchases on desktop
  - Can we connect them? (Only if logged in or same IP + timing heuristic)
  - Otherwise attribute to direct?

**Organic vs Paid overlap:**
- Customer clicks paid Google ad, then searches brand name and clicks organic result
  - Which gets credit? (Last click = organic)
  - Is this a "problem"?

**Recommendation**:
```
Multi-touch:
- Last click wins (per definition)
- Log full journey in separate table for future analysis
- Don't show journey to users in v1 (too complex)

Cross-device:
- Only connect if customer_id available (logged in)
- Otherwise treat as separate sessions
- Document limitation in help docs

Organic vs Paid:
- Last click wins (even if organic after paid)
- This is a known limitation of last-click
- Acceptable for v1 since it's consistent
```

---

#### 4. Expectation Management
**Questions to answer:**
- How do we explain attribution in the UI?
- Do we show disclaimers?
- Where do we link to help docs?
- What do we say when attribution is "Unknown"?

**Recommendation**:
```
UI Help Text:
"This dashboard uses last-click attribution within a 7-day
window. The traffic source of the last ad click before
purchase receives credit for the sale."

Disclaimers (footer or tooltip):
"Attribution is directional and may not match platform
reports due to differences in tracking and attribution
windows."

Unknown Attribution:
"Some orders cannot be attributed to a specific source due
to missing tracking data or ad blocker usage. These are
labeled as 'Direct / None'."
```

---

### 🤖 AI-Executable Tasks

Once human decisions above are finalized:

1. **Create attribution SQL models**
   - `models/marts/attribution/fct_attributed_orders.sql`
   - Join orders to session/click tracking data
   - Implement last-click logic with 7-day window
   - Handle missing UTMs per fallback rules

2. **Create attribution tests**
   - Test deterministic scenarios:
     - Single click → order (should attribute)
     - Multiple clicks → order (last wins)
     - Old click (8 days) → order (direct)
     - No click → order (direct)
   - Use dbt seed data for reproducibility

3. **Create attribution documentation**
   - Document logic in `schema.yml`
   - Add examples to help docs

---

### ✅ Human Validation Checklist

- [ ] Run attribution on 100 real orders
- [ ] Manually verify 10 attributed orders (check against GA4/Shopify)
- [ ] Check attribution breakdown matches expectations:
  - [ ] Meta roughly X% of orders?
  - [ ] Google roughly Y% of orders?
  - [ ] Direct roughly Z% of orders?
- [ ] Test rerun stability (same input = same output)
- [ ] Verify attribution explainability:
  - [ ] Can you explain to a merchant why order X was attributed to source Y?
- [ ] Confirm edge case handling:
  - [ ] Multi-click journey
  - [ ] Missing UTMs
  - [ ] Organic after paid

---

## 🛡️ STORY 4.7 – Data Quality & Freshness Tests

### 🧠 Human Decisions Required (BLOCKING)

#### 1. Define "Bad Data"
**Questions to answer:**
- Which failures should block deployment?
  - Critical: Revenue calculation broken?
  - Critical: Customer PII exposed?
  - Warning: One merchant's data is 2 hours stale?
- Which failures are warnings only?
  - Informational: Unusual spike in orders?
  - Informational: New UTM parameter seen?

**Recommendation**:
```
BLOCKING (fail CI/CD):
- Revenue metric returns negative total
- Customer PII in wrong table
- Duplicate order_ids in fact table
- Required fields are >10% NULL
- Data freshness >24 hours old

WARNING (alert but don't block):
- Order volume >2x daily average
- New traffic source not in taxonomy
- AOV outside 2 standard deviations
- Attribution rate <50% (too much "direct")
```

---

#### 2. Threshold Tuning
**Questions to answer:**
- Freshness SLAs:
  - How old can data be before it's a problem?
  - 1 hour? 6 hours? 24 hours?
  - Different for orders vs. ad spend?
- Volume anomaly thresholds:
  - What % change is suspicious?
  - Day-over-day >50% = alert?
  - Week-over-week >100% = alert?
- Null rate thresholds:
  - What % NULLs is acceptable?
  - 5%? 10%? 20%?

**Recommendation**:
```
Freshness SLAs:
- Orders: Max 1 hour stale (Shopify webhook should be real-time)
- Ad Spend: Max 6 hours stale (API sync runs every 4 hours)
- Sessions: Max 2 hours stale (clickstream buffer)

Anomaly Thresholds:
- Order volume day-over-day >3x = alert
- Revenue day-over-day >5x = alert
- Ad spend day-over-day >2x = alert (could be intentional campaign)

NULL Thresholds:
- order_id: 0% NULLs allowed (block)
- customer_email: <5% NULLs (warn if higher)
- utm_source: <50% NULLs (expected for direct traffic)
```

---

#### 3. Incident Response
**Questions to answer:**
- Who gets alerted?
  - Slack channel?
  - PagerDuty?
  - Email?
- What's the expected response time?
  - Immediate? Within 1 hour? Next business day?
- Who is on-call?
- What's the escalation path?

**Recommendation**:
```
Alert Routing:
- Blocking failures → #analytics-incidents (urgent)
- Warning failures → #analytics-monitoring (review daily)
- Info messages → Logs only

Response SLAs:
- Blocking failures: 30-minute response, 2-hour fix
- Warning failures: Same-day review
- Info messages: Weekly review

On-call Rotation:
- Analytics Engineer (primary)
- Data Engineer (backup)
- Engineering Manager (escalation)

PagerDuty integration for after-hours blocking failures
```

---

### 🤖 AI-Executable Tasks

Once human decisions above are finalized:

1. **Create dbt freshness tests**
   - `models/staging/sources.yml`
   - Configure freshness for each source table
   - Set warn_after and error_after thresholds

2. **Create dbt data tests**
   - Schema tests (not null, unique, relationships)
   - Custom tests for business logic:
     - `tests/assert_revenue_positive.sql`
     - `tests/assert_no_duplicate_orders.sql`
     - `tests/assert_attribution_rate_reasonable.sql`

3. **Create anomaly detection macros**
   - `macros/test_volume_anomaly.sql`
   - Compare current day to trailing 7-day average
   - Flag if >3 standard deviations

4. **Configure dbt-checkpoint pre-commit hooks**
   - Block commits if model has no tests
   - Block commits if documentation missing

---

### ✅ Human Validation Checklist

- [ ] Simulate data failures:
  - [ ] Set orders table to 3 hours stale → should alert
  - [ ] Insert duplicate order_id → should block
  - [ ] Set revenue to negative → should block
- [ ] Confirm alert delivery:
  - [ ] Slack message received in correct channel
  - [ ] PagerDuty triggered for blocking failure
- [ ] Confirm CI behavior:
  - [ ] PR with test failure is blocked from merge
  - [ ] Warning allows merge but shows notice
- [ ] Test alert fatigue:
  - [ ] Are we getting too many warnings?
  - [ ] Tune thresholds if needed

---

## 🔄 STORY 4.8 – Backfills & Reprocessing

### 🧠 Human Decisions Required (BLOCKING)

#### 1. Backfill Policy
**Questions to answer:**
- Who can trigger backfills?
  - Engineers only?
  - Analysts with approval?
  - Automated system?
- Which environments allow backfills?
  - Production? Staging? Dev?
- Maximum date range?
  - 7 days? 30 days? All-time?
  - Different limits for different models?
- Approval required?
  - Always? Only for production? Only for >30 days?

**Recommendation**:
```
Authorization:
- Engineers: Can backfill any range in any environment
- Analysts: Can backfill ≤7 days in staging (request engineer for production)
- Automated: Never (all backfills are manual for v1)

Environment Rules:
- Development: No restrictions
- Staging: ≤90 days
- Production: ≤30 days (require manager approval for >30 days)

Approval Process:
- ≤7 days: Slack message in #analytics with reason
- 8-30 days: Slack + manager approval
- >30 days: Slack + manager + incident review
```

---

#### 2. Risk Mitigation
**Questions to answer:**
- Do we lock reporting during backfills?
  - Show "maintenance mode" banner?
  - Block dashboard loads?
  - Allow read but show warning?
- Do we notify users?
  - Email all users?
  - In-app banner?
  - No notification (silent)?
- Do we snapshot current state before backfill?
- How do we rollback if backfill corrupts data?

**Recommendation**:
```
During Backfill:
- No read lock (users can still view dashboards)
- Show banner: "Data is being reprocessed. Metrics may be
  temporarily inconsistent."
- Disable scheduled refreshes during backfill

User Notification:
- In-app banner only (no email for <7 day backfills)
- Email notification for >7 day backfills

Safety Measures:
- Snapshot current metrics table before backfill
- Backfill writes to temporary table first
- Run quality tests on temp table
- Swap temp → production only if tests pass
- Keep snapshot for 7 days for rollback
```

---

#### 3. Audit Requirements
**Questions to answer:**
- What metadata is logged?
  - Who triggered?
  - When?
  - Date range?
  - Reason?
  - Success/failure?
- Where is it logged?
  - Database table?
  - Spreadsheet?
  - Git commit?
- How long do we retain logs?
- Who can access logs?

**Recommendation**:
```
Audit Log Fields:
- backfill_id (UUID)
- triggered_by (email)
- triggered_at (timestamp)
- date_range_start
- date_range_end
- models_affected (array)
- reason (text)
- approved_by (email, if applicable)
- status (running|completed|failed)
- rows_affected
- duration_seconds

Storage:
- Database table: `audit.backfills`
- Also log to Slack #analytics-audit (immutable record)

Retention:
- Keep forever (disk is cheap, audits are important)

Access:
- All engineers and analysts can read
- Only engineers can write
```

---

### 🤖 AI-Executable Tasks

Once human decisions above are finalized:

1. **Create dbt backfill macro**
   - `macros/backfill.sql`
   - Parameters: `start_date`, `end_date`, `models`, `reason`
   - Validates date range
   - Creates snapshot
   - Runs specified models
   - Logs to audit table

2. **Create audit schema and table**
   - `models/audit/backfills.sql`
   - Immutable (append-only)

3. **Create backfill documentation**
   - `docs/runbooks/backfill_process.md`
   - Step-by-step instructions
   - Examples
   - Rollback procedure

4. **Create safety checks**
   - Prevent backfill if another backfill is running
   - Prevent backfill beyond max date range
   - Require reason (non-empty string)

---

### ✅ Human Validation Checklist

- [ ] Run controlled backfill in staging:
  - [ ] Backfill last 3 days of orders
  - [ ] Verify metrics update correctly
  - [ ] Check audit log created
  - [ ] Confirm snapshot saved
- [ ] Test failure scenario:
  - [ ] Introduce error in backfill SQL
  - [ ] Confirm rollback works
  - [ ] Verify production data unchanged
- [ ] Test tenant isolation:
  - [ ] Backfill merchant A's data
  - [ ] Verify merchant B's data unchanged
- [ ] Validate notification:
  - [ ] Banner shows during backfill
  - [ ] Banner disappears after completion
- [ ] Check performance:
  - [ ] 7-day backfill completes in <10 minutes?

---

## 🤖 STORY 4.9 – CI & Regression Integration

### 🧠 Human Decisions Required (BLOCKING)

#### 1. CI Policy
**Questions to answer:**
- Which tests are blocking?
  - All dbt tests?
  - Only schema tests (unique, not_null)?
  - Only custom tests?
  - Depends on severity tag?
- When are overrides allowed?
  - Never?
  - With manager approval?
  - In emergencies?
- What about test performance?
  - If tests take >10 minutes, do we fail CI?
  - Do we run all tests or sample?

**Recommendation**:
```
Blocking Tests:
- All tests tagged with severity: error
- All schema tests (unique, not_null, relationships)
- All freshness tests (error_after threshold)

Warning Tests (don't block but require acknowledgment):
- Tests tagged with severity: warn
- Anomaly detection tests

Override Policy:
- Overrides allowed only for warn-level tests
- Must document reason in PR
- Must create follow-up issue to fix root cause

Performance:
- CI timeout: 15 minutes
- If tests exceed 12 minutes, flag for optimization
- Don't sample tests (always run full suite)
```

---

#### 2. Ownership
**Questions to answer:**
- Who fixes broken dbt builds?
  - Person who committed the breaking change?
  - On-call engineer?
  - Team lead?
- What's the SLA for fixes?
  - Immediate? Same day? 48 hours?
- What happens if fix is not quick?
  - Revert the PR?
  - Hotfix?
- Who is notified when build breaks?
  - Just the committer?
  - Whole team?

**Recommendation**:
```
Ownership:
- Committer owns the fix (primary)
- On-call engineer assists (secondary)
- If both unavailable, team lead assigns owner

SLA:
- Blocking failures: Fix within 2 hours or revert
- Warning failures: Fix within 1 business day

Notification:
- Slack #analytics-builds (all failures)
- Tag @committer in thread
- Escalate to @team after 1 hour if no response

Revert Policy:
- Auto-revert if no response within 2 hours
- Committer can re-commit after fix
```

---

#### 3. Change Management
**Questions to answer:**
- PR review requirements:
  - 1 approval? 2 approvals?
  - Any engineer? Specific codeowner?
  - Require approval from analyst if metric changes?
- Changelog requirements:
  - Required for all PRs?
  - Only for user-facing changes?
  - What format (Keep a Changelog? Custom)?
- Documentation requirements:
  - Update schema.yml required?
  - Update README required?
  - Update help docs required?

**Recommendation**:
```
PR Review:
- 1 approval required (any engineer)
- 2 approvals if:
  - Changes to metric definitions
  - Changes to attribution logic
  - Changes to >10 models
- Codeowners: Analytics team for /models/marts/

Changelog:
- Required for all PRs that change:
  - Metric definitions
  - Attribution logic
  - User-facing values
- Not required for:
  - Performance improvements
  - Refactors with no behavior change
- Format: Keep a Changelog (Added, Changed, Fixed, Removed)

Documentation:
- schema.yml must be updated if model changes
- README updated if new model added
- Help docs updated if user-facing change
- CI checks for missing docs
```

---

### 🤖 AI-Executable Tasks

Once human decisions above are finalized:

1. **Create GitHub Actions workflow**
   - `.github/workflows/dbt_ci.yml`
   - Triggers on PR to main
   - Steps:
     - Checkout code
     - Setup Python + dbt
     - Run `dbt deps`
     - Run `dbt build --select state:modified+` (only changed models)
     - Run `dbt test`
     - Post results as PR comment

2. **Create pre-commit hooks**
   - `.pre-commit-config.yaml`
   - Hooks:
     - `dbt-checkpoint` (check for missing tests/docs)
     - `sqlfluff` (SQL linting)
     - `yamllint` (YAML validation)

3. **Create failure notification**
   - Slack webhook integration
   - Post to #analytics-builds on failure
   - Include:
     - PR link
     - Failed test name
     - Error message
     - Tag committer

4. **Create dbt slim CI config**
   - Use `state:modified` to only test changed models
   - Speeds up CI significantly
   - Still runs downstream dependencies

5. **Create CODEOWNERS file**
   - `.github/CODEOWNERS`
   - Automatically request review from analytics team

---

### ✅ Human Validation Checklist

- [ ] Break a model intentionally:
  - [ ] Add a syntax error to a SQL file
  - [ ] Push to PR
  - [ ] Confirm CI fails
  - [ ] Confirm Slack notification sent
  - [ ] Confirm PR is blocked from merge
- [ ] Test error message clarity:
  - [ ] Can you understand what's wrong from CI output?
  - [ ] Is the fix obvious?
- [ ] Test override flow:
  - [ ] Create a warn-level test failure
  - [ ] Confirm PR can still merge
  - [ ] Confirm warning is visible
- [ ] Test performance:
  - [ ] Measure CI run time
  - [ ] <5 minutes for small PRs?
  - [ ] <15 minutes for large refactors?
- [ ] Validate state-based testing:
  - [ ] Change one model
  - [ ] Confirm only that model + downstream tests run
  - [ ] Confirm upstream models not tested

---

## 🗂️ Implementation Checklist

### Pre-work (Before Starting Any Story)
- [ ] Fact tables exist (orders, sessions, customers, ad_spend)
- [ ] Development environment configured
- [ ] Access to Shopify, Meta, Google APIs
- [ ] dbt project initialized
- [ ] Git repo with branch protection rules

### Story 4.5: Core Metrics
- [ ] **Human decisions documented** (Sections 1-7 above)
- [ ] Metric owners assigned
- [ ] Revenue definition finalized
- [ ] AOV definition finalized
- [ ] ROAS definition finalized
- [ ] CAC definition finalized
- [ ] Discrepancy policy documented
- [ ] Metric stability rules documented
- [ ] **AI execution complete**
- [ ] Metric SQL models created
- [ ] Metric documentation written
- [ ] dbt tests written
- [ ] Test seed data created
- [ ] **Human validation complete**
- [ ] Metrics tested against production data
- [ ] Edge cases validated
- [ ] Stakeholder approval received

### Story 4.6: Attribution
- [ ] **Human decisions documented** (Sections 1-4 above)
- [ ] Attribution philosophy documented
- [ ] UTM trust rules defined
- [ ] Edge case handling defined
- [ ] User communication strategy defined
- [ ] **AI execution complete**
- [ ] Attribution SQL models created
- [ ] Attribution tests written
- [ ] Attribution documentation written
- [ ] **Human validation complete**
- [ ] Attribution tested on real orders
- [ ] Rerun stability confirmed
- [ ] Explainability validated

### Story 4.7: Data Quality
- [ ] **Human decisions documented** (Sections 1-3 above)
- [ ] "Bad data" definition documented
- [ ] Thresholds tuned
- [ ] Incident response process defined
- [ ] **AI execution complete**
- [ ] Freshness tests configured
- [ ] Data tests written
- [ ] Anomaly detection macros created
- [ ] Pre-commit hooks configured
- [ ] **Human validation complete**
- [ ] Data failures simulated
- [ ] Alert delivery confirmed
- [ ] CI blocking behavior validated

### Story 4.8: Backfills
- [ ] **Human decisions documented** (Sections 1-3 above)
- [ ] Backfill policy documented
- [ ] Risk mitigation plan defined
- [ ] Audit requirements defined
- [ ] **AI execution complete**
- [ ] Backfill macro created
- [ ] Audit table created
- [ ] Backfill documentation written
- [ ] Safety checks implemented
- [ ] **Human validation complete**
- [ ] Controlled backfill tested
- [ ] Rollback procedure validated
- [ ] Tenant isolation confirmed

### Story 4.9: CI Integration
- [ ] **Human decisions documented** (Sections 1-3 above)
- [ ] CI policy documented
- [ ] Ownership and SLAs defined
- [ ] Change management rules defined
- [ ] **AI execution complete**
- [ ] GitHub Actions workflow created
- [ ] Pre-commit hooks configured
- [ ] Slack notifications configured
- [ ] CODEOWNERS file created
- [ ] **Human validation complete**
- [ ] Intentional failure tested
- [ ] Error messages validated
- [ ] Override flow tested
- [ ] CI performance measured

---

## 🚨 Critical Risks & Mitigations

### Risk 1: Metric Definition Disagreements
**Impact**: High - Could block entire project
**Mitigation**:
- Schedule dedicated 2-hour workshop with all stakeholders
- Use real data examples to drive consensus
- Document all decisions in writing with sign-off
- Create comparison report showing implications of different definitions

### Risk 2: Attribution Accuracy Concerns
**Impact**: Medium - Users may not trust the data
**Mitigation**:
- Set clear expectations about limitations upfront
- Provide comparison view (Shopify vs. Meta vs. Google)
- Over-document the logic
- Offer "debug mode" to see attribution logic for any order

### Risk 3: Test Performance Degradation
**Impact**: Medium - Slow CI kills developer productivity
**Mitigation**:
- Use dbt slim CI (state-based testing)
- Profile slow tests and optimize
- Consider parallel test execution
- Set hard timeout at 15 minutes

### Risk 4: Backfill Causes Data Corruption
**Impact**: High - Could destroy trust in entire platform
**Mitigation**:
- Always snapshot before backfill
- Always backfill to temp table first
- Always run quality tests before swap
- Keep snapshots for 7+ days
- Practice rollback procedure quarterly

### Risk 5: Alert Fatigue
**Impact**: Medium - Real issues get ignored
**Mitigation**:
- Start with conservative thresholds
- Review alerts weekly and tune
- Separate channels for urgent vs. informational
- Auto-resolve alerts after fix

---

## 📊 Success Metrics

### Story 4.5: Core Metrics
- [ ] All 4 metrics (Revenue, AOV, ROAS, CAC) running in production
- [ ] <5% variance between Shopify admin and our calculated revenue
- [ ] Zero metric definition questions in support for first 30 days
- [ ] 100% test coverage on metric models

### Story 4.6: Attribution
- [ ] Attribution rate >50% (less than half of orders are "direct")
- [ ] Zero "how is this attributed?" support questions
- [ ] 100% reproducibility (same input = same output)
- [ ] Attribution runs in <5 minutes for 10K orders

### Story 4.7: Data Quality
- [ ] Zero production incidents caused by bad data in first 60 days
- [ ] All quality tests run in <10 minutes
- [ ] <3 false-positive alerts per week
- [ ] 100% of blocking failures caught before reaching production

### Story 4.8: Backfills
- [ ] Zero backfill-related incidents
- [ ] 100% of backfills logged in audit table
- [ ] All backfills complete within expected time (7 days in <10 min)
- [ ] Zero unauthorized backfills

### Story 4.9: CI Integration
- [ ] Zero breaking changes merged to main
- [ ] PR cycle time <1 day (including CI)
- [ ] CI test time <5 minutes for 80% of PRs
- [ ] 100% of PRs have required approvals

---

## 🎯 Next Steps

1. **Schedule human decision workshops** (Week 1)
   - Story 4.5: Metric definitions workshop (2 hours)
   - Story 4.6: Attribution philosophy workshop (1 hour)
   - Story 4.7-4.9: Operations and governance workshop (1 hour)

2. **Complete human decisions** (Week 1)
   - Use this document as the agenda
   - Document all answers in decision log
   - Get stakeholder sign-off

3. **Execute AI tasks** (Week 2-3)
   - Work through stories sequentially (4.5 → 4.6 → 4.7 → 4.8 → 4.9)
   - Use this document as the implementation guide
   - Run human validation after each story

4. **Production deployment** (Week 4)
   - Deploy to staging first
   - Run for 3 days
   - Deploy to production
   - Monitor closely for first week

---

## 📞 Questions & Clarifications Needed

Before I proceed with execution, I need you to review and decide on these critical items:

### Immediate Blockers:
1. **Metric Ownership**: Who owns each metric? Who approves changes?
2. **Revenue Definition**: Do we include taxes? How do we handle refunds?
3. **Attribution Window**: Confirming 7-day click window for v1?
4. **CI Blocking**: Which test failures should block deployment?

### Can Be Decided During Execution:
5. **Alert Thresholds**: Can tune these based on data
6. **Backfill Limits**: Can start conservative and expand
7. **Changelog Format**: Can standardize as we go

---

**This plan is ready for your review. Once you've made decisions on the human decision sections, I can execute the AI-codable portions.**

Would you like me to:
1. Create a separate decision log document for tracking answers?
2. Create workshop agendas for the decision sessions?
3. Start executing any non-blocking tasks while you review?