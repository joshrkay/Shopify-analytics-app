# MarkInsight / Signals AI — Marketing Feature Summary

**Audience:** Marketing team
**Purpose:** Overview of every feature built, what it does, and who it's for
**Last updated:** March 2026

---

## What Is MarkInsight?

MarkInsight (also branded as Signals AI) is an AI-powered analytics and marketing intelligence platform embedded directly inside Shopify Admin. It gives Shopify merchants and agencies a single place to see all their marketing performance data, understand what's working, act on AI-generated recommendations, and build custom reports — without leaving Shopify.

**Who it's for:**
- **Solo Shopify merchants** who run ads on Google, Meta, TikTok, and other platforms and want to know what's actually driving revenue
- **Marketing teams** who need customizable dashboards and attribution data without paying for a separate BI tool
- **Agencies** managing multiple Shopify stores who need to switch between clients, oversee campaigns, and approve AI-driven actions

---

## Feature Areas

### 1. Analytics Overview Dashboard

The home screen gives merchants an instant snapshot of their marketing health.

**What merchants see:**
- **Revenue, Ad Spend, ROAS, and Conversions** — the four numbers that matter most, with trend arrows vs. the prior period
- **Revenue & Spend Trends** — an area chart showing daily performance over the selected timeframe
- **Channel Comparison** — side-by-side bar chart of revenue vs. spend for every connected ad platform
- **Detailed Channel Table** — one row per platform with Spend, Revenue, ROAS, Conversions, CTR, CPC, and Conversion Rate
- **Timeframe selector** — Last 7 days, This week, Last 30 days, This month, Last 90 days, This quarter

**Supported channels:** Google Ads, Facebook Ads, Instagram Ads, TikTok Ads, Pinterest Ads, Twitter/X Ads, Organic

---

### 2. Channel Deep-Dive Pages

Clicking into any channel opens a dedicated analytics page for that platform.

**What's inside:**
- Per-channel KPI cards: Revenue, Spend, ROAS, Orders, Clicks, CTR, Conversion Rate
- Daily revenue trend for that channel
- Top products driving revenue from that channel
- Same timeframe selector as the overview

**Use case:** A merchant running both Google Shopping and Meta Dynamic Ads can compare daily trends side-by-side and identify which platform is pulling its weight.

---

### 3. Attribution Dashboard (UTM Last-Click)

Shows which campaigns and channels deserve credit for actual Shopify orders.

**Key metrics:**
- **Attribution Rate** — what percentage of orders are linked to a marketing touchpoint
- **Attributed Revenue** — total revenue from attributed orders
- **Campaign count** — how many campaigns are actively driving conversions
- **Cross-channel ROAS comparison** — bar chart comparing return across platforms
- **Top Campaigns table** — ranked by attributed revenue and orders
- **Attributed Orders table** — every order with UTM Source, Medium, and Campaign filled in

**Use case:** Stop guessing which campaigns converted. See the full list of orders tagged to specific UTM parameters, with platform color-coding for quick identification.

---

### 4. Cohort Analysis

Tracks customer retention over time by grouping customers by when they first purchased.

**What merchants get:**
- **Retention heatmap** — color-coded grid showing what % of each acquisition cohort returned in months 1, 2, 3, etc.
- **Cohort groupings** by acquisition period
- **Multiple timeframe views** — 3, 6, or 12 months
- **Retention percentages** calculated automatically across all cohorts

**Use case:** A merchant running a loyalty campaign can see whether customers acquired during a promotion retained at a higher rate than organic customers — and by exactly how much.

---

### 5. Orders View with UTM Overlay

A paginated list of all Shopify orders with marketing attribution data layered on top.

**Columns:** Order Number, Date, Revenue, UTM Source, Campaign, Platform, Order Status
**Status types:** Paid, Pending, Refunded, Partially Refunded, Voided
**Pagination:** 50 orders per page
**Filtering:** 7 / 30 / 90-day timeframes

**Use case:** Verify attribution quality and audit which orders are tagged to campaigns vs. coming in unattributed.

---

### 6. AI Insights Feed

The platform continuously monitors marketing data and surfaces important findings automatically — no manual digging required.

**Types of insights generated:**
- Spend anomaly detected (e.g., daily spend jumped 40% overnight)
- ROAS change (e.g., Google Shopping ROAS dropped from 4.2x to 2.1x)
- CTR change (e.g., Meta ad CTR is trending down week-over-week)
- CPC change (e.g., cost-per-click on TikTok increased 25%)
- Conversion rate shift
- Budget pacing alert
- Performance trend (sustained improvement or decline)

**Insight attributes:** severity (Critical / Warning / Info), confidence score, estimated dollar impact

**How it works:** Insights appear in a feed. Merchants can mark them as read, dismiss them, or click through to see related recommendations. A separate "Dismissed" tab keeps a history.

**Available on:** Growth plan and above

---

### 7. AI Recommendations

For every insight, the AI generates concrete, actionable recommendations — things to actually do about what it detected.

**Types of recommendations:**
- Reduce budget on underperforming campaigns
- Scale spend on high-ROAS campaigns
- Pause campaigns with negative ROI
- Adjust bidding strategies
- Reallocate budget between platforms
- Improve audience targeting
- Review creative performance

**Each recommendation includes:**
- **Priority:** Low / Medium / High
- **Risk level:** Low / Medium / High
- **Expected impact:** estimated revenue or efficiency change
- **Confidence score:** how certain the AI is
- **Full rationale** explaining why it's recommending this

Merchants can Accept (acknowledge and track) or Dismiss recommendations. Nothing is applied automatically.

**Available on:** Growth plan and above

---

### 8. Action Proposals with Approval Workflow (Enterprise)

The most powerful capability — takes recommendations all the way to execution, with human control at every step.

**How it works:**
1. A recommendation is converted into a specific, platform-targeted action proposal
2. An admin reviews it in the Approvals Inbox — seeing the full context, predicted impact, risk level, and confidence score
3. The admin approves or rejects
4. Upon approval, the action can be executed (budget change, campaign pause, bid adjustment, etc.)
5. The system captures state before and after execution
6. If anything looks wrong, the action can be rolled back

**Action types:** Adjust campaign budgets, pause/resume campaigns, modify bidding, change targeting, scale campaigns

**Safety guarantees:** Every action requires explicit approval. No bulk or automated execution. Full audit trail. Rollback always available.

**Available on:** Enterprise plan only

---

### 9. Custom Dashboard Builder

Merchants aren't limited to the built-in dashboards. They can build their own from scratch.

**Builder capabilities:**
- Drag-and-drop report placement on a grid canvas
- Six chart types: Bar, Line, Area, Pie, KPI card, Table
- Custom metric builder with selectable dimensions (platform, period, campaign)
- Filter configuration per report
- Display settings (colors, labels, legend)
- Auto-save as you build
- Unsaved changes protection (prompts before leaving)

**Dashboard management:**
- Save as Draft, Publish, or Archive
- Duplicate any dashboard
- Version history with restore capability
- Share dashboards with team members

**Available on:** Growth plan and above

---

### 10. Template Gallery

Pre-built dashboard templates so merchants don't have to start from zero.

**Template categories:** Sales, Marketing, Customer, Product, Operations

**How it works:** Browse templates with previews showing the layout, included reports, and sample data. One click to create your own copy, fully customizable from there.

**Available on:** Growth plan and above

---

### 11. Budget Pacing Tracker

Monitors monthly ad budgets in real time so merchants never overspend or underpace.

**Per platform, merchants see:**
- Budget amount set for the month
- Current spend-to-date
- Pacing percentage
- Visual progress bar with a time-elapsed marker
- Status badge: **On Pace** (green) / **Slightly Over** (yellow) / **Over Budget** (red)

Merchants can set and edit budget limits per platform directly in the UI.

**Use case:** It's the 20th of the month and Meta is at 95% of budget — the pacing tracker flags it so the merchant can decide whether to pause spend or increase the cap.

---

### 12. Automated Alerts

Rule-based alerts that fire when metrics cross thresholds, without requiring anyone to log in and check.

**Setting up an alert:**
- Pick a metric: ROAS, Ad Spend, or Revenue
- Set a comparison: greater than / less than / equal to
- Set a threshold value
- Pick an evaluation period: Daily, Weekly, or Monthly
- Set a severity: Info, Warning, or Critical

**Alert history tab** shows every time a rule fired — what the metric was, what the threshold was, when it fired, and whether it resolved.

---

### 13. Data Sources & Integrations

Connects all major advertising platforms using secure OAuth authentication.

**Supported integrations:**
| Platform | Status |
|---|---|
| Shopify | Native integration |
| Google Ads | OAuth connected |
| Meta (Facebook + Instagram) | OAuth connected |
| TikTok Ads | OAuth connected |
| Snapchat Ads | OAuth connected |
| Pinterest Ads | OAuth connected |
| Twitter/X Ads | OAuth connected |

**After connecting:**
- Data syncs automatically on a configurable schedule
- Each source shows connection status, last sync time, and health
- Test connection button validates credentials at any time
- Disconnect with a single click

**Onboarding wizard** guides new merchants through connecting Shopify and ad platforms in 4 steps.

---

### 14. Sync Status & Data Health Monitoring

A dedicated monitoring view showing the health of every connected data source.

**Per connector:**
- Status indicator: Healthy (green) / Delayed (yellow) / Error (red)
- Last successful sync timestamp
- Time since last sync

**Additional health features across the app:**
- Data freshness badge visible on dashboards
- Incident banners for critical sync issues
- Automatic retry logic for transient failures

---

### 15. Team Management & Role-Based Access

Control who can see and do what inside the platform.

**Roles:**
| Role | What they can do |
|---|---|
| **Owner** | Full access including billing |
| **Admin** | Full access except billing; can approve AI actions |
| **Analyst** | Read data and create custom dashboards |
| **Viewer** | Read-only access to dashboards |

**Team management:** Add and remove team members, update roles, track member status.

**Limits by plan:** Free (1 member), Growth (10 members), Enterprise (unlimited)

---

### 16. Agency Multi-Store Management (Enterprise)

Built for agencies that manage multiple Shopify stores.

**What agencies can do:**
- Switch between client stores from a single account
- View analytics for any assigned store
- Approve AI action proposals on behalf of clients
- Maintain separate role-based permissions per store

**Available on:** Enterprise plan only

---

### 17. Data Export

Download analytics data for use in external tools, board decks, or custom analysis.

**Export formats:** CSV (Excel-compatible), JSON
**Available datasets:** Orders, Marketing Metrics, Marketing Spend, Attribution Data
**Date range filtering:** Export any custom date range

**Row limits by plan:**
- Free: 100 rows
- Growth: 10,000 rows
- Enterprise: 1,000,000 rows

---

### 18. What's New / Changelog

An in-app release notes feed so merchants always know what's changed.

**Entry types:** New Features, Improvements, Bug Fixes, Deprecations, Security updates
**Features:** Unread count badge, mark all as read, filter by release type, pagination

Context-aware feature banners also surface the 3 most recent updates relevant to the page a merchant is viewing.

---

### 19. Billing & Plan Management

Self-serve subscription management built into the app.

**Plan tiers:** Free, Growth, Enterprise
**Features:** View current plan and limits, upgrade or change plans, billing history
**Grace period:** 3 days for failed payments before hard block
**Paywall screens:** Clear upgrade prompts when a merchant tries to access a feature above their plan

---

## Pricing Tier Summary

| Feature | Free | Growth | Enterprise |
|---|---|---|---|
| Analytics overview dashboard | Yes | Yes | Yes |
| Attribution dashboard | Yes | Yes | Yes |
| Orders view with UTM | Yes | Yes | Yes |
| Channel deep-dive pages | Yes | Yes | Yes |
| AI Insights Feed | No | Yes | Yes |
| AI Recommendations | No | Yes | Yes |
| Custom Dashboard Builder | No | Yes | Yes |
| Template Gallery | No | Yes | Yes |
| Budget Pacing Tracker | No | Yes | Yes |
| Automated Alerts | No | Yes | Yes |
| Data Export (CSV) | No | Yes | Yes |
| Cohort Analysis | No | No | Yes |
| AI Action Proposals (with approval) | No | No | Yes |
| Agency multi-store management | No | No | Yes |
| API Access | No | Yes | Yes |
| SSO | No | No | Yes |
| Audit Logs | No | No | Yes |
| Monthly Orders Limit | 1,000 | 20,000 | Unlimited |
| Team Members | 1 | 10 | Unlimited |
| Data Export Row Limit | 100 | 10,000 | 1,000,000 |

---

## Key Use Cases

### The Solo Merchant Running Multiple Ad Channels
A Shopify store owner is spending $5,000/month across Google and Meta. They log into MarkInsight, see their ROAS is 2.1x on Meta but 4.8x on Google, and find an AI insight flagging that their Meta spend anomalied up 30% yesterday with no corresponding revenue lift. They accept the recommendation to reallocate $1,000/month from Meta to Google. Two weeks later they check the cohort analysis and see retention is up.

### The Marketing Manager Building Reports for Leadership
The marketing manager needs a weekly ROAS report for their CMO. Instead of pulling CSVs and building Excel charts, they open the Dashboard Builder, drag in a Channel Comparison bar chart and a Revenue KPI card, filter to the last 30 days, and publish the dashboard. The CMO gets a link. Done.

### The Agency Managing 12 Shopify Stores
An agency uses Enterprise to switch between client stores. For their biggest client, they review 5 pending AI action proposals in the Approvals Inbox — budget adjustments across Meta and TikTok campaigns. They approve 4, reject 1 (risk level too high). The full audit trail is captured. They never touch the ad platform dashboards directly.

### The Data Team Validating Attribution
The analytics team exports the full attributed orders dataset (up to 1M rows) in CSV, joins it with their CRM data in Snowflake, and validates that the UTM attribution in MarkInsight matches their internal attribution model. Any discrepancy triggers a backfill request to reprocess historical data.

---

## Platform & Technical Positioning Points

- **Embedded in Shopify Admin** — no separate login, no switching tabs
- **Multi-channel, single pane of glass** — all ad platforms in one dashboard
- **AI insights are automatic** — no configuration required; anomalies surface themselves
- **Human-in-the-loop actions** — the AI suggests, the merchant decides; nothing auto-executes
- **Enterprise-grade multi-tenancy** — data is fully isolated between stores; agencies never see cross-client data
- **OAuth-only connections** — no storing of platform passwords; tokens are encrypted at rest
