# UI primitives (minimal)

This folder intentionally keeps only what **GlobalSearch** needs:

- `command.tsx` — cmdk + Radix dialog wrapper
- `dialog.tsx` — Radix dialog primitives
- `utils.ts` — `cn()` helper

The rest of the app uses **Shopify Polaris** (data-heavy flows) and **Tailwind + Lucide** (main shell in `layout/Root.tsx`). Do not re-expand the shadcn kit without a deliberate design decision.
