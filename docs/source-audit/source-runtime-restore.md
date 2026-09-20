# Source Runtime & Restore Evidence

## Scope

source runtime and restore starts only the Microsoft SQL Server runtime required for the WideWorldImporters OLTP source. Airflow, PostgreSQL warehouse, dbt, and pipeline components remain out of scope.

## Runtime

- Docker service: `wwi-sqlserver`
- Container: `supply-chain-control-tower-wwi-sqlserver-1`
- Image: `mcr.microsoft.com/mssql/server:2022-latest`
- Host binding: `127.0.0.1:14333 -> 1433/tcp`
- Restart policy: `no`
- Persistent volume: `supply-chain-control-tower_wwi_sqlserver_data`

## Restore Result

Source artifact:

`data/wwi/WideWorldImporters-Full.bak`

Restore verification returned:

`The backup set on file 1 is valid.`

The restore completed successfully and SQL Server upgraded the restored database from backup version 852 to server version 957.

## Source Validation

Post-restore validation returned:

- database: `WideWorldImporters`
- database state: ONLINE
- SQL Server product version: `16.0.4275.2`
- edition: `Developer Edition (64-bit)`
- required WWI schemas: PASS
- required core source tables: PASS
- official `DataLoadSimulation.PopulateDataToCurrentDate` procedure: PASS
- table count observed during structural validation: 48
- foreign-key count observed during structural validation: 98

These counts are structural validation evidence only. Detailed source-volume and relationship auditing belongs to source audit.

## Host Connectivity

TCP connectivity from the host to `127.0.0.1:14333` passed. This is the host endpoint intended for tools such as DBeaver.

## Persistence Test

The `wwi-sqlserver` container was restarted. After restart:

- container health returned to `healthy`
- `WideWorldImporters` remained ONLINE
- required schemas/tables remained available
- source validation passed again

Result: `PASS_AFTER_RESTART`.

## Implementation Fix During 0B

The initial restore runner exposed a shell-quoting bug before any restore operation executed. The runner was corrected to invoke `sqlcmd` directly and use the container-provided `SQLCMDPASSWORD` environment variable. The corrected scripts parsed successfully and the restore/validation path then passed.

## source runtime and restore Status

`PASS`

source audit - Source Audit is the next dependency stage and must not be started automatically without the current milestone decision.
