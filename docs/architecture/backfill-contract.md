# Backfill Contract

## Purpose

backfill layer provides controlled historical analytical reprocessing without moving the production incremental watermark, creating duplicate warehouse rows, or replaying historical operational alerts.

Backfill is an analytical concern only. It reads the existing WideWorldImporters source and rewrites project-owned PostgreSQL staging/core data for an explicit historical window.

## Explicit window

Every backfill requires a timezone-aware `start` and `end` supplied in the Airflow DAG-run configuration.

Example:

```json
{"start":"2026-08-01T00:00:00+00:00","end":"2026-08-02T00:00:00+00:00"}
```

The business delta loaders keep their existing contract: start is the exclusive lower cutoff and end is the inclusive upper cutoff where the WWI Integration procedures use that convention. Telemetry intentionally recomputes the overlapping 5-minute bucket at the lower boundary.

A backfill is rejected if `end` is greater than `control.source_frontier.safe_through_cutoff`.

## Isolation from production watermark

Production incremental state remains in:

- `control.pipeline_state`
- `control.pipeline_run_history`

Backfill state is separate:

- `control.backfill_run_history`

Each backfill persists:

- Airflow run id
- start/end cutoff
- run status
- production watermark before and after
- source frontier captured at start
- verification JSON
- start/finish timestamps
- failure message when applicable

A successful backfill must prove that the production watermark after processing is identical to the watermark captured before processing. The backfill completion transaction fails closed if the watermark changed unexpectedly.

## Cross-DAG processing guard

`control.processing_guard` serializes analytical processing modes.

Allowed modes:

- `incremental`
- `backfill`

The guard prevents a production incremental run and a historical backfill from mutating shared analytical staging/core state at the same time.

The production `PipelineStateStore.begin_run()` now acquires the same guard for non-no-op incremental runs and releases it on success/failure. `BackfillStateStore.begin()` acquires it for a backfill and releases it only after success/failure finalization.

The guard is fail-closed. It is never automatically stolen based only on elapsed time; operator verification is required before clearing a stale guard after an abnormal platform failure.

## Data path

```text
explicit historical window
        |
        +--> incremental staging loader
        |
        +--> rolling telemetry recompute
                    |
                    v
              dbt/core rebuild
                    |
                    v
             duplicate checks
                    |
                    v
          backfill run finalization
```

The existing staging loaders are key-replacing/idempotent. For current/snapshot tables they perform source-vs-target diff synchronization. Telemetry deletes and recomputes the bounded bucket range.

The dbt `core` models are table materializations, so after the bounded staging correction the core layer is rebuilt deterministically from the complete staging state rather than attempting unsafe partial table surgery.

## Realtime / alert boundary

Backfill does not modify authoritative WWI business rows. It only reads SQL Server and writes PostgreSQL analytical tables.

Therefore a normal backfill must not:

- publish Service Broker business events
- replay historical realtime events
- open historical operational alerts
- change current-state realtime projections

Operational event processing remains owned by Phases 6-8.

## Verification gate

Every successful backfill validates:

- production watermark unchanged
- zero duplicate keys across all seven core facts
- zero duplicate cold-room 5-minute buckets
- zero duplicate vehicle 5-minute buckets
- persisted verification snapshot in `control.backfill_run_history`

The backfill layer closure proof additionally runs the exact same historical window twice and requires identical verification output and unchanged global row counts.

## Failure behavior

If a processing task fails:

- the backfill history row is marked `failed`
- production watermark is not advanced
- the shared processing guard is released by the failure path
- the historical window can be submitted again under a new Airflow run id

A failed historical run is never converted into a production incremental watermark commit.

## Phase boundary

backfill layer provides controlled backfill orchestration and correctness proof. Broader automated DQ/freshness/reconciliation policy belongs to data quality and reconciliation layer.
