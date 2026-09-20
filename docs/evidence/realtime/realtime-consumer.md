# Realtime Consumer & Current-State Projections

## Scope

realtime consumer adds a dedicated realtime worker that consumes SQL Server Service Broker events and maintains project-owned PostgreSQL current-state projections. It does not poll WWI business tables while idle.

## Runtime

- Docker service: `realtime-consumer`
- Worker: `src/realtime/consumer.py`
- Broker receive path: `WAITFOR RECEIVE` on `ControlTower.EventConsumerQueue`
- Event principal: `sct_event_consumer`
- Current-state reads: project-owned `ControlTower.Get*CurrentState` procedures with `EXECUTE AS OWNER`
- PostgreSQL schema: `realtime`

## Seeded projections

Initial projection state was seeded once from the already reconciled analytical staging layer:

- `realtime.current_order_state`: 323,525 rows
- `realtime.current_delivery_state`: 308,053 rows
- `realtime.current_procurement_state`: 8,374 rows
- `realtime.current_inventory_state`: 227 rows
- `realtime.current_sensor_state`: 6 sensors

Subsequent maintenance is event-driven.

## Event proof

A source-data-neutral proof published change notifications for existing entities only. The worker processed:

- `order.changed` -> order projection refreshed
- `delivery.changed` -> delivery projection refreshed
- `procurement.changed` -> procurement projection refreshed
- `inventory.changed` -> inventory projection refreshed
- `telemetry.coldroom.batch_recorded` -> 4 sensor projections refreshed
- `deadline.phase6d.probe` -> recorded as a deadline signal for later alert evaluation

All events were persisted idempotently in `realtime.event_log` by `event_id`.

## Retry / poison-message proof

An implementation defect during initial proof caused repeated transaction rollback; SQL Server poison-message protection disabled the consumer queue after repeated failures. No events were lost: the messages remained queued. After fixing the defect and re-enabling the queue, the original backlog was processed without republishing.

The worker was then hardened with bounded in-process retry plus `ControlTower.EventDeadLetter`. A malformed proof message was dead-lettered after retry, the queue remained enabled, and a valid `inventory.changed` message immediately behind it processed successfully.

Final proof:

- `EventConsumerQueue` receive enabled: yes
- malformed proof dead-letter rows observed: 1
- valid event after malformed: processed
- ingress queue rows: 0
- consumer queue rows: 0
- transmission queue rows: 0

The proof dead-letter row was removed after validation.

## Broker lifecycle

`ControlTower.ProcessEventIngressQueue` activation cleans initiator-side Service Broker lifecycle messages. Remaining conversation endpoints observed after proof were `CLOSED` only; no active transport backlog remained.

## Phase boundary

realtime consumer does not expose browser/API streaming. SSE push, API serving contract, and the explicit idle/no-source-polling measurement remain SSE/API serving.