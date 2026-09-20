# Procurement REST Serving

## Scope

Implemented the Procurement business-serving page as the next business serving layer serving area.

## Backend

Endpoint:

`GET /api/procurement/overview`

Source boundary:

- `realtime.current_procurement_state`
- `core.dim_supplier`
- `alert.alerts`
- `alert.rule_config`
- `control.source_frontier`

The browser does not query WWI directly.

## Current measured serving state

At validation time:

- purchase orders in 30-day source window: 48
- open POs: 2
- under-received POs: 2
- overdue POs: 0
- due at source frontier: 0
- ordered outers: 2,705,313
- received outers: 2,576,151
- active procurement alerts: 0

Priority POs:

- PO 8373 — Fabrikam, Inc. — 86,392 ordered / 0 received — expected 2026-10-05
- PO 8374 — Litware, Inc. — 42,770 ordered / 0 received — expected 2026-10-05

30-day supplier activity:

- Fabrikam, Inc. — 24 POs
- Litware, Inc. — 24 POs

## Frontend

Added `frontend/src/ProcurementPage.tsx` and the Procurement REST contract in `frontend/src/api.ts`.

Page sections:

- KPI strip
- ordered-vs-received progress
- supplier activity mix
- procurement alert summary
- priority purchase-order table
- manual refresh action

The page reuses the locked business serving layer design system and responsive shell.

## Validation

- Procurement API: HTTP 200
- Vite production build: PASS
- Dashboard dev server: HTTP 200
- 1,884 frontend modules transformed successfully

## Boundary

This checkpoint is REST serving only.

Procurement SSE realtime refresh is intentionally deferred to the next small business serving layer batch.
