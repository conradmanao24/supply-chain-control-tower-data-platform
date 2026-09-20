# Watermark & Run-State Contract

## Implemented

- Created PostgreSQL schema `control`.
- Created `control.pipeline_state` for the durable last-successful cutoff.
- Created `control.pipeline_run_history` for attempt/audit history.
- Initialized `supply_chain_incremental_pipeline` at `2026-09-16T00:00:00Z`, the end cutoff of the successful Airflow end-to-end orchestration proof run.
- Locked the rule that watermark advancement occurs only after complete pipeline success.
- Locked the rule that failed attempts never advance `pipeline_state`.

## Current persisted state

`pipeline_name = supply_chain_incremental_pipeline`

`last_successful_cutoff = 2026-09-16T00:00:00Z`

`last_successful_run_id = manual__2026-09-17T03:20:12.088082+00:00`

## Boundary

pipeline-state schema provisions durable state only. State mutation helpers, Airflow state consumption/commit, and deliberate failure/restart proof remain persisted state operations-5D.
