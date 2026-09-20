# Alert & Exception Engine

Status: **PASS / CLOSED**

## Scope

alert and exception layer adds persisted, configurable operational exceptions on top of the operational event plane realtime event plane.

Implemented components:

- PostgreSQL `alert` schema for rules, alerts, lifecycle history, and engine state
- event-driven rule evaluation inside `realtime-consumer`
- Service Broker deadline scheduling/cancellation for time-driven exceptions
- alert REST API and lifecycle actions
- PostgreSQL NOTIFY -> SSE alert push
- platform alert signals from Airflow / API
- go-live historical backlog protection

Implementation contract: `docs/architecture/alert-exception-contract.md`.

## Rule coverage

The final controlled projection proof opened every required source-backed business rule without modifying WWI source rows:

- `inventory.negative_stock`
- `inventory.reorder`
- `inventory.target_watch`
- `fulfillment.overdue`
- `fulfillment.due_today`
- `fulfillment.backorder`
- `delivery.overdue`
- `delivery.due_today`
- `delivery.receiver_not_present`
- `procurement.overdue_under_received`
- `procurement.due_today_under_received`

The proof also reported zero duplicate active rule/entity groups.

Raw proof: `projection-rule-proof.txt`.

## Cold-room timer and configurable-temperature proof

A synthetic sensor was used only inside the project-owned realtime projection for a controlled proof. Production defaults were temporarily shortened to make the timer proof fast, then restored.

Observed sequence:

- fresh 7 C reading -> configurable critical temperature rule opened
- after 3 seconds -> stale warning opened
- after 6 seconds -> stale transitioned out and offline critical opened
- Service Broker deadline rows showed both stale and offline timers firing
- a later fresh reading scheduled new deadlines, which were then cancelled during cleanup
- synthetic sensor and synthetic alert state were removed
- production rule defaults restored to stale `60s`, offline `120s`
- project-owned temperature warning/critical rules restored disabled with null boundaries

Raw proof: `coldroom-proof.txt`.

## Event -> alert -> SSE proof

A source-data-neutral publication referenced existing WWI entities only; no authoritative WWI business row was changed.

The final E2E run produced:

- `inventory.changed` -> `inventory.reorder` alert -> `event: alert` SSE
- `order.changed` -> `fulfillment.overdue` + `fulfillment.backorder` alerts -> SSE
- `delivery.changed` -> `delivery.overdue` + `delivery.receiver_not_present` alerts -> SSE

The same stream also emitted the corresponding processed realtime `event: update` messages.

Raw proof: `final-sse-proof.txt`.

## Lifecycle proof

The API successfully proved:

- open platform exception
- automatic clear / resolve
- explicit acknowledge
- explicit manual resolve
- persisted lifecycle history
- actor attribution

Platform rules exercised during proof:

- `platform.pipeline_failed`
- `platform.reconciliation_mismatch`
- `platform.data_quality_failed`

Raw proof: `platform-lifecycle-proof.txt`.

A final actor-attribution check additionally confirmed that a `platform.reconciliation_mismatch` signal opened and resolved with `resolved_by = phase7-final-proof` and matching history actors.

Raw actor proof: `platform-actor-proof.txt`.

## Airflow integration proof

The stateful DAG now emits project-owned platform signals for pipeline failure and data-quality failure/clear conditions.

The controlled no-new-window run:

`phase7_platform_alert_noop_proof_20260917`

completed with status `success`, preserving the existing analytical watermark while clearing the pipeline-failure condition as a successful no-op.

## Go-live backlog protection

At engine activation, the source still contained 15,472 historically overdue/unpicked rows. The engine did not perform a historical sweep.

`alert.engine_state` records:

- policy: `event_touched_only`
- only post-activation touched entities are evaluated

The proof confirmed zero alerts opened at or before the activation timestamp despite the historical unresolved population.

Raw proof: `backlog-policy-proof.txt`.

## Dead-letter recovery during implementation

The first deadline-sync integration exposed a least-privilege gap: `sct_event_consumer` lacked `EXECUTE` on `ControlTower.CancelDeadline` / `ScheduleDeadline`.

The messages were preserved by the existing dead-letter mechanism. The grants were added to the infrastructure script, both dead letters were replayed, and current validation shows:

- `sct_event_consumer` has `EXECUTE` on `ControlTower.CancelDeadline`
- `sct_event_consumer` has `EXECUTE` on `ControlTower.ScheduleDeadline`
- unreplayed dead letters: `0`

Raw recovery proof: `deadletter-recovery.txt`.

## Final transport/runtime audit

Final SQL Server state:

```text
IngressQueue        0
ConsumerQueue       0
TransmissionQueue   0
DeadLetters         0
ScheduledDeadlines  0
```

Queue state:

- `EventConsumerQueue`: receive/enqueue enabled
- `DeadlineTimerQueue`: receive/enqueue/activation enabled

Final application runtime:

- SQL Server WWI: healthy
- PostgreSQL warehouse: healthy
- realtime consumer: running
- realtime API: healthy
- realtime SSE PostgreSQL listener: connected
- Airflow API server: healthy
- Airflow scheduler: healthy

Raw final audit: `final-audit.txt`.

Static validation:

- `docker compose config --quiet`: PASS
- realtime Python syntax: PASS
- Airflow DAG syntax: PASS
- alert and exception layer SQL migration reapplied idempotently: PASS

## Final cleanup

Controlled proof artifacts were removed from active runtime state:

- synthetic cold-room sensor rows: `0`
- proof alert rows: `0`
- active alerts after proof cleanup: `0`
- duplicate active alert groups: `0`
- production cold-room rule defaults restored

Raw event-log proof records remain available as operational evidence, but no proof-created active exception remains in the alert engine.

## Exit gate

alert and exception layer passes because the platform now has:

1. persisted and idempotent actionable exceptions;
2. source-backed inventory, fulfillment, delivery, and procurement rules;
3. timer-driven cold-room stale/offline evaluation without table polling;
4. configurable temperature rules without inventing a WWI safety threshold;
5. alert acknowledge/resolve lifecycle with audit history;
6. SSE alert push;
7. platform exception signals;
8. explicit go-live backlog protection;
9. clean queues, dead-letter state, and proof cleanup.

