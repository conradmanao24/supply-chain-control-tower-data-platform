# Final Source Audit Report

## Scope

This report records the source bootstrap, restore, audit, controlled simulation, full catch-up, validation, and frozen baseline for the project-owned Microsoft WideWorldImporters OLTP source.

## Final source baseline

- Database: `WideWorldImporters`
- Source lineage: official Microsoft `WideWorldImporters-Full.bak`
- Final operational date: **2026-09-15**
- Historical business range: **2013-01-01 through 2026-09-15**
- User tables: **48**
- Final raw rows across user tables: **93,334,276**
- Initial source audit raw rows: **4,713,833**
- Net growth from the controlled simulation program: **+88,620,443 rows**

## Final rows by operational schema

| Schema | Rows |
|---|---:|
| Warehouse | 90,159,172 |
| Sales | 3,078,431 |
| Purchasing | 53,311 |
| Application | 43,362 |
| **Total** | **93,334,276** |

## Final core business volume

| Source table | Final rows |
|---|---:|
| Sales.Orders | 323,525 |
| Sales.OrderLines | 1,009,327 |
| Sales.Invoices | 308,053 |
| Sales.InvoiceLines | 993,477 |
| Sales.CustomerTransactions | 443,041 |
| Purchasing.PurchaseOrders | 8,374 |
| Purchasing.PurchaseOrderLines | 35,089 |
| Purchasing.SupplierTransactions | 9,812 |
| Warehouse.StockItemTransactions | 1,028,716 |

The six primary business-event tables (`Orders`, `Invoices`, `CustomerTransactions`, `PurchaseOrders`, `SupplierTransactions`, and `StockItemTransactions`) contain **2,121,521 rows** in total. This is not a single transaction count; it is the combined row volume across distinct event types.

The three principal line-item tables (`OrderLines`, `InvoiceLines`, and `PurchaseOrderLines`) contain **2,037,893 rows** in total.

## Telemetry volume

| Telemetry table | Final rows |
|---|---:|
| Warehouse.ColdRoomTemperatures_Archive | 87,439,548 |
| Warehouse.VehicleTemperatures | 1,689,502 |
| **Total telemetry** | **89,129,050** |

Telemetry represents approximately **95.49%** of the final raw row volume. Therefore the project must describe the source as **93.3M+ raw operational records**, not as 93.3M business transactions.

## Final master/reference examples

| Master data | Final rows |
|---|---:|
| Warehouse.StockItems | 227 |
| Sales.Customers | 813 |
| Purchasing.Suppliers | 13 |
| Application.People | 1,261 |
| Application.Cities | 37,940 |

## Business date ranges

The final measured source ranges include:

| Table / date field | Minimum | Maximum |
|---|---|---|
| Sales.Orders.OrderDate | 2013-01-01 | 2026-09-15 |
| Sales.Invoices.InvoiceDate | 2013-01-01 | 2026-09-15 |
| Sales.CustomerTransactions.TransactionDate | 2013-01-01 | 2026-09-15 |
| Purchasing.PurchaseOrders.OrderDate | 2013-01-01 | 2026-09-15 |
| Purchasing.SupplierTransactions.TransactionDate | 2013-01-02 | 2026-09-15 |
| Warehouse.StockItemTransactions.TransactionOccurredWhen | 2013-01-01 | 2026-09-15 |
| Warehouse.VehicleTemperatures.RecordedWhen | 2016-01-01 | 2026-09-15 |
| Warehouse.ColdRoomTemperatures_Archive.RecordedWhen | 2015-12-20 | 2026-09-15 |

## Source simulation result

A seven-day controlled pilot first proved that the official WWI `DataLoadSimulation` logic creates coordinated deltas across sales, purchasing, inventory, financial transactions, and telemetry.

The approved full catch-up then advanced the source from June 2016 through **2026-09-15**. The catch-up was executed once to create a reusable project baseline so future clean-clone users do not repeat the multi-day historical simulation.

Final simulation cleanup state:

- foreign-key relationships: **98**
- disabled/untrusted foreign keys: **0**
- temporal current tables: **17**
- temporal history tables: **17**
- leftover simulation triggers: **0**

## Final source integrity

Source validation recorded:

- `DBCC CHECKDB(... WITH PHYSICAL_ONLY)` — **PASS**
- final `MAX(Sales.Orders.OrderDate)` — **2026-09-15**
- disabled/untrusted foreign keys — **0**
- temporal configuration restored — **PASS**
- simulation trigger cleanup — **PASS**

Evidence: `docs/source-audit/evidence/simulation/final/`.

## Frozen full baseline

The final project baseline is the **full 2013–2026 source**. The previously explored 2023–2026 trimmed distribution is **not the selected baseline design**.

Local frozen backup:

- file: `data/baselines/full-master/wwi-full-master-2026-09-15.bak`
- backup type: full SQL Server backup
- compression: enabled
- `COPY_ONLY`: enabled
- backup checksum: enabled
- exact size: **1,662,111,744 bytes**
- size: **1.548 GiB**
- SHA-256: `1F779A53D9AE1E5B90F2C62BA74D3E48E5FED0F75096E5EC798A09ABF04DEE30`
- `RESTORE VERIFYONLY WITH CHECKSUM` — **PASS**

Because the full compressed baseline is 1.548 GiB, historical trimming is unnecessary for the selected project baseline. The frozen baseline is distributed separately from Git history through the project's `v1.0-data-baseline` GitHub Release.

## Baseline distribution decision

**Selected:** full history, 2013-01-01 through 2026-09-15.

**Not selected:** trimmed 2023–2026 distribution experiment.

Reasons:

1. the full source is already compact enough after native SQL Server backup compression;
2. full history avoids unnecessary referential-closure and temporal-history trimming logic;
3. downstream source selection can occur in ingestion/modeling without mutating the canonical source baseline;
4. preserving full source history maximizes reproducibility and auditability.

The local `WideWorldImporters_Distribution` copy and trimming evidence are experimental artifacts only and are not authoritative project source state.

## Incremental extraction conclusions

The source audit confirmed that the source requires more than one incremental strategy:

- mutable operational tables: timestamp watermark based on `LastEditedWhen` plus key-based merge/upsert;
- system-versioned master/reference tables: temporal-aware handling using `ValidFrom` / `ValidTo`;
- append-heavy event tables: treated conservatively as update-capable until downstream reconciliation proves a narrower strategy safe;
- tie-safe timestamp boundaries and idempotent merge behavior are required.

These conclusions inform the downstream Airflow, PostgreSQL, dbt, pipeline-state, and serving implementation.

## Source validation summary

| Requirement | Result |
|---|---|
| Official source acquired and validated | PASS |
| SQL Server source restored | PASS |
| Persistence verified | PASS |
| Schema/table inventory | PASS |
| Actual row counts and volume | PASS |
| PK/FK and relationship audit | PASS |
| Business date-range audit | PASS |
| Change-behavior classification | PASS |
| Incremental candidates | PASS |
| Official WWI simulation pilot | PASS |
| Full historical catch-up | PASS |
| Source delta proven | PASS |
| Final source health validation | PASS |
| Frozen full baseline backup | PASS |
| Backup integrity verification | PASS |
| Final Source Audit Report | PASS |

**All listed source validation checks passed.**
