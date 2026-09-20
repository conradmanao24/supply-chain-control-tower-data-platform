# Tests

This project uses layered validation rather than a standalone unit-test package.

Current automated validation is implemented through:

- **dbt tests** in `dbt/` for structural, referential, uniqueness, SCD, semantic, and reconciliation checks
- **persisted quality gates** in `src/quality/quality_gate.py`
- **Airflow task verification** in the incremental/backfill/quality DAGs
- **repository smoke/proof scripts** under `scripts/testing/`
- **serving/API runtime checks** recorded in the serving validation evidence

Recorded validation includes:

- dbt tests: **116 / 116 PASS**
- full quality gate: **52 PASS / 0 FAIL / 6 expected live-source warnings**
- controlled cold-stack stop/start recovery: PASS
- post-restart manual incremental Airflow run: PASS
- post-restart automatically scheduled Airflow run: PASS
- raw cold-room telemetry reconciliation after late-arrival repair: PASS
- realtime event backlog: 0

See:

- `docs/evidence/data-quality/final-freshness-semantics.md`
- `docs/evidence/serving/serving-validation.md`
