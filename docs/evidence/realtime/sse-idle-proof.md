# SSE Push Contract & Idle-Polling Proof

## Scope

SSE/API serving exposes the realtime consumer PostgreSQL current-state projections through a local realtime API and proves browser-oriented SSE push without repeatedly polling WideWorldImporters business tables while the runtime is idle.

## Runtime

- Docker service: `realtime-api`
- Application: `src/realtime/api.py`
- Host endpoint: `http://127.0.0.1:${REALTIME_API_PORT}` (local `.env`: port `18000`)
- Database used by the API: PostgreSQL warehouse only
- SSE notification channel: PostgreSQL `LISTEN/NOTIFY` channel `control_tower_realtime`
- Notification trigger: `sql/warehouse/sse_notify.sql`

The serving API does not open a SQL Server connection. WWI current-state reads remain confined to the realtime consumer consumer and occur only after a Service Broker event is received.

## Serving contract

The realtime API exposes:

- `GET /health` - database/listener health and active SSE subscriber count
- `GET /api/realtime/events?limit=N` - recent processed event metadata
- `GET /api/realtime/events/{event_id}` - full persisted event, including original `entity_keys`
- `GET /api/realtime/state/{domain}/{entity_id}` - current projected state for orders, deliveries, procurement, inventory, or sensors
- `GET /api/realtime/stream` - Server-Sent Events stream

SSE is an invalidation/push signal rather than a duplicate business-row transport. Each committed processed event emits compact metadata including `event_id`, `event_type`, `entity_type`, `operation`, `processing_result`, and timestamps. A client can use `event_id` to retrieve the persisted event envelope and then read the current PostgreSQL projection.

The stream sends:

- `event: ready` on connection
- `event: update` for committed processed events
- comment keepalives (`: keepalive`) during idle periods

PostgreSQL delivers `NOTIFY` only on transaction commit, so the browser-facing update is emitted after the realtime consumer projection transaction commits.

## End-to-end SSE proof

A source-data-neutral proof published an `order.changed` notification for existing `order_id = 1` through `ControlTower.PublishBusinessEvent`; no WWI business row was modified.

Observed event:

- event id: `a5eb2dee-43f4-4cf9-8673-3aea0d94f9c8`
- event type: `order.changed`
- source marker: `Phase6E.SSE.Proof`
- consumer result: `processed`
- occurred: `2026-09-17T11:20:48.259476+00:00`
- processed: `2026-09-17T11:20:48.271236+00:00`

The open SSE client received the matching `update` event without refresh or source polling. Raw capture: `docs/evidence/realtime/sse-e2e.txt`.

`GET /api/realtime/events/a5eb2dee-43f4-4cf9-8673-3aea0d94f9c8` returned the persisted envelope including `entity_keys: [{"entity_id": 1}]`, proving the SSE event can be resolved to the affected entity through PostgreSQL.

## Idle no-source-polling proof

The realtime consumer was left idle for 35 seconds, crossing at least one configured 30-second `WAITFOR RECEIVE` timeout cycle. Procedure execution counters for all controlled WWI current-state reads were captured before and after the idle window.

| Controlled source read | Before | After | Delta |
| --- | ---: | ---: | ---: |
| `GetDeliveryCurrentState` | 1 | 1 | 0 |
| `GetInventoryCurrentState` | 2 | 2 | 0 |
| `GetOrderCurrentState` | 4 | 4 | 0 |
| `GetProcurementCurrentState` | 1 | 1 | 0 |

The PostgreSQL event log also remained unchanged during the window:

- event count before: `10`
- event count after: `10`
- latest processed event before/after: `2026-09-17 11:20:48.271236+00`

At both samples the `sct_event_consumer` SQL Server session was suspended on `BROKER_RECEIVE_WAITFOR`. This is a blocking wait on the Service Broker queue, not repeated reads of WWI business tables.

Raw samples:

- `docs/evidence/realtime/idle-before.txt`
- `docs/evidence/realtime/idle-after.txt`

## Restart sanity check

`realtime-api` was restarted independently. After restart:

- container returned healthy
- PostgreSQL health check passed
- SSE listener reported `connected`
- listener error remained `null`

The API is therefore independently restartable without restarting the SQL Server source or the realtime consumer.

## Exit gate

SSE/API serving passes because:

- REST/current-state serving is available from project-owned PostgreSQL projections
- SSE delivers committed realtime event notifications
- SSE remains connected during idle with keepalives
- the serving API does not query WWI directly
- controlled WWI current-state procedure execution counts remain unchanged across an idle interval longer than the consumer receive timeout
- the consumer is observed waiting on Service Broker rather than polling business tables

