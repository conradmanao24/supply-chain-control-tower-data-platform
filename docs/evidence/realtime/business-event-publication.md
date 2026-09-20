# Business Event Publication Evidence

Date: 2026-09-17

## Runtime recovery

After the laptop restart, `wwi-sqlserver` was started explicitly and reached healthy state. `WideWorldImporters` reported `ONLINE`; Service Broker reported enabled.

The existing source and event integration transport was revalidated after reboot:

- 2 ControlTower queues enabled for receive/enqueue
- 2 `//SupplyChainControlTower/...` services present
- `sct_event_consumer` present
- send/receive smoke test PASS
- ingress queue 0, consumer queue 0, transmission queue 0 after cleanup

## Publisher implementation

`sql/infrastructure/business_event_publication.sql` adds:

- `ControlTower.PublishBusinessEvent`
- 7 enabled, set-based DML triggers for Order, Delivery, Procurement, and Inventory current-state changes
- one JSON Service Broker message per DML statement containing only the event envelope and de-duplicated entity ids

No source-table polling job was introduced.

## WWI columnstore constraint

Attempting to create a DML trigger on `Warehouse.StockItemTransactions` was rejected by SQL Server because that table has clustered columnstore index `CCX_Warehouse_StockItemTransactions`. The final reproducible script does not attempt to alter or remove that WWI index. Inventory change publication is attached to `Warehouse.StockItemHoldings` instead.

## Probe

The publisher was invoked directly with a synthetic ControlTower probe, without changing business data. `EventConsumerQueue` received a schema-version-1 message with:

- `event_type = phase6a.probe`
- `entity_type = probe`
- `operation = TEST`
- JSON `entity_keys`

After cleanup:

- ingress queue rows = 0
- consumer queue rows = 0
- transmission queue rows = 0

## Source preservation

The business event publication proof did not mutate business rows. Post-proof source counts remained aligned with the locked source baseline, including Orders 323,525; Invoices 308,053; PurchaseOrders 8,374; and StockItemHoldings 227.

## Result

Business-table changes can now publish lightweight, event-driven notifications over the already-proven Service Broker transport without adding repeated source-table polling.