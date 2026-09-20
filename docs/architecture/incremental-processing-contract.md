# Incremental Contract

Date: 2026-09-17

## Boundary

incremental analytical pipeline implements incremental analytical processing only. Persistent watermark/run-state ownership, restart recovery, and exactly-once run state are deferred to pipeline-state layer.

Every incremental analytical pipeline entry point therefore accepts an explicit half-open processing window:

`(last_cutoff, new_cutoff]`

No incremental analytical pipeline component invents or persists its own authoritative watermark.

## Official WWI delta sources

Use official `Integration` procedures first:

- `GetOrderUpdates`: changed order-line grain, change timestamp = later of order/header and line `LastEditedWhen`.
- `GetSaleUpdates`: changed invoice-line grain, change timestamp = later of invoice/header and line `LastEditedWhen`.
- `GetPurchaseUpdates`: changed purchase-order-line grain, change timestamp = later of purchase-order/header and line `LastEditedWhen`.
- `GetMovementUpdates`: changed stock movement rows by `LastEditedWhen`.
- `GetTransactionUpdates`: changed customer/supplier transaction rows by `LastEditedWhen`.
- temporal master update procedures use `ValidFrom` cutoff semantics.

`Integration.GetStockHoldingUpdates` has no cutoff parameters and is not a delta contract.

## Staging write policy

Incremental loaders use existing staging business keys/primary keys and perform idempotent upserts.

Facts:
- order line: `(wwi_order_id, wwi_stock_item_id)`
- sales line: `(wwi_invoice_id, wwi_stock_item_id)`
- inventory movement: `wwi_stock_item_transaction_id`
- purchase line: `(wwi_purchase_order_id, wwi_stock_item_id)`
- financial transaction: customer or supplier transaction identifier

Current-state/master rows are upserted by their source business key. Semantic history rows are upserted by `(business_id, valid_from)`.

## Current-state/master delta policy

Official Integration procedures are used where they provide the required business attributes. Project-owned least-privilege extraction procedures/views are used where the official contract is incomplete for this platform, including customer current/history semantics and operational current-state rows.

`StockItemHoldings` is a small current snapshot (227 baseline rows); incremental analytical pipeline may refresh/upsert that bounded snapshot because WWI provides no official cutoff contract for it.

## Telemetry policy

Raw telemetry remains authoritative in SQL Server. PostgreSQL receives 5-minute aggregates only.

For an incremental window, recompute from the beginning of the 5-minute bucket containing `last_cutoff` through `new_cutoff`. Upsert aggregate rows by telemetry bucket primary key. This overlap makes a partially filled boundary bucket idempotent and prevents stale aggregates.

For a tail refresh where the durable analytical watermark already equals the source frontier, telemetry must still re-read the configured late-arrival overlap ending at the committed cutoff. Projection-only refresh is insufficient because source telemetry rows may be committed after the frontier publication while carrying `RecordedWhen` values before that cutoff. The overlap recomputation preserves idempotency and captures those late arrivals without advancing the production watermark.

## Core/dbt policy

incremental analytical pipeline must not rebuild source-aligned staging from scratch. Core refresh consumes only staging rows touched by the current explicit batch window, except small/static dimensions where bounded recomputation is demonstrably cheaper and does not cause source re-extraction.

Delivery events are replacement-by-invoice for impacted invoices because the source JSON event array can change as a unit.

## incremental analytical pipeline exclusions

- authoritative persisted watermarks
- run ledger / restart state
- retry recovery semantics based on persisted state
- operational Service Broker event consumption

Those belong to later phases.
