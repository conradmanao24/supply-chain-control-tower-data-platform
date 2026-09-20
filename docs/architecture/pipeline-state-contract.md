# Pipeline State Contract

## Purpose

pipeline-state layer adds durable analytical pipeline state. The state belongs to the project-owned PostgreSQL warehouse, not the WWI source and not Airflow UI parameters.

## State tables

### `control.pipeline_state`
One row per logical pipeline. `last_successful_cutoff` is the exclusive lower bound for the next incremental run. It may advance only after the complete analytical DAG succeeds.

### `control.pipeline_run_history`
One row per Airflow attempt. It records the exact cutoff window and final status for audit and restart proof.

## Commit rule

1. Read the current `last_successful_cutoff`.
2. Resolve a new safe `end_cutoff`.
3. Record the attempt as `running`.
4. Execute staging, telemetry, dbt/core, and verification.
5. On failure: mark the attempt `failed`; **do not change `pipeline_state`**.
6. On success: atomically mark the attempt `success` and advance `pipeline_state.last_successful_cutoff = end_cutoff`.

This makes a retry reuse the same uncommitted window and keeps incremental analytical pipeline idempotency meaningful.

## Initial state

The initial persisted watermark is `2026-09-16T00:00:00Z`, matching the end cutoff of the proven successful Airflow end-to-end orchestration E2E run. It is a continuation point from tested pipeline history, not wall-clock time.

## Phase boundary

pipeline-state schema defines and provisions durable state only. Airflow automatic state consumption/commit and deliberate failure/restart proof belong to later pipeline-state layer sub-phases.
## Source frontier

`control.source_frontier` is the durable upper bound for automated processing. Airflow must not advance the analytical watermark beyond this cutoff. The source-production/simulation workflow may advance the frontier only after the corresponding source period is complete and validated.

When `safe_through_cutoff <= last_successful_cutoff`, the DAG performs a successful no-op and does not create a processing run-history row.
