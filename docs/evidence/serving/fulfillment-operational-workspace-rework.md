# Fulfillment Operational Workspace Rework

Date: 2026-09-18

## Why this rework was needed

The previous Fulfillment page mixed a useful overdue chart with a mostly raw 30-day table and a misleading historical backlog panel. It also exposed a semantic bug in the Backorders KPI.

The goal of this rework is:

summary KPI -> operational queue -> exact order detail -> line-level evidence

without dumping historical/source rows on the page.

## Semantic correction: Backorders

WideWorldImporters source metadata was checked directly.

- BackorderOrderID: if the order itself is a backorder, this holds the original order number.
- IsUndersupplyBackordered: policy flag that says whether unsupplied items should be backordered.

The previous implementation incorrectly treated IsUndersupplyBackordered=true as proof that the order was currently a backorder. In the current 30-day source window that flag is true for all 2,092 orders, which made the old Backorders=164 KPI meaningless.

Corrected active-backorder definition:

- picking is not completed; and
- BackorderOrderID is not null.

Current active backorders: 0.

The Fulfillment alert evaluator was corrected to the same source semantics and aligned to the source-frontier business date plus 30-day operational scope. Existing false backorder alerts were reconciled/resolved.

## Current verified Fulfillment state

Business date: 2026-09-18

- 2,092 orders in 30-day window
- 164 open orders
- 154 overdue
- 3 due today
- 7 upcoming open
- 0 active backorders
- 1,928 completed
- overdue share of open queue: 93.9%
- median overdue age: 16 days
- oldest overdue: 29 days

## UI changes

### Actionable KPIs

All four top KPIs now open their exact filtered queue:

- Open orders -> 164
- Overdue -> 154
- Due today -> 3
- Active backorders -> 0

### Removed misleading historical panel

The old Full backlog panel (15,474 all-time open orders) was removed from the operational workspace.

It was replaced by an Operational snapshot showing:

- overdue rate
- median overdue age
- oldest overdue age
- upcoming open
- completed orders in the 30-day window

### Operational order queue

Direct navigation to Fulfillment now opens the Open queue by default instead of All 30d.

The queue supports:

- Open / Overdue / Due today / Backorder / All 30d filters
- server-side pagination (50/page)
- search by order ID, customer ID, or customer name
- sticky table header
- internal table scrolling so the page remains one workspace

Queue columns were changed from source-like fields to operational context:

- Order
- Customer
- Expected
- Status
- Order size (lines / units)
- Order value
- Actual backorder state

### Order detail

Clicking a row opens a right-side drawer, preserving queue context.

The drawer now includes:

- customer
- order date
- expected delivery
- days overdue
- picking completion
- line count
- units ordered
- order value
- actual backorder reference
- last source update
- exact order lines with product description, stock item ID, units, and line value

## Alert reconciliation impact

After correcting the false backorder rule and reconciling the current operational window:

- active alert signals: 202
- affected records: 186
- fulfillment overdue alerts: 154
- fulfillment due-today alerts: 3
- fulfillment backorder alerts: 0
- active alert explanation validation: 202 / 202 verified, 0 fallback

## Validation

1920x1080:
- page height equals viewport
- horizontal overflow: none
- direct Fulfillment nav -> Open order queue / 164
- Overdue KPI -> 154
- Due today KPI -> 3
- Active backorders KPI -> 0
- search exact order -> 1 result
- row -> right-side order drawer
- browser errors: 0

2560x1440:
- page height equals viewport
- horizontal overflow: none
- title size: 38px
- table text: 13px
- same functional validations PASS
- browser errors: 0

This checkpoint preceded the final application validation.
