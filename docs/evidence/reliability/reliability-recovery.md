# Reliability & Recovery

Date: 2026-09-17

## Scope

reliability and recovery layer proves the recovery contract for the analytical and realtime paths created in Phases 4-7. It covers retry, dead-letter recovery, idempotent duplicate handling, consumer restart, analytical rerun correctness, deterministic current-state rebuild, and the documented no-loss/no-duplicate boundary.

Contract: `docs/architecture/reliability-recovery-contract.md`.

## Implementation changes

### Realtime consumer hardening

`src/realtime/consumer.py` now:

- logs each intermediate retry as `EVENT_RETRY`;
- retains the existing bounded retry count (`REALTIME_EVENT_MAX_ATTEMPTS`, default 3);
- keeps failed terminal messages in `ControlTower.EventDeadLetter`;
- uses PostgreSQL advisory transaction lock key `807008` while applying a new event, serializing event application against a projection rebuild.

The existing `event_id` primary key remains the operational idempotency boundary.

### Deterministic projection rebuild

`src/realtime/rebuild.py` was added.

Supported domains:

- `orders`
- `deliveries`
- `procurement`
- `inventory`
- `sensors`
- `all`

Business projections are rebuilt from the durable staging snapshot and then refreshed for event-touched entities from authoritative WWI current-state procedures. Sensors are seeded from the latest curated staging aggregate and overlaid with retained non-proof telemetry events. Rebuild uses the same advisory transaction lock as normal event processing.

A bug discovered during proof was fixed: historical controlled telemetry proof events could resurrect the synthetic `coldroom:999999` sensor during rebuild. Rebuild replay now excludes controlled `Phase*Proof*` telemetry events. The corrected rebuild returns six real sensors and zero synthetic proof sensors.

## Retry and controlled recovery proof

A controlled source-read permission failure was introduced by revoking `EXECUTE` on `ControlTower.GetInventoryCurrentState` from `sct_event_consumer`, then publishing a real-entity `inventory.changed` event.

Event:

`307F0634-0E5A-4D27-A024-95EB1A25C3F3`

Observed behavior:

- attempt 1 failed and emitted `EVENT_RETRY`;
- attempt 2 failed and emitted `EVENT_RETRY`;
- final attempt failed and the original message was dead-lettered;
- the permission was restored;
- `DeadLetterID=4` was replayed;
- the preserved event was processed successfully on attempt 1.

Raw evidence: `retry-recovery.txt`.

**passed.**

## Duplicate-delivery idempotency proof

The exact preserved event body for event `307F0634-0E5A-4D27-A024-95EB1A25C3F3` was deliberately delivered a second time.

Before and after duplicate delivery:

- `realtime.event_log` rows for the event remained `1`;
- alert rows sourced by that event remained `1`;
- alert history rows sourced by that event remained `1`.

Consumer result on redelivery:

`result=duplicate`

Raw evidence: `idempotency.txt`.

**passed.**

## Consumer restart / queue persistence proof

The realtime consumer was stopped before publishing a controlled event.

Event:

`113A78C1-FB43-471E-8B75-89833C609186`

While the consumer was offline, `EventConsumerQueue` retained two Broker messages: the business event plus the corresponding `EndDialog` message.

After restarting the consumer:

- the event was processed successfully;
- `EventConsumerQueue` returned to `0`;
- PostgreSQL `realtime.event_log.processing_result` was `processed`.

Raw evidence: `consumer-restart.txt`.

**passed.**

## Current-state rebuild proof

Inventory projection row `stock_item_id=203` was deliberately deleted from PostgreSQL.

Before deletion and in authoritative WWI current state:

- stock item: `Tape dispenser (Black)`
- quantity on hand: `3`
- last stocktake quantity: `3`
- reorder level: `20`
- target stock level: `30`
- last edited: `2026-09-15 12:00:00`

Running:

`python /opt/airflow/src/realtime/rebuild.py --domain inventory`

restored the projection to 227 rows and restored stock item 203 exactly to the authoritative source values.

Sensor rebuild proof then returned:

- 4 cold-room seed sensors;
- 2 vehicle seed sensors;
- 6 final sensors;
- synthetic `coldroom:999999` rows: `0`.

Raw evidence: `rebuild.txt`.

**passed.**

## Analytical rerun correctness proof

Manual Airflow run:

`phase8_rerun_correctness_20260917`

completed with state `success` while source frontier was not ahead of the committed watermark.

Watermark before:

`2026-09-16 00:00:00+00`

Watermark after:

`2026-09-16 00:00:00+00`

The rerun therefore behaved as a correct successful no-op and did not corrupt persisted pipeline state.

Raw evidence: `rerun-correctness.txt`.

**passed.**

## No-loss / no-duplicate guarantee

The proven reliability model is:

- Service Broker retains uncommitted/undelivered events across consumer downtime;
- PostgreSQL event processing is transactional;
- duplicate Broker delivery is collapsed by `realtime.event_log.event_id`;
- current-state writes use keyed upserts;
- active-alert duplication is blocked by the unique active-alert index;
- repeated processing failures retain the original body in dead-letter storage;
- replay re-enters the normal idempotent pipeline;
- projection rebuild can reconstruct current state without a historical source-table polling loop.

The project therefore claims **at-least-once redelivery with effective-once project-owned state effects**, not a distributed exactly-once transaction across SQL Server and PostgreSQL.

The contract does not claim zero data loss if all durable database storage is destroyed without a backup.

## Final cleanup and audit

After proof completion:

- reliability and recovery layer proof event-log rows: `0`;
- active alerts: `0`;
- duplicate active-alert groups: `0`;
- inventory projection rows: `227`;
- sensor projection rows: `6`;
- synthetic sensor rows: `0`;
- ingress queue: `0`;
- consumer queue: `0`;
- transmission queue: `0`;
- unreplayed dead letters: `0`;
- scheduled proof deadlines: `0`;
- realtime API: healthy;
- realtime consumer: running;
- WWI SQL Server, warehouse PostgreSQL, Airflow API server, and Airflow scheduler: healthy.

Raw evidence: `final-audit.txt`.

## Exit gate

reliability and recovery layer requirements are satisfied:

- retry: PASS
- idempotency: PASS
- controlled recovery: PASS
- rerun correctness: PASS
- queue-consumer restart behavior: PASS
- current-state rebuild: PASS
- no-loss/no-duplicate contract: DOCUMENTED + PROVEN WITH CONTROLLED FAILURE CASES

