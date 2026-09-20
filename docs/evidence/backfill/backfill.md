# Controlled Historical Backfill

## Goal

Prove that an explicit historical window can be reprocessed through staging, telemetry, dbt/core, and verification without moving the production incremental watermark, creating duplicates, replaying historical operational alerts, or racing the production analytical pipeline.

Contract: `docs/architecture/backfill-contract.md`.

## Implemented components

### Durable control state

Migration: `sql/warehouse/backfill_control.sql`

Added:

- `control.processing_guard`
- `control.backfill_run_history`

`processing_guard` serializes `incremental` and `backfill` analytical mutation modes. `backfill_run_history` records the historical window, production watermark before/after, source frontier, final status, and verification payload.

The backfill layer migration was reapplied successfully with all objects/indexes already present, proving idempotent provisioning.

Evidence: `migration-idempotency.txt`.

### Backfill state service

Implementation: `src/orchestration/backfill_state.py`

The store:

- validates timezone-aware explicit windows
- rejects `end > source_frontier`
- acquires the shared analytical processing guard
- rejects overlap with another analytical mutation mode
- snapshots the production watermark before processing
- records success/failure independently from `control.pipeline_state`
- refuses successful completion if the production watermark changed during the backfill
- releases the guard only during controlled finalization

The production `PipelineStateStore` was also integrated with the same guard for non-no-op incremental runs so incremental and backfill writes cannot overlap.

### Airflow backfill DAG

DAG: `supply_chain_backfill`

Tasks:

```text
prepare_backfill
      |
      +--> backfill_staging
      |
      +--> backfill_telemetry
                  |
                  v
           dbt_core_refresh
                  |
                  v
           verify_backfill
                  |
                  v
         complete_backfill

mark_failed = failure-only path
```

The DAG requires explicit `start` and `end` configuration and does not derive the historical window from the production watermark.

## Primary proof window

Both successful proof runs used the same historical window:

```text
start = 2026-08-01T00:00:00+00:00
end   = 2026-08-02T00:00:00+00:00
```

Production state before the proof:

```text
production watermark = 2026-09-16 00:00:00+00
source frontier      = 2026-09-16 00:00:00+00
active alerts        = 0
```

Baseline analytical counts:

```text
fact_order_line             1,009,327
fact_sales_line               993,477
fact_inventory_movement     1,028,716
fact_purchase_order_line       35,089
fact_delivery_event           616,062
fact_customer_transaction     443,041
fact_supplier_transaction       9,812
staging.coldroom_5m         4,519,296
staging.vehicle_5m            844,776
```

Evidence: `baseline.txt`.

## Airflow run 1

Run id:

`phase9_backfill_run1_20260917`

All processing tasks succeeded. The failure-only task was correctly skipped.

Persisted result:

```text
status                      success
production_watermark_before 2026-09-16 00:00:00+00
production_watermark_after  2026-09-16 00:00:00+00
```

The verification payload reported zero duplicate groups across all seven core facts plus both telemetry staging grains.

## Airflow run 2 - same window

Run id:

`phase9_backfill_run2_20260917`

The exact same historical window was submitted a second time. All processing tasks again succeeded and the production watermark again remained unchanged.

The persisted verification JSON for run 1 and run 2 produced the same digest:

```text
run 1  89bb66ff843c343cb6c5781cd26c9e01
run 2  89bb66ff843c343cb6c5781cd26c9e01
verification_equal = true
```

This proves the tested backfill window is repeatable/idempotent against the frozen WWI baseline.

Evidence:

- `airflow-task-states.txt`
- `two-run-idempotency.txt`

## Watermark isolation

Before both runs:

`2026-09-16 00:00:00+00`

After both runs:

`2026-09-16 00:00:00+00`

Backfill never called the production watermark commit path. Successful finalization independently records `production_watermark_after` and requires it to match the captured before value.

## Cross-DAG concurrency protection

A controlled guard proof verified both directions:

```text
incremental while guard=backfill  -> blocked
backfill while guard=incremental  -> blocked
```

No conflict-test history rows were created and the guard returned to `FREE`.

A backfill ending beyond the durable safe source frontier was also rejected before history/guard mutation:

```text
2026-09-17 > 2026-09-16 source frontier -> rejected
```

Evidence: `processing-guard-proof.txt`.

A separate free-guard acquisition proof also exercised the production `PipelineStateStore` success path for guard ownership using a temporary test pipeline state. The incremental guard was acquired as `incremental`, released by the failure-finalization path, the test watermark remained unchanged, and all synthetic rows were removed.

Evidence: `incremental-guard-success-proof.txt`.

## Failure-state behavior

A controlled state-only failure proof acquired a real backfill guard and history row, then finalized it as failed.

Observed:

```text
status                      failed
watermark before            2026-09-16 00:00:00+00
watermark after             2026-09-16 00:00:00+00
guard during run            backfill
guard after failure         FREE
```

The synthetic failure-history row was cleaned after the evidence was captured.

Evidence: `failure-state-proof.txt`.

## Production incremental regression

After the backfill layer guard integration, the normal `supply_chain_incremental_pipeline` was triggered again as run:

`phase9_incremental_regression_20260917`

The source frontier equaled the production watermark, so the run correctly completed as a successful no-op path. All normal tasks succeeded and `mark_failed` was skipped.

Evidence: `incremental-regression.txt`.

## No operational event / alert replay

The two real historical backfill runs occurred between approximately 13:26:35Z and 13:28:33Z.

Realtime event-log rows with `occurred_at_utc` inside that interval:

```text
0
```

Final operational state:

```text
active alerts             0
duplicate active alerts   0
EventIngressQueue         0
EventConsumerQueue        0
TransmissionQueue         0
UnreplayedDeadLetters     0
ScheduledDeadlines        0
```

This matches the architecture boundary: backfill reads WWI and rewrites the analytical PostgreSQL path; it does not mutate WWI business rows or replay historical operational exceptions.

## Final analytical audit

Final counts exactly matched the pre-backfill baseline after two identical runs:

```text
fact_order_line             1,009,327
fact_sales_line               993,477
fact_inventory_movement     1,028,716
fact_purchase_order_line       35,089
fact_delivery_event           616,062
fact_customer_transaction     443,041
fact_supplier_transaction       9,812
staging.coldroom_5m         4,519,296
staging.vehicle_5m            844,776
```

Production watermark and source frontier remained:

```text
2026-09-16 00:00:00+00
```

The shared processing guard finished `FREE` and all required runtime services were healthy/running.

Evidence: `final-audit.txt`.

## Exit gate

backfill layer passes because the platform now supports:

- explicit historical backfill windows
- durable independent backfill audit history
- safe-frontier enforcement
- production-watermark isolation
- cross-DAG mutation serialization
- idempotent staging and telemetry reprocessing
- deterministic dbt/core refresh after bounded staging correction
- zero-duplicate verification
- repeat-run equivalence for the tested historical window
- clean failure-state finalization
- no operational event/alert replay during historical analytical backfill

