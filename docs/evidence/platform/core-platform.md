# Core Platform Runtime

Date: 2026-09-16

## Scope

core platform runtime establishes only the core analytical runtime. It does not start ingestion, warehouse modeling, business marts, realtime event publication, or dashboard implementation.

## Runtime

- Microsoft SQL Server WWI source remains on `127.0.0.1:14333`
- PostgreSQL 17.11 analytical warehouse is exposed on `127.0.0.1:15434`
- PostgreSQL 17.11 Airflow metadata database is internal-only
- Apache Airflow 3.3.1 uses LocalExecutor
- Airflow API/UI is exposed on `127.0.0.1:28080`
- Python runtime is 3.12
- dbt Core 1.11.15 and dbt-postgres 1.11.0 run inside the project-owned Airflow image
- dbt project source is mounted read-only; writable runtime artifacts use a dedicated `dbt_runtime` volume
- realtime API port `18000` is reserved but not implemented in core platform runtime

## Port Isolation

Ports were selected to coexist with other local projects. Existing local services occupy 5432, 8080, and 8000, so this project does not reuse them.

## Validation Evidence

- Docker Compose configuration validation: PASS
- WWI SQL Server: healthy
- PostgreSQL warehouse: healthy
- Airflow metadata PostgreSQL: healthy
- Airflow metadata migration: PASS
- Airflow version: 3.3.1
- Airflow API server: healthy
- Airflow scheduler: healthy
- Airflow DAG processor: healthy
- Airflow API health endpoint: HTTP 200
- Airflow scheduler to PostgreSQL warehouse connectivity: PASS
- warehouse host port 15434: listening
- dbt version validation: PASS
- dbt `profiles.yml`: valid
- dbt `dbt_project.yml`: valid
- dbt PostgreSQL adapter: 1.11.0
- dbt connection to `warehouse-db:5432`: PASS
- dbt `All checks passed!`: PASS

## dbt Runtime Resolution

The first build attempt allowed `dbt-postgres 1.11.0` to resolve against dbt Core 1.12.x, which introduced `dbt-core-experimental-parser` and made the build path less deterministic. A temporary dbt Core 1.10.23 test proved the dependency issue but was rejected because dbt reported that version as deprecated for new projects.

The final core platform runtime runtime pins dbt Core `1.11.15` with `dbt-postgres 1.11.0`. This combination supports Python 3.12, does not require the experimental parser dependency, and passed the final runtime and warehouse-connection checks.

The build also exposed a separate Docker-to-PyPI read timeout. The Airflow Dockerfile now uses a longer pip timeout and retry policy for the dbt install step. dbt project files remain read-only, while `logs` and `target` artifacts are written to a dedicated project-owned runtime volume initialized for the Airflow UID.

## Exit Result

**core platform runtime passed.**

No source data was modified, no ingestion was started, and no business model was created in this work package.
