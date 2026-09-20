# Inventory Operational Workspace Rework

Date: 2026-09-18

## Goal

Bring Inventory to the same functional and visual standard as Fulfillment and Delivery:

summary KPI -> operational context -> filtered queue -> stock-item drawer -> factual source evidence

## Source semantics correction

WideWorldImporters metadata was checked directly for Warehouse.StockItemHoldings:

- QuantityOnHand: quantity currently on hand
- LastStocktakeQuantity: quantity at last stocktake
- ReorderLevel: quantity below which reordering should take place
- TargetStockLevel: typical quantity ordered

The previous Inventory implementation incorrectly treated TargetStockLevel as a target on-hand inventory threshold. That created:

- a misleading Below target state
- a false inventory.target_watch alert
- misleading units_to_target calculations

This interpretation was removed.

The historical inventory.target_watch rule is retained for audit history but disabled and marked non-source-native. Its active alert was reconciled/resolved.

## Current verified inventory state

- stock items: 227
- reorder required: 6
- out of stock: 1
- negative stock: 0
- items above reorder level: 221
- total units on hand: 141,118,854
- combined gap below reorder trigger: 66 units
- source typical order quantity across currently flagged items: 210 units
- active inventory alerts: 6
- active inventory alert type: inventory.reorder only

Stock-state partition:
- negative: 0
- out of stock: 1
- positive but at/below reorder level: 5
- above reorder level: 221

## Functional changes

### Actionable KPI cards

All four primary KPI cards now open exact record sets:

- Stock items -> All inventory items / 227
- Reorder required -> Reorder-required queue / 6
- Out of stock -> Out-of-stock items / 1
- Negative stock -> Negative-stock exceptions / 0

Direct sidebar navigation to Inventory opens the Reorder-required queue by default.

Control Tower -> Inventory reorder opens the same Reorder-required queue / 6.

### Replenishment context

The old Target watch concept was removed.

The context panel now shows factual operational information:

- items above reorder level
- total units on hand
- combined quantity gap below reorder triggers
- configured typical order quantity for currently flagged items

The UI explicitly states that WWI TargetStockLevel means typical order quantity and is not used as an on-hand stock threshold.

### Operational inventory queue

The queue supports:

- Reorder required / Out of stock / Negative / Above reorder / All items
- server-side pagination
- search by stock-item ID or name
- sticky header
- internal scrolling
- exact current on-hand quantity
- source reorder trigger
- quantity below trigger
- typical order quantity
- last stocktake quantity
- change since last stocktake
- current factual stock state

### Stock-item drawer

Clicking a row opens the shared right-side record drawer.

The drawer shows:

- stock item ID and name
- quantity on hand
- reorder trigger
- quantity below trigger
- typical order quantity
- last stocktake quantity
- change since stocktake
- last source update
- a factual state explanation

## Alert reconciliation

After semantic correction and reconciliation:

- inventory.reorder active: 6
- inventory.negative_stock active: 0
- inventory.target_watch active: 0
- inventory.target_watch enabled: false
- all active alert explanations globally: 201 verified / 0 fallback

## Visual consistency

Inventory reuses the same design system and interaction structure as Fulfillment and Delivery:

- same Plus Jakarta Sans typography
- same KPI cards
- same two-panel middle layout
- same search/filter controls
- same pagination
- same internal table scrolling
- same right-side record drawer
- same 1080p / 2K adaptive behavior

## Browser validation

1920x1080:
- page height: 1080 / 1080
- horizontal overflow: none
- Reorder queue: 6
- All items: 227 with 50 rows/page
- internal table height: 190px
- browser errors: 0

2560x1440:
- page height: 1440 / 1440
- horizontal overflow: none
- Reorder queue: 6
- All items: 227 with 50 rows/page
- internal table height: 450px on full-list view
- title: 38px
- table text: 13px
- browser errors: 0

Functional browser proof:
- direct Inventory nav -> Reorder-required queue / 6
- all four KPI actions route correctly
- exact item search -> 1 result
- row -> right-side drawer
- Control Tower Inventory reorder -> Reorder-required queue / 6

This checkpoint preceded the final application validation.
