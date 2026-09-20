# Data Quality & Reconciliation Contract

Date: 2026-09-17

## Purpose

data quality and reconciliation layer turns the existing dbt tests and source reconciliation work into a persisted, auditable quality gate. The gate validates structural integrity, freshness, volume, referential integrity, semantic integrity, source-to-staging reconciliation, staging-to-core reconciliation, telemetry preservation, and explicitly documented WideWorldImporters source behavior.

The quality layer is read-only against authoritative WWI business data and analytical facts. It persists only quality-run metadata/results and the existing platform-alert lifecycle state.

## Persistence

PostgreSQL schema `quality` owns:

- `quality.run_history`: one row per quality-gate execution;
- `quality.check_result`: one persisted result per named check in that execution;
- `quality.known_source_behavior`: source quirks/behaviors that must be preserved rather than silently normalized.

Each result has a category, severity, status, source value, target value, and JSON details.

## Gate Modes

### `standard`

Runs:

- dbt structural/referential/semantic tests;
- production watermark vs safe source frontier;
- current-state source-vs-staging max edit timestamps;
- exact source-to-staging row-count parity;
- staging-to-core fact/bridge count parity;
- staging-to-core measure parity;
- delivery-event source-behavior preservation;
- telemetry latest-bucket freshness and aggregate invariants.

### `full`

Includes every `standard` check plus direct SQL Server raw-telemetry reconciliation:

- raw reading count vs summed aggregate `reading_count`;
- raw min temperature vs aggregate global min;
- raw max temperature vs aggregate global max.

`full` is intentionally an explicit mode because scanning the complete telemetry history is materially heavier than the standard gate.

## Freshness Semantics

Freshness is source-relative, not wall-clock-relative.

The frozen/local WWI source is not treated as stale merely because the current calendar date advances. The analytical pipeline is considered current when its production watermark equals `control.source_frontier.safe_through_cutoff`, and source-backed current-state/telemetry maxima reconcile to the corresponding warehouse maxima.

This avoids fabricated freshness failures against a deliberately frozen source.

## Volume & Reconciliation

Source-to-staging counts use the project-owned `ControlTowerExtract.GetReconciliationCounts` contract and require exact parity for the analytical staging scope.

Staging-to-core checks require exact row-count parity for seven facts plus the product-stock-group bridge and exact measure parity for the locked financial/quantity measures.

Delivery-event count parity is derived from the actual JSON `Events` arrays in staging.

## Referential & Semantic Integrity

The existing dbt suite remains authoritative for deterministic keys, required non-null keys, relationships, conditional orphans, SCD current coverage, SCD non-overlap, core row-count reconciliation, and measure reconciliation.

data quality and reconciliation layer executes that suite as part of the quality gate and persists the suite result. The data quality and reconciliation layer implementation has 116 dbt data tests after adding the explicit source-behavior preservation test.

## Explicit WWI Source Behavior

`delivery_attempt_status_absent` is a known source behavior:

- some `DeliveryAttempt` JSON events have no `Status` value;
- `core.fact_delivery_event.event_status` must remain NULL for those rows;
- `is_unconfirmed_attempt=true` is the deterministic interpretation flag;
- the project must not invent or normalize a delivery status.

The quality gate compares the source-aligned staging count, core NULL-status count, and `is_unconfirmed_attempt` count, and rejects any incorrectly flagged row.

## Telemetry Integrity

For cold-room and vehicle 5-minute aggregates, data quality and reconciliation layer checks:

- latest source reading maps to the latest expected 5-minute bucket;
- `min_temperature <= avg_temperature <= max_temperature`;
- positive reading counts;
- exact five-minute bucket alignment;
- non-negative max gap;
- in `full` mode, raw count/min/max preservation.

Raw telemetry remains authoritative in SQL Server.

## Platform Alert Integration

A failing quality run opens/updates:

- `platform.data_quality_failed` for any failed quality check;
- `platform.reconciliation_mismatch` when freshness, volume, or reconciliation fails.

A subsequent passing gate resolves those platform alerts through the existing alert lifecycle.

## Airflow Contract

DAG: `supply_chain_quality_gate`

The DAG accepts optional configuration:

```json
{"mode":"standard"}
```

or:

```json
{"mode":"full"}
```

The default is `standard`. A failed quality gate fails its Airflow task after persisting the failed run and platform alert state.

## Exit Gate

data quality and reconciliation layer can close only when:

- the full Airflow quality gate succeeds;
- all dbt tests pass;
- all persisted quality checks pass;
- source-to-staging counts match;
- staging-to-core counts/measures match;
- telemetry raw preservation passes in full mode;
- the documented WWI delivery-status behavior is preserved;
- failure signaling and recovery are proven;
- no active synthetic quality alerts remain;
- runtime and Broker state are clean.
