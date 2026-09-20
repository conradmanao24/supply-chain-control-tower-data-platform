# Data Quality & Reconciliation

## Scope

data quality and reconciliation layer formalizes a durable data-quality control plane on top of the existing dbt tests and source/warehouse reconciliation work. The goal is to make structural, freshness, volume, referential, semantic, source-behavior, and reconciliation checks reproducible and persisted rather than relying on ad-hoc validation.

## Implemented

- `quality.run_history` persists each quality-gate execution.
- `quality.check_result` persists individual checks and categories.
- `quality.known_source_behavior` documents source quirks that must be preserved instead of normalized.
- `src/quality/quality_gate.py` runs the full gate and persists results.
- `supply_chain_quality_gate` Airflow DAG exposes the quality gate as a standalone operational workflow.
- dbt structural/referential/semantic tests remain part of the gate.
- source-to-staging row-count reconciliation is checked across 24 source-aligned datasets.
- staging-to-core row-count and measure reconciliation is checked for the business warehouse facts and bridge.
- telemetry freshness, reading-count preservation, min/max preservation, and bucket invariants are checked.
- the known WWI delivery-event quirk (`DeliveryAttempt` with absent/null `Status`) is preserved explicitly and tested.
- a controlled mismatch proof demonstrated platform DQ/reconciliation alert creation and automatic resolution after recovery.

## Airflow proof

Run:

`phase10_full_airflow_proof_20260917`

Result:

- DAG state: `success`
- quality run state: `pass`
- persisted checks: `57`
- failed checks: `0`
- warning checks: `0`

The dbt suite used by the gate reports 116/116 tests passing after adding the explicit source-behavior preservation test.

## Key reconciliation results

Business row-count parity includes:

- order lines: 1,009,327 = 1,009,327
- sales lines: 993,477 = 993,477
- inventory movements: 1,028,716 = 1,028,716
- purchase lines: 35,089 = 35,089
- customer transactions: 443,041 = 443,041
- supplier transactions: 9,812 = 9,812
- delivery events: 616,062 = 616,062
- product-stock-group bridge: 442 = 442

Measure parity includes order total including tax, sales total including tax, sales profit, inventory quantity, customer transaction total, and supplier transaction total.

Telemetry reconciliation:

- cold-room raw readings: 87,439,552 = aggregate reading-count sum 87,439,552
- vehicle raw readings: 1,689,502 = aggregate reading-count sum 1,689,502
- source and aggregate min/max temperatures match
- zero invalid 5-minute bucket invariants in both telemetry datasets

Known source behavior:

- WWI `DeliveryAttempt` events with absent/null `Status`: 30,733
- warehouse preserves the null status and derives `is_unconfirmed_attempt=true`; it does not invent a status value

## Failure and recovery proof

A controlled reconciliation mismatch (`100` vs `99`) produced:

- `platform.data_quality_failed` open alert
- `platform.reconciliation_mismatch` open alert

A subsequent passing reconciliation (`100` vs `100`) resolved both alerts with `platform_recovered`.

The synthetic proof results were cleaned after verification.

## Final audit

Final state:

- latest production quality gate: PASS
- failed persisted quality checks: 0
- active alerts after proof cleanup: 0
- known source behavior registration enabled
- Airflow scheduler and DAG processor healthy
- SQL Server, warehouse PostgreSQL, realtime API, and realtime consumer healthy/running

## Exit gate

data quality and reconciliation layer passes because structural integrity, freshness/volume validation, referential/semantic checks, source-to-staging reconciliation, staging-to-core reconciliation, telemetry reconciliation, source-behavior preservation, persisted quality history, Airflow execution, and failure-to-alert/recovery behavior have all been demonstrated.

