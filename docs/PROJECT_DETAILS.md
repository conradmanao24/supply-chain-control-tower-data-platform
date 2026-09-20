# Supply Chain Control Tower Data Platform

An end-to-end Data Engineering portfolio project built on Microsoft WideWorldImporters OLTP.

The project combines **operational supply-chain visibility**, historical analytics, realtime serving, and data-quality/reconciliation workflows.

## Scope

The application covers order fulfillment, shipping and delivery, inventory control, procurement and inbound supply, cold-chain monitoring, analytics, platform health, and configurable operational alert rules.

The operational investigation pattern is:

```text
exception -> business impact -> evidence -> derived cause -> related records -> timeline
```

The serving layer includes Control Tower, Fulfillment, Delivery, Inventory, Procurement, Cold Chain, Analytics, Platform Health, Admin, and a shared cross-domain Exception Workbench.

## Architecture

```text
SQL SERVER WWI
  |
  +--> business changes --> Service Broker --> realtime backend --> current state / alerts --> SSE --> Control Tower UI
  |
  `--> incremental extraction --> Airflow --> PostgreSQL staging --> dbt --> warehouse / marts --> analytics / DQ / reconciliation
```

The operational event plane serves current operational state and exceptions. The analytical plane serves historical analysis, reconciliation, and business marts.

## Technology

- Microsoft SQL Server 2022 + WideWorldImporters OLTP
- SQL Server Service Broker
- Apache Airflow 3.3.1
- Python / SQL
- PostgreSQL 17
- dbt Core
- Docker / Docker Compose
- React / Vite
- Server-Sent Events (SSE)
- persisted data-quality and reconciliation checks

## Business Users

The serving layer is organized for Supply Chain / Operations, Order Fulfillment / Customer Service, Warehouse / Inventory, Procurement, Logistics / Delivery, QA / Cold Chain, Data / Platform Operations, and Administration.

## Source Snapshot

The frozen source baseline is measured through **2026-09-15**:

- **93,334,276 raw user-table rows**
- **323,525 sales orders**
- **308,053 invoices**
- **308,009 delivery-attempt events**
- **1,028,716 stock-item transactions**
- **8,374 purchase orders**
- **227 products**
- **89,129,050 telemetry rows**
- **98 foreign-key relationships**, with zero disabled/untrusted FKs

The canonical baseline preserves history from **2013-01-01 through 2026-09-15**. The compressed SQL Server backup is **1.548 GiB** (`1,662,111,744` bytes).

SHA-256:

```text
1F779A53D9AE1E5B90F2C62BA74D3E48E5FED0F75096E5EC798A09ABF04DEE30
```

Source audit: [source-audit/source-audit-final.md](source-audit/source-audit-final.md)

## Analytical Pipeline

```text
SQL Server WWI -> incremental extraction -> PostgreSQL staging -> dbt dimensions/facts/marts -> quality/reconciliation -> analytics serving
```

Implemented behavior includes source-aligned staging, incremental extraction, durable production watermark, source-frontier tracking, idempotent reruns, bounded historical backfill, dbt transformations/tests, and source/staging/core/telemetry reconciliation.

Evidence:
- [Initial ingestion](evidence/ingestion/initial-ingestion.md)
- [Warehouse modeling](evidence/warehouse/warehouse-modeling.md)
- [Incremental Airflow path](evidence/incremental-pipeline/airflow-e2e.md)
- [Pipeline state](evidence/pipeline-state/pipeline-state.md)
- [Backfill](evidence/backfill/backfill.md)
- [Data quality and reconciliation](evidence/data-quality/data-quality-reconciliation.md)

## Operational Event Plane

Business and telemetry changes publish through the project-owned SQL Server Service Broker path. The realtime backend consumes events, maintains PostgreSQL current-state projections and alerts, exposes REST endpoints, and pushes browser updates through SSE.

Evidence:
- [Business event publication](evidence/realtime/business-event-publication.md)
- [Realtime consumer](evidence/realtime/realtime-consumer.md)
- [SSE idle proof](evidence/realtime/sse-idle-proof.md)
- [Alert and exception engine](evidence/alerts/alert-exception-engine.md)
- [Reliability and recovery](evidence/reliability/reliability-recovery.md)

## Serving Layer

- **Control Tower** — cross-domain operational status and active exceptions
- **Fulfillment** — order queue, overdue exposure, backorders, and order investigation
- **Delivery** — pending/overdue/confirmed delivery state and event history
- **Inventory** — current stock, projected coverage, inbound timing, and linked demand
- **Procurement** — open inbound commitments, receipt status, and downstream exposure
- **Cold Chain** — cold-room and vehicle sensor status, freshness, movement, and history
- **Analytics** — revenue, profit, orders, receipt completion, and customer/product drill-downs
- **Platform Health** — watermark, source frontier, freshness, quality, and realtime status
- **Admin** — persisted alert-rule configuration

Product walkthrough: [demo/README.md](demo/README.md)

Serving evidence: [evidence/serving/serving-validation.md](evidence/serving/serving-validation.md)

## Validation Evidence

Recorded validation includes:

- frontend production build
- application navigation and interaction checks
- 1920x1080 and 2560x1440 layout checks
- **116 / 116 dbt tests passing**
- source-to-staging and staging-to-core reconciliation
- raw-to-aggregate telemetry reconciliation
- controlled Docker stop/start recovery
- post-restart Airflow incremental execution
- clean-clone bootstrap on fresh Docker volumes
- full quality gate with zero hard failures

Runtime evidence:
- [Runtime validation](evidence/runtime/runtime-validation-2026-09-20.md)
- [Reproducibility](evidence/runtime/reproducibility.md)

## Local Quick Start

Prerequisites: Docker Desktop / Docker Compose, PowerShell, Node.js, and npm.

```powershell
Copy-Item .env.example .env
```

Replace local secret placeholders in `.env`. For the exact portfolio state, place the checksum-pinned frozen baseline at:

```text
data/baselines/full-master/wwi-full-master-2026-09-15.bak
```

Run the platform bootstrap:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/bootstrap/bootstrap-platform.ps1
```

Start the frontend separately:

```powershell
Set-Location frontend
npm ci
npm run dev
```

Default endpoints:

```text
Frontend     http://127.0.0.1:5173
Realtime API http://127.0.0.1:18000
Airflow      http://127.0.0.1:28080
```

## Baseline Distribution

Backups and runtime data are excluded from Git history. The exact precomputed **2026-09-15 portfolio baseline** is a separate local artifact. A clone can use the documented source bootstrap and simulation path; exact reproduction from the frozen state additionally requires the checksum-pinned baseline artifact.

## Repository Layout

```text
.
|-- airflow/dags/          # orchestration DAGs
|-- dbt/                   # analytical models and tests
|-- frontend/              # Control Tower UI
|-- src/                   # ingestion, realtime, quality, simulation
|-- sql/                   # SQL Server and PostgreSQL contracts
|-- scripts/               # bootstrap and testing utilities
|-- docs/
|   |-- architecture/      # architecture contracts
|   |-- demo/              # product walkthrough
|   |-- evidence/          # engineering evidence by capability
|   `-- source-audit/      # source audit and simulation evidence
|-- tests/
|-- docker-compose.yml
`-- README.md
```

## Engineering Notes

See [ENGINEERING_NOTES.md](ENGINEERING_NOTES.md) for the capability/evidence map.

## Author

Victor
