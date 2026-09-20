# dbt Runtime Validation

Validated on 2026-09-16.

- dbt Core: 1.11.15
- dbt Postgres adapter: 1.11.0
- Python: 3.12.13
- dbt project config: PASS
- dbt profile config: PASS
- PostgreSQL warehouse connection: PASS
- dbt runtime source mount remains read-only
- dbt logs/target use project-owned writable runtime volume
- Airflow scheduler is running the image that contains dbt
- `dbt debug`: All checks passed

The earlier build issue was traced to Docker/PyPI read timeouts and an unsuitable dependency path through dbt Core 1.12.x. The final pinned runtime avoids the experimental parser dependency and uses explicit pip timeout/retry behavior.