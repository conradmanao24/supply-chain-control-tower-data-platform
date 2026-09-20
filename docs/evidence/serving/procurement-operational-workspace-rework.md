# Procurement Operational Workspace Rework

Date: 2026-09-18

## Goal

Bring Procurement to the same operational and visual standard as Fulfillment, Delivery, and Inventory:

summary KPI -> operational commitment context -> filtered queue -> PO drawer -> line-level source evidence

## Source semantics review

WideWorldImporters metadata was checked directly:

- PurchaseOrders.OrderDate: date the purchase order was raised
- PurchaseOrders.ExpectedDeliveryDate: expected delivery date for the purchase order
- PurchaseOrders.IsOrderFinalized: whether the purchase order is considered finalized
- PurchaseOrderLines.OrderedOuters: quantity of the stock item ordered
- PurchaseOrderLines.ReceivedOuters: quantity received so far
- PurchaseOrderLines.LastReceiptDate: last date the stock item was received for the PO

The prior UI called any open PO with received quantity below ordered quantity "under-received".

That was misleading for current data. The two current open POs were created on 2026-09-18, are expected on 2026-10-08, and currently have zero receipts. They are future-due supplier commitments awaiting receipt, not overdue/under-received exceptions.

The serving layer now distinguishes:

- open / awaiting receipt
- due today
- overdue
- finalized

Receipt gap is shown factually as outstanding quantity, without automatically labeling future-due POs as exceptions.

## Current verified procurement state

Business date: 2026-09-18

- purchase orders in 30-day window: 50
- open POs: 2
- finalized POs: 48
- overdue open POs: 0
- due today: 0
- upcoming open POs: 2
- outstanding open outers: 129,209
- outstanding open lines: 10
- nearest open PO due: 2026-10-08
- days to nearest due: 20
- ordered outers in 30-day window: 2,836,138
- received outers in 30-day window: 2,706,929
- receipt completion: 95.4%
- active procurement alerts: 0

Open supplier commitments:

- Fabrikam, Inc.: 1 PO / 86,410 outstanding outers / due 2026-10-08
- Litware, Inc.: 1 PO / 42,799 outstanding outers / due 2026-10-08

## Functional changes

### Actionable KPI cards

All four primary KPI cards now open exact queues:

- Purchase orders 30d -> All purchase orders / 50
- Open POs -> Open purchase-order queue / 2
- Overdue -> Overdue purchase-order queue / 0
- Due today -> Due-today purchase-order queue / 0

Direct sidebar navigation to Procurement opens the Open queue by default.

Control Tower Procurement monitoring now shows:

- 2 open POs
- 0 overdue
- 0 due today
- 129,209 outstanding outers

Clicking Procurement from Control Tower opens the same Open purchase-order queue / 2.

### Operational commitment context

The old "under-received" interpretation was removed from the user-facing workspace.

The page now shows:

- outstanding open outers
- outstanding open lines
- nearest expected delivery date
- days to nearest due
- finalized POs
- upcoming open POs
- 30-day ordered/received totals
- receipt completion rate
- supplier-level open commitments

Supplier rows are actionable and filter the open queue.

### Operational PO queue

The queue supports:

- Open / Overdue / Due today / Finalized / All 30d
- server-side pagination
- search by PO ID, supplier ID, or supplier name
- sticky header
- internal scrolling
- expected delivery
- current procurement state
- received / ordered progress
- outstanding outers
- outstanding line count

### PO drawer

Clicking a row opens the shared right-side record drawer.

The drawer shows:

- supplier
- order date
- expected delivery
- current operational state
- ordered / received / outstanding outers
- outstanding line count
- finalized state
- last source update
- exact PO lines

PO-line evidence includes:

- stock item name and ID
- package type
- ordered outers
- received outers
- outstanding outers

## Alert alignment

Procurement alert evaluation now uses the source-frontier business date rather than host UTC date.

A reconciliation of all 50 current-window POs returned:

- 100 clear rule evaluations
- 0 active procurement alerts

No synthetic/future-due receipt gap was turned into an exception.

## Visual consistency

Procurement reuses the same design system and workspace pattern as the prior operational pages:

- Plus Jakarta Sans
- same KPI cards
- same two-panel middle section
- same search/filter controls
- same pagination
- same internal table scrolling
- same right-side drawer
- same 1080p / 2K adaptive behavior

## Browser validation

1920x1080:
- page height: 1080 / 1080
- horizontal overflow: none
- All 30d: 50 rows available / 50 on page
- table viewport: 130px
- browser errors: 0

2560x1440:
- page height: 1440 / 1440
- horizontal overflow: none
- All 30d: 50 rows available / 50 on page
- table viewport: 350px
- title: 38px
- table text: 13px
- browser errors: 0

Functional proof:
- direct Procurement nav -> Open purchase-order queue / 2
- all four KPI actions route correctly
- exact PO search -> 1 result
- row -> right-side drawer
- PO #8380 -> 4 line items
- Control Tower Procurement -> Open purchase-order queue / 2

This checkpoint preceded the final application validation.
