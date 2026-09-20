# Operational Event Contract

## Purpose

operational event plane adds an event-driven operational plane beside the analytical batch pipeline. Business changes publish lightweight entity-change notifications through SQL Server Service Broker so downstream current-state projections can react without repeatedly polling WWI business tables.

## Existing broker transport

operational event plane reuses the source and event integration transport in `WideWorldImporters`:

- message type `//SupplyChainControlTower/Event`
- contract `//SupplyChainControlTower/EventContract`
- service `//SupplyChainControlTower/EventIngress`
- service `//SupplyChainControlTower/EventConsumer`
- queues `ControlTower.EventIngressQueue` and `ControlTower.EventConsumerQueue`

The transport remains local to SQL Server and uses Service Broker transactional messaging.

## Event envelope v1

Each business DML statement publishes one JSON message, not one message per affected row.

Required fields:

- `schema_version`: `1`
- `event_id`: UUID generated at publication time
- `event_type`: domain-level change type
- `entity_type`: entity to refresh downstream
- `source_table`: source object that caused the notification
- `operation`: `INSERT`, `UPDATE`, or `DELETE`
- `occurred_at_utc`: source-side UTC publication time
- `entity_keys`: de-duplicated affected entity ids

The message is a change notification, not a copy of the business row. Downstream consumers use the key to refresh current state through controlled source reads or project-owned projections.

## Business publication map

| Source table | Event type | Entity |
| --- | --- | --- |
| `Sales.Orders` | `order.changed` | order |
| `Sales.OrderLines` | `order.changed` | order |
| `Sales.Invoices` | `delivery.changed` | invoice |
| `Sales.InvoiceLines` | `delivery.changed` | invoice |
| `Purchasing.PurchaseOrders` | `procurement.changed` | purchase order |
| `Purchasing.PurchaseOrderLines` | `procurement.changed` | purchase order |
| `Warehouse.StockItemHoldings` | `inventory.changed` | stock item |

`Warehouse.StockItemTransactions` is intentionally not trigger-published because WWI uses a clustered columnstore index on that table and SQL Server prohibits DML triggers on clustered-columnstore tables. Inventory realtime change notification therefore uses the current-state `StockItemHoldings` object rather than altering the official WWI index design.

## OLTP protection

Triggers are set-based and only inspect `inserted`/`deleted`; they do not scan the source tables. They call `ControlTower.PublishBusinessEvent`, which sends one batched notification per DML statement. The normal trigger path does not rethrow publication errors, so an event-plane fault must not take down the authoritative OLTP write path. Broker availability and projection freshness must therefore be surfaced later as platform-health signals and reconciliation controls.

## Phase boundary

business event publication covers disk-based business publication only. Telemetry publication uses a separate wrapper path in telemetry publish wrapper. Deadline/timer events, the realtime consumer/current-state projections, SSE delivery, and the explicit idle/no-source-polling proof remain later operational event plane scope.
## Telemetry publication

Memory-optimized telemetry tables do not use DML triggers. Project-owned wrappers call the official WWI telemetry write procedures and then publish one batched Service Broker notification for non-empty input:

- `ControlTower.RecordColdRoomTemperaturesAndPublish` -> `Website.RecordColdRoomTemperatures`
- `ControlTower.RecordVehicleTemperatureAndPublish` -> `Website.RecordVehicleTemperature`

The event is an invalidation/change notification, not a duplicate raw telemetry stream. Raw telemetry remains authoritative in SQL Server. Consumers refresh the relevant current-state projection in response to the event rather than polling the source repeatedly.
## Deadline / timer events

Deadline-driven exceptions use SQL Server Service Broker conversation timers rather than repeated source-table polling. `ControlTower.ScheduleDeadline` records a project-owned timer, and `ControlTower.ProcessDeadlineTimerQueue` is activated only when the broker timer becomes due.

Timer messages are signals that an evaluation point has arrived; they do not assert that a business alert is true. Current state must be evaluated downstream before an alert is opened or maintained. `ControlTower.CancelDeadline` cancels deadlines whose underlying condition is resolved or superseded.

## Realtime consumer and current-state projections

The realtime consumer worker blocks on Service Broker `WAITFOR RECEIVE`; it does not repeatedly poll WWI business tables. Business events contain entity keys only. The consumer uses project-owned `ControlTower.GetOrderCurrentState`, `GetDeliveryCurrentState`, `GetProcurementCurrentState`, and `GetInventoryCurrentState` procedures with `EXECUTE AS OWNER` to perform bounded point reads without granting broad table access to the event principal.

PostgreSQL `realtime.event_log` provides event-id deduplication. Current operational projections are maintained in `realtime.current_order_state`, `current_delivery_state`, `current_procurement_state`, `current_inventory_state`, and `current_sensor_state`.

Telemetry event metadata carries only the latest observed value per sensor in the published batch, allowing the sensor projection to update without scanning raw telemetry tables. Deadline messages remain evaluation signals only; alert lifecycle belongs to alert and exception layer.

Consumer processing is at-least-once and idempotent. Downstream failures are retried in-process; persistent malformed events are preserved in `ControlTower.EventDeadLetter` so poison-message protection does not disable the operational queue during normal error handling.

## SSE serving contract

SSE/API serving exposes committed realtime state from PostgreSQL; the serving API does not connect directly to WWI SQL Server.

`realtime.event_log` emits a compact PostgreSQL `NOTIFY` after a processed event transaction commits. The `realtime-api` service maintains a blocking `LISTEN` connection on channel `control_tower_realtime` and fans committed notifications out through Server-Sent Events at `GET /api/realtime/stream`.

The SSE payload is intentionally metadata-only. It carries the persisted `event_id` and event classification rather than duplicating full business rows or an arbitrarily large `entity_keys` array. Clients resolve the event through `GET /api/realtime/events/{event_id}` and read authoritative project-owned current state through `GET /api/realtime/state/{domain}/{entity_id}`.

During idle periods, the SSE connection is kept open with comments/keepalives. The realtime consumer source consumer remains blocked on Service Broker `WAITFOR RECEIVE`. A 35-second SSE/API serving idle proof showed zero additional executions of all four `ControlTower.Get*CurrentState` source-read procedures across a window longer than the configured 30-second broker receive timeout.

operational event plane therefore closes with an event-driven operational path from WWI publication through Service Broker, PostgreSQL current-state projection, and browser-oriented SSE push without periodic WWI business-table polling.
