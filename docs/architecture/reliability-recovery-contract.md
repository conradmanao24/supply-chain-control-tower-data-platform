# Reliability & Recovery Contract

## Purpose

reliability and recovery layer hardens the existing analytical and operational paths without changing the operational event plane/7 business semantics. The goal is controlled recovery with repeatable evidence for retry, replay, idempotency, consumer restart, analytical rerun, and current-state projection rebuild.

## Reliability model

The operational event path remains:

```text
WWI transaction / publisher
        |
        v
SQL Server Service Broker queue
        |
        v
realtime-consumer
        |
        +--> PostgreSQL realtime.event_log
        +--> PostgreSQL current-state projections
        +--> PostgreSQL alert state/history
        |
        v
conversation completion
```

Service Broker receive work is transactional. The consumer does not commit the SQL Server receive transaction until PostgreSQL event processing and deadline synchronization have completed or the message has been deliberately captured in the dead-letter table.

PostgreSQL event processing is transactional and uses `realtime.event_log.event_id` as the idempotency key. Projection and alert effects for a new event are committed in the same PostgreSQL transaction as the event-log row.

## Failure windows and recovery behavior

### Failure before PostgreSQL commit

The PostgreSQL transaction rolls back. Closing/losing the SQL Server connection rolls back the uncommitted `RECEIVE`, so Service Broker makes the message available again.

### Failure after PostgreSQL commit but before SQL Server receive commit

The Service Broker receive transaction rolls back and the message can be redelivered. On redelivery, the event-log insert conflicts on `event_id` and the event is treated as `duplicate`; projection and alert side effects are not applied a second time. Deadline synchronization still runs after duplicate detection, so the non-distributed PostgreSQL/SQL Server boundary remains recoverable.

### Repeated processing failure

The consumer attempts a message up to `REALTIME_EVENT_MAX_ATTEMPTS` (default 3). Failed intermediate attempts are logged as `EVENT_RETRY`. After the final failed attempt the original message body, conversation handle, message type, and error are persisted in `ControlTower.EventDeadLetter`. Once the cause is corrected, `ControlTower.ReplayDeadLetter` republishes the preserved body through the normal consumer path.

## Idempotency guarantees

Within project-owned state:

- `realtime.event_log.event_id` is the event idempotency key.
- duplicate delivery of the same event ID does not create a second event-log row;
- duplicate delivery does not re-run projection or alert evaluation;
- current-state tables are keyed by the business entity identifier and use upsert semantics;
- active alerts have a unique partial index on `(rule_id, entity_type, entity_id)` for `open`/`acknowledged` state;
- telemetry projection updates only when the incoming `recorded_when` is not older than the current projection.

This provides **effective-once project-owned state effects on top of at-least-once redelivery semantics**. It is intentionally not described as a distributed exactly-once transaction across SQL Server and PostgreSQL.

## Consumer restart guarantee

If the realtime consumer is stopped while events are published, messages remain in `ControlTower.EventConsumerQueue`. After the consumer restarts, it resumes `WAITFOR RECEIVE`, processes the queued messages, and drains the queue. Container/process restart therefore does not require source-table polling or manual event regeneration.

## Current-state rebuild

`src/realtime/rebuild.py` provides deterministic projection recovery.

Business domains (`orders`, `deliveries`, `procurement`, `inventory`):

1. rebuild the full projection from the durable PostgreSQL staging snapshot;
2. read distinct post-seed entity IDs recorded in `realtime.event_log`;
3. refresh those touched entities from the authoritative WWI current-state procedures;
4. delete a projected entity when the authoritative current-state read no longer returns it.

Sensor domain:

1. seed the latest cold-room and vehicle sensor state from curated staging aggregates;
2. replay retained non-proof telemetry events in chronological order;
3. retain the newest reading per sensor through the existing monotonic upsert rule.

Controlled Phase proof events are excluded from telemetry rebuild replay so synthetic test sensors cannot be resurrected by a later rebuild.

The rebuild and normal event processing share PostgreSQL advisory transaction lock key `807008`, preventing a rebuild transaction from racing a live consumer transaction.

Projection rebuild intentionally does not perform a historical alert sweep. Existing alert state is preserved and future events continue normal evaluation, maintaining the alert and exception layer `event_touched_only` backlog policy.

## Analytical rerun correctness

The analytical DAG continues to use durable `control.pipeline_state` and `control.source_frontier`. When the frontier is not ahead of the committed watermark, a manual rerun completes as a successful no-op and leaves the watermark unchanged. A failed processing run does not advance the watermark, preserving the pipeline-state layer restart contract.

## Guarantee boundary

reliability and recovery layer guarantees recovery behavior for project-owned runtime failures when the SQL Server source, Service Broker database, and PostgreSQL durable database remain available or are restored from their persistent volumes/backups.

reliability and recovery layer does **not** claim zero data loss after destruction of all durable database storage without a backup. Cross-database exactly-once delivery is also not claimed. The implemented contract is transactional redelivery + idempotent effects + dead-letter capture/replay + deterministic projection rebuild.
