# Failure & Restart Proof

## Purpose

Prove that a failed stateful Airflow run does not advance its analytical watermark, and that a retry reuses the same uncommitted window without duplicate analytical rows.

## Isolation

The proof used the production DAG code and production analytical tables, but an isolated pipeline-state key ($TestPipeline). The production state row for $DagId was not modified.

Source frontier remained 2026-09-16T00:00:00Z. The isolated test watermark began at 2026-09-15T00:00:00Z, replaying the already-proven historical window (2026-09-15, 2026-09-16].

## Deliberate failure run

- Airflow run: $failRunId
- DAG result: **FAILED** as deliberately injected at
erify_core, after incremental staging, telemetry, and dbt/core processing.
- Ledger: $failLedger
- Watermark after failure: $testAfterFail
- Expected behavior: the watermark stayed at the original lower bound.

Task states:

``text
dag_id                             logical_date    task_id                state            start_date                        end_date
supply_chain_incremental_pipeline                  prepare_run            success          2026-09-17T08:18:29.651494+00:00  2026-09-17T08:18:29.939817+00:00
supply_chain_incremental_pipeline                  incremental_staging    success          2026-09-17T08:18:30.660819+00:00  2026-09-17T08:18:46.175927+00:00
supply_chain_incremental_pipeline                  dbt_core_refresh       success          2026-09-17T08:18:46.377158+00:00  2026-09-17T08:18:56.541698+00:00
supply_chain_incremental_pipeline                  verify_core            failed           2026-09-17T08:18:57.668605+00:00  2026-09-17T08:18:58.102416+00:00
supply_chain_incremental_pipeline                  commit_success         upstream_failed  2026-09-17T08:18:58.561529+00:00  2026-09-17T08:18:58.561529+00:00
supply_chain_incremental_pipeline                  incremental_telemetry  success          2026-09-17T08:18:30.667075+00:00  2026-09-17T08:18:33.153825+00:00
supply_chain_incremental_pipeline                  mark_failed            success          2026-09-17T08:18:58.737413+00:00  2026-09-17T08:18:58.935579+00:00
``

## Restart / retry run

- Airflow run: $retryRunId
- DAG result: **SUCCESS**
- Ledger: $retryLedger
- Retry reused the same start/end window because the failed attempt did not commit the watermark.
- Watermark after success: $testAfterRetry

Task states:

``text
dag_id                             logical_date    task_id                state    start_date                        end_date
supply_chain_incremental_pipeline                  incremental_staging    success  2026-09-17T08:19:10.437980+00:00  2026-09-17T08:19:25.420651+00:00
supply_chain_incremental_pipeline                  prepare_run            success  2026-09-17T08:19:09.368849+00:00  2026-09-17T08:19:09.618824+00:00
supply_chain_incremental_pipeline                  incremental_telemetry  success  2026-09-17T08:19:10.438579+00:00  2026-09-17T08:19:12.519061+00:00
supply_chain_incremental_pipeline                  dbt_core_refresh       success  2026-09-17T08:19:26.525287+00:00  2026-09-17T08:19:37.083379+00:00
supply_chain_incremental_pipeline                  verify_core            success  2026-09-17T08:19:37.533611+00:00  2026-09-17T08:19:39.572839+00:00
supply_chain_incremental_pipeline                  mark_failed            skipped  2026-09-17T08:19:39.676164+00:00  2026-09-17T08:19:39.676164+00:00
supply_chain_incremental_pipeline                  commit_success         success  2026-09-17T08:19:39.847756+00:00  2026-09-17T08:19:40.038879+00:00
``

## Data integrity after replay

Core fingerprint before the proof, after the deliberate failure, and after the successful retry was identical. Final values:

``text
fact_order_line=1009327
fact_sales_line=993477
fact_inventory_movement=1028716
fact_purchase_order_line=35089
fact_delivery_event=616062
fact_customer_transaction=443041
fact_supplier_transaction=9812
dim_customer=991
bridge_product_stock_group=442
delivery_event_duplicate_keys=0
order_line_duplicate_keys=0
``

Duplicate guards remained zero for delivery_event_key and order_line_key.

## Production-state guard

Production state before and after the isolated proof was identical:

``text
2026-09-16 00:00:00+00|manual__2026-09-17T03:20:12.088082+00:00
``

The temporary failure marker, temporary DAG state-key override, and isolated warehouse pipeline-state rows were removed after the proof. Airflow DAG-run records remain visible as execution evidence.