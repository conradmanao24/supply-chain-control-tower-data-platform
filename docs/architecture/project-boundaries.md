# Project Boundaries

## Source System

The operational source is Microsoft WideWorldImporters OLTP on Microsoft SQL Server 2022.

WWI supplies the operational schemas, historical data, relationships, temporal history, official workload simulation, and source-native integration procedures used by this project.

## What This Project Builds

This repository owns the engineering and serving layers around WWI:

- reproducible source bootstrap and audit evidence
- operational change/event integration
- project-owned current-state projections
- exception and alert lifecycle
- realtime backend and server-to-browser push
- orchestration and incremental analytical ingestion
- PostgreSQL staging/warehouse
- dbt transformations and marts
- watermark/run-state management
- idempotency, recovery, and backfill
- data quality and reconciliation
- observability and platform health
- role-based Supply Chain Control Tower
- project-owned administration/RBAC
- clean-clone reproducibility

WWI remains the authoritative business system. The Control Tower does not provide arbitrary mutation of source business transactions.

## Locked Business Scope

Core domains:
- order fulfillment
- shipping and delivery
- inventory control
- procurement/inbound supply
- cold-chain monitoring
- demand/customer/geography analytics

Secondary context:
- workforce execution
- financial exposure/finalization

The authoritative decision record is `docs/architecture/business-architecture-design-gate.md`.

## Explicit Non-Goals

The project does not:

- create a custom ERP
- copy Microsoft WideWorldImportersDW or SSIS as the project solution
- introduce Kafka or CDC/Debezium in the base architecture
- introduce Spark, Kubernetes, a Data Lake, or cloud infrastructure merely for complexity
- build capabilities that depend on operational facts absent from the audited source
- claim shipment-to-vehicle or shipment-to-temperature lineage the source does not contain
- build multi-warehouse planning, lot/batch traceability, FEFO, MRP, or demand forecasting without supporting data
- fabricate metrics, alerts, thresholds, or benchmark numbers unsupported by evidence

## Data-Minimization Boundary

Only business-required attributes are copied into project-owned analytical/application layers.

Unnecessary sensitive fields such as password hashes, photos, personal contact details, and supplier banking details are excluded unless a future documented requirement explicitly justifies them.

## Public-Repository Boundary

The repository must be reproducible without developer-specific absolute paths, secret configuration, manually restored hidden state, or undocumented runtime dependencies.

Local-only backups, database files, `.env`, logs, caches, credentials, and generated runtime artifacts remain outside version control.
