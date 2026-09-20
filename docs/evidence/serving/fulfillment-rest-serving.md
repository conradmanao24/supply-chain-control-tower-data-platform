# Fulfillment Serving Page - REST Proof

Date: 2026-09-17

## Scope

The Fulfillment serving area now reads project-owned PostgreSQL operational projections through the realtime API. The browser does not query WideWorldImporters directly.

## Endpoint

`GET /api/fulfillment/overview`

The serving contract returns:
- source-frontier date used as the operational as-of date
- 30-day fulfillment operating-window KPIs
- overdue aging buckets
- explicit all-time historical backlog context
- priority order queue with customer names
- fulfillment-domain alert summary

## Measured live state

At source frontier `2026-09-16`:
- 2,097 orders in the 30-day window
- 170 open orders
- 167 overdue orders
- 3 due at the frontier date
- 170 open backorders
- 15,472 all-time open orders

Overdue aging:
- 1-2 days: 19
- 3-7 days: 20
- 8-14 days: 35
- 15+ days: 93

The full historical backlog is deliberately separated from the 30-day operating window so the dashboard does not present old WWI backlog as if it were all current-period work.

## Frontend proof

- Fulfillment navigation renders a dedicated serving page.
- KPI, aging, backlog context, and priority-order table use live REST data.
- UI production build passed.
- Local UI HTTP 200.

## Next

Add SSE-driven fulfillment refresh using the existing realtime stream without interval polling.
