# Airflow DAGs

This directory contains the orchestration DAGs for the Supply Chain Control Tower Data Platform.

Current workflows cover:

- incremental analytical processing
- controlled historical backfill
- persisted data-quality and reconciliation checks

The DAGs use project-owned pipeline state and source-frontier contracts stored in PostgreSQL.
