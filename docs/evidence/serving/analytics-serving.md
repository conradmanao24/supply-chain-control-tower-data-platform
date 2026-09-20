# Analytics Serving

## Scope

Implemented the Analytics serving page backed by the analytical warehouse.

## Backend

Endpoint:

`GET /api/analytics/overview`

Source boundary:

- `core.fact_sales_line`
- `core.fact_purchase_order_line`
- `core.dim_date`
- `core.dim_customer`
- `core.dim_product`
- `control.source_frontier`

The browser does not query WWI directly.

## Current measured analytics state

At validation time, using the last 30 source days through the current source frontier:

- orders: 1,877
- invoices: 1,877
- units sold: 251,505
- revenue: 5,212,048.45
- profit: 2,237,863.20
- margin: 42.94%
- procurement receipt rate: 95.23%

The page also serves:

- 12-month monthly revenue/profit trend
- top customers by revenue
- top products by revenue/profit/units
- procurement ordered-vs-received context

The current source month is explicitly shown as frontier-to-date rather than as a completed month.

## Frontend

Added `frontend/src/AnalyticsPage.tsx` and the Analytics contract in `frontend/src/api.ts`.

Page sections:

- KPI strip
- 12-month revenue trend
- top-customer concentration view
- top-product contribution table
- manual refresh action

The page reuses the locked business serving layer design system and responsive shell.

## Validation

- Analytics API: HTTP 200
- Vite production build: PASS
- Dashboard dev server: HTTP 200
- 1,886 frontend modules transformed successfully
- realtime API: OK
- database: OK
- SSE listener: connected
- Control Tower active exceptions: 0
- latest quality gate: PASS

## Result

Analytics serving is operational from the warehouse with no direct browser-to-WWI access.
