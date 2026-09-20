# Source & Event Integration

Date: 2026-09-17

## Scope

source and event integration establishes the project-owned SQL Server source-access and Service Broker event infrastructure. It does not implement ingestion DAGs, business transformations, DML business triggers, alert rules, realtime business projections, or UI behavior.

## SQL Server Source Access

Two project-specific principals were provisioned instead of using `sa` for runtime access:

- `sct_airflow_reader` for analytical/source reads
- `sct_event_consumer` for Service Broker receive access

The Airflow reader is not a sysadmin. Its database access is limited to the official `Integration` stored-procedure boundary plus direct read access to the telemetry tables required by the locked architecture.

Validated from the Airflow scheduler:

- database: `WideWorldImporters`
- user: `sct_airflow_reader`
- sysadmin membership: `0`
- `Integration.GetOrderUpdates` execution: PASS
- test window `2026-09-15T00:00:00` to `2026-09-16T00:00:00`: 145 rows

## Airflow MSSQL Runtime

The project-owned Airflow image includes the versions pinned by the Airflow 3.3.1 Python 3.12 constraints:

- `apache-airflow-providers-microsoft-mssql==4.7.0`
- `pymssql==2.3.13`

The provider build and Airflow service recreation passed. Airflow API server, scheduler, and DAG processor returned healthy after recreation.

## Service Broker Infrastructure

Service Broker was enabled on `WideWorldImporters` after preflight confirmed there were no open user transactions.

Project-owned Broker objects:

- schema: `ControlTower`
- message type: `//SupplyChainControlTower/Event`
- contract: `//SupplyChainControlTower/EventContract`
- queue: `ControlTower.EventIngressQueue`
- queue: `ControlTower.EventConsumerQueue`
- service: `//SupplyChainControlTower/EventIngress`
- service: `//SupplyChainControlTower/EventConsumer`

Validation:

- `is_broker_enabled = 1`
- project queues = 2
- project services = 2
- send/receive smoke test: PASS
- least-privilege receive as `sct_event_consumer`: PASS
- ingress queue after cleanup = 0
- consumer queue after cleanup = 0
- transmission queue after cleanup = 0

## Source Persistence Regression

The SQL Server container was recreated once to add the read-only infrastructure SQL mount. The existing named volume remained attached.

Post-recreate source signature:

- `Sales.Orders`: 323,525
- `Sales.Invoices`: 308,053
- `Warehouse.StockItemTransactions`: 1,028,716
- database state: ONLINE

## Realtime Service Boundary

source and event integration reserves the realtime application boundary only. The future backend is responsible for:

- consuming Broker messages with the project event-consumer credential
- evaluating current-state rules outside SQL Server triggers
- maintaining current projections and alert state
- exposing server-to-browser push through SSE
- exposing REST endpoints for acknowledgement/configuration actions

No business event trigger, telemetry publish wrapper, current-state projection, alert rule, SSE endpoint, or browser UI is implemented in source and event integration. Those belong to later implementation phases.

See `docs/architecture/realtime-service-boundary.md`.

## Final Regression

- Docker Compose configuration: PASS
- SQL Server WWI: healthy
- PostgreSQL warehouse: healthy
- Airflow metadata database: healthy
- Airflow API: HTTP 200
- Airflow scheduler: healthy
- Airflow DAG processor: healthy
- dbt 1.11.15 debug: PASS
- dbt PostgreSQL connection: PASS
- MSSQL provider version: 4.7.0
- pymssql version: 2.3.13
- Airflow-to-WWI least-privilege connection: PASS
- Service Broker: enabled
- Broker transmission queue: empty

## Exit Result

**source and event integration passed.**

No analytical ingestion layer ingestion was started.