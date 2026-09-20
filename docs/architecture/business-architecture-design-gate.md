# Business & Architecture Design Gate

This document is the authoritative pre-Phase-1 decision record. It is based on the audited WideWorldImporters source frozen through **2026-09-15** and intentionally excludes features the source cannot support.

## 1. Product Definition

The project builds an **Operational Supply Chain Control Tower Data Platform** for a wholesale/distribution business.

It combines current operational visibility, exception management, order-to-delivery visibility, inventory control, procurement/inbound visibility, cold-chain monitoring, historical analytics, and data-platform health.

It is not a generic BI dashboard and does not recreate an ERP.

## 2. System Users

Primary business user:
- Supply Chain / Operations Manager

Functional users:
- Order Fulfillment / Customer Service
- Warehouse / Inventory Control
- Procurement / Purchasing
- Logistics / Delivery Operations
- QA / Cold Chain

Technical/governance users:
- Data / Platform Operations
- Administrator

Administrator manages project-owned users, roles, permissions, thresholds, alert/notification configuration, system settings, and application audit logs. Administrator does not modify authoritative WWI business transactions.

## 3. Locked Business Scope

### Order Fulfillment - CORE

Source: `Sales.Orders`, `Sales.OrderLines`, `Sales.Invoices`, `Sales.InvoiceLines`.

Supported:
- open/unpicked orders
- overdue unpicked orders
- backorders
- picking completion
- order-to-invoice lifecycle
- cycle-time analysis
- demand by customer/product/territory

Measured source evidence:
- 323,525 orders
- 1,009,327 order lines
- 308,053 invoiced orders
- 15,472 historical orders with no picking completion timestamp

Historical unresolved rows require a go-live backlog policy and must not automatically become new active alerts.

### Shipping & Delivery - CORE

Primary source: `Sales.Invoices.ReturnedDeliveryData` JSON plus invoice/customer fields.

Supported event content:
- Ready for collection
- DeliveryAttempt
- DriverID
- latitude/longitude
- delivered status
- `Receiver not present`
- confirmed delivery time
- received-by person

Measured evidence:
- 308,053 valid delivery JSON documents
- 308,009 delivery attempts
- 277,276 Delivered attempt events
- 30,733 Receiver-not-present attempt events
- 19 driver IDs map to WWI employees
- audited attempt coordinates match delivery destinations

Supported use cases:
- ready-for-collection queue
- pending/overdue delivery
- delivery-attempt exceptions
- destination visibility
- delivery lead time
- driver activity context

Not supported:
- live vehicle route tracking
- route optimization
- outbound carrier comparison
- shipment-to-vehicle lineage

### Inventory Control - CORE

Source: `Warehouse.StockItemHoldings`, `Warehouse.StockItemTransactions`, `Warehouse.StockItems`.

Measured evidence:
- 227 products
- 227 current stock holdings
- 1,028,716 stock movements
- 993,477 Stock Issue
- 35,079 Stock Receipt
- 160 stocktake adjustments

Supported:
- quantity on hand
- reorder/target exceptions
- receipt and issue history
- demand versus stock
- reconciliation using an explicit opening snapshot plus subsequent movements

Not supported:
- multi-warehouse network inventory
- ATP/CTP planning
- lot/batch stock
- FEFO

### Procurement / Supply - CORE

Source: purchase orders, PO lines, suppliers, supplier transactions.

Measured evidence:
- 8,374 purchase orders
- 35,089 PO lines
- 9,812 supplier transactions
- 10 current under-received/open lines
- zero audited historical late-receipt lines

Supported:
- open PO
- ordered versus received
- under-received lines
- expected receipts
- lead time
- supplier/product dependency
- inbound exceptions

Do not fabricate a supplier-lateness leaderboard from a source with no meaningful historical lateness variation.

### Cold Chain - CORE

Source: `Warehouse.ColdRoomTemperatures`, `Warehouse.ColdRoomTemperatures_Archive`, `Warehouse.VehicleTemperatures`, chiller-product attributes.

Measured evidence:
- 4 cold-room sensors
- 87,439,548 cold-room historical readings
- history from 2015-12-20 through 2026-09-15
- recent cold-room median gap about 16 seconds, P99 about 30 seconds
- 1 vehicle with 2 chiller sensors
- 1,689,502 vehicle-temperature rows
- 8 chiller products
- chiller products expose a 7-day shelf-life attribute

Supported:
- latest sensor state
- sensor freshness/staleness
- configurable temperature alerts
- historical min/max/avg trends
- gap/availability analysis
- excursion analytics after thresholds are configured

Not supported:
- shipment-level temperature compliance
- invoice-to-vehicle linkage
- lot expiry monitoring
- FEFO

WWI does not define a temperature safety threshold. Temperature thresholds are project-owned anomaly rules. The runtime default uses the historical WWI 3.0-5.0 C operating envelope for warning detection and a wider 2.5-5.5 C critical guard band; these are explicitly not regulatory or product-safety limits.

### Demand / Customer / Geography - CORE ANALYTICS

Supported context includes customer segmentation, buying groups, delivery geography, product demand, territory demand, and bill-to hierarchy.

### Workforce Execution - SECONDARY

Salesperson, picker, packer, and delivery driver are valid execution context. This is not an HR analytics product.

### Financial Exposure - SECONDARY

Customer/supplier transactions provide outstanding/finalization context. This is not a Finance BI product.

## 4. Explicitly Excluded Features

Excluded unless new source data is introduced and a new design decision is approved:
- capabilities that require source relationships or operational facts not present in the audited source
- shipment-to-vehicle relationship
- shipment-temperature compliance
- multi-warehouse planning
- lot/batch traceability
- FEFO/expiry execution
- demand forecasting engine
- supplier-capacity planning
- manufacturing/MRP execution
- outbound carrier comparison
- promotion analytics as a current core domain

## 5. Operational Event Architecture

The base operational architecture is change-driven. It does **not** use UI polling, Kafka, or CDC.

Business-table path:

```text
SQL Server business change
        |
        v
lightweight DML trigger
        |
        v
SQL Server Service Broker
        |
        v
realtime backend
        |
        v
current state / alert evaluation
        |
        v
SSE push
        |
        v
Control Tower UI
```

Triggers only publish minimal change events. They must not perform heavy joins, KPI calculation, HTTP calls, UI calls, or ETL work.

### Telemetry write path

`Warehouse.ColdRoomTemperatures` and `Warehouse.VehicleTemperatures` are memory-optimized. Telemetry therefore uses the supported WWI write path plus a project-owned interpreted publish wrapper rather than blindly applying the ordinary disk-table trigger pattern.

A compile-only check against SQL Server 2022 was performed and rolled back completely. It confirmed an interpreted wrapper can call the native cold-room writer and contain Service Broker statements. Runtime integration still requires implementation-phase testing.

### Time-driven exceptions

Some exceptions happen because time passes rather than because a row changes:
- an unpicked order becomes overdue
- a sensor becomes stale because no reading arrives

The design therefore includes deadline/timer events. These are event-driven timers, not repeated table polling.

### Broker bootstrap dependency

The audited WWI database currently has Service Broker disabled. platform infrastructure must explicitly enable and validate it in the restored project runtime.

## 6. Realtime Transport

Initial browser transport:

```text
realtime backend -> Server-Sent Events (SSE) -> browser
```

SSE fits the primary server-to-browser push requirement. User actions such as acknowledge/resolve/admin changes use normal HTTP APIs. WebSocket is deferred unless true persistent bidirectional realtime communication becomes necessary.

## 7. Analytical Architecture

Realtime operational state and historical analytics remain separate responsibilities.

```text
SQL Server WWI
      |
      v
incremental analytical extraction
      |
      v
Airflow
      |
      v
PostgreSQL staging
      |
      v
dbt core facts/dimensions
      |
      v
business marts
      |
      v
historical analytics / DQ / reconciliation
```

WWI already exposes an `Integration` schema with procedures including `GetOrderUpdates`, `GetSaleUpdates`, `GetPurchaseUpdates`, `GetMovementUpdates`, `GetTransactionUpdates`, `GetCustomerUpdates`, `GetSupplierUpdates`, and `GetStockItemUpdates`.

These source-native integration procedures must be evaluated first for analytical incremental extraction before custom delta logic is invented.

## 8. Technology Decisions

Selected:
- SQL Server 2022 + WideWorldImporters
- SQL Server Service Broker for project-local operational messaging
- project-owned realtime backend
- SSE for browser push
- PostgreSQL analytical warehouse
- Apache Airflow for orchestration, analytical ingestion, DQ, reconciliation, backfill, and recovery
- dbt for transformations, tests, dimensions/facts, and marts

Not selected for the base architecture:
- Kafka
- CDC / Debezium
- Data Lake
- Spark
- Kubernetes

These are not universally rejected; they are unnecessary for the audited source, scale, consumers, and current requirements.

## 9. Alert Rules

Alerting represents actionable exceptions, not every state change.

### Inventory

Source-native thresholds:
- `QuantityOnHand <= ReorderLevel` -> replenishment exception
- `QuantityOnHand < 0` -> critical inventory/data exception
- `ReorderLevel < QuantityOnHand < TargetStockLevel` -> watch state

### Fulfillment

- expected delivery date passed + picking incomplete -> overdue fulfillment exception
- due today + still unpicked -> warning
- backorder reference -> backorder exception/context

Historical unresolved rows are not automatically opened as new alerts at go-live.

### Delivery

- ready for collection + still pending before expected date -> normal
- due today without completion -> warning
- expected date passed without completion -> overdue delivery exception
- `Receiver not present` -> delivery-attempt exception

WWI simulation can contain contradictory delivery fields. Event status/comment and consistency checks must be preserved rather than treating one timestamp as universally authoritative.

### Procurement

- under-received while expected date is still future -> normal open inbound state
- due today and under-received -> warning
- expected date passed + under-received/open -> overdue inbound exception

### Cold-room sensor health

Measured recent cadence:
- median gap about 16 seconds
- P95 about 29 seconds
- P99 about 30 seconds
- recent observed maximum about 53 seconds

Initial configurable policy:
- last seen <= 30 seconds -> normal
- last seen > 60 seconds -> stale warning
- last seen > 120 seconds -> offline/critical

### Cold-room temperature

WWI generates roughly 3-5 C values but does not define safety limits.

The project therefore uses a project-owned anomaly policy: outside 3.0-5.0 C is a warning and outside 2.5-5.5 C is critical. The wider critical band is an operational guard band around the historical WWI envelope, not a regulatory or food-safety threshold. Temperature values remain visible and the bands remain configuration, not source-native truth.

### Vehicle sensor health

Vehicle telemetry has a slower cadence and must use separate configurable stale/offline rules.

### Platform health

Engineering exceptions include:
- source/event freshness
- queue processing lag
- analytical pipeline failure
- failed dbt/data-quality checks
- source-to-warehouse reconciliation mismatch

## 10. Alert Persistence

Alert rows reference business entities and do not duplicate the full master record.

Conceptual fields:

```text
alert_id
rule_id
entity_type
entity_id
severity
status
opened_at
observed_value
threshold_value
resolved_at
```

Observed values and active thresholds are snapshotted so historical alerts remain explainable after configuration changes.

## 11. Warehouse Modeling Direction

The warehouse is not a 1:1 WWI mirror.

Core dimensions are expected to include:
- product
- customer
- supplier
- employee
- geography
- date
- delivery method
- transaction type
- package type

Product-to-stock-group is many-to-many and requires a bridge.

Planned fact grains include:
- one row per order line
- one row per invoice/sales line
- one row per stock movement
- one row per purchase-order line
- one row per delivery event
- one row per customer transaction
- one row per supplier transaction

### Master history / SCD policy

WWI temporal history is not copied blindly into SCD2 dimensions.

Measured product history contains 671 temporal versions across 227 products, while audited core business attributes did not materially change in those versions; much of the additional versioning came from custom-field/tag enrichment.

Warehouse SCD history is therefore **business-attribute-driven**: create a new dimension version only when an attribute that changes historical interpretation changes.

### Telemetry analytical retention

SQL Server remains the authoritative raw telemetry store.

The PostgreSQL analytical warehouse primarily retains curated telemetry aggregates rather than duplicating all 87+ million raw cold-room rows without a business requirement.

Initial aggregate grain: 5 minutes, with fields such as min/max/avg temperature, reading count, gap metrics, and excursion metrics after thresholds exist.

## 12. Serving-Layer Information Architecture

Control Tower:
- cross-domain current exceptions
- operational freshness

Fulfillment:
- open orders
- unpicked/overdue
- backorders
- order lifecycle

Delivery:
- ready for collection
- pending delivery
- attempts
- receiver-not-present events
- completion
- destination context

Inventory:
- current stock
- reorder exceptions
- target watch state
- receipt/issue history
- demand versus stock
- reconciliation

Procurement:
- open PO
- expected receipts
- under-received lines
- lead time
- supplier/product dependency

Cold Chain:
- current sensor state
- latest temperature
- freshness
- configured alerts
- history/gaps/trends

Analytics:
- demand, customer, product, territory, fulfillment, inventory, procurement, cold-chain trends

Platform Health:
- queue/event freshness
- current-state freshness
- warehouse freshness
- Airflow/dbt status
- data-quality failures
- reconciliation
- backfill history

Admin:
- users
- roles/permissions
- alert rules
- thresholds
- notifications
- system settings
- audit log

## 13. RBAC Direction

Planned roles:
- Supply Chain / Operations Manager
- Order Fulfillment / Customer Service
- Warehouse / Inventory Control
- Procurement / Purchasing
- Logistics / Delivery Operations
- QA / Cold Chain
- Data / Platform Operations
- Administrator

Permissions apply to project-owned application/serving layers and do not grant arbitrary mutation of WWI source transactions.

## 14. Design Gate Exit Decision

The source audit and implementation pre-mortem support the planned core project without requiring fabricated business data.

The design is **LOCKED** with these constraints:

1. Do not expand into unsupported domains without a new source/data decision.
2. Keep realtime current-state processing separate from historical analytical processing.
3. Use Service Broker rather than Kafka/CDC for the current operational event requirement.
4. Account explicitly for memory-optimized telemetry write paths.
5. Model time-driven exceptions with deadline/timer events rather than source-table polling.
6. Keep non-source-native alert thresholds configurable and explainable.
7. Prevent historical unresolved source artifacts from flooding go-live alerts.
8. Keep raw telemetry authoritative in SQL Server and store business-oriented aggregates in the analytical warehouse unless a later requirement proves raw duplication necessary.
9. Use semantic/business SCD history instead of blindly mirroring every temporal version.
10. platform infrastructure implementation begins only after explicit approval.
