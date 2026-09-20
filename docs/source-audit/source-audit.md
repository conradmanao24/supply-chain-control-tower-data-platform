# Source Audit Report

## Status

**PASS — source audit source audit completed against the restored `WideWorldImporters` OLTP database.**

This report is limited to source inspection. No WWI simulation/workload was executed in source audit.

## Runtime audited

- Database: `WideWorldImporters`
- SQL Server source runtime: project-owned `wwi-sqlserver` container
- Host binding: `127.0.0.1:14333`
- Source state: healthy and online

## Schema inventory

The restored source contains 48 user tables across the four operational table schemas:

| Schema | Tables |
|---|---:|
| Application | 15 |
| Purchasing | 7 |
| Sales | 12 |
| Warehouse | 14 |
| **Total** | **48** |

`DataLoadSimulation` exists as an operational simulation schema but does not contain user tables included in the 48-table inventory above.

## Actual row counts and source volume

Exact `COUNT_BIG(*)` was executed for every user table. Total rows across all 48 user tables:

**4,713,833 rows**

Rows by schema:

| Schema | Rows |
|---|---:|
| Warehouse | 3,958,807 |
| Sales | 701,656 |
| Application | 40,455 |
| Purchasing | 12,915 |

Largest tables:

| Table | Rows |
|---|---:|
| Warehouse.ColdRoomTemperatures_Archive | 3,654,736 |
| Warehouse.StockItemTransactions | 236,667 |
| Sales.OrderLines | 231,412 |
| Sales.InvoiceLines | 228,265 |
| Sales.CustomerTransactions | 97,147 |
| Sales.Orders | 73,595 |
| Sales.Invoices | 70,510 |
| Warehouse.VehicleTemperatures | 65,998 |
| Application.Cities | 37,940 |
| Purchasing.PurchaseOrderLines | 8,367 |
| Purchasing.SupplierTransactions | 2,438 |
| Purchasing.PurchaseOrders | 2,074 |

The archive temperature table dominates physical row volume, so raw total-row numbers must not be mistaken for the volume of the core supply-chain business scope.

## Primary keys

31 current/user tables expose primary-key constraints in the audited database. The business tables relevant to the control-tower scope have explicit keys, including:

- `Sales.Customers.CustomerID`
- `Sales.Orders.OrderID`
- `Sales.OrderLines.OrderLineID`
- `Sales.Invoices.InvoiceID`
- `Sales.InvoiceLines.InvoiceLineID`
- `Sales.CustomerTransactions.CustomerTransactionID`
- `Purchasing.Suppliers.SupplierID`
- `Purchasing.PurchaseOrders.PurchaseOrderID`
- `Purchasing.PurchaseOrderLines.PurchaseOrderLineID`
- `Purchasing.SupplierTransactions.SupplierTransactionID`
- `Warehouse.StockItems.StockItemID`
- `Warehouse.StockItemHoldings.StockItemID`
- `Warehouse.StockItemTransactions.StockItemTransactionID`

Historical `_Archive` tables are system-versioning history structures and are not treated as independent operational source entities for downstream modeling.

## Foreign keys and verified relationships

The database exposes **98 foreign-key column relationships**.

Important source relationships verified directly from FK metadata include:

```text
Sales.Customers
    -> Sales.Orders (CustomerID)
    -> Sales.Invoices (CustomerID / BillToCustomerID)
    -> Sales.CustomerTransactions (CustomerID)
```

```text
Sales.Orders
    -> Sales.OrderLines (OrderID)
    -> Sales.Invoices (OrderID)
```

```text
Sales.Invoices
    -> Sales.InvoiceLines (InvoiceID)
    -> Sales.CustomerTransactions (InvoiceID)
    -> Warehouse.StockItemTransactions (InvoiceID)
```

```text
Purchasing.Suppliers
    -> Purchasing.PurchaseOrders (SupplierID)
    -> Purchasing.SupplierTransactions (SupplierID)
```

```text
Purchasing.PurchaseOrders
    -> Purchasing.PurchaseOrderLines (PurchaseOrderID)
    -> Purchasing.SupplierTransactions (PurchaseOrderID)
    -> Warehouse.StockItemTransactions (PurchaseOrderID)
```

```text
Warehouse.StockItems
    -> Warehouse.StockItemHoldings (StockItemID)
    -> Warehouse.StockItemTransactions (StockItemID)
    -> Sales.OrderLines (StockItemID)
    -> Sales.InvoiceLines (StockItemID)
    -> Purchasing.PurchaseOrderLines (StockItemID)
```

`Warehouse.StockItemTransactions` is especially useful as a cross-domain inventory movement source because its FK structure can connect inventory movement to stock items and, where populated, customer/invoice/purchase-order/supplier context.

## Business date ranges

The principal transactional source tables cover a historical baseline from 2013 through 31 May 2016 before simulation:

| Table / column | Minimum | Maximum |
|---|---|---|
| Sales.Orders.OrderDate | 2013-01-01 | 2016-05-31 |
| Sales.Invoices.InvoiceDate | 2013-01-01 | 2016-05-31 |
| Sales.CustomerTransactions.TransactionDate | 2013-01-01 | 2016-05-31 |
| Purchasing.PurchaseOrders.OrderDate | 2013-01-01 | 2016-05-31 |
| Purchasing.SupplierTransactions.TransactionDate | 2013-01-02 | 2016-05-31 |
| Purchasing.PurchaseOrderLines.LastReceiptDate | 2013-01-02 | 2016-05-31 |
| Warehouse.StockItemTransactions.TransactionOccurredWhen | 2013-01-01T12:00:00 | 2016-05-31T12:00:00 |

Expected-delivery dates extend beyond the transaction baseline (`Sales.Orders` to 2016-06-01 and `Purchasing.PurchaseOrders` to 2016-06-20), which is expected because planned delivery can occur after order creation.

## Change-behavior audit

source audit identifies three structural change patterns relevant to incremental extraction.

### 1. System-versioned mutable master data

Examples:

- `Sales.Customers`
- `Purchasing.Suppliers`
- `Warehouse.StockItems`
- supporting master/reference tables such as Cities, People, Categories, Colors, Package Types, etc.

These tables are SQL Server system-versioned temporal tables with `ValidFrom` / `ValidTo` history rather than a normal `LastEditedWhen` column on the current table. Their history tables are the corresponding `_Archive` structures.

Candidate approach: **temporal watermark based on `ValidFrom` plus key-based merge/upsert**, with temporal history available when historical attribute tracking is required.

### 2. Mutable operational/current-state tables

Examples:

- `Sales.Orders`
- `Sales.OrderLines`
- `Purchasing.PurchaseOrders`
- `Purchasing.PurchaseOrderLines`
- `Warehouse.StockItemHoldings`

These expose `LastEditedWhen` and contain lifecycle or current-state values that can change after creation.

Candidate approach: **`LastEditedWhen` timestamp watermark plus merge/upsert**.

### 3. Append-heavy transaction tables

Examples:

- `Sales.Invoices`
- `Sales.InvoiceLines`
- `Sales.CustomerTransactions`
- `Purchasing.SupplierTransactions`
- `Warehouse.StockItemTransactions`

These are transaction/event-oriented tables, but they also expose `LastEditedWhen`. source audit therefore does **not** assume they are perfectly immutable.

Candidate approach: **`LastEditedWhen` timestamp watermark plus merge/upsert** until source simulation proves whether append-only treatment is safe for any of them.

## Incremental-candidate findings

Important observations from actual metadata:

1. A single incremental method should not be forced onto all tables.
2. Core transaction/process tables expose `LastEditedWhen` and are suitable for timestamp-watermark extraction.
3. Core master tables such as Customers, Suppliers, and StockItems are system-versioned and expose `ValidFrom`/`ValidTo`, requiring a temporal-aware strategy rather than `LastEditedWhen`.
4. `StockItemHoldings` is a current-state table keyed by `StockItemID`; it must be treated as mutable/upsert-oriented rather than append-only.
5. The core business IDs are not broadly implemented as SQL Server identity columns; increasing-key extraction alone would miss updates and is not recommended as the general strategy.
6. For timestamp watermarks, later implementation must use a tie-safe boundary (for example an overlapping `>=` extraction window combined with key-based deduplication/merge) rather than assuming timestamp values are unique.

The detailed source audit matrix is stored in `evidence/audit/07_change_behavior_matrix.csv`.

## source audit evidence

Reproducible SQL is stored under `sql/audit/` and the captured outputs are stored under `docs/source-audit/evidence/audit/`:

- `01_schema_inventory.txt`
- `02_table_row_counts.txt`
- `03_primary_keys.txt`
- `04_foreign_keys.txt`
- `05_date_ranges.txt`
- `06_incremental_candidates.txt`
- `07_change_behavior_matrix.csv`

The audit can be rerun with `scripts/testing/run-source-audit.ps1` while the source bootstrap and audit source runtime is healthy.

## Known limitations / deferred proof

source audit classifies behavior from actual schema design, keys, temporal metadata, date columns, and operational table semantics. It has **not yet observed a new source delta**.

Therefore the following remain explicitly deferred to source simulation:

- execute the official WWI simulation/workload;
- capture before/after counts and maximum keys/dates;
- observe which tables insert and/or update;
- prove source delta;
- confirm or revise the change-behavior assumptions above;
- lock the recommended downstream source scope.

## source audit gate

```text
Schema inventory                 PASS
Actual row counts                PASS
Actual source volume             PASS
Primary-key audit                PASS
Foreign-key audit                PASS
Relationship audit               PASS
Business date ranges             PASS
Change-behavior classification   PASS (simulation confirmation pending 0D)
Incremental candidates           PASS
Evidence captured                PASS
```

**source audit recommendation: COMPLETE. Proceed to source simulation only after approval.**
