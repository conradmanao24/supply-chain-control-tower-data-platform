# Alert & Exception Contract

## Purpose

alert and exception layer turns the operational event plane operational event plane into actionable, persisted exceptions. Alerts are derived from project-owned realtime current-state projections and platform signals; they do not mutate authoritative WideWorldImporters business transactions.

## Alert persistence

PostgreSQL schema `alert` owns the alert and exception layer state:

- `alert.rule_config` - rule enablement, severity, and configurable parameters
- `alert.alerts` - one persisted alert instance per rule/entity condition
- `alert.alert_history` - lifecycle audit trail
- `alert.engine_state` - engine activation timestamp and go-live backlog policy

A partial unique index prevents more than one active (`open` or `acknowledged`) alert for the same `(rule_id, entity_type, entity_id)`.

Observed values and threshold values are snapshotted into each alert so historical decisions remain explainable after configuration changes.

## Lifecycle

Supported alert states:

`open -> acknowledged -> resolved`

The engine may resolve an open or acknowledged alert automatically when the evaluated condition clears. A later qualifying event can open a new alert instance for the same rule/entity after the previous instance has resolved.

Manual acknowledgement and resolution are exposed through the realtime API and recorded in `alert.alert_history` with the actor.

## Rule set

Source-backed operational rules:

- inventory negative stock
- inventory at/below reorder level
- inventory below target watch state
- fulfillment overdue while unpicked
- fulfillment due today while unpicked
- fulfillment backorder context
- delivery overdue without completion
- delivery due today without completion
- delivery attempt: `Receiver not present`
- procurement overdue while under-received/open
- procurement due today while under-received/open

Cold-chain rules:

- cold-room stale warning
- cold-room offline critical
- configurable temperature warning band
- configurable temperature critical band

Platform rules:

- analytical pipeline failure
- data-quality/dbt failure
- source-to-warehouse reconciliation mismatch

Temperature thresholds are project-owned anomaly guardrails. WWI historically operates around 3.0-5.0 C, so the runtime default enables a warning outside 3.0-5.0 C and a critical excursion outside 2.5-5.5 C. These bands are not regulatory, food-safety, product-specification, or shipment-compliance limits.

## Time-driven evaluation

Time-driven exceptions use the operational event plane Service Broker deadline/timer path rather than repeated source polling.

Business/telemetry events reschedule or cancel deadline keys for:

- fulfillment due / overdue
- delivery due / overdue
- procurement due / overdue
- cold-room stale / offline

When a deadline event fires, the alert engine evaluates the latest PostgreSQL realtime projection. The timer is a signal to evaluate current state; it does not itself assert that an alert is true.

## Event-driven evaluation

The realtime consumer evaluates alerts only after updating the corresponding current-state projection. Business events therefore follow:

`SQL Server event -> Service Broker -> realtime consumer -> PostgreSQL current state -> alert evaluation -> persisted alert -> PostgreSQL NOTIFY -> SSE`

Alert changes use the same `control_tower_realtime` PostgreSQL notification channel as operational event plane. SSE emits them as `event: alert` messages.

## Go-live backlog policy

`alert.engine_state.backlog_policy = event_touched_only`.

Historical unresolved rows are not swept into new active alerts at engine activation. Only entities touched by post-activation events or explicit platform signals are evaluated. This prevents historical WWI artifacts from flooding the Control Tower at go-live.

## Configuration API

The realtime API exposes:

- rule listing and rule patching
- active/resolved alert listing and filtering
- alert detail with lifecycle history
- acknowledge / resolve actions
- platform-signal ingestion
- engine-state visibility

Cold-room and vehicle stale/offline intervals are configurable positive durations. Temperature rules accept numeric low/high boundaries. The runtime ships with the project-owned WWI anomaly guardrails enabled and they can still be changed through the rule API.

## Platform integration

The stateful Airflow incremental DAG emits `platform.pipeline_failed` and `platform.data_quality_failed` signals. The general platform signal endpoint also supports `platform.reconciliation_mismatch`, allowing reconciliation jobs to open/clear the exception without coupling alert persistence to a specific future reconciliation implementation.

## Failure handling

The realtime consumer remains at-least-once and idempotent. Alert persistence is protected by the active-rule/entity uniqueness constraint. An implementation-time permission gap on the operational event plane deadline procedures was detected by the dead-letter path, corrected with least-privilege `EXECUTE` grants for `sct_event_consumer`, replayed successfully, and left with zero unreplayed dead letters.

## Phase boundary

alert and exception layer implements alert rules, persistence, lifecycle, configuration, time-driven evaluation, SSE alert push, platform signals, and backlog policy.

Broader recovery/rebuild/no-loss demonstrations belong to reliability and recovery layer. Historical backfill belongs to backfill layer. Broader data-quality/reconciliation implementation belongs to data quality and reconciliation layer. Role-oriented business serving/UI belongs to business serving layer.
