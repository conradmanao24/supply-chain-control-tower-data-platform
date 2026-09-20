# Controlled Simulation Pilot

> **source simulation final status:** this pilot was later followed by the approved full historical catch-up through `2026-09-15`. source simulation is now **PASS** and source bootstrap and audit is **CLOSED**. See `source-audit-final.md` for the authoritative final source state.

## Pilot status

**FUNCTIONAL PILOT: PASS**

The pilot used the WideWorldImporters `DataLoadSimulation` workload with the Microsoft-recommended order-volume parameters and a controlled date window from 2016-06-01 through 2016-06-07.

## Before state

The source audit source audit recorded the baseline through 2016-05-31.

| Table | Before rows |
|---|---:|
| Warehouse.ColdRoomTemperatures_Archive | 3,654,736 |
| Warehouse.StockItemTransactions | 236,667 |
| Sales.OrderLines | 231,412 |
| Sales.InvoiceLines | 228,265 |
| Sales.CustomerTransactions | 97,147 |
| Sales.Orders | 73,595 |
| Sales.Invoices | 70,510 |
| Warehouse.VehicleTemperatures | 65,998 |
| Purchasing.PurchaseOrderLines | 8,367 |
| Purchasing.SupplierTransactions | 2,438 |
| Purchasing.PurchaseOrders | 2,074 |

## After state

After the controlled workload completed, the operational date range advanced through 2016-06-07.

| Table | After rows | Delta |
|---|---:|---:|
| Warehouse.ColdRoomTemperatures_Archive | 3,810,228 | +155,492 |
| Warehouse.StockItemTransactions | 237,964 | +1,297 |
| Sales.OrderLines | 232,673 | +1,261 |
| Sales.InvoiceLines | 229,511 | +1,246 |
| Sales.CustomerTransactions | 97,677 | +530 |
| Sales.Orders | 73,996 | +401 |
| Sales.Invoices | 70,896 | +386 |
| Warehouse.VehicleTemperatures | 68,996 | +2,998 |
| Purchasing.PurchaseOrderLines | 8,418 | +51 |
| Purchasing.SupplierTransactions | 2,452 | +14 |
| Purchasing.PurchaseOrders | 2,086 | +12 |

Validated maximum operational dates included:

- `Sales.Orders.OrderDate`: 2016-06-07
- `Sales.Invoices.InvoiceDate`: 2016-06-07
- `Purchasing.PurchaseOrders.OrderDate`: 2016-06-07
- `Warehouse.StockItemTransactions.TransactionOccurredWhen`: 2016-06-07
- `Warehouse.VehicleTemperatures.RecordedWhen`: 2016-06-07

The workload therefore produced coordinated changes across sales, purchasing, inventory, financial transactions, and telemetry rather than only adding sales orders.

## Post-pilot source state

The WWI temporal configuration returned to normal after the pilot sequence:

- temporal current tables: 17
- temporal history tables: 17
- leftover `*_DataLoad_Modify` simulation triggers: 0
- disabled foreign keys observed during validation: 0
- untrusted foreign keys observed during validation: 0

## Capacity finding from the pilot

The seven-day pilot added **155,492 rows** to `Warehouse.ColdRoomTemperatures_Archive`, or roughly **22,213 rows/day** over this pilot window.

A simple linear extrapolation over the remaining ten-year gap suggested telemetry would dominate source growth. This estimate was used only as a planning signal before the approved full catch-up; the final measured source volume is documented in `source-audit-final.md`.

## Runtime note

The pilot orchestration path did not preserve a trustworthy end-to-end runtime measurement. Runtime is therefore deliberately recorded as **not measured**, rather than inferred or fabricated.

## Historical decision gate

At the time of the pilot, the full catch-up was intentionally held pending review of telemetry growth. That gate was later explicitly approved and executed. The resulting full baseline reached `2026-09-15`, was validated, frozen, and became the selected canonical source baseline.
