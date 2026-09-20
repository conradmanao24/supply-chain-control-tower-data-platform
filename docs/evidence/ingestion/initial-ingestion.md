# Analytical Initial Ingestion

Date: 2026-09-17

## Scope

analytical ingestion layer loads the approved historical analytical scope from Microsoft WideWorldImporters into project-owned PostgreSQL staging. It does not create the final dimensional/star model; that remains warehouse modeling layer.

The initial load is reproducible through project-owned Python loaders running inside the Airflow image. Incremental scheduling, watermark state, and routine source-gap handling are intentionally deferred to later phases.

## Source Extraction Boundary

### Historical business facts

The following datasets use Microsoft WWI `Integration.*` procedures with the full baseline cutoff window:

- `Integration.GetOrderUpdates` -> `staging.order_line`
- `Integration.GetSaleUpdates` -> `staging.sale_line`
- `Integration.GetMovementUpdates` -> `staging.inventory_movement`
- `Integration.GetPurchaseUpdates` -> `staging.purchase_line`
- `Integration.GetTransactionUpdates` -> `staging.financial_transaction`

The baseline grain audit proved that `(OrderID, StockItemID)`, `(InvoiceID, StockItemID)`, and `(PurchaseOrderID, StockItemID)` are unique in this source snapshot even though the Integration procedures do not expose line IDs.

### Operational/current-state and master extraction

Project-owned `ControlTowerExtract` views/procedures expose only business-required fields. Sensitive source fields such as passwords/hashes, bank details, phone/email, photos, and internal comments are not exposed to staging.

The source reader remains least-privilege and does not receive broad direct-table access.

A source-specific issue was found during validation: `Integration.GetCustomerUpdates` uses an inner join to `BuyingGroups`, while 411 of 813 current customers have no buying group. Using that procedure alone would therefore omit those customers. The project uses an owner-executed customer extraction procedure instead, which returns all 813 current customers and all 991 temporal customer versions while retaining the least-privilege boundary.

## Full Non-Telemetry Load

| Staging dataset | Rows |
|---|---:|
| order_line | 1,009,327 |
| sale_line | 993,477 |
| inventory_movement | 1,028,716 |
| purchase_line | 35,089 |
| financial_transaction | 452,853 |
| order_state | 323,525 |
| invoice_delivery | 308,053 |
| purchase_order_state | 8,374 |
| customer_current | 813 |
| customer_history | 991 |
| supplier_current | 13 |
| supplier_history | 26 |
| product_current | 227 |
| product_history | 671 |
| product_stock_group | 442 |
| stock_holding_current | 227 |
| employee_current | 19 |
| employee_history | 307 |
| geography_current | 37,940 |
| delivery_method_current | 10 |
| transaction_type_current | 13 |
| payment_method_current | 4 |
| package_type_current | 14 |
| stock_group_current | 10 |

Every listed dataset passed source-target row-count reconciliation.

## Telemetry Retention

Raw telemetry remains authoritative in SQL Server. PostgreSQL receives 5-minute analytical aggregates rather than a second copy of every raw sensor row.

Each aggregate preserves:

- minimum temperature
- maximum temperature
- average temperature
- reading count
- first reading timestamp
- last reading timestamp
- maximum intra-bucket reading gap

The aggregate loader processes aligned monthly ranges. Because each bucket is aligned to a five-minute boundary, no five-minute bucket is split across monthly chunks.

### Cold room

- raw source rows used: **87,439,552** (`87,439,548` archive + `4` current)
- PostgreSQL 5-minute buckets: **4,519,296**
- `SUM(reading_count)`: **87,439,552**
- source minimum / aggregate minimum: **3.00 / 3.0000**
- source maximum / aggregate maximum: **5.00 / 5.0000**

### Vehicle

- raw source rows: **1,689,502**
- PostgreSQL 5-minute buckets: **844,776**
- `SUM(reading_count)`: **1,689,502**
- source minimum / aggregate minimum: **3.00 / 3.0000**
- source maximum / aggregate maximum: **5.00 / 5.0000**

No regulatory or source-native temperature threshold is inferred from these values.

## Validation

- source-target row-count reconciliation: PASS
- telemetry raw-reading count preservation: PASS
- telemetry min/max preservation: PASS
- aggregate invariant `min <= avg <= max`: PASS
- aggregate reading counts positive: PASS
- five-minute bucket alignment: PASS
- negative gap metrics: 0
- forbidden sensitive staging columns: 0
- loader column-contract checks: PASS
- PostgreSQL primary/unique constraints applied to proven grains: PASS

## Implementation Evidence

- source extraction boundary: `sql/infrastructure/extraction_views.sql`
- PostgreSQL staging DDL: `sql/warehouse/staging.sql`
- non-telemetry loader: `src/ingestion/initial_load.py`
- telemetry aggregate loader: `src/ingestion/telemetry_load.py`
- Integration audit: `docs/evidence/ingestion/integration-proc-audit.json`
- fact-grain audit: `docs/evidence/ingestion/fact-grain-audit.txt`
- full load log: `docs/evidence/ingestion/full-initial-load.log`
- telemetry load log: `docs/evidence/ingestion/telemetry-full-load.log`
- final reconciliation: `docs/evidence/ingestion/reconciliation.txt`

## Exit Result

The project now has a reconciled source-aligned PostgreSQL staging layer. Final dimensional modeling, semantic SCD decisions, and marts have not started and remain warehouse modeling layer+ work.