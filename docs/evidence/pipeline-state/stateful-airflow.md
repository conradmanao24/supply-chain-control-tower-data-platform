# Stateful Airflow Orchestration

## Scope

stateful Airflow orchestration moves analytical cutoff ownership out of Airflow UI parameters and into durable project-owned state.

## Durable inputs

- `control.pipeline_state.last_successful_cutoff` is the exclusive lower bound for the next analytical window.
- `control.source_frontier.safe_through_cutoff` is the maximum source cutoff Airflow is allowed to process.
- Initial WWI frontier is `2026-09-16T00:00:00Z`, backed by the completed simulator run through 2026-09-15.

## DAG behavior

The `supply_chain_incremental_pipeline` DAG now:

1. reads the persisted watermark and source frontier,
2. begins a persisted processing attempt only when `frontier > watermark`,
3. runs incremental staging and telemetry,
4. runs dbt/core incremental refresh,
5. verifies core duplicate-key guards,
6. atomically commits success and advances the watermark,
7. marks a processing attempt failed when any processing task fails,
8. performs a safe no-op when no new source window exists.

No `start_cutoff` or `end_cutoff` Airflow UI parameter remains.

## No-op proof

Airflow run:

`manual__2026-09-17T03:58:25.005833+00:00`

Result: **SUCCESS**.

Task states:

- `prepare_run`: success
- `incremental_staging`: success (`NOOP`)
- `incremental_telemetry`: success (`NOOP`)
- `dbt_core_refresh`: success (`NOOP`)
- `verify_core`: success (`NOOP`)
- `commit_success`: success (`NOOP`, watermark unchanged)
- `mark_failed`: skipped, as expected because there was no failed processing task

State after proof:

- watermark: `2026-09-16T00:00:00Z`
- source frontier: `2026-09-16T00:00:00Z`
- run-history rows for the no-op Airflow run: `0`
- cutoff UI parameters: `0`

This proves the DAG consumes durable state automatically and does not manufacture a processing run or advance state when the source has no new safe window.

## Phase boundary

Deliberate failure, watermark non-advance, same-window retry, and successful recovery remain failure and restart validation.