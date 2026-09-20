# Source Bootstrap Design

## Purpose

Provide a reproducible WideWorldImporters OLTP source without committing the database backup or requiring a manual dataset search/restore workflow.

## Bootstrap sequence

```text
Source acquisition
        |
        v
Source runtime and restore
        |
        v
Source audit
        |
        v
Source simulation
        |
        v
Validation
```

The source-only bootstrap is isolated from Airflow, PostgreSQL warehouse, and dbt runtime startup.

## Source acquisition

Docker and SQL Server remain OFF.

The acquisition step obtains the official Microsoft release artifact:

`WideWorldImporters-Full.bak`

from:

`https://github.com/microsoft/sql-server-samples/releases/download/wide-world-importers-v1.0/WideWorldImporters-Full.bak`

The downloaded file is stored under `data/wwi/`, excluded from version control, and validated by expected size, SQL Server backup header signature, and the project-pinned SHA-256 fingerprint.

## Source runtime and restore

After source acquisition and artifact validation:

```text
start only wwi-sqlserver
        |
        v
RESTORE VERIFYONLY
        |
        v
restore WideWorldImporters
        |
        v
validate connectivity
        |
        v
validate persistence across restart
```

## Safety decisions

- Docker Desktop is never started automatically by project scripts.
- Source acquisition is independent of Docker runtime.
- The SQL Server service uses `restart: "no"`.
- The host SQL port is configurable through `MSSQL_HOST_PORT` and must be checked for conflicts before source runtime and restore startup.
- SQL Server is bound to `127.0.0.1` rather than all host interfaces.
- The SQL Server data directory uses a named Docker volume for persistence.
- The WWI backup remains under `data/wwi/` and outside version control.
- Existing databases are not dropped or overwritten automatically.

## Default SQL Server port

```text
host      14333
container 1433
```

`14333` is only a default. Runtime preflight must prove the selected host port is free (or already owned by this project's source container) immediately before startup.

## Evidence

Source acquisition evidence is stored in:

`docs/source-audit/source-acquisition.md`
