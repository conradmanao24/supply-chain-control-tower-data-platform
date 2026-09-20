# Functional Review — Drill-Down Pilot

Status: **PASS — first functional-review batch**

This checkpoint preceded the final serving validation.
## Locked global rule

Operational summary values must support this investigation path:

`summary/KPI → filtered full list → record detail → factual reason/evidence`

See:

`docs/architecture/functional-drilldown-standard.md`

## First implemented pilot

### Control Tower → Delivery Pending

The Control Tower `Delivery pending` KPI now acts as an investigation entry point.

Expected flow:

`Delivery pending 44`
→ opens Delivery page
→ applies `Pending` filter
→ shows the full 44-row pending list
→ click an invoice
→ shows record detail and source-backed reason/evidence.

### Delivery full-list API

Added:

- `GET /api/delivery/list?status=pending`
- `GET /api/delivery/list?status=all`
- `GET /api/delivery/list?status=confirmed`
- `GET /api/delivery/list?status=receiver_not_present`
- `GET /api/delivery/{invoice_id}`

The list is aligned to the same 30-source-day delivery window used by the Delivery KPIs.

Validation:

- pending list: 44 rows
- receiver-not-present list: 207 rows
- record detail resolves invoice-level evidence

Example current pending evidence:

- invoice 308053
- pending reason / latest source event: `Ready for collection`
- days pending at source frontier: 1

### Delivery investigation fields

The full list now exposes:

- invoice
- customer
- order
- invoice date
- expected delivery date
- current reason/state
- days pending
- delivery run / position

Record detail additionally exposes:

- confirmed delivery time
- received by
- last source update
- returned-delivery source event evidence

No business reason is invented. If the source has no specific event reason, the fallback is factual: `No delivery confirmation received`.

## Validation

- frontend production build: PASS
- dashboard: HTTP 200
- realtime API: OK
- database: OK
- SSE listener: connected

## Next review step

Continue reviewing the **Control Tower** function before moving to the next page. Replicate the drill-down standard only after each KPI/domain behavior is approved.
