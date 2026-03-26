# Figma prototype vs Markinsight — page map

This document records how the [Figma Make site](https://slot-arch-71887855.figma.site) lines up with the app, and how authenticated navigation in [`frontend/src/components/layout/Root.tsx`](../frontend/src/components/layout/Root.tsx) maps to routes in [`frontend/src/App.tsx`](../frontend/src/App.tsx).

## Figma URL probes (automated fetch, 2025)

| URL | Result |
|-----|--------|
| `/` | Single HTML text bundle: title "Ecommerce Analytics Dashboard", hero, three value props, testimonial, sign-in card (Google, GitHub, email copy, CTAs). |
| `/analytics` | Same text as `/` (SPA shell; no distinct post-login content in extracted text). |
| `/signup` | Fetch timed out (no reliable second page from automation). |

**Conclusion:** The prototype exposes **one composite pre-auth screen** in text extraction. Additional frames (dashboard, charts, etc.) require opening the site in a **browser** or the **Figma / Figma Make** source file.

## Figma: single screen (content order)

1. Document title: Ecommerce Analytics Dashboard  
2. Brand: Markinsight  
3. Hero: "Welcome back! Your data awaits." + ROAS / AI subcopy  
4. Value props: Automatic Data Sync (4h) · Real Attribution (UTM) · AI-Powered Insights  
5. Testimonial: $12K / +34% ROAS — Sarah Chen  
6. Auth card: Welcome back · Google · GitHub · email path · Sign In & View Data · sign up · Terms / Privacy  

## Markinsight: signed-out routes

| Path | UI |
|------|-----|
| `/` | [`Landing.tsx`](../frontend/src/pages/Landing.tsx) — marketing + CTAs to Clerk |
| `/sign-in/*` | Clerk `<SignIn />` |
| `/sign-up/*` | Clerk `<SignUp />` |
| `*` (signed out) | Redirect to `/` |

## Markinsight: `Root` sidebar vs routes

Sidebar order is implemented in `Root.tsx`. App routes are in `App.tsx` (feature gates apply where noted).

| Sidebar label | Route | Notes |
|---------------|-------|--------|
| Overview | `/` | [`Dashboard.tsx`](../frontend/src/pages/Dashboard.tsx) |
| Attribution | `/attribution` | |
| Orders | `/orders` | |
| **Intelligence** | | |
| AI Consultant | `/ai-consultant` | |
| Automated Alerts | `/alerts` | Entitlement: `alerts` |
| Budget Pacing | `/budget-pacing` | Entitlement: `budget_pacing` |
| Cohort Analysis | `/cohorts` | Entitlement: `cohort_analysis`; alias `/cohort-analysis` |
| Report Builder | `/reports` | Entitlement: `custom_reports`; `/builder` same wizard |
| **Channels** | `/channel/:key` → `/channels/:platform` | Per-channel analytics |
| **System** | | |
| Sync Status | `/sync` | `/sync-health` redirects to `/sync` |

**Not in sidebar but in `App.tsx`:** `/home` (DashboardHome), `/analytics` (embedded Superset), `/insights`, `/approvals`, `/whats-new`, `/data-sources`, `/sources`, `/paywall`, billing, `/dashboards/*`, `/templates`, `/onboarding`, `/oauth/callback`, `/admin/*`, etc.

## Figma themes → app pages

| Theme | Primary routes |
|-------|----------------|
| Automatic Data Sync | `/sync`, `/sources`, `/data-sources` |
| Real Attribution | `/attribution`, `/orders`, `/channels/:platform` |
| AI-Powered Insights | `/insights`, `/ai-consultant`, `/approvals` |
| ROAS / overview | `/` (KPI overview), `/analytics` (Superset), `/home` (Polaris home) |

## Feature-gated route groups (entitlements)

- `custom_reports`: `/dashboards`, `/dashboards/:id`, `/dashboards/:id/edit`, `/reports`, `/builder`, `/dashboards/wizard`, `/templates`  
- `cohort_analysis`: `/cohorts`, `/cohort-analysis`  
- `budget_pacing`: `/budget-pacing`  
- `alerts`: `/alerts`  

## Maintenance

When navigation or routes change, update `Root.tsx` / `App.tsx` and this doc together.
