# dbt/Core Incremental Refresh Evidence

Explicit proof window: `2026-09-14T00:00:00` to `2026-09-16T00:00:00`.

Core strategy:
- 12 high-value models use dbt incremental materialization.
- SCD dimensions recompute full semantic history only for affected business entities.
- Facts refresh direct source changes plus rows impacted by operational-state or SCD changes.
- Delivery events use `delete+insert` on deterministic event keys.
- 5 bounded reference/bridge models are rebuilt as small tables for deterministic delete handling.
- No persistent watermark/run-state table is introduced; that remains pipeline-state layer.

Proof:
- staging incremental rerun completed successfully
- dbt parse passed
- dbt build passed: 12 incremental models + 5 bounded table models + 115 tests
- final result: 132 PASS, 0 WARN, 0 ERROR, 0 SKIP
- identical dbt rerun with the same explicit run-start also passed 132/132
- deterministic core keys remained duplicate-free

Logs:
