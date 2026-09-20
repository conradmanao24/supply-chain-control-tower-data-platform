# Engineering Notes

This document maps the implemented platform capabilities to their supporting contracts and evidence.

## Source and Platform

- Microsoft WideWorldImporters OLTP restored on SQL Server 2022
- source relationships, date ranges, change behavior, and telemetry characteristics audited
- project-owned PostgreSQL warehouse and Airflow runtime provisioned through Docker Compose
- dbt runtime integrated with the project-owned Airflow image

Evidence:
- [Source audit](source-audit/source-audit-final.md)
- [Core platform](evidence/platform/core-platform.md)
- [Source and event integration](evidence/platform/source-event-integration.md)

## Analytical Ingestion and Warehouse

- full initial analytical load
- source-aligned staging
- curated telemetry aggregates
- dbt dimensions, facts, and marts
- source-to-target reconciliation

Evidence:
- [Initial ingestion](evidence/ingestion/initial-ingestion.md)
- [Warehouse modeling](evidence/warehouse/warehouse-modeling.md)

## Incremental Processing and Pipeline State

- incremental extraction
- production watermark
- source frontier
- stateful Airflow orchestration
- rerun and restart handling

Contracts and evidence:
- [Incremental processing contract](architecture/incremental-processing-contract.md)
- [Incremental Airflow evidence](evidence/incremental-pipeline/airflow-e2e.md)
- [Pipeline-state contract](architecture/pipeline-state-contract.md)
- [Pipeline-state evidence](evidence/pipeline-state/pipeline-state.md)

## Realtime Event Processing

- project-owned SQL Server Service Broker publication
- business and telemetry event handling
- deadline/timer events
- PostgreSQL current-state projections
- REST and SSE serving

Contracts and evidence:
- [Operational event contract](architecture/operational-event-contract.md)
- [Realtime consumer](evidence/realtime/realtime-consumer.md)
- [SSE idle proof](evidence/realtime/sse-idle-proof.md)

## Alerts and Exceptions

- persisted operational and platform alerts
- acknowledgement/resolution history
- source-native and configurable project-owned rules
- active exception workspace
- cross-domain investigation links

Contracts and evidence:
- [Alert and exception contract](architecture/alert-exception-contract.md)
- [Alert and exception evidence](evidence/alerts/alert-exception-engine.md)
- [Serving validation](evidence/serving/serving-validation.md)

## Reliability and Recovery

- bounded retry
- dead-letter capture and replay
- duplicate-event idempotency
- queue persistence through consumer restart
- deterministic current-state rebuild
- controlled Docker stop/start recovery

Contracts and evidence:
- [Reliability and recovery contract](architecture/reliability-recovery-contract.md)
- [Reliability and recovery evidence](evidence/reliability/reliability-recovery.md)
- [Runtime validation](evidence/runtime/runtime-validation-2026-09-20.md)

## Backfill

- explicit historical windows
- independent backfill run history
- production-watermark isolation
- shared processing guard
- repeat-run idempotency

Contracts and evidence:
- [Backfill contract](architecture/backfill-contract.md)
- [Backfill evidence](evidence/backfill/backfill.md)

## Data Quality and Reconciliation

- persisted quality-run history
- dbt structural, referential, and semantic tests
- source-to-staging reconciliation
- staging-to-core reconciliation
- telemetry count/min/max/freshness reconciliation
- platform alert integration for quality failures

Contracts and evidence:
- [Data-quality and reconciliation contract](architecture/data-quality-reconciliation-contract.md)
- [Data-quality evidence](evidence/data-quality/data-quality-reconciliation.md)
- [Final freshness semantics](evidence/data-quality/final-freshness-semantics.md)

## Business Serving

- Control Tower
- Fulfillment
- Delivery
- Inventory
- Procurement
- Cold Chain
- Analytics
- Platform Health
- Admin
- shared Exception Workbench

Design and evidence:
- [Dashboard design system](architecture/dashboard-design-system.md)
- [Functional drill-down standard](architecture/functional-drilldown-standard.md)
- [Serving validation](evidence/serving/serving-validation.md)
- [Product walkthrough](demo/README.md)

## Reproducibility

The repository bootstrap was exercised from a clean clone against fresh Docker volumes using the checksum-pinned frozen baseline artifact.

Evidence:
- [Reproducibility](evidence/runtime/reproducibility.md)

## Distribution Note

The frozen SQL Server portfolio baseline is intentionally excluded from Git history because of its size and is distributed through the `v1.0-data-baseline` GitHub Release. The source bootstrap and simulation path remain documented in the repository.
