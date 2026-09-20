# Post-Reboot Runtime Regression - 2026-09-17

Purpose: verify project persistence and runtime health after an abrupt laptop/Docker shutdown before entering incremental analytical pipeline.

## Source Runtime

- WWI SQL Server container restarted without restore or rebuild.
- Database `WideWorldImporters`: ONLINE.
- `DBCC CHECKDB (WideWorldImporters) WITH PHYSICAL_ONLY`: PASS (no error; sqlcmd `-b` exit 0).
- Orders: 323,525.
- Invoices: 308,053.
- OrderLines: 1,009,327.
- InvoiceLines: 993,477.
- StockItemTransactions: 1,028,716.
- ColdRoomTemperatures_Archive: 87,439,548 rows; with 4 current rows this preserves the previously reconciled 87,439,552 readings.
- VehicleTemperatures: 1,689,502.
- Order date range remains 2013-01-01 through 2026-09-15.

## Source & Event Integration

- Service Broker remains enabled.
- Project Broker queues: 2.
- Project Broker services: 2.
- Transmission queue: empty.
- Post-reboot Broker send/receive smoke test: passed.
- `sct_event_consumer` permission context successfully received the test message.
- Queues returned to zero after cleanup.
- `sct_airflow_reader` remains non-sysadmin and can execute `Integration.GetOrderUpdates`.

## Analytical Runtime

- PostgreSQL warehouse: healthy.
- Airflow metadata PostgreSQL: healthy.
- Airflow API server: healthy.
- Airflow scheduler: healthy.
- Airflow DAG processor: healthy.
- Airflow health endpoint: HTTP 200.
- dbt Core 1.11.15 / dbt-postgres 1.11.0: connection passed.
- dbt regression tests: 115/115 PASS, 0 warnings, 0 errors.

## Persistence Samples

- `staging.order_line`: 1,009,327.
- `staging.coldroom_5m`: 4,519,296.
- `core.dim_customer`: 991.
- `core.fact_order_line`: 1,009,327.
- `core.fact_delivery_event`: 616,062.
- Core warehouse tables: 17.

## Gate Result

**passed.** source bootstrap and audit-3 artifacts and runtime state survived the reboot. incremental analytical pipeline remains NOT STARTED until explicitly entered.