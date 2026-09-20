# Delivery Operational Workspace Rework

Date: 2026-09-18

## Goal

Bring Delivery to the same operational standard and visual system already established for Fulfillment:

summary KPI -> operational context -> filtered queue -> record drawer -> source-event evidence

## Current business state

Business date: 2026-09-18

- deliveries in 30-day window: 2,000
- pending confirmation: 84
- overdue pending: 5
- due today: 1
- upcoming pending: 78
- confirmed: 1,916
- confirmation rate: 95.8%
- receiver-not-present historical events: 205
- receiver-not-present current pending cases: 0
- overdue share of pending queue: 6.0%
- median overdue age: 39 days
- oldest overdue age: 1,488 days

The 1,488-day oldest overdue value is source-native: the current source contains 2026 invoices linked to older orders/expected-delivery dates. The serving layer does not silently rewrite this evidence.

## Functional corrections

### KPI actions

All four primary KPI cards are now actionable:

- Deliveries 30d -> All delivery records / 2,000
- Pending confirmation -> Pending delivery queue / 84
- Overdue -> Overdue delivery queue / 5
- Due today -> Due-today delivery queue / 1

Direct sidebar navigation to Delivery opens the Pending queue by default.

Control Tower -> Delivery overdue preserves the Overdue filter and opens exactly 5 records.

### Corrected delivery age semantics

The old UI displayed "Age" from invoice age, which could show 0d for an invoice that was already overdue against its expected delivery date.

The serving contract now exposes separate factual fields:

- days_overdue
- days_until_due
- days_since_invoice
- delivery_state

Operational status uses expected delivery date, so overdue rows show the actual overdue age.

### Historical event separation

Receiver-not-present count is no longer presented as an active operational KPI.

It is shown as event history with an explicit distinction:

- 205 historical receiver-absent events
- 0 current pending receiver-absent cases

Confirmed deliveries and receiver-absent history remain investigable through filters.

### Operational context

Delivery now includes:

- overdue-aging distribution
- confirmation rate
- confirmed volume
- upcoming pending count
- median overdue age
- oldest overdue age
- receiver-absent historical context

### Operational queue

The queue now supports:

- Pending / Overdue / Due today / Confirmed / Receiver absent history / All 30d
- server-side pagination
- search by invoice, order, customer ID, or customer name
- sticky header
- internal scrolling
- factual current-state status
- latest source event
- route/run context

### Delivery drawer

Clicking an invoice opens the shared right-side record drawer.

The drawer shows:

- customer
- order
- invoice date
- expected delivery
- operational state
- actual days overdue where applicable
- latest source event
- latest event comment
- delivery run and run position
- confirmed delivery timestamp
- receiver
- last source update
- full source-event timeline

## Visual consistency

Delivery reuses the same components and classes as Fulfillment:

- Plus Jakarta Sans design system
- same KPI cards
- same context-card structure
- same queue/search/filter system
- same pagination
- same sticky internal table
- same right-side record drawer
- same 1080p / 2K adaptive rules

## Validation

1920x1080:
- exact viewport height: 1080 / 1080
- horizontal overflow: none
- 50 rows in pending page
- internal table height: 200px
- browser errors: 0

2560x1440:
- exact viewport height: 1440 / 1440
- horizontal overflow: none
- 50 rows in pending page
- internal table height: 450px
- title: 38px
- table text: 13px
- browser errors: 0

Functional browser proof:
- Delivery direct nav -> Pending delivery queue / 84
- Deliveries KPI -> All delivery records / 2,000
- Pending KPI -> 84
- Overdue KPI -> 5
- Due-today KPI -> 1
- search -> exact result
- row -> right-side drawer
- Control Tower Delivery overdue -> Overdue delivery queue / 5

This checkpoint preceded the final application validation.
