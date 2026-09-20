# Reproducibility

This record documents a full bootstrap from a clean Git clone using a separate Docker Compose project and fresh Docker volumes.

Validated repository state: `69478f9`

## Test setup

The clean clone used separate SQL Server, PostgreSQL, Airflow metadata, and application runtime containers and volumes. No existing project database volume was reused.

The reproduction exercise used the checksum-pinned frozen portfolio baseline. Public clones obtain the same artifact through the `v1.0-data-baseline` GitHub Release when it is not already present locally.

## Bootstrap

The repository bootstrap:

```powershell
scripts/bootstrap/bootstrap-platform.ps1
```

completed the following from the clean clone:

1. restored and validated the frozen SQL Server baseline
2. recreated project-owned SQL Server extraction and realtime integration objects
3. built the Airflow/dbt runtime image
4. created fresh PostgreSQL warehouse and Airflow metadata databases
5. created staging tables
6. loaded the source-aligned business baseline
7. rebuilt 5-minute telemetry aggregates
8. built the dbt analytical warehouse
9. provisioned control, realtime, alert, backfill, quality, and serving objects
10. started the backend runtime
11. unpaused the repository DAGs with zero Airflow import errors

## Source catch-up and scheduling

The source simulator started from the frozen business date `2026-09-15` and completed catch-up through `2026-09-19`.

Published source frontier:

```text
2026-09-20 00:00:00+00
```

The analytical pipeline advanced its production watermark to the same cutoff. A later scheduled incremental Airflow run at `2026-09-20T04:45:00+00:00` completed successfully.

## Quality and reconciliation

Full-mode validation returned:

- dbt data tests: **116 / 116 passed**
- persisted quality checks: **55 passed / 0 failed / 3 warnings**
- watermark/source-frontier alignment: matched
- staging-to-core count reconciliation: matched
- staging-to-core measure reconciliation: matched
- raw telemetry count/min/max reconciliation: matched
- telemetry freshness and bucket integrity: matched

Raw telemetry at the committed cutoff:

- cold-room readings: **87,528,204 = 87,528,204**
- vehicle readings: **1,691,262 = 1,691,262**

The three warnings reflected live-source volume drift while the simulator continued producing operational changes.

## Runtime health

Final health checks returned HTTP 200 for the realtime API and Airflow health endpoint. SQL Server, PostgreSQL, Airflow services, the realtime consumer, and the source simulator were running.

Final SQL Server event transport state:

```text
IngressQueue          0
ConsumerQueue         0
TransmissionQueue     0
UnreplayedDeadLetters 0
```

## Bootstrap corrections found during reproduction

The clean-clone exercise exposed three packaging issues that were corrected:

1. PowerShell native-command stderr handling was changed to evaluate native command exit codes.
2. SQL restore scripts were updated so caller-supplied `sqlcmd` variables are not overridden internally.
3. Frozen-baseline container path conversion was changed to literal string replacement.

These corrections affected bootstrap/reproducibility behavior and did not change business-serving logic.

## Reproduction result

The backend/data-platform state was recreated from empty Docker volumes using the checksum-pinned frozen baseline.
