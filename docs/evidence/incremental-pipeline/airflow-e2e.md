# Airflow End-to-End Orchestration Evidence

Date: 2026-09-17

## Scope

Airflow end-to-end orchestration proves that the incremental analytical path is orchestrated end to end by Airflow without introducing persistent watermark state. The DAG accepts explicit `start_cutoff` and `end_cutoff` parameters; persistent run state remains pipeline-state layer scope.

## DAG

DAG ID: `supply_chain_incremental_pipeline`

Proof window:

- `start_cutoff = 2026-09-14T00:00:00`
- `end_cutoff = 2026-09-16T00:00:00`

Manual proof run:

- Run ID: `manual__2026-09-17T03:20:12.088082+00:00`
- Logical date: `2026-09-17T03:17:22+00:00`
- Start: `2026-09-17T03:20:14.997198+00:00`
- End: `2026-09-17T03:20:56.546566+00:00`
- Run state: **success**
- Elapsed runtime: approximately 42 seconds

## Task Results

| Task | State |
| --- | --- |
| `validate_window` | success |
| `incremental_telemetry` | success |
| `incremental_staging` | success |
| `dbt_core_refresh` | success |
| `verify_core` | success |

The dependency path is:

`validate_window -> (incremental_staging || incremental_telemetry) -> dbt_core_refresh -> verify_core`

## Boundary Confirmation

Airflow end-to-end orchestration orchestrates the already-validated the validated incremental components components. It does **not** persist or advance a watermark. The proof run uses explicit cutoffs, keeping restart/watermark correctness reserved for pipeline-state layer.

## Exit Decision

Airflow end-to-end orchestration validation result: **passed**.

